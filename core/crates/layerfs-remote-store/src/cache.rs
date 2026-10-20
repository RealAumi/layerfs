//! Nonauthoritative canonical cache. An object built here and not yet known
//! to the Store is local; Commit uploads the local objects its root reaches.
use crate::wire::{error, Result};
use layerfs_content::{FinalizedObject, ObjectId, ObjectRole};
use rusqlite::{params, Connection, OptionalExtension};
use std::{path::Path, sync::Mutex};
pub struct Cache(Mutex<Connection>);
impl Cache {
    pub fn open(path: &Path) -> Result<Self> {
        let db = Connection::open(path).map_err(error)?;
        db.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=OFF; PRAGMA mmap_size=0; PRAGMA cache_size=-2048;
            CREATE TABLE IF NOT EXISTS objects(id BLOB PRIMARY KEY, body BLOB NOT NULL, role INTEGER, remote INTEGER NOT NULL DEFAULT 1);
            CREATE INDEX IF NOT EXISTS object_presence ON objects(id,remote,role);
            CREATE TABLE IF NOT EXISTS lengths(id BLOB PRIMARY KEY, value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS restore_points(scope BLOB, branch BLOB, key TEXT, body BLOB NOT NULL, PRIMARY KEY(scope,branch,key));").map_err(error)?;
        Ok(Self(Mutex::new(db)))
    }
    pub fn restore(&self, scope: ObjectId, branch: &[u8], key: &str) -> Result<Option<Vec<u8>>> {
        self.0
            .lock()
            .map_err(error)?
            .query_row(
                "SELECT body FROM restore_points WHERE scope=? AND branch=? AND key=?",
                params![scope.as_bytes().as_slice(), branch, key],
                |r| r.get(0),
            )
            .optional()
            .map_err(error)
    }
    pub fn save_restore(
        &self,
        scope: ObjectId,
        branch: &[u8],
        key: &str,
        body: &[u8],
    ) -> Result<()> {
        let mut db = self.0.lock().map_err(error)?;
        let tx = db.transaction().map_err(error)?;
        tx.execute("INSERT INTO restore_points VALUES(?,?,?,?) ON CONFLICT(scope,branch,key) DO UPDATE SET body=excluded.body",
            params![scope.as_bytes().as_slice(), branch, key, body]).map_err(error)?;
        tx.commit().map_err(error)
    }
    pub fn metadata_start(&self, root: ObjectId) -> Result<bool> {
        let db = self.0.lock().map_err(error)?;
        db.execute_batch("PRAGMA temp_store=FILE;
            CREATE TABLE IF NOT EXISTS metadata_roots(id BLOB PRIMARY KEY);
            CREATE TEMP TABLE IF NOT EXISTS metadata_queue(id BLOB PRIMARY KEY,kind INTEGER NOT NULL,done INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS temp.metadata_pending ON metadata_queue(done,id);").map_err(error)?;
        let done: bool = db
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM metadata_roots WHERE id=?)",
                [root.as_bytes().as_slice()],
                |r| r.get(0),
            )
            .map_err(error)?;
        if done {
            return Ok(false);
        }
        db.execute("DELETE FROM metadata_queue", [])
            .map_err(error)?;
        db.execute(
            "INSERT INTO metadata_queue(id,kind) VALUES(?,?)",
            params![root.as_bytes().as_slice(), crate::metadata::ROOT],
        )
        .map_err(error)?;
        Ok(true)
    }
    pub fn metadata_page(&self) -> Result<Vec<crate::metadata::Demand>> {
        let db = self.0.lock().map_err(error)?;
        let mut q = db
            .prepare("SELECT kind,id FROM metadata_queue WHERE done=0 ORDER BY id LIMIT 256")
            .map_err(error)?;
        let mut rows = q.query([]).map_err(error)?;
        let mut out = Vec::new();
        while let Some(row) = rows.next().map_err(error)? {
            let id: Vec<u8> = row.get(1).map_err(error)?;
            out.push((
                row.get(0).map_err(error)?,
                ObjectId::from_bytes(&id).map_err(error)?,
            ));
        }
        Ok(out)
    }
    pub fn metadata_advance(
        &self,
        done: &[crate::metadata::Demand],
        next: &[crate::metadata::Demand],
    ) -> Result<()> {
        let mut db = self.0.lock().map_err(error)?;
        let tx = db.transaction().map_err(error)?;
        for (_, id) in done {
            tx.execute(
                "UPDATE metadata_queue SET done=1 WHERE id=?",
                [id.as_bytes().as_slice()],
            )
            .map_err(error)?;
        }
        for (kind, id) in next {
            tx.execute(
                "INSERT OR IGNORE INTO metadata_queue(id,kind) VALUES(?,?)",
                params![id.as_bytes().as_slice(), kind],
            )
            .map_err(error)?;
        }
        tx.commit().map_err(error)
    }
    pub fn metadata_complete(&self, root: ObjectId) -> Result<()> {
        self.0
            .lock()
            .map_err(error)?
            .execute(
                "INSERT OR IGNORE INTO metadata_roots VALUES(?)",
                [root.as_bytes().as_slice()],
            )
            .map_err(error)?;
        Ok(())
    }
    pub fn get(&self, id: ObjectId) -> Result<Option<Vec<u8>>> {
        let bytes = self.body(id)?;
        if bytes.as_ref().is_some_and(|b| ObjectId::for_bytes(b) != id) {
            return Err(error("cache identity mismatch"));
        }
        Ok(bytes)
    }
    /// Unauthenticated bytes: restore must admit them before using references.
    pub fn body(&self, id: ObjectId) -> Result<Option<Vec<u8>>> {
        self.0
            .lock()
            .map_err(error)?
            .query_row(
                "SELECT body FROM objects WHERE id=?",
                [id.as_bytes().as_slice()],
                |r| r.get(0),
            )
            .optional()
            .map_err(error)
    }
    /// An object the Store served: known there from now on.
    pub fn put(&self, id: ObjectId, bytes: &[u8]) -> Result<()> {
        if bytes.len() > crate::wire::MAX_OBJECT || ObjectId::for_bytes(bytes) != id {
            return Err(error("object identity/size"));
        }
        let db = self.0.lock().map_err(error)?;
        db.execute(
            "INSERT INTO objects(id,body) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET remote=1",
            params![id.as_bytes().as_slice(), bytes],
        )
        .map_err(error)?;
        Ok(())
    }
    pub fn length(&self, id: ObjectId) -> Result<Option<u64>> {
        let value: Option<i64> = self
            .0
            .lock()
            .map_err(error)?
            .query_row(
                "SELECT value FROM lengths WHERE id=?",
                [id.as_bytes().as_slice()],
                |r| r.get(0),
            )
            .optional()
            .map_err(error)?;
        value.map(u64::try_from).transpose().map_err(error)
    }
    pub fn keep_length(&self, id: ObjectId, n: u64) -> Result<()> {
        self.0
            .lock()
            .map_err(error)?
            .execute(
                "INSERT OR IGNORE INTO lengths VALUES(?,?)",
                params![id.as_bytes().as_slice(), i64::try_from(n).map_err(error)?],
            )
            .map_err(error)?;
        Ok(())
    }
    /// An object construction emitted: local until the Store reports it.
    pub fn accept(&self, object: FinalizedObject) -> Result<()> {
        let (id, bytes) = (object.id(), object.canonical());
        if bytes.len() > crate::wire::MAX_OBJECT {
            return Err(error("object size"));
        }
        self.0
            .lock()
            .map_err(error)?
            .execute(
                "INSERT INTO objects(id,body,role,remote) VALUES(?,?,?,0)
                 ON CONFLICT(id) DO UPDATE SET role=excluded.role",
                params![id.as_bytes().as_slice(), bytes, object.role().code()],
            )
            .map_err(error)?;
        Ok(())
    }
    /// Covering index lookup: do not pull payload overflow pages into memory.
    pub fn presence(&self, id: ObjectId) -> Result<Option<(bool, Option<u8>)>> {
        self.0
            .lock()
            .map_err(error)?
            .query_row(
                "SELECT remote,role FROM objects INDEXED BY object_presence WHERE id=?",
                [id.as_bytes().as_slice()],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()
            .map_err(error)
    }
    /// A local object's role and bytes; `None` for one the Store has or
    /// this cache never held.
    pub fn local(&self, id: ObjectId) -> Result<Option<(ObjectRole, Vec<u8>)>> {
        let row: Option<(u8, Vec<u8>)> = self
            .0
            .lock()
            .map_err(error)?
            .query_row(
                "SELECT role,body FROM objects WHERE id=? AND remote=0",
                [id.as_bytes().as_slice()],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()
            .map_err(error)?;
        let Some((role, body)) = row else {
            return Ok(None);
        };
        if ObjectId::for_bytes(&body) != id {
            return Err(error("cache identity mismatch"));
        }
        Ok(Some((ObjectRole::from_code(role).map_err(error)?, body)))
    }
    /// Objects the Store now has.
    pub fn stored(&self, ids: &[ObjectId]) -> Result<()> {
        let mut db = self.0.lock().map_err(error)?;
        let tx = db.transaction().map_err(error)?;
        for id in ids {
            tx.execute(
                "UPDATE objects SET remote=1 WHERE id=?",
                [id.as_bytes().as_slice()],
            )
            .map_err(error)?;
        }
        tx.commit().map_err(error)
    }
}

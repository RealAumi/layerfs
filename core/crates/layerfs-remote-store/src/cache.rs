//! Nonauthoritative canonical cache and disk-backed construction emission order.
use crate::wire::{error, Result};
use layerfs_content::{FinalizedObject, ObjectId, ObjectRole};
use rusqlite::{params, Connection, OptionalExtension};
use std::{path::Path, sync::Mutex};
pub struct Cache(Mutex<Connection>);
pub struct Row {
    pub sequence: i64,
    pub id: ObjectId,
    pub role: ObjectRole,
    pub bytes: Vec<u8>,
}
impl Cache {
    pub fn open(path: &Path) -> Result<Self> {
        let db = Connection::open(path).map_err(error)?;
        db.execute_batch("PRAGMA journal_mode=MEMORY; PRAGMA synchronous=OFF; PRAGMA mmap_size=0; PRAGMA cache_size=-2048;
            CREATE TABLE IF NOT EXISTS objects(id BLOB PRIMARY KEY, body BLOB NOT NULL, role INTEGER);
            CREATE TABLE IF NOT EXISTS lengths(id BLOB PRIMARY KEY, value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY AUTOINCREMENT);
            CREATE TABLE IF NOT EXISTS emitted(sequence INTEGER PRIMARY KEY, attempt INTEGER NOT NULL, id BLOB NOT NULL, UNIQUE(attempt,id));
            CREATE INDEX IF NOT EXISTS emission_order ON emitted(attempt,sequence);").map_err(error)?;
        Ok(Self(Mutex::new(db)))
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
        let db = self.0.lock().map_err(error)?;
        let bytes: Option<Vec<u8>> = db
            .query_row(
                "SELECT body FROM objects WHERE id=?",
                [id.as_bytes().as_slice()],
                |r| r.get(0),
            )
            .optional()
            .map_err(error)?;
        if bytes.as_ref().is_some_and(|b| ObjectId::for_bytes(b) != id) {
            return Err(error("cache identity mismatch"));
        }
        Ok(bytes)
    }
    pub fn put(&self, id: ObjectId, bytes: &[u8]) -> Result<()> {
        if bytes.len() > crate::wire::MAX_OBJECT || ObjectId::for_bytes(bytes) != id {
            return Err(error("object identity/size"));
        }
        let db = self.0.lock().map_err(error)?;
        db.execute(
            "INSERT OR IGNORE INTO objects(id,body) VALUES(?,?)",
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
    pub fn attempt(&self) -> Result<i64> {
        let db = self.0.lock().map_err(error)?;
        db.execute("INSERT INTO attempts DEFAULT VALUES", [])
            .map_err(error)?;
        Ok(db.last_insert_rowid())
    }
    pub fn accept(&self, attempt: i64, object: FinalizedObject) -> Result<()> {
        self.put(object.id(), object.canonical())?;
        let mut db = self.0.lock().map_err(error)?;
        let tx = db.transaction().map_err(error)?;
        tx.execute(
            "UPDATE objects SET role=? WHERE id=?",
            params![object.role().code(), object.id().as_bytes().as_slice()],
        )
        .map_err(error)?;
        tx.execute(
            "INSERT OR IGNORE INTO emitted(attempt,id) VALUES(?,?)",
            params![attempt, object.id().as_bytes().as_slice()],
        )
        .map_err(error)?;
        tx.commit().map_err(error)
    }
    pub fn page(&self, attempt: i64, after: i64) -> Result<Vec<Row>> {
        let db = self.0.lock().map_err(error)?;
        let mut statement=db.prepare("SELECT e.sequence,e.id,o.role,length(o.body) FROM emitted e JOIN objects o ON o.id=e.id WHERE e.attempt=? AND e.sequence>? ORDER BY e.sequence LIMIT 512").map_err(error)?;
        let mut query = statement.query(params![attempt, after]).map_err(error)?;
        let mut rows = Vec::new();
        let mut bytes = 0;
        while let Some(row) = query.next().map_err(error)? {
            let size = usize::try_from(row.get::<_, i64>(3).map_err(error)?).map_err(error)?;
            if size > crate::wire::MAX_OBJECT {
                return Err(error("cache object size"));
            }
            if !rows.is_empty() && bytes + size >= 4 * 1024 * 1024 {
                break;
            }
            let raw: Vec<u8> = row.get(1).map_err(error)?;
            let id = ObjectId::from_bytes(&raw).map_err(error)?;
            let body: Vec<u8> = db
                .query_row("SELECT body FROM objects WHERE id=?", [raw], |r| r.get(0))
                .map_err(error)?;
            if ObjectId::for_bytes(&body) != id {
                return Err(error("cache identity mismatch"));
            }
            rows.push(Row {
                sequence: row.get(0).map_err(error)?,
                id,
                role: ObjectRole::from_code(row.get(2).map_err(error)?).map_err(error)?,
                bytes: body,
            });
            bytes += size;
        }
        Ok(rows)
    }
}

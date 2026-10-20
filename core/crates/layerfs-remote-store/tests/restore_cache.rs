//! Actual SQLite/cache/manifest tests, with bounded authenticated idle peers.
use layerfs_bridge::duplex;
use layerfs_content::{
    construct_bytes,
    filesystem::{
        attributes::portable::PortableMetadata, build_filesystem, scope_for_seed, DirectoryUpdate,
        FilesystemInput, FilesystemObjects, FilesystemResources, InodeUpdate, PathName,
    },
    inode_leaf::{InodeKind, InodeMetadata, InodeValue},
    ConstructionPolicy, ContentResult, FinalizedConsumer, FinalizedObject, ObjectId,
};
use layerfs_history::{BranchId, BranchRecord, BranchSnapshot, HistoryName, LayerId, LayerStackId};
use layerfs_remote_store::{
    config::hex,
    wire::{self, Decode, Encode},
    Client, Config,
};
use layerfs_store_service::store::{
    ignore::{RestorePoint, Seed},
    RemoteBuild, RemoteStore,
};
use layerfs_telemetry::timer::Timing;
use std::{
    collections::BTreeSet,
    fs,
    net::{Shutdown, TcpListener, TcpStream},
    os::unix::fs::PermissionsExt,
    path::Path,
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Duration, Instant},
};

struct Peer {
    client: Arc<Client>,
    stop: Vec<TcpStream>,
    known: Arc<Mutex<BTreeSet<ObjectId>>>,
    requests: Arc<Mutex<Vec<Vec<ObjectId>>>>,
    worker: Option<thread::JoinHandle<()>>,
}
impl Drop for Peer {
    fn drop(&mut self) {
        for socket in &self.stop {
            let _ = socket.shutdown(Shutdown::Both);
        }
        if let Some(worker) = self.worker.take() {
            worker.join().unwrap();
        }
    }
}
fn connect(dir: &Path, n: usize) -> Peer {
    let server = duplex::generate_keypair().unwrap();
    let token = duplex::generate_keypair().unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let setup = dir.join(format!("config-{n}"));
    fs::write(
        &setup,
        format!(
            "server={}\nserver_key={}\ntoken={}\ncache={}\n",
            listener.local_addr().unwrap(),
            hex(&server.public),
            hex(&token.private),
            dir.join("cache.sqlite").display()
        ),
    )
    .unwrap();
    fs::set_permissions(&setup, fs::Permissions::from_mode(0o600)).unwrap();
    let (tx, rx) = mpsc::channel();
    let known = Arc::new(Mutex::new(BTreeSet::new()));
    let server_known = known.clone();
    let requests = Arc::new(Mutex::new(Vec::new()));
    let server_requests = requests.clone();
    let worker = thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut channels = Vec::new();
        let mut shutdown = Vec::new();
        while channels.len() != 2 {
            match listener.accept() {
                Ok((socket, _)) => {
                    socket.set_nonblocking(false).unwrap();
                    socket
                        .set_read_timeout(Some(Duration::from_secs(3)))
                        .unwrap();
                    socket
                        .set_write_timeout(Some(Duration::from_secs(3)))
                        .unwrap();
                    shutdown.push(socket.try_clone().unwrap());
                    channels.push(duplex::accept(socket, &server.private, token.public).unwrap());
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    assert!(Instant::now() < deadline, "accept deadline");
                    thread::sleep(Duration::from_millis(5));
                }
                Err(e) => panic!("{e}"),
            }
        }
        tx.send(shutdown).unwrap();
        while let Ok(bytes) = wire::receive(&mut channels[0]) {
            let mut input = Decode(&bytes);
            let request = input.number().unwrap();
            assert_eq!(input.byte().unwrap(), wire::LACKING);
            let ids = wire::ids(&mut input).unwrap();
            input.finish().unwrap();
            server_requests.lock().unwrap().push(ids.clone());
            let mut out = Encode::new();
            out.number(request);
            out.byte(0);
            for id in ids {
                out.byte(u8::from(!server_known.lock().unwrap().contains(&id)));
            }
            wire::send(&mut channels[0], &out.0).unwrap();
        }
    });
    Peer {
        client: Client::connect(&Config::read(&setup).unwrap()).unwrap(),
        stop: rx.recv_timeout(Duration::from_secs(5)).unwrap(),
        known,
        requests,
        worker: Some(worker),
    }
}
struct Sink<'a>(&'a dyn RemoteBuild);
impl FinalizedConsumer for Sink<'_> {
    fn accept(&mut self, obj: FinalizedObject) -> ContentResult<()> {
        self.0.accept(obj).unwrap();
        Ok(())
    }
}
fn point(client: &Client, tag: u8) -> (RestorePoint, ObjectId) {
    let build = client.build().unwrap();
    let policy = ConstructionPolicy::frozen_default();
    let bytes = vec![tag; 4096];
    let leaf = Timing::disabled("restore.file", |t| {
        construct_bytes(
            policy,
            &policy.capacities(),
            &bytes,
            &mut Sink(build.as_ref()),
            t.child("file"),
        )
    })
    .0
    .unwrap()
    .root;
    let meta = InodeMetadata::Inline(PortableMetadata {
        mode: 0o755,
        mtime_seconds: 1700000000,
        mtime_nanoseconds: 0,
    });
    let inodes = [
        InodeUpdate {
            serial: 1,
            value: InodeValue {
                kind: InodeKind::Directory,
                namespace_ref_count: 0,
                content_root: leaf,
                metadata_root: meta,
            },
        },
        InodeUpdate {
            serial: 2,
            value: InodeValue {
                kind: InodeKind::RegularFile,
                namespace_ref_count: 0,
                content_root: leaf,
                metadata_root: meta,
            },
        },
    ];
    let dirs = [DirectoryUpdate {
        parent: 1,
        changes: vec![(PathName::new("private").unwrap(), Some(2))],
    }];
    let scope = scope_for_seed([5; 32]);
    let input = FilesystemInput {
        base: None,
        scope,
        root_serial: 1,
        directories: &dirs,
        inodes: &inodes,
        new_inodes: &[1, 2],
        resources: FilesystemResources::default(),
    };
    let root = build_filesystem(
        &mut FilesystemObjects::new_with_accepted(
            build.reader(),
            &mut Sink(build.as_ref()),
            build.reader(),
        ),
        &input,
        None,
    )
    .unwrap()
    .root;
    let binding = BranchSnapshot {
        branch: BranchRecord {
            forked_from: None,
            id: BranchId::from_authority([1; 16]),
            stack: LayerStackId::from_authority([2; 16]),
            name: HistoryName::new("main").unwrap(),
            base_layer: LayerId::from_bytes([0x32; 33]).unwrap(),
            head_commit: None,
        },
        head_root: None,
        base_root: root.0,
        effective_root: root.0,
        scope: scope.object(),
        profile: layerfs_content::filesystem::profile_id(),
    };
    (
        RestorePoint {
            local: root.0,
            published: leaf,
            binding,
            seeds: vec![
                Seed::Directory(tag.into()),
                Seed::Path(format!("nested/{tag}")),
            ],
        },
        leaf,
    )
}
fn temp(label: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("cxi-cache-{}-{label}", std::process::id()));
    fs::create_dir(&dir).unwrap();
    dir
}
#[test]
fn restart_atomic_last_writer_and_scoped_keys() {
    let dir = temp("records");
    // Simulate an old cache: opening it adds only the new table, with no bump.
    let db = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    db.execute_batch("PRAGMA user_version=19;").unwrap();
    let first = connect(&dir, 1);
    let (a, _) = point(&first.client, 10);
    first.client.save_restore("shared", &a).unwrap();
    let second = connect(&dir, 2);
    let (b, _) = point(&second.client, 20);
    second.client.save_restore("shared", &b).unwrap();
    assert_ne!(a.local, b.local);
    assert_ne!(a.binding, b.binding);
    assert_ne!(a.seeds, b.seeds);
    drop(first);
    drop(second);
    let reopened = connect(&dir, 3);
    assert_eq!(
        reopened.client.restore(&b.binding, "shared").unwrap(),
        Some(b.clone())
    );
    assert_eq!(reopened.client.restore_status(), "restored");
    assert!(reopened
        .client
        .restore(&b.binding, "other")
        .unwrap()
        .is_none());
    let mut other = b.binding.clone();
    other.branch.id = BranchId::from_authority([9; 16]);
    assert!(reopened.client.restore(&other, "shared").unwrap().is_none());
    other = b.binding.clone();
    other.scope = ObjectId::for_bytes(b"other-store");
    assert!(reopened.client.restore(&other, "shared").unwrap().is_none());
    assert_eq!(reopened.client.restore_status(), "not-found");
    assert_eq!(reopened.client.round_trips(), 0);
    assert_eq!(
        db.query_row("PRAGMA user_version", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        19
    );
    drop(db);
    drop(reopened);
    fs::remove_dir_all(dir).unwrap();
}
fn missing(root: bool) {
    let dir = temp(if root { "missing-root" } else { "missing-leaf" });
    let peer = connect(&dir, 1);
    let (point, leaf) = point(&peer.client, 31);
    peer.client.save_restore("key", &point).unwrap();
    let db = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    let id = if root { point.local } else { leaf };
    assert_eq!(
        db.execute(
            "DELETE FROM objects WHERE id=? AND remote=0",
            [id.as_bytes().as_slice()]
        )
        .unwrap(),
        1
    );
    drop(peer);
    let reopened = connect(&dir, 2);
    assert!(
        reopened
            .client
            .restore(&point.binding, "key")
            .unwrap()
            .is_none(),
        "no rejected root or seeds"
    );
    assert_eq!(reopened.client.restore_status(), "missing-local-objects");
    assert_eq!(reopened.client.uploaded(), (0, 0));
    drop(db);
    drop(reopened);
    fs::remove_dir_all(dir).unwrap();
}
#[test]
fn missing_local_leaf_rejects_record() {
    missing(false);
}
#[test]
fn missing_local_root_rejects_record() {
    missing(true);
}
#[test]
fn remote_objects_are_not_required_in_manifest_and_corruption_has_reason() {
    let dir = temp("remote");
    let peer = connect(&dir, 1);
    let (point, leaf) = point(&peer.client, 41);
    let db = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    peer.known.lock().unwrap().insert(leaf);
    db.execute(
        "UPDATE objects SET remote=1 WHERE id=?",
        [leaf.as_bytes().as_slice()],
    )
    .unwrap();
    peer.client.save_restore("key", &point).unwrap();
    db.execute(
        "DELETE FROM objects WHERE id=?",
        [leaf.as_bytes().as_slice()],
    )
    .unwrap();
    assert_eq!(
        peer.client.restore(&point.binding, "key").unwrap(),
        Some(point.clone())
    );
    db.execute(
        "UPDATE objects SET body=X'00' WHERE id=?",
        [point.local.as_bytes().as_slice()],
    )
    .unwrap();
    assert!(peer
        .client
        .restore(&point.binding, "key")
        .unwrap()
        .is_none());
    assert_eq!(peer.client.restore_status(), "invalid-local-objects");
    db.execute("UPDATE restore_points SET body=X'00'", [])
        .unwrap();
    assert!(peer
        .client
        .restore(&point.binding, "key")
        .unwrap()
        .is_none());
    assert_eq!(peer.client.restore_status(), "invalid-record");
    drop(db);
    drop(peer);
    fs::remove_dir_all(dir).unwrap();
}

#[test]
fn saving_restore_does_not_read_the_unchanged_object_graph() {
    let dir = temp("constant-save");
    let peer = connect(&dir, 1);
    let (point, _) = point(&peer.client, 51);
    let db = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    // A record write owns no canonical-object reads, including the root.
    db.execute(
        "UPDATE objects SET body=X'00' WHERE id=?",
        [point.local.as_bytes().as_slice()],
    )
    .unwrap();
    let saved = peer.client.save_restore("key", &point);
    drop(db);
    drop(peer);
    fs::remove_dir_all(dir).unwrap();
    assert!(
        saved.is_ok(),
        "record save read the old local tree: {saved:?}"
    );
}
#[test]
fn restore_presence_does_not_materialize_file_payload_leaves() {
    let dir = temp("leaf-presence");
    let peer = connect(&dir, 1);
    let (point, leaf) = point(&peer.client, 52);
    peer.client.save_restore("key", &point).unwrap();
    let db = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    db.execute(
        "UPDATE objects SET body=X'00' WHERE id=?",
        [leaf.as_bytes().as_slice()],
    )
    .unwrap();
    let restored = peer.client.restore(&point.binding, "key").unwrap();
    // Content authentication remains on demand; restore checks leaf presence.
    assert!(peer.client.objects(&[leaf]).is_err());
    drop(db);
    drop(peer);
    fs::remove_dir_all(dir).unwrap();
    assert_eq!(restored, Some(point));
}
#[test]
fn save_failure_preserves_previous_record_and_exposes_status() {
    let dir = temp("save-failure");
    let peer = connect(&dir, 1);
    let (point, _) = point(&peer.client, 53);
    peer.client.save_restore("key", &point).unwrap();
    let db = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    db.execute_batch("CREATE TRIGGER refuse_restore BEFORE INSERT ON restore_points BEGIN SELECT RAISE(ABORT,'injected record failure'); END;").unwrap();
    let mut later = point.clone();
    later.seeds.clear();
    assert!(peer.client.save_restore("key", &later).is_err());
    let status = peer.client.restore_status();
    let restored = peer.client.restore(&point.binding, "key").unwrap();
    drop(db);
    drop(peer);
    fs::remove_dir_all(dir).unwrap();
    assert_eq!(restored, Some(point));
    assert_eq!(status, "save-failed");
}
#[test]
fn cache_uses_a_process_crash_safe_journal() {
    let dir = temp("journal");
    let peer = connect(&dir, 1);
    let db = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    let mode: String = db
        .query_row("PRAGMA journal_mode", [], |r| r.get(0))
        .unwrap();
    drop(db);
    drop(peer);
    fs::remove_dir_all(dir).unwrap();
    assert_eq!(mode, "wal");
}
#[test]
fn absent_local_references_are_resolved_in_one_batch() {
    let dir = temp("absence-batch");
    let peer = connect(&dir, 1);
    let (point, _) = point(&peer.client, 61);
    peer.client.save_restore("key", &point).unwrap();
    let db = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    let removed = db
        .execute("DELETE FROM objects WHERE remote=0 AND role IN (1,2,7)", [])
        .unwrap();
    assert!(removed >= 2);
    assert!(peer
        .client
        .restore(&point.binding, "key")
        .unwrap()
        .is_none());
    assert_eq!(peer.client.restore_status(), "missing-local-objects");
    let queries = peer.requests.lock().unwrap().clone();
    assert_eq!(queries.len(), 1);
    assert_eq!(queries[0].len(), removed);
    drop(db);
    drop(peer);
    fs::remove_dir_all(dir).unwrap();
}

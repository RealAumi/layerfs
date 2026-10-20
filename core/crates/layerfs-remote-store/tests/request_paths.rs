//! Offline diagnostic: map canonical IDs to their immutable namespace owners.
use layerfs_content::{
    filesystem::{FilesystemRead, FilesystemRootId, LogicalPath},
    inode_leaf::InodeKind,
    AuthenticatedObjects, ContentResult, ObjectId,
};
use layerfs_history::{BranchId, HistoryName, LayerStackId};
use layerfs_remote_store::config::{unhex, Config};
use layerfs_store_service::StoreService;
use layerfs_telemetry::timer::Timing;
use std::path::Path;
struct Traced<'a> {
    reader: &'a dyn AuthenticatedObjects,
    path: &'a str,
}
impl AuthenticatedObjects for Traced<'_> {
    fn read_canonical_batch(&self, ids: &[ObjectId]) -> ContentResult<Vec<Vec<u8>>> {
        for id in ids {
            println!("OWNER\t{id}\t{}", self.path);
        }
        self.reader.read_canonical_batch(ids)
    }
}
#[test]
#[ignore = "explicit offline diagnostic on an owned Store copy"]
fn request_paths() {
    let cfg = Config::read(Path::new("/state/server.setup")).unwrap();
    let service = StoreService::open_direct(
        Path::new(cfg.get("store").unwrap()),
        &unhex(cfg.get("binding").unwrap()).unwrap(),
        cfg.key("cursor").unwrap(),
        Path::new("/state/paths-overlay/template.sqlite"),
    )
    .unwrap();
    let branch = BranchId::named(
        LayerStackId::from_authority([23; 16]),
        &HistoryName::new("work").unwrap(),
    );
    let snapshot = service
        .store
        .history()
        .branch_snapshot(branch)
        .unwrap()
        .unwrap();
    let ports = service.store.ports(ObjectId::for_bytes(b"diagnostic"));
    let mut fs =
        FilesystemRead::new(ports.as_ref(), FilesystemRootId(snapshot.effective_root)).unwrap();
    let mut pending = vec![(LogicalPath::root(), fs.root().root_inode().serial())];
    while let Some((path, serial)) = pending.pop() {
        let value = fs.resolve_inode(serial).unwrap().value;
        let reader = Traced {
            reader: ports.as_ref(),
            path: path.as_str(),
        };
        match value.kind {
            InodeKind::RegularFile => {
                Timing::disabled("map", |scope| {
                    layerfs_content::read_all(
                        &reader,
                        value.content_root,
                        &mut std::io::sink(),
                        scope.child("read"),
                    )
                })
                .0
                .unwrap();
            }
            InodeKind::Directory => {
                let mut traced =
                    FilesystemRead::new(&reader, FilesystemRootId(snapshot.effective_root))
                        .unwrap();
                let mut after = None;
                loop {
                    let page = traced
                        .list_inode(serial, after.as_ref(), 512, 65536)
                        .unwrap();
                    pending.extend(
                        page.entries
                            .into_iter()
                            .map(|(name, child)| (path.join(&name), child)),
                    );
                    after = page.continuation;
                    if after.is_none() {
                        break;
                    }
                }
            }
            InodeKind::Symlink => {
                reader.read_canonical(value.content_root).unwrap();
            }
        }
    }
    drop(ports);
    service.close().unwrap();
}

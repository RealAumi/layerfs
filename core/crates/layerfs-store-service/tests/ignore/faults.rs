//! Exercise the real remote Commit driver with failures supplied by its provider.
use super::*;
use layerfs_history::{
    BranchId, BranchRecord, BranchSnapshot, CommitOutcome, HistoryName, LayerId, LayerStackId,
    WorkspaceId,
};
use layerfs_storage::StoragePolicy;
use layerfs_store_service::store::{
    backend::{BackendError, RemoteBuild, RemoteStore, WorkspaceBackend},
    publish::{CandidateInput, Publication, PublishedCandidate},
    BindRequest, BoundWorkspace, CommitError, CommitOptions, CommitPhase,
};
use layerfs_store_service::{Owner, OwnerConfig};
use std::sync::{Arc, Mutex};

#[derive(Clone, Copy, Debug, PartialEq)]
enum Fault {
    None,
    Upload,
    InstallRead,
    RebaseWrite,
    SaveRestore,
}
#[derive(Debug)]
struct State {
    objects: BTreeMap<ObjectId, Vec<u8>>,
    snapshot: BranchSnapshot,
    fault: Fault,
    published: bool,
    calls: usize,
    hit: usize,
    records: BTreeMap<String, layerfs_store_service::store::ignore::RestorePoint>,
}
#[derive(Clone, Debug)]
struct Remote(Arc<Mutex<State>>);
fn failure() -> BackendError {
    BackendError {
        detail: "injected boundary failure".into(),
        unknown: false,
    }
}
impl Remote {
    fn mem(&self) -> Mem {
        Mem {
            objects: RefCell::new(self.0.lock().unwrap().objects.clone()),
            next: Cell::new(10000),
        }
    }
    fn root(&self) -> FilesystemRootId {
        FilesystemRootId(self.0.lock().unwrap().snapshot.effective_root)
    }
}
impl AuthenticatedObjects for Remote {
    fn read_canonical_batch(&self, ids: &[ObjectId]) -> ContentResult<Vec<Vec<u8>>> {
        self.objects(ids).map_err(|_| ContentError::MissingObject)
    }
}
impl RemoteStore for Remote {
    fn restore(
        &self,
        _: &BranchSnapshot,
        key: &str,
    ) -> Result<Option<layerfs_store_service::store::ignore::RestorePoint>, BackendError> {
        Ok(self.0.lock().unwrap().records.get(key).cloned())
    }
    fn save_restore(
        &self,
        key: &str,
        point: &layerfs_store_service::store::ignore::RestorePoint,
    ) -> Result<(), BackendError> {
        if self.0.lock().unwrap().fault == Fault::SaveRestore {
            return Err(failure());
        }
        self.0
            .lock()
            .unwrap()
            .records
            .insert(key.into(), point.clone());
        Ok(())
    }
    fn policy(&self) -> StoragePolicy {
        StoragePolicy::frozen_default()
    }
    fn snapshot(&self, _: BranchId) -> Result<BranchSnapshot, BackendError> {
        Ok(self.0.lock().unwrap().snapshot.clone())
    }
    fn objects(&self, ids: &[ObjectId]) -> Result<Vec<Vec<u8>>, BackendError> {
        let mut s = self.0.lock().unwrap();
        if s.published && s.fault == Fault::InstallRead {
            s.hit += 1;
            return Err(failure());
        }
        ids.iter()
            .map(|id| s.objects.get(id).cloned().ok_or_else(failure))
            .collect()
    }
    fn lengths(&self, ids: &[ObjectId]) -> Result<Vec<u64>, BackendError> {
        let mem = self.mem();
        ids.iter()
            .map(|id| {
                read_file(&mem, *id, 1 << 20)
                    .map(|b| b.unwrap().len() as u64)
                    .map_err(|_| failure())
            })
            .collect()
    }
    fn reserve(&self, _: ObjectId, _: u64) -> Result<(u64, u64), BackendError> {
        panic!("fixture only edits existing files")
    }
    fn build(&self) -> Result<Box<dyn RemoteBuild>, BackendError> {
        Ok(Box::new(self.clone()))
    }
}
impl RemoteBuild for Remote {
    fn reader(&self) -> &dyn AuthenticatedObjects {
        self
    }
    fn failure(&self) -> Option<BackendError> {
        None
    }
    fn accept(&self, object: FinalizedObject) -> Result<(), BackendError> {
        let mut s = self.0.lock().unwrap();
        if s.published && s.fault == Fault::RebaseWrite {
            s.hit += 1;
            return Err(failure());
        }
        let p = object.into_parts();
        s.objects.insert(p.id, p.canonical);
        Ok(())
    }
    fn publish(
        &self,
        input: &CandidateInput,
    ) -> Result<(PublishedCandidate, Publication), BackendError> {
        {
            let mut s = self.0.lock().unwrap();
            s.calls += 1;
            if s.fault == Fault::Upload {
                s.hit += 1;
                return Err(failure());
            }
        }
        let mem = self.mem();
        let moved = self.0.lock().unwrap().fault == Fault::RebaseWrite;
        let root = if moved {
            mem.edit(Some(input.root), &[Write("src/server", b"server")])
        } else if input.binding.effective_root != self.root().0 {
            restore::merge(
                &mem,
                FilesystemRootId(input.binding.effective_root),
                input.root,
                self.root(),
            )
        } else {
            input.root
        };
        let mut s = self.0.lock().unwrap();
        s.objects = mem.objects.into_inner();
        s.snapshot.effective_root = root.0;
        s.snapshot.head_root = Some(root.0);
        s.published = true;
        Ok((
            PublishedCandidate {
                binding: s.snapshot.clone(),
                root,
                merge: None,
                pending: None,
                replaced: None,
            },
            Publication {
                phase: CommitPhase::Publish,
                published: Some(CommitOutcome::UpToDate {
                    head: None,
                    root: root.0,
                }),
                ..Publication::default()
            },
        ))
    }
}
fn view<T>(
    ws: &BoundWorkspace,
    f: impl FnOnce(&layerfs_store_service::store::StoreOperation, &layerfs_workspace::SourceView) -> T,
) -> T {
    let op = ws.operation().unwrap();
    let source = op.overlay().acquire_base_source(ws.route(), 31).unwrap();
    let view = op.workspace().view_for_source(source).unwrap();
    let result = f(&op, &view);
    drop(view);
    op.overlay()
        .release_base_source(ws.route(), source)
        .unwrap();
    result
}
fn file(ws: &BoundWorkspace, path: &[&str], write: Option<&[u8]>) -> Vec<u8> {
    view(ws, |op, view| {
        let mut serial = view.root_serial();
        for part in path {
            serial = view
                .lookup(op.overlay(), serial, &name(part))
                .unwrap()
                .serial;
        }
        if let Some(bytes) = write {
            let outcome = op
                .workspace()
                .mutate(
                    op.overlay(),
                    op.ports(),
                    view,
                    layerfs_workspace::Operation::Write {
                        serial,
                        position: layerfs_workspace::Position::At(0),
                        data: bytes.into(),
                    },
                    layerfs_workspace::Time {
                        seconds: 1700000000,
                        nanoseconds: 0,
                    },
                )
                .unwrap();
            let layerfs_workspace::Outcome::Applied { publication, .. } = outcome else {
                panic!("write {outcome:?}")
            };
            op.overlay().reply_attempted(publication).unwrap();
        }
        let mut bytes = Vec::new();
        view.read(op.overlay(), serial, 0, 1024, &mut bytes)
            .unwrap();
        bytes
    })
}
fn scenario(fault: Fault) {
    let mem = Mem::default();
    let root = warm(&mem);
    let snapshot = BranchSnapshot {
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
        scope: TreeTable::open(&mem, root).unwrap().root.scope().object(),
        profile: layerfs_content::filesystem::profile_id(),
    };
    let remote = Remote(Arc::new(Mutex::new(State {
        objects: mem.objects.into_inner(),
        snapshot,
        fault: Fault::None,
        published: false,
        calls: 0,
        hit: 0,
        records: Default::default(),
    })));
    let dir = std::env::temp_dir().join(format!("cxi-fault-{}-{fault:?}", std::process::id()));
    std::fs::create_dir(&dir).unwrap();
    let owner = Owner::start(
        &dir.join("overlay.sqlite"),
        layerfs_overlay::ProfileConfig::default(),
        OwnerConfig::default(),
    )
    .unwrap();
    let branch = remote.0.lock().unwrap().snapshot.branch.id;
    let ws = WorkspaceBackend::remote(Arc::new(remote.clone()), 1 << 20, true)
        .bind(
            owner.client(),
            BindRequest {
                branch,
                workspace: WorkspaceId::from_authority([3; 32]).unwrap(),
            },
        )
        .unwrap()
        .workspace;
    file(&ws, &["target", "old.class"], Some(b"local1"));
    ws.commit_captured(&CommitOptions::default()).unwrap();
    let pair = || {
        (
            ws.operation()
                .unwrap()
                .workspace()
                .base()
                .unwrap()
                .identity(),
            ws.snapshot().unwrap().effective_root,
        )
    };
    let prior = pair();
    assert_ne!(prior.0 .0, prior.1);
    file(&ws, &["target", "old.class"], Some(b"local2"));
    file(&ws, &["src", "A.java"], Some(b"v2"));
    {
        let mut s = remote.0.lock().unwrap();
        s.fault = fault;
        s.published = false;
    }
    let failed = ws.commit_captured(&CommitOptions::default()).unwrap_err();
    assert_eq!(pair(), prior, "pair changes only after installation");
    assert_eq!(remote.0.lock().unwrap().hit, 1);
    {
        let mut s = remote.0.lock().unwrap();
        s.fault = Fault::None;
    }
    assert_eq!(file(&ws, &["target", "old.class"], None), b"local2");
    assert_eq!(file(&ws, &["src", "A.java"], None), b"v2");
    assert!(has(
        &remote.mem().files(remote.root()),
        "target/old.class",
        "old"
    ));
    if fault == Fault::Upload {
        assert!(failed.locally_settled);
        drop(failed);
        ws.commit_captured(&CommitOptions::default()).unwrap();
        assert!(has(&remote.mem().files(remote.root()), "src/A.java", "v2"));
        assert!(has(
            &remote.mem().files(remote.root()),
            "target/old.class",
            "old"
        ));
        assert_eq!(file(&ws, &["target", "old.class"], None), b"local2");
        ws.close().unwrap();
    } else {
        assert!(failed.published.is_some());
        assert!(!failed.locally_settled);
        let calls = remote.0.lock().unwrap().calls;
        let next = ws.commit_captured(&CommitOptions::default()).unwrap_err();
        assert!(matches!(next.error, CommitError::InFlight));
        assert_eq!(
            remote.0.lock().unwrap().calls,
            calls,
            "no stale-root publication"
        );
        drop(next);
        drop(failed);
    }
    drop(ws);
    drop(owner);
    std::fs::remove_dir_all(dir).unwrap();
}
#[test]
fn definite_upload_refusal_preserves_the_next_explicit_commit() {
    scenario(Fault::Upload);
}
#[test]
fn published_install_read_failure_retains_custody_and_refuses_next_commit() {
    scenario(Fault::InstallRead);
}
#[test]
fn published_rebase_write_failure_retains_custody_and_refuses_next_commit() {
    scenario(Fault::RebaseWrite);
}
#[path = "restore.rs"]
mod restore;

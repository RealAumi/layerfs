//! Failing-first restore contract against the real bind/Commit/install path.
use super::*;

fn remote() -> Remote {
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
    Remote(Arc::new(Mutex::new(State {
        objects: mem.objects.into_inner(), snapshot, fault: Fault::None,
        published: false, calls: 0, hit: 0,
    })))
}
fn bind(remote: &Remote, owner: &Owner, id: u8, _restore_key: Option<&str>) -> BoundWorkspace {
    // Baseline has no key field; exercise the existing bind, then wire the
    // explicit key here when the production entry point exists.
    let branch = remote.0.lock().unwrap().snapshot.branch.id;
    WorkspaceBackend::remote(Arc::new(remote.clone()), 1 << 20, true)
        .bind(owner.client(), BindRequest {
            branch,
            workspace: WorkspaceId::from_authority([id; 32]).unwrap(),
        }).unwrap().workspace
}
fn restored_last_commit(restart: bool) {
    let dir = std::env::temp_dir().join(format!("cxi-restore-{}-{restart}", std::process::id()));
    std::fs::create_dir(&dir).unwrap();
    let start = |n| {
        let incarnation = dir.join(format!("overlay-{n}"));
        std::fs::create_dir(&incarnation).unwrap();
        Owner::start(&incarnation.join("template.sqlite"),
            layerfs_overlay::ProfileConfig::default(), OwnerConfig::default()).unwrap()
    };
    let remote = remote();
    let mut owner = start(1);
    let ws = bind(&remote, &owner, 3, Some("sandbox"));
    file(&ws, &["target", "old.class"], Some(b"private"));
    file(&ws, &["src", "A.java"], Some(b"tracked"));
    ws.commit_captured(&CommitOptions::default()).unwrap();
    let saved = ws.operation().unwrap().workspace().base().unwrap().identity();
    file(&ws, &["target", "old.class"], Some(b"unsaved"));
    ws.close().unwrap();
    drop(ws);
    if restart { drop(owner); owner = start(2); }
    let next = bind(&remote, &owner, 4, Some("sandbox"));
    let actual = next.operation().unwrap().workspace().base().unwrap().identity();
    let bytes = file(&next, &["target", "old.class"], None);
    let tracked = file(&next, &["src", "A.java"], None);
    next.close().unwrap();
    drop(next); drop(owner);
    std::fs::remove_dir_all(dir).unwrap();
    assert_eq!(actual, saved, "restore last installed local root");
    assert_eq!(bytes, b"private");
    assert_eq!(tracked, b"tracked");
}
#[test]
fn remount_restores_last_successful_commit() { restored_last_commit(false); }
#[test]
fn restart_restores_last_successful_commit() { restored_last_commit(true); }

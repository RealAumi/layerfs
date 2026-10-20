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
        objects: mem.objects.into_inner(),
        snapshot,
        fault: Fault::None,
        published: false,
        calls: 0,
        hit: 0,
        records: Default::default(),
    })))
}
fn bind(remote: &Remote, owner: &Owner, id: u8, restore_key: Option<&str>) -> BoundWorkspace {
    let branch = remote.0.lock().unwrap().snapshot.branch.id;
    WorkspaceBackend::remote(Arc::new(remote.clone()), 1 << 20, true)
        .bind_restore(
            owner.client(),
            BindRequest {
                branch,
                workspace: WorkspaceId::from_authority([id; 32]).unwrap(),
            },
            restore_key.map(str::to_owned),
        )
        .unwrap()
        .workspace
}
fn restored_last_commit(restart: bool) {
    let dir = std::env::temp_dir().join(format!("cxi-restore-{}-{restart}", std::process::id()));
    std::fs::create_dir(&dir).unwrap();
    let start = |n| {
        let incarnation = dir.join(format!("overlay-{n}"));
        std::fs::create_dir(&incarnation).unwrap();
        Owner::start(
            &incarnation.join("template.sqlite"),
            layerfs_overlay::ProfileConfig::default(),
            OwnerConfig::default(),
        )
        .unwrap()
    };
    let remote = remote();
    let mut owner = start(1);
    let ws = bind(&remote, &owner, 3, Some("sandbox"));
    file(&ws, &["target", "old.class"], Some(b"private"));
    file(&ws, &["src", "A.java"], Some(b"tracked"));
    ws.commit_captured(&CommitOptions::default()).unwrap();
    let saved = ws
        .operation()
        .unwrap()
        .workspace()
        .base()
        .unwrap()
        .identity();
    file(&ws, &["target", "old.class"], Some(b"unsaved"));
    ws.close().unwrap();
    drop(ws);
    if restart {
        drop(owner);
        owner = start(2);
    }
    let next = bind(&remote, &owner, 4, Some("sandbox"));
    let actual = next
        .operation()
        .unwrap()
        .workspace()
        .base()
        .unwrap()
        .identity();
    let bytes = file(&next, &["target", "old.class"], None);
    let tracked = file(&next, &["src", "A.java"], None);
    next.close().unwrap();
    drop(next);
    drop(owner);
    std::fs::remove_dir_all(dir).unwrap();
    assert_eq!(actual, saved, "restore last installed local root");
    assert_eq!(bytes, b"private");
    assert_eq!(tracked, b"tracked");
}
#[test]
fn remount_restores_last_successful_commit() {
    restored_last_commit(false);
}
#[test]
fn restart_restores_last_successful_commit() {
    restored_last_commit(true);
}

pub(super) fn merge(
    mem: &Mem,
    base: FilesystemRootId,
    ours: FilesystemRootId,
    theirs: FilesystemRootId,
) -> FilesystemRootId {
    use layerfs_content::merge::*;
    let policy = ConstructionPolicy::frozen_default();
    let capacities = policy.capacities();
    let input = MergeInput {
        base,
        ours,
        theirs,
        labels: ["local", "server"],
        rules_from: RulesFrom::Theirs,
        policy,
        capacities: &capacities,
        hints: None,
        decide_from: Side::Ours,
        bound: None,
    };
    let mut fresh = || {
        let n = mem.next.get() + 1;
        mem.next.set(n);
        Ok(n)
    };
    let result = Timing::disabled("restore.merge", |t| {
        merge_roots(mem, &mut Sink(mem), &input, &mut fresh, None, t)
    })
    .0
    .unwrap();
    assert!(result.clean());
    result.root
}
fn server(remote: &Remote, changes: &[Op<'_>]) {
    let mem = remote.mem();
    let root = mem.edit(Some(remote.root()), changes);
    let mut s = remote.0.lock().unwrap();
    s.objects = mem.objects.into_inner();
    s.snapshot.effective_root = root.0;
    s.snapshot.head_root = Some(root.0);
}
fn with_owner(label: &str, f: impl FnOnce(&Remote, &Owner)) {
    let dir = std::env::temp_dir().join(format!("cxi-restore-{}-{label}", std::process::id()));
    std::fs::create_dir(&dir).unwrap();
    let owner = Owner::start(
        &dir.join("template.sqlite"),
        layerfs_overlay::ProfileConfig::default(),
        OwnerConfig::default(),
    )
    .unwrap();
    f(&remote(), &owner);
    drop(owner);
    std::fs::remove_dir_all(dir).unwrap();
}
#[test]
fn restored_old_binding_merges_head_moved_while_down() {
    with_owner("moved", |remote, owner| {
        let ws = bind(remote, owner, 3, Some("key"));
        file(&ws, &["target", "old.class"], Some(b"private"));
        ws.commit_captured(&CommitOptions::default()).unwrap();
        let original = ws.snapshot().unwrap();
        ws.close().unwrap();
        drop(ws);
        server(remote, &[Write("src/A.java", b"server-new")]);
        let next = bind(remote, owner, 4, Some("key"));
        assert_eq!(next.snapshot().unwrap(), original);
        next.commit_captured(&CommitOptions::default()).unwrap();
        assert_eq!(file(&next, &["src", "A.java"], None), b"server-new");
        assert_eq!(file(&next, &["target", "old.class"], None), b"private");
        assert!(has(
            &remote.mem().files(remote.root()),
            "target/old.class",
            "old"
        ));
        next.close().unwrap();
    });
}
#[test]
fn pending_server_rule_flip_survives_and_next_noop_publishes() {
    with_owner("seeds", |remote, owner| {
        let ws = bind(remote, owner, 3, Some("key"));
        file(&ws, &["target", "old.class"], Some(b"private"));
        ws.commit_captured(&CommitOptions::default()).unwrap();
        server(
            remote,
            &[Write(".gitignore", b"node_modules/\nbuild/\nout/\n*.log\n")],
        );
        ws.commit_captured(&CommitOptions::default()).unwrap();
        assert!(!remote.0.lock().unwrap().records["key"].seeds.is_empty());
        assert!(has(
            &remote.mem().files(remote.root()),
            "target/old.class",
            "old"
        ));
        ws.close().unwrap();
        drop(ws);
        let next = bind(remote, owner, 4, Some("key"));
        next.commit_captured(&CommitOptions::default()).unwrap();
        assert!(has(
            &remote.mem().files(remote.root()),
            "target/old.class",
            "private"
        ));
        assert!(remote.0.lock().unwrap().records["key"].seeds.is_empty());
        next.close().unwrap();
    });
}
#[test]
fn same_key_last_commit_replaces_root_snapshot_and_seeds_together() {
    with_owner("last-writer", |remote, owner| {
        let first = bind(remote, owner, 3, Some("key"));
        let last = bind(remote, owner, 4, Some("key"));
        file(&first, &["target", "old.class"], Some(b"first-private"));
        first.commit_captured(&CommitOptions::default()).unwrap();
        server(
            remote,
            &[Write(".gitignore", b"node_modules/\nbuild/\nout/\n*.log\n")],
        );
        file(&last, &["target", "old.class"], Some(b"last-private"));
        last.commit_captured(&CommitOptions::default()).unwrap();
        let record = remote.0.lock().unwrap().records["key"].clone();
        assert_eq!(
            record.local,
            last.operation()
                .unwrap()
                .workspace()
                .base()
                .unwrap()
                .identity()
                .0
        );
        assert_eq!(record.binding, last.snapshot().unwrap());
        assert!(!record.seeds.is_empty());
        first.close().unwrap();
        last.close().unwrap();
        drop(first);
        drop(last);
        server(remote, &[Write("src/A.java", b"server-later")]);
        let incarnation =
            std::env::temp_dir().join(format!("cxi-shared-key-restart-{}", std::process::id()));
        std::fs::create_dir(&incarnation).unwrap();
        let restarted = Owner::start(
            &incarnation.join("template.sqlite"),
            layerfs_overlay::ProfileConfig::default(),
            OwnerConfig::default(),
        )
        .unwrap();
        let next = bind(remote, &restarted, 5, Some("key"));
        assert_eq!(next.snapshot().unwrap(), record.binding);
        assert_eq!(
            next.operation()
                .unwrap()
                .workspace()
                .base()
                .unwrap()
                .identity()
                .0,
            record.local
        );
        next.commit_captured(&CommitOptions::default()).unwrap();
        assert_eq!(file(&next, &["target", "old.class"], None), b"last-private");
        assert_eq!(file(&next, &["src", "A.java"], None), b"server-later");
        assert!(has(
            &remote.mem().files(remote.root()),
            "target/old.class",
            "last-private"
        ));
        next.close().unwrap();
        drop(next);
        drop(restarted);
        std::fs::remove_dir_all(incarnation).unwrap();
    });
}
#[test]
fn absent_key_and_ignore_off_do_not_restore_or_save() {
    with_owner("opt-in", |remote, owner| {
        let ws = bind(remote, owner, 3, None);
        file(&ws, &["target", "old.class"], Some(b"private"));
        ws.commit_captured(&CommitOptions::default()).unwrap();
        assert!(remote.0.lock().unwrap().records.is_empty());
        ws.close().unwrap();
        drop(ws);
        let next = bind(remote, owner, 4, None);
        assert_eq!(file(&next, &["target", "old.class"], None), b"old");
        next.close().unwrap();
        let branch = remote.0.lock().unwrap().snapshot.branch.id;
        let off = WorkspaceBackend::remote(Arc::new(remote.clone()), 1 << 20, false)
            .bind_restore(
                owner.client(),
                BindRequest {
                    branch,
                    workspace: WorkspaceId::from_authority([5; 32]).unwrap(),
                },
                Some("key".into()),
            )
            .unwrap()
            .workspace;
        file(&off, &["target", "old.class"], Some(b"public"));
        off.commit_captured(&CommitOptions::default()).unwrap();
        assert!(remote.0.lock().unwrap().records.is_empty());
        assert!(has(
            &remote.mem().files(remote.root()),
            "target/old.class",
            "public"
        ));
        off.close().unwrap();
    });
}

use super::*;

#[test]
fn unreadable_index_withholds_tracked_ignored_edits_until_readable() {
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    ws.commit(
        &[
            Write(".git/index", b"split or malformed"),
            Write("build/keep.txt", b"new kept bytes"),
        ],
        &[],
    );
    assert!(ws.state.last.unwrap().unreadable_index);
    assert!(has(&mem.files(ws.published), "build/keep.txt", "keep v1"));
    assert!(has(
        &mem.files(ws.local()),
        "build/keep.txt",
        "new kept bytes"
    ));
    ws.commit(&[Write(".git/index", &index(TRACKED))], &[]);
    assert!(has(
        &mem.files(ws.published),
        "build/keep.txt",
        "new kept bytes"
    ));
}

#[test]
fn server_delete_prunes_two_levels_but_preserves_local_only_file() {
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    ws.commit(
        &[
            Write("logs/deep/kept", b"tracked"),
            Write("logs/deep/private.log", b"local"),
        ],
        &[],
    );
    ws.commit(&[], &[Remove("logs")]);
    let local = mem.files(ws.local());
    assert!(has(&local, "logs/deep/private.log", "local"));
    assert!(!local.contains_key("logs/deep/kept"));
    ws.commit(&[], &[]);
    assert!(has(
        &mem.files(ws.local()),
        "logs/deep/private.log",
        "local"
    ));
}

#[test]
fn server_rebind_prunes_old_directory_with_local_only_names() {
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    ws.commit(
        &[
            Write("logs/kept", b"tracked"),
            Write("logs/private.log", b"local"),
        ],
        &[],
    );
    ws.commit(&[], &[Remove("logs"), Write("logs", b"replacement")]);
    let local = mem.files(ws.local());
    assert!(has(&local, "logs/private.log", "local"));
    assert!(!local.contains_key("logs/kept"));
}

#[test]
fn server_move_carries_local_only_descendants_without_pruning() {
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    ws.commit(
        &[
            Write("logs/kept", b"tracked"),
            Write("logs/private.log", b"local"),
        ],
        &[],
    );
    ws.commit(&[], &[Move("logs", "moved")]);
    let local = mem.files(ws.local());
    assert!(has(&local, "moved/private.log", "local"));
    assert!(has(&local, "moved/kept", "tracked"));
    assert!(!local.contains_key("logs/"));
}

#[test]
fn server_nested_rules_exclude_and_index_flip_on_next_noop_commit() {
    for variant in 0..4 {
        let mem = Mem::default();
        let mut ws = Workspace::new(&mem);
        ws.commit(
            &[
                Write("logs/keep.log", b"local"),
                Write("target/private", b"target"),
                Write(".git/info/exclude", b"private\n"),
                Write("private", b"secret"),
            ],
            &[],
        );
        let index = index(&[
            ".gitignore",
            "build/keep.txt",
            "src/A.java",
            "target/private",
        ]);
        let (server, path, bytes) = match variant {
            0 => (
                Write("logs/.gitignore", b"!keep.log\n"),
                "logs/keep.log",
                "local",
            ),
            1 => (Remove(".git/info/exclude"), "private", "secret"),
            2 => (Write(".git/index", &index), "target/private", "target"),
            _ => (Remove(".git/info"), "private", "secret"),
        };
        ws.commit(&[], &[server]);
        ws.commit(&[], &[]);
        assert!(
            has(&mem.files(ws.published), path, bytes),
            "variant={variant}"
        );
    }
}

#[test]
fn missing_hints_for_1000_rewrites_list_probe_directories_once() {
    struct Counting<'a> {
        mem: &'a Mem,
        probes: BTreeSet<ObjectId>,
        reads: Cell<usize>,
    }
    impl AuthenticatedObjects for Counting<'_> {
        fn read_canonical_batch(&self, ids: &[ObjectId]) -> ContentResult<Vec<Vec<u8>>> {
            self.reads
                .set(self.reads.get() + ids.iter().filter(|id| self.probes.contains(id)).count());
            self.mem.read_canonical_batch(ids)
        }
    }
    let mem = Mem::default();
    let paths: Vec<_> = (0..1000).map(|n| format!("target/f{n:04}")).collect();
    let probes: Vec<_> = (0..16).map(|n| format!("a{n:02}/probe")).collect();
    let mut ops: Vec<_> = paths.iter().map(|p| Write(p, b"old")).collect();
    ops.extend(probes.iter().map(|p| Write(p, b"probe")));
    let base = mem.edit(Some(warm(&mem)), &ops);
    let built = mem.edit(
        Some(base),
        &paths
            .iter()
            .map(|p| Write(p, b"private"))
            .collect::<Vec<_>>(),
    );
    let tree = TreeTable::open(&mem, built).unwrap();
    // These directory roots are never needed by name classification or value
    // comparison: each canonical read here is a fallback traversal listing.
    let ids = (0..16)
        .map(|n| {
            let serial = tree
                .lookup(&mem, ROOT, &name(&format!("a{n:02}")))
                .unwrap()
                .unwrap();
            tree.value(&mem, serial).unwrap().unwrap().content_root
        })
        .collect();
    let reader = Counting {
        mem: &mem,
        probes: ids,
        reads: Cell::new(0),
    };
    let mut state = IgnoreState::default();
    let projected = state
        .project(
            &reader,
            &mut Sink(&mem),
            &PathHints::default(),
            [base, base, built],
        )
        .unwrap();
    eprintln!(
        "PLACEMENT_PROBE_READS={} files=1000 probe_directories=16",
        reader.reads.get()
    );
    assert!(
        reader.reads.get() <= 16,
        "probe listings={}, expected at most one walk",
        reader.reads.get()
    );
    assert_eq!(mem.files(projected), mem.files(base));
}

#[test]
fn deleted_nested_rule_reconciles_a_retained_directory_absent_from_q() {
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    ws.commit(
        &[
            Write("local/.gitignore", b"secret\n"),
            Write("local/secret", b"local only"),
        ],
        &[],
    );
    ws.commit(&[], &[Remove("local")]);
    assert!(has(&mem.files(ws.local()), "local/secret", "local only"));
    ws.commit(&[], &[]);
    assert!(has(&mem.files(ws.published), "local/secret", "local only"));
}

#[test]
fn kept_write_below_pruned_directory_reaches_next_publication() {
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    ws.commit(
        &[
            Write("logs/deep/kept", b"tracked"),
            Write("logs/deep/private.log", b"private"),
        ],
        &[],
    );
    ws.commit(&[], &[Remove("logs")]);
    ws.commit(&[Write("logs/deep/next", b"next")], &[]);
    assert!(has(&mem.files(ws.published), "logs/deep/next", "next"));
}

#[test]
fn pending_flips_survive_projection_failure_and_unacknowledged_publish() {
    struct Reject;
    impl FinalizedConsumer for Reject {
        fn accept(&mut self, _: FinalizedObject) -> ContentResult<()> {
            Err(ContentError::OutputRejected)
        }
    }
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    ws.commit(&[Write("target/private", b"private")], &[]);
    ws.commit(
        &[],
        &[Write(".gitignore", b"node_modules/\nbuild/\nout/\n*.log\n")],
    );
    let roots = [ws.published, ws.local(), ws.local()];
    assert!(ws
        .state
        .project(&mem, &mut Reject, &ws.hints, roots)
        .is_err());
    for _ in 0..2 {
        // No publication acknowledgement: neither projection consumes seeds.
        let root = ws
            .state
            .project(&mem, &mut Sink(&mem), &ws.hints, roots)
            .unwrap();
        assert!(has(&mem.files(root), "target/private", "private"));
    }
    ws.commit(&[], &[]);
    assert!(has(&mem.files(ws.published), "target/private", "private"));
}

#[test]
fn split_index_uses_patterns_and_reports_unreadable() {
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    let mut split = index(TRACKED);
    split.truncate(split.len() - 20);
    split.extend_from_slice(b"link");
    split.extend_from_slice(&0u32.to_be_bytes());
    split.extend_from_slice(&[0; 20]);
    ws.commit(
        &[
            Write(".git/index", &split),
            Write("build/keep.txt", b"withheld"),
        ],
        &[],
    );
    assert!(ws.state.last.unwrap().unreadable_index);
    assert!(has(&mem.files(ws.published), "build/keep.txt", "keep v1"));
    assert!(has(&mem.files(ws.local()), "build/keep.txt", "withheld"));
}

#[test]
fn hardlinks_beyond_hint_capacity_are_all_classified() {
    let mem = Mem::default();
    let mut ws = Workspace::new(&mem);
    let paths: Vec<_> = (0..12).map(|n| format!("target/link{n}")).collect();
    ws.published = mem.edit(
        Some(ws.published),
        &paths
            .iter()
            .map(|p| Link("target/old.class", p))
            .collect::<Vec<_>>(),
    );
    let tree = TreeTable::open(&mem, ws.published).unwrap();
    let parent = tree.lookup(&mem, ROOT, &name("target")).unwrap().unwrap();
    let file = tree
        .lookup(&mem, parent, &name("old.class"))
        .unwrap()
        .unwrap();
    for path in &paths {
        ws.hints
            .record(file, parent, &name(path.split('/').next_back().unwrap()));
    }
    // Include stale advisory evidence; validation must not treat it as a kept alias.
    ws.hints.record(file, ROOT, &name("nonexistent"));
    ws.commit(&[Write("target/old.class", b"private")], &[]);
    assert!(has(&mem.files(ws.published), "target/old.class", "old"));
    assert_eq!(ws.state.last.unwrap().unplaced, 0);
}

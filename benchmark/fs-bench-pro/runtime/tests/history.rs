//! Independent whole-history proof accepts exact public roots and rejects custody corruption.
#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
mod namespace;
use layerfs_api::{InitRequest, ProjectApi};
use layerfs_content::{
    filesystem::{
        attributes::{
            codec::AttributeEntry, keys::AttributeKey, portable::PortableMetadata,
            value::emit_value,
        },
        build_filesystem, DirectoryUpdate, FilesystemInput, FilesystemObjects, FilesystemResources,
        InodeScope, InodeUpdate, PathName,
    },
    object::inode_leaf::{InodeKind, InodeValue},
    AuthenticatedObjects, ContentError, ContentResult, FinalizedConsumer, FinalizedObject,
    ObjectId,
};
use layerfs_history::{
    BranchId, CommitOutcome, CommitRequest, HistoryCatalog, HistoryCatalogConfig, HistoryName,
    LayerStackId,
};
use layerfs_persistence::{Handles, PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::{Storage, StoragePolicy};
use layerfs_telemetry::timer::Timing;
use namespace::reference;
use std::{
    collections::BTreeMap,
    fs,
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Clone, Default)]
struct Bag {
    bytes: BTreeMap<ObjectId, Vec<u8>>,
    objects: Vec<FinalizedObject>,
}
impl FinalizedConsumer for Bag {
    fn accept(&mut self, object: FinalizedObject) -> ContentResult<()> {
        self.bytes.insert(object.id(), object.canonical().to_vec());
        self.objects.push(object);
        Ok(())
    }
}
impl AuthenticatedObjects for Bag {
    fn read_canonical_batch(&self, ids: &[ObjectId]) -> ContentResult<Vec<Vec<u8>>> {
        ids.iter()
            .map(|id| {
                self.bytes
                    .get(id)
                    .cloned()
                    .ok_or(ContentError::MissingObject)
            })
            .collect()
    }
}
fn metadata(bag: &mut Bag, kind: InodeKind, mode: u32) -> ObjectId {
    metadata_at(bag, kind, mode, 1000000000)
}
fn metadata_at(bag: &mut Bag, kind: InodeKind, mode: u32, seconds: i64) -> ObjectId {
    let reader = bag.clone();
    let mut objects = FilesystemObjects::new(&reader, bag);
    let portable = PortableMetadata {
        mode,
        mtime_seconds: seconds,
        mtime_nanoseconds: 0,
    };
    let mode = emit_value(&mut objects, &portable.mode_bytes(kind).unwrap()).unwrap();
    let mtime = emit_value(&mut objects, &portable.mtime_bytes().unwrap()).unwrap();
    layerfs_content::filesystem::attributes::build::build_attribute_tree(
        &mut objects,
        vec![
            Ok(AttributeEntry {
                key: AttributeKey::new("portable".into(), b"mode".to_vec()).unwrap(),
                value_root: mode,
            }),
            Ok(AttributeEntry {
                key: AttributeKey::new("portable".into(), b"mtime".to_vec()).unwrap(),
                value_root: mtime,
            }),
        ]
        .into_iter(),
    )
    .unwrap()
    .0
}
fn entries(step: u8) -> Vec<reference::workspace_common::Entry> {
    use reference::workspace_common::{Content, Entry};
    let mut entries = vec![Entry::directory(".")];
    entries[0].mode = 0o755;
    entries[0].mtime_seconds = 1000000000;
    for index in 0..10 {
        let mut file = Entry::file(
            format!("source{index:02}.ts"),
            Content::Literal(vec![index, if index == 9 { step } else { 0 }, b'\n']),
        );
        file.mode = 0o644;
        file.mtime_seconds = 1000000000;
        entries.push(file);
    }
    entries
}
fn constructed(scope: InodeScope, step: u8) -> (ObjectId, Bag) {
    let policy = layerfs_content::ConstructionPolicy::frozen_default();
    let mut bag = Bag::default();
    let file_metadata = metadata(&mut bag, InodeKind::RegularFile, 0o644);
    let directory_metadata = metadata(&mut bag, InodeKind::Directory, 0o755);
    let mut inodes = vec![InodeUpdate {
        serial: 1,
        value: InodeValue {
            kind: InodeKind::Directory,
            namespace_ref_count: 0,
            content_root: ObjectId::for_bytes(b"replaced directory"),
            metadata_root: directory_metadata,
        },
    }];
    for index in 0..10u8 {
        let bytes = [index, if index == 9 { step } else { 0 }, b'\n'];
        let root = Timing::disabled("external.history.bytes", |timer| {
            layerfs_content::construct_bytes(
                policy,
                &policy.capacities(),
                &bytes,
                &mut bag,
                timer.child("file"),
            )
        })
        .0
        .unwrap()
        .root;
        inodes.push(InodeUpdate {
            serial: u64::from(index) + 2,
            value: InodeValue {
                kind: InodeKind::RegularFile,
                namespace_ref_count: 0,
                content_root: root,
                metadata_root: file_metadata,
            },
        });
    }
    let dirs = [DirectoryUpdate {
        parent: 1,
        changes: (0..10u64)
            .map(|i| {
                (
                    PathName::new(&format!("source{i:02}.ts")).unwrap(),
                    Some(i + 2),
                )
            })
            .collect(),
    }];
    let serials = (1..=11).collect::<Vec<_>>();
    let input = FilesystemInput {
        base: None,
        scope,
        root_serial: 1,
        directories: &dirs,
        inodes: &inodes,
        new_inodes: &serials,
        resources: FilesystemResources::default(),
    };
    let reader = bag.clone();
    let mut objects = FilesystemObjects::new(&reader, &mut bag);
    let root = build_filesystem(&mut objects, &input, None).unwrap().root;
    (root.0, bag)
}
fn proof(home: &Path, label: &str, selected: Option<usize>) -> bool {
    proof_case(home, label, selected, "small-file-delta-10x30-v1", 10)
}
fn proof_case(home: &Path, label: &str, selected: Option<usize>, case: &str, seconds: u64) -> bool {
    let mut command = Command::new(env!("CARGO_BIN_EXE_layerfs-r7-runtime"));
    command
        .args([
            "verify-history",
            "--socket",
            "/unused",
            "--volume",
            "unused",
            "--daemon",
            "/unused",
            "--case",
            case,
            "--uid",
            "1",
            "--gid",
            "1",
        ])
        .arg("--manifest")
        .arg(home.join("manifest"))
        .arg("--sealed")
        .arg(home.join("store.sqlite"))
        .arg("--history-file")
        .arg(home.join("history.tsv"))
        .arg("--receipt")
        .arg(home.join(format!("{label}.jsonl")))
        .stdout(Stdio::from(
            fs::File::create(home.join(format!("{label}.stdout"))).unwrap(),
        ))
        .stderr(Stdio::from(
            fs::File::create(home.join(format!("{label}.stderr"))).unwrap(),
        ))
        .env("LAYERFS_CONSTRUCTION_WORKERS", "1");
    if let Some(step) = selected {
        command.arg("--history-step").arg(step.to_string());
    }
    let mut child = command.spawn().unwrap();
    let stop = Instant::now() + Duration::from_secs(seconds);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status.success();
        }
        if Instant::now() >= stop {
            child.kill().unwrap();
            let end = Instant::now() + Duration::from_secs(1);
            while Instant::now() < end {
                if child.try_wait().unwrap().is_some() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(5));
            }
            panic!("history proof exceeded bounded external deadline");
        }
        std::thread::sleep(Duration::from_millis(5));
    }
}

fn snapshot_constructed(scope: InodeScope, step: usize) -> (ObjectId, Bag) {
    let case =
        reference::workspace_registry::resolve("local-snapshot-create-25000-onebyte-v1").unwrap();
    let entries = reference::workspace_registry::expected(&case, 1, step).unwrap();
    let mut bag = Bag::default();
    let file_metadata = metadata_at(&mut bag, InodeKind::RegularFile, 0o644, 1700000000);
    let directory_metadata = metadata_at(&mut bag, InodeKind::Directory, 0o755, 1700000000);
    let mut inodes = vec![InodeUpdate {
        serial: 1,
        value: InodeValue {
            kind: InodeKind::Directory,
            namespace_ref_count: 0,
            content_root: ObjectId::for_bytes(b"replaced directory"),
            metadata_root: directory_metadata,
        },
    }];
    let policy = layerfs_content::ConstructionPolicy::frozen_default();
    let mut changes = Vec::new();
    for (index, entry) in entries.iter().skip(1).enumerate() {
        let reference::workspace_common::EntryKind::File(
            reference::workspace_common::Content::Literal(bytes),
        ) = &entry.kind
        else {
            panic!("original snapshot one-byte file required")
        };
        let root = Timing::disabled("external.snapshot.bytes", |timer| {
            layerfs_content::construct_bytes(
                policy,
                &policy.capacities(),
                bytes,
                &mut bag,
                timer.child("file"),
            )
        })
        .0
        .unwrap()
        .root;
        let serial = index as u64 + 2;
        changes.push((PathName::new(&entry.path).unwrap(), Some(serial)));
        inodes.push(InodeUpdate {
            serial,
            value: InodeValue {
                kind: InodeKind::RegularFile,
                namespace_ref_count: 0,
                content_root: root,
                metadata_root: file_metadata,
            },
        });
    }
    let dirs = [DirectoryUpdate { parent: 1, changes }];
    let serials = (1..=25001).collect::<Vec<_>>();
    let input = FilesystemInput {
        base: None,
        scope,
        root_serial: 1,
        directories: &dirs,
        inodes: &inodes,
        new_inodes: &serials,
        resources: FilesystemResources::default(),
    };
    let reader = bag.clone();
    let mut objects = FilesystemObjects::new(&reader, &mut bag);
    let root = build_filesystem(&mut objects, &input, None).unwrap().root;
    (root.0, bag)
}

#[test]
fn complete_snapshot_history_all_original_states_accept_restored_root_and_reject_old_bytes() {
    let case =
        reference::workspace_registry::resolve("local-snapshot-create-25000-onebyte-v1").unwrap();
    let home = std::env::temp_dir().join(format!("fsb-snapshot-history-{}", std::process::id()));
    fs::create_dir(&home).unwrap();
    reference::workspace_common::create_fixture(
        &home.join("source"),
        &reference::workspace_registry::fixture(&case, 1).unwrap(),
    )
    .unwrap();
    let project = Timing::disabled("external.snapshot.init", |timer| {
        ProjectApi::new().init(
            InitRequest {
                source: home.join("source"),
                store: PersistenceConfig::sqlite(home.join("store.sqlite"))
                    .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
                locator: "/layerfs-store/global/store.sqlite".into(),
                policy: StoragePolicy::frozen_default(),
                catalog: HistoryCatalogConfig {
                    binding_key: b"external-snapshot".to_vec(),
                    cursor_key: [71; 32],
                    incarnation: 1,
                },
                stack: LayerStackId::from_authority([72; 16]),
                stack_name: HistoryName::new("snapshot").unwrap(),
                branch: BranchId::from_authority([73; 16]),
                branch_name: HistoryName::new("main").unwrap(),
                scope_seed: [74; 32],
                deadline: Instant::now() + Duration::from_secs(5),
            },
            timer,
        )
    })
    .0
    .unwrap();
    fs::write(home.join("manifest"), project.manifest.encode().unwrap()).unwrap();
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(home.join("store.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &project.manifest.binding,
        project.manifest.cursor_key,
    )
    .unwrap();
    let storage = Storage::new(handles.storage.clone()).unwrap();
    let reader = storage.reader().unwrap();
    let initial = ObjectId::from_bytes(&project.manifest.root).unwrap();
    let scope = layerfs_content::filesystem::root::FilesystemRoot::decode(
        &reader.read_canonical(initial).unwrap(),
    )
    .unwrap()
    .scope();
    drop(reader);
    let state = home.join("state-0.tsv");
    fs::write(
        &state,
        reference::workspace_common::manifest(
            &reference::workspace_registry::expected(&case, 1, 0).unwrap(),
        )
        .unwrap(),
    )
    .unwrap();
    let mut transcript = format!(
        "0\t-\t-\t{}\t{}\n",
        hex(&initial.to_bytes()),
        state.display()
    );
    let mut published = Vec::new();
    for step in 1..=3 {
        let branch = handles
            .history
            .branch_snapshot(BranchId::from_bytes(project.manifest.branch).unwrap())
            .unwrap()
            .unwrap();
        let (root, bag) = snapshot_constructed(scope, step);
        let save = storage.begin_save().unwrap();
        for object in bag.objects {
            save.accept(object).unwrap();
        }
        save.finish().unwrap();
        let outcome = handles
            .history
            .commit_branch(&CommitRequest {
                branch: branch.branch.id,
                expected_head: branch.branch.head_commit,
                expected_base: branch.branch.base_layer,
                expected_root: branch.effective_root,
                candidate_root: root,
                profile: branch.profile,
                scope: branch.scope,
                second_parent: None,
                meta: layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
                force: false,
            })
            .unwrap();
        let CommitOutcome::Committed { record, .. } = outcome else {
            panic!("distinct state must Commit")
        };
        let state = home.join(format!("state-{step}.tsv"));
        fs::write(
            &state,
            reference::workspace_common::manifest(
                &reference::workspace_registry::expected(&case, 1, step).unwrap(),
            )
            .unwrap(),
        )
        .unwrap();
        transcript += &format!(
            "{step}\t{}\t{}\t{}\t{}\n",
            hex(&record.id.to_bytes()),
            record
                .parent
                .map(|id| hex(&id.to_bytes()))
                .unwrap_or_else(|| "-".into()),
            hex(&root.to_bytes()),
            state.display()
        );
        published.push(root);
    }
    assert_eq!(
        published[0], published[2],
        "restored canonical root can repeat"
    );
    drop(storage);
    handles.seal().unwrap();
    fs::write(home.join("history.tsv"), &transcript).unwrap();
    assert!(proof_case(&home, "snapshot-complete", None, &case.id, 30));
    let body = fs::read_to_string(home.join("snapshot-complete.jsonl")).unwrap();
    assert!(body.contains("\"roots\":4"));
    assert!(body.contains("\"verified_bytes\":75000"));
    assert!(body.contains("\"paths\":75004"));
    fs::write(
        home.join("state-2.tsv"),
        reference::workspace_common::manifest(
            &reference::workspace_registry::expected(&case, 1, 1).unwrap(),
        )
        .unwrap(),
    )
    .unwrap();
    assert!(!proof_case(
        &home,
        "snapshot-wrong-old",
        Some(2),
        &case.id,
        30
    ));
    assert!(fs::read_to_string(home.join("snapshot-wrong-old.stderr"))
        .unwrap()
        .contains("differs from original complete state"));
    fs::remove_dir_all(home).unwrap();
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
#[test]
fn complete_history_uses_actual_31_roots_and_rejects_wrong_parent_and_old_root_bytes() {
    let home = std::env::temp_dir().join(format!("fsb-whole-history-{}", std::process::id()));
    fs::create_dir(&home).unwrap();
    reference::workspace_common::create_fixture(&home.join("source"), &entries(0)).unwrap();
    let project = Timing::disabled("external.history.init", |timer| {
        ProjectApi::new().init(
            InitRequest {
                source: home.join("source"),
                store: PersistenceConfig::sqlite(home.join("store.sqlite"))
                    .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
                locator: "/layerfs-store/global/store.sqlite".into(),
                policy: StoragePolicy::frozen_default(),
                catalog: HistoryCatalogConfig {
                    binding_key: b"external-history".to_vec(),
                    cursor_key: [31; 32],
                    incarnation: 1,
                },
                stack: LayerStackId::from_authority([41; 16]),
                stack_name: HistoryName::new("history").unwrap(),
                branch: BranchId::from_authority([42; 16]),
                branch_name: HistoryName::new("main").unwrap(),
                scope_seed: [43; 32],
                deadline: Instant::now() + Duration::from_secs(5),
            },
            timer,
        )
    })
    .0
    .unwrap();
    fs::write(home.join("manifest"), project.manifest.encode().unwrap()).unwrap();
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(home.join("store.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &project.manifest.binding,
        project.manifest.cursor_key,
    )
    .unwrap();
    let storage = Storage::new(handles.storage.clone()).unwrap();
    let reader = storage.reader().unwrap();
    let initial = ObjectId::from_bytes(&project.manifest.root).unwrap();
    let scope = layerfs_content::filesystem::root::FilesystemRoot::decode(
        &reader.read_canonical(initial).unwrap(),
    )
    .unwrap()
    .scope();
    drop(reader);
    let first = home.join("state-0.tsv");
    fs::write(
        &first,
        reference::workspace_common::manifest(&entries(0)).unwrap(),
    )
    .unwrap();
    let mut transcript = format!(
        "0\t-\t-\t{}\t{}\n",
        hex(&project.manifest.root),
        first.display()
    );
    for step in 1..=30u8 {
        let branch = handles
            .history
            .branch_snapshot(BranchId::from_bytes(project.manifest.branch).unwrap())
            .unwrap()
            .unwrap();
        let (root, bag) = constructed(scope, step);
        let save = storage.begin_save().unwrap();
        for object in bag.objects {
            save.accept(object).unwrap();
        }
        save.finish().unwrap();
        let outcome = handles
            .history
            .commit_branch(&CommitRequest {
                branch: branch.branch.id,
                expected_head: branch.branch.head_commit,
                expected_base: branch.branch.base_layer,
                expected_root: branch.effective_root,
                candidate_root: root,
                profile: branch.profile,
                scope: branch.scope,
                second_parent: None,
                meta: layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
                force: false,
            })
            .unwrap();
        let CommitOutcome::Committed { record, .. } = outcome else {
            panic!("external changed candidate must Commit")
        };
        let state = home.join(format!("state-{step}.tsv"));
        fs::write(
            &state,
            reference::workspace_common::manifest(&entries(step)).unwrap(),
        )
        .unwrap();
        transcript += &format!(
            "{step}\t{}\t{}\t{}\t{}\n",
            hex(&record.id.to_bytes()),
            record
                .parent
                .map(|id| hex(&id.to_bytes()))
                .unwrap_or_else(|| "-".into()),
            hex(&root.to_bytes()),
            state.display()
        );
    }
    drop(storage);
    handles.seal().unwrap();
    fs::write(home.join("history.tsv"), &transcript).unwrap();
    assert!(proof(&home, "complete", None));
    let text = fs::read_to_string(home.join("complete.jsonl")).unwrap();
    assert_eq!(
        text.matches("\"event\":\"history_root_verified\"").count(),
        31
    );
    assert!(text.contains("\"roots\":31"));
    assert!(proof(&home, "selected-old", Some(15)));
    let selected = fs::read_to_string(home.join("selected-old.jsonl")).unwrap();
    assert_eq!(
        selected
            .matches("\"event\":\"history_root_verified\"")
            .count(),
        1
    );
    assert!(selected.contains("\"roots\":1"));
    assert!(selected.contains("\"commits\":30"));
    let mut lines = transcript.lines().map(str::to_owned).collect::<Vec<_>>();
    let mut fields = lines[16].split('\t').map(str::to_owned).collect::<Vec<_>>();
    fields[2] = "-".into();
    lines[16] = fields.join("\t");
    fs::write(home.join("history.tsv"), lines.join("\n") + "\n").unwrap();
    assert!(!proof(&home, "wrong-parent", Some(15)));
    assert!(fs::read_to_string(home.join("wrong-parent.stderr"))
        .unwrap()
        .contains("ancestry/stack/base differs"));
    fs::write(home.join("history.tsv"), &transcript).unwrap();
    fs::write(
        home.join("state-15.tsv"),
        reference::workspace_common::manifest(&entries(14)).unwrap(),
    )
    .unwrap();
    assert!(!proof(&home, "wrong-old-bytes", Some(15)));
    assert!(fs::read_to_string(home.join("wrong-old-bytes.stderr"))
        .unwrap()
        .contains("persisted custody digest differs"));
    fs::remove_dir_all(home).unwrap();
}

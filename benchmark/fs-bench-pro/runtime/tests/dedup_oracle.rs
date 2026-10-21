//! External current typed dedup/import oracle qualification, never a benchmark sample.
//! Synthetic public objects and one public Disposable Init supply bounded proof fixtures.
#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
pub(crate) mod namespace;
pub(crate) mod project {
    pub(crate) use crate::namespace;
}
pub(crate) use namespace::reference;
#[allow(dead_code)]
#[path = "../../engine/recipes/dedup_input.rs"]
pub(crate) mod dedup_input;
pub(crate) type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[allow(dead_code)]
#[path = "../src/args.rs"]
pub(crate) mod args;
#[allow(dead_code)]
#[path = "../../engine/recipes/edit_model.rs"]
pub(crate) mod edit_model;
#[allow(dead_code)]
#[path = "../src/edit_oracle.rs"]
pub(crate) mod edit_oracle;
#[allow(dead_code)]
#[path = "../src/events.rs"]
pub(crate) mod events;
#[allow(dead_code)]
#[path = "../src/workspace_oracle.rs"]
pub(crate) mod workspace_oracle;

use layerfs_api::{InitRequest, ProjectApi};
use layerfs_content::{
    file::{mapping, FileView},
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
use reference::workspace_common::{Entry, EntryKind};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

pub(crate) fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[derive(Default, Clone)]
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
impl Bag {
    fn put(&mut self, bytes: Vec<u8>) -> ObjectId {
        let id = ObjectId::for_bytes(&bytes);
        self.bytes.insert(id, bytes);
        id
    }
}

fn metadata(bag: &mut Bag, kind: InodeKind, entry: &Entry) -> ObjectId {
    let reader = bag.clone();
    let mut objects = FilesystemObjects::new(&reader, bag);
    let portable = PortableMetadata {
        mode: entry.mode,
        mtime_seconds: entry.mtime_seconds,
        mtime_nanoseconds: entry.mtime_nanoseconds,
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

fn constructed(scope: InodeScope, entries: &[Entry]) -> (ObjectId, Bag) {
    let mut serials = BTreeMap::new();
    for entry in entries {
        if !matches!(entry.kind, EntryKind::Hardlink(_)) {
            serials.insert(entry.path.clone(), serials.len() as u64 + 1);
        }
    }
    constructed_with_serials(scope, entries, serials)
}

fn constructed_with_serials(
    scope: InodeScope,
    entries: &[Entry],
    serials: BTreeMap<String, u64>,
) -> (ObjectId, Bag) {
    let mut bag = Bag::default();
    let mut inodes = Vec::new();
    for entry in entries {
        if matches!(entry.kind, EntryKind::Hardlink(_)) {
            continue;
        }
        let kind = match entry.kind {
            EntryKind::Directory => InodeKind::Directory,
            EntryKind::File(_) => InodeKind::RegularFile,
            _ => panic!("test file/directory fixture required"),
        };
        let content_root = match &entry.kind {
            EntryKind::File(content) => {
                let mut bytes = Vec::new();
                content.write_to(&mut bytes).unwrap();
                let policy = layerfs_content::ConstructionPolicy::frozen_default();
                Timing::disabled("external.batch4.file", |timer| {
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
                .root
            }
            _ => ObjectId::for_bytes(b"directory replaced by public builder"),
        };
        let metadata_root = metadata(&mut bag, kind, entry);
        inodes.push(InodeUpdate {
            serial: serials[&entry.path],
            value: InodeValue {
                kind,
                content_root,
                metadata_root,
                namespace_ref_count: 0,
            },
        });
    }
    let mut directories = BTreeMap::<u64, Vec<_>>::new();
    for entry in entries {
        if matches!(entry.kind, EntryKind::Directory) {
            directories.insert(serials[&entry.path], Vec::new());
        }
    }
    for entry in entries {
        if entry.path == "." {
            continue;
        }
        let path = Path::new(&entry.path);
        let parent = path.parent().unwrap().to_str().unwrap();
        let parent = if parent.is_empty() { "." } else { parent };
        let serial = match &entry.kind {
            EntryKind::Hardlink(target) => serials[target],
            _ => serials[&entry.path],
        };
        directories.entry(serials[parent]).or_default().push((
            PathName::new(path.file_name().unwrap().to_str().unwrap()).unwrap(),
            Some(serial),
        ));
    }
    let dirs = directories
        .into_iter()
        .map(|(parent, mut changes)| {
            changes.sort_by(|left, right| left.0.cmp(&right.0));
            DirectoryUpdate { parent, changes }
        })
        .collect::<Vec<_>>();
    let mut new = serials.values().copied().collect::<Vec<_>>();
    new.sort_unstable();
    inodes.sort_by_key(|update| update.serial);
    let input = FilesystemInput {
        base: None,
        scope,
        root_serial: serials["."],
        directories: &dirs,
        inodes: &inodes,
        new_inodes: &new,
        resources: FilesystemResources::default(),
    };
    let reader = bag.clone();
    let root = build_filesystem(&mut FilesystemObjects::new(&reader, &mut bag), &input, None)
        .unwrap()
        .root
        .0;
    (root, bag)
}

fn qualified(case: &str, step: usize) -> (ObjectId, Bag, workspace_oracle::VerifiedTree) {
    let entries = edit_model::entries(case, step).unwrap();
    let (root, bag) = constructed(
        InodeScope::from_object(ObjectId::for_bytes(b"dedup-oracle-scope")),
        &entries,
    );
    let proof = workspace_oracle::verify_tree(&bag, root, &entries, false, None, true).unwrap();
    (root, bag, proof)
}

#[test]
fn dedup_oracle_boundary_current_representation_and_independent_shape_are_separate() {
    let case = "dedup-cdc-boundaries-proof";
    let (_, bag, proof) = qualified(case, 0);
    let files = workspace_oracle::verify_dedup_files(&bag, case, 0, &proof.files).unwrap();
    assert_eq!(files.len(), 60);
    assert_eq!(files.values().filter(|f| f.spans.is_empty()).count(), 6);
    assert_eq!(files.values().filter(|f| f.spans.len() == 1).count(), 54);
    let independent = dedup_input::expected(case, 0).unwrap();
    for (path, chunks) in independent {
        if path.contains("/n32769/") {
            assert!(chunks.len() >= 2);
        }
    }
    for seed in 1..=3 {
        for n in [1, 8191, 8192, 16384, 32768, 32769] {
            let prefix = format!("boundary/s{seed}/n{n}");
            assert_eq!(
                files[&format!("{prefix}/a.dat")].root,
                files[&format!("{prefix}/b.dat")].root
            );
            assert_ne!(
                files[&format!("{prefix}/a.dat")].root,
                files[&format!("{prefix}/changed.dat")].root
            );
        }
    }
}

#[test]
fn dedup_oracle_full_bytes_do_not_substitute_for_exact_independent_chunk_partition() {
    let case = "dedup-cross-file-anchor-1";
    let (_, mut bag, proof) = qualified(case, 0);
    workspace_oracle::verify_dedup_files(&bag, case, 0, &proof.files).unwrap();
    let entries = edit_model::entries(case, 0).unwrap();
    let EntryKind::File(content) = &entries
        .iter()
        .find(|e| e.path == "files/f0000.dat")
        .unwrap()
        .kind
    else {
        panic!()
    };
    let mut bytes = Vec::new();
    content.write_to(&mut bytes).unwrap();
    // A different valid current mapping reconstructs every correct byte but violates the frozen CDC partitions.
    let mut extents = Vec::new();
    for chunk in bytes.chunks(32768) {
        let id = bag.put(mapping::encode_chunk_object(chunk).unwrap());
        extents.push(mapping::ExtentSlice::new(id, 0, chunk.len() as u32).unwrap());
    }
    let count = extents.len() as u64;
    let leaf = bag.put(
        mapping::encode_node(
            &mapping::ExtentNode::Leaf {
                subtree_logical_bytes: bytes.len() as u64,
                extents,
            },
            true,
        )
        .unwrap(),
    );
    let root = bag.put(
        mapping::encode_file_state(mapping::FileState {
            logical_len: bytes.len() as u64,
            extent_count: count,
            tree_level: 0,
            profile_id: mapping::profile_id(),
            mapping_root: leaf,
        })
        .unwrap(),
    );
    let view = Timing::disabled("external.dedup.wrong-partition", |timer| {
        FileView::open(&bag, root, timer.child("open"))
    })
    .0
    .unwrap();
    workspace_oracle::verify_mapping(&bag, &view).unwrap();
    let observed = Timing::disabled("external.dedup.same-bytes", |timer| {
        let mut actual = Vec::new();
        view.read_range(&bag, 0..bytes.len() as u64, &mut actual, timer)
            .unwrap();
        Ok::<_, Box<dyn std::error::Error>>(actual)
    })
    .0
    .unwrap();
    assert_eq!(observed, bytes);
    let mut files = proof.files;
    files.get_mut("files/f0000.dat").unwrap().content_root = root;
    assert!(workspace_oracle::verify_dedup_files(&bag, case, 0, &files)
        .unwrap_err()
        .to_string()
        .contains("ordered payload spans"));
}

#[test]
fn dedup_oracle_reuse_exact_typed_maps_and_semantic_mutations_fail_closed() {
    let case = "dedup-workspace-exact-100";
    let (_, initial_bag, initial) = qualified(case, 0);
    workspace_oracle::verify_dedup_files(&initial_bag, case, 0, &initial.files).unwrap();
    let (_, bag, final_tree) = qualified(case, 1);
    let files = workspace_oracle::verify_dedup_files(&bag, case, 1, &final_tree.files).unwrap();
    assert_eq!(files["base/b0000.dat"].root, files["added/a0000.dat"].root);
    assert_eq!(
        files["base/b0000.dat"].spans,
        files["added/a0000.dat"].spans
    );
    let mut wrong = files.clone();
    wrong.get_mut("added/a0000.dat").unwrap().root = ObjectId::for_bytes(b"different current root");
    assert!(workspace_oracle::require_dedup_storage(case, 1, &wrong).is_err());
    let mut wrong = files.clone();
    wrong.get_mut("added/a0000.dat").unwrap().spans[0].payload =
        ObjectId::for_bytes(b"new regular payload");
    assert!(workspace_oracle::require_dedup_storage(case, 1, &wrong)
        .unwrap_err()
        .to_string()
        .contains("new regular payload"));
    let mut wrong = files.clone();
    wrong.get_mut("added/a0000.dat").unwrap().spans[0].source = 1;
    assert!(workspace_oracle::require_dedup_storage(case, 1, &wrong)
        .unwrap_err()
        .to_string()
        .contains("partial payload span"));
    let mut wrong = files;
    let value = wrong.remove("added/a0000.dat").unwrap();
    wrong.insert("added/wrong.dat".into(), value);
    assert!(workspace_oracle::require_dedup_storage(case, 1, &wrong)
        .unwrap_err()
        .to_string()
        .contains("membership"));
}

#[test]
fn dedup_oracle_unique_cross_and_reuse_internal_disjointness_are_real_guards() {
    let case = "dedup-workspace-unique-100";
    let (_, bag, proof) = qualified(case, 1);
    let files = workspace_oracle::verify_dedup_files(&bag, case, 1, &proof.files).unwrap();
    let mut wrong = files.clone();
    wrong.get_mut("added/a0000.dat").unwrap().spans[0] = files["base/b0000.dat"].spans[0].clone();
    assert!(workspace_oracle::require_dedup_storage(case, 1, &wrong).is_err());
    let mut wrong = files;
    let chunk = wrong["added/a0000.dat"].spans[0].clone();
    wrong.get_mut("added/a0000.dat").unwrap().spans.push(chunk);
    assert!(workspace_oracle::require_dedup_storage(case, 1, &wrong).is_err());
    let case = "dedup-cross-file-unique-100";
    let mut synthetic = BTreeMap::new();
    for i in 0..100 {
        synthetic.insert(
            format!("files/f{i:04}.dat"),
            workspace_oracle::DedupFile {
                root: ObjectId::for_bytes(format!("file-{i}").as_bytes()),
                spans: vec![workspace_oracle::DedupSpan {
                    payload: ObjectId::for_bytes(format!("payload-{i}").as_bytes()),
                    source: 0,
                    len: 8192,
                    payload_len: 8192,
                }],
            },
        );
    }
    workspace_oracle::require_dedup_storage(case, 0, &synthetic).unwrap();
    let duplicate = synthetic["files/f0000.dat"].spans.clone();
    synthetic.get_mut("files/f0009.dat").unwrap().spans = duplicate;
    assert!(workspace_oracle::require_dedup_storage(case, 0, &synthetic).is_err());
}

fn temporary(label: &str) -> PathBuf {
    let home = std::env::temp_dir().join(format!(
        "fsb-b6-dedup-oracle-{label}-{}",
        std::process::id()
    ));
    fs::create_dir(&home).unwrap();
    home
}
fn init(case: &str, label: &str) -> PathBuf {
    let home = temporary(label);
    reference::workspace_common::create_fixture(
        &home.join("source"),
        &edit_model::entries(case, 0).unwrap(),
    )
    .unwrap();
    let project = Timing::disabled("external.dedup.public-init", |timer| {
        ProjectApi::new().init(
            InitRequest {
                source: home.join("source"),
                store: PersistenceConfig::sqlite(home.join("store.sqlite"))
                    .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
                locator: "/layerfs-store/global/store.sqlite".into(),
                policy: StoragePolicy::frozen_default(),
                catalog: HistoryCatalogConfig {
                    binding_key: b"external-b6-dedup-oracle".to_vec(),
                    cursor_key: [21; 32],
                    incarnation: 1,
                },
                stack: LayerStackId::from_authority([22; 16]),
                stack_name: HistoryName::new("proof").unwrap(),
                branch: BranchId::from_authority([23; 16]),
                branch_name: HistoryName::new("main").unwrap(),
                scope_seed: [24; 32],
                deadline: Instant::now() + Duration::from_secs(15),
            },
            timer,
        )
    })
    .0
    .unwrap();
    fs::write(home.join("manifest"), project.manifest.encode().unwrap()).unwrap();
    home
}
fn args(home: &Path, case: &str, label: &str) -> args::Args {
    args::Args {
        mode: "verify-init".into(),
        socket: "/unused".into(),
        image: args::IMAGE.into(),
        volume: "unused".into(),
        executable: "/unused".into(),
        receipt: home.join(format!("{label}.jsonl")),
        manifest: home.join("manifest"),
        installed_manifest: None,
        uid: 1,
        gid: 1,
        source: None,
        sealed: Some(home.join("store.sqlite")),
        init_seconds: 15,
        environment: vec!["LAYERFS_CONSTRUCTION_WORKERS=1".into()],
        observation_scope: [26; 32],
        case: Some(case.into()),
        history_file: None,
        history_step: None,
    }
}

#[test]
fn dedup_oracle_real_public_import_provider_and_exact_gate_are_qualified() {
    let case = "dedup-cross-file-anchor-1";
    let home = init(case, "import");
    let before = fs::read(home.join("store.sqlite")).unwrap();
    let request = args(&home, case, "public-proof");
    let mut events = events::Events::new(&request.receipt).unwrap();
    workspace_oracle::verify_import(&request, &mut events).unwrap();
    drop(events);
    assert_eq!(fs::read(home.join("store.sqlite")).unwrap(), before);
    let body = fs::read_to_string(&request.receipt).unwrap();
    for text in [
        "project_verified",
        "current-public-schema-source-binding-validated",
        "provider_store_unchanged\":1",
        "\"verified_bytes\":1048576",
    ] {
        assert!(body.contains(text), "{text}");
    }
    let wrong = args(&home, "payload-create-1m-compact-v2", "wrong-case");
    let mut events = events::Events::new(&wrong.receipt).unwrap();
    assert!(workspace_oracle::verify_import(&wrong, &mut events).is_err());
    drop(events);
    let request = args(&home, case, "wrong-binding");
    let original_manifest = fs::read(&request.manifest).unwrap();
    let mut manifest =
        layerfs_bridge::provision::StoreManifest::decode(&original_manifest).unwrap();
    manifest.binding.push(7);
    fs::write(&request.manifest, manifest.encode().unwrap()).unwrap();
    let mut events = events::Events::new(&request.receipt).unwrap();
    assert!(workspace_oracle::verify_import(&request, &mut events).is_err());
    drop(events);
    fs::write(&request.manifest, original_manifest).unwrap();
    assert_eq!(fs::read(home.join("store.sqlite")).unwrap(), before);
    fs::remove_dir_all(home).unwrap();
}

#[test]
fn dedup_oracle_real_reuse_initial_and_first_commit_bind_both_immutable_states() {
    let case = "dedup-workspace-exact-100";
    let home = init(case, "reuse");
    let mut request = args(&home, case, "pristine");
    request.mode = "verify-reuse-initial".into();
    let mut events = events::Events::new(&request.receipt).unwrap();
    workspace_oracle::verify_reuse_initial(&request, &mut events).unwrap();
    drop(events);
    let manifest =
        layerfs_bridge::provision::StoreManifest::decode(&fs::read(&request.manifest).unwrap())
            .unwrap();
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(home.join("store.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &manifest.binding,
        manifest.cursor_key,
    )
    .unwrap();
    let storage = Storage::new(handles.storage.clone()).unwrap();
    let snapshot = handles
        .history
        .branch_snapshot(BranchId::from_bytes(manifest.branch).unwrap())
        .unwrap()
        .unwrap();
    let reader = storage.reader().unwrap();
    let mut tree = layerfs_content::filesystem::FilesystemRead::new(
        &reader,
        layerfs_content::filesystem::FilesystemRootId(snapshot.effective_root),
    )
    .unwrap();
    let mut serials = BTreeMap::new();
    for entry in edit_model::entries(case, 0).unwrap() {
        let logical = layerfs_content::filesystem::LogicalPath::new(if entry.path == "." {
            ""
        } else {
            &entry.path
        })
        .unwrap();
        serials.insert(entry.path, tree.resolve(&logical).unwrap().serial);
    }
    let mut next_serial = serials.values().max().unwrap() + 1;
    for entry in edit_model::entries(case, 1).unwrap() {
        if !serials.contains_key(&entry.path) {
            serials.insert(entry.path, next_serial);
            next_serial += 1;
        }
    }
    drop(tree);
    drop(reader);
    let (root, bag) = constructed_with_serials(
        InodeScope::from_object(snapshot.scope),
        &edit_model::entries(case, 1).unwrap(),
        serials,
    );
    let save = storage.begin_save().unwrap();
    for object in bag.objects {
        save.accept(object).unwrap();
    }
    save.finish().unwrap();
    let outcome = handles
        .history
        .commit_branch(&CommitRequest {
            branch: snapshot.branch.id,
            expected_head: snapshot.branch.head_commit,
            expected_base: snapshot.branch.base_layer,
            expected_root: snapshot.effective_root,
            candidate_root: root,
            profile: snapshot.profile,
            scope: snapshot.scope,
            second_parent: None,
            meta: layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
            force: false,
        })
        .unwrap();
    let CommitOutcome::Committed { record: commit, .. } = outcome else {
        panic!("actual first changed state must Commit")
    };
    assert_eq!(
        commit.id,
        layerfs_history::CommitId::derive(root, None, commit.base_layer, None, &commit.meta)
    );
    drop(storage);
    handles.seal().unwrap();
    let before = fs::read(home.join("store.sqlite")).unwrap();
    let mut request = args(&home, case, "final");
    request.mode = "verify-workspace".into();
    let initial_manifest = home.join("source.manifest.tsv");
    let final_manifest = home.join("expected-native.manifest.tsv");
    fs::write(
        &initial_manifest,
        reference::workspace_common::manifest(&edit_model::entries(case, 0).unwrap()).unwrap(),
    )
    .unwrap();
    fs::write(
        &final_manifest,
        reference::workspace_common::manifest(&edit_model::entries(case, 1).unwrap()).unwrap(),
    )
    .unwrap();
    let initial_row = format!(
        "0\t-\t-\t{}\t{}\n",
        hex(&manifest.root),
        initial_manifest.display()
    );
    let final_row = format!(
        "1\t{}\t-\t{}\t{}\n",
        hex(commit.id.as_slice()),
        hex(root.as_bytes()),
        final_manifest.display()
    );
    let body = format!("{initial_row}{final_row}");
    let transcript = home.join("history.tsv");
    fs::write(&transcript, &body).unwrap();
    request.history_file = Some(transcript.clone());
    let mut events = events::Events::new(&request.receipt).unwrap();
    workspace_oracle::verify(&request, &mut events).unwrap();
    drop(events);
    assert_eq!(fs::read(home.join("store.sqlite")).unwrap(), before);
    let text = fs::read_to_string(&request.receipt).unwrap();
    assert!(text.contains("\"roots\":2"));
    assert!(text.contains("\"verified_bytes\":3145728"));
    assert!(text.contains(&hex(commit.id.as_slice())));
    assert!(text.contains(&reference::sdk_edit_common::sha256_hex(body.as_bytes())));
    let wrong_manifest = home.join("wrong.manifest.tsv");
    fs::write(&wrong_manifest, "forged independent state\n").unwrap();
    let bad = vec![
        initial_row.clone(),
        body.trim_end_matches('\n').to_owned(),
        format!("{final_row}{final_row}"),
        body.replacen("0\t", "00\t", 1),
        body.replacen(
            &format!("1\t{}\t-\t", hex(commit.id.as_slice())),
            &format!(
                "1\t{}\t{}\t",
                hex(commit.id.as_slice()),
                hex(commit.id.as_slice())
            ),
            1,
        ),
        body.replacen(&hex(&manifest.root), &hex(root.as_bytes()), 1),
        body.replacen(
            &hex(commit.id.as_slice()),
            &hex(layerfs_history::CommitId::derive(
                root,
                Some(commit.id),
                commit.base_layer,
                None,
                &commit.meta,
            )
            .as_slice()),
            1,
        ),
        body.replacen(&hex(root.as_bytes()), &hex(&manifest.root), 1),
        body.replacen(
            &final_manifest.display().to_string(),
            &initial_manifest.display().to_string(),
            1,
        ),
        body.replacen(&final_manifest.display().to_string(), "-", 1),
        body.replacen(
            &final_manifest.display().to_string(),
            &wrong_manifest.display().to_string(),
            1,
        ),
        format!("{body}{final_row}"),
        body.replace('\n', "\r\n"),
    ];
    let mut missing = args(&home, case, "missing-ack");
    missing.mode = "verify-workspace".into();
    let mut events = events::Events::new(&missing.receipt).unwrap();
    assert!(workspace_oracle::verify(&missing, &mut events).is_err());
    drop(events);
    for (index, invalid) in bad.into_iter().enumerate() {
        fs::write(&transcript, invalid).unwrap();
        let mut invalid_request = args(&home, case, &format!("ack-negative-{index}"));
        invalid_request.mode = "verify-workspace".into();
        invalid_request.history_file = Some(transcript.clone());
        let mut events = events::Events::new(&invalid_request.receipt).unwrap();
        assert!(
            workspace_oracle::verify(&invalid_request, &mut events).is_err(),
            "negative{index}"
        );
        drop(events);
    }
    fs::write(&transcript, body).unwrap();
    assert_eq!(fs::read(home.join("store.sqlite")).unwrap(), before);
    let mut wrong = args(&home, case, "initial-after-commit");
    wrong.mode = "verify-reuse-initial".into();
    let mut events = events::Events::new(&wrong.receipt).unwrap();
    assert!(workspace_oracle::verify_reuse_initial(&wrong, &mut events).is_err());
    drop(events);
    fs::remove_dir_all(home).unwrap();
}

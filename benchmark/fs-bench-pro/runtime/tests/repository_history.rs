//! Public current objects and Stores exercise actual selective proof failures.
//! Synthetic selective fixtures qualify the oracle, never a benchmark sample.
#[allow(dead_code)]
#[path = "../../engine/recipes/dedup_input.rs"]
mod dedup_input;
#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
pub(crate) mod namespace;
pub(crate) mod project {
    pub(crate) use crate::namespace;
}
pub(crate) use namespace::reference;
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
#[path = "../src/repository_history.rs"]
mod repository_history;
#[allow(dead_code)]
#[path = "../src/workspace_oracle.rs"]
pub(crate) mod workspace_oracle;

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
use reference::workspace_common::{Content, Entry, EntryKind};
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
    let mut bag = Bag::default();
    let mut serials = BTreeMap::new();
    for entry in entries {
        if !matches!(entry.kind, EntryKind::Hardlink(_)) {
            serials.insert(entry.path.clone(), serials.len() as u64 + 1);
        }
    }
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

use layerfs_history::{ForkRequest, ForkSource};

struct Fixture {
    home: PathBuf,
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if std::thread::panicking() {
            eprintln!("RETAINED_FAILED_REPOSITORY_FIXTURE={}", self.home.display());
        } else {
            fs::remove_dir_all(&self.home).unwrap();
        }
    }
}
fn fixture(case: &str, label: &str) -> Fixture {
    let home = std::env::temp_dir().join(format!("fsb-repository-{label}-{}", std::process::id()));
    fs::create_dir(&home).unwrap();
    let initial = vec![Entry::directory(".")];
    reference::workspace_common::create_fixture(&home.join("source"), &initial).unwrap();
    let project = Timing::disabled("external.repository.init", |timer| {
        ProjectApi::new().init(
            InitRequest {
                source: home.join("source"),
                store: PersistenceConfig::sqlite(home.join("store.sqlite"))
                    .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
                locator: "/layerfs-store/global/store.sqlite".into(),
                policy: StoragePolicy::frozen_default(),
                catalog: HistoryCatalogConfig {
                    binding_key: b"external-repository-oracle".to_vec(),
                    cursor_key: [61; 32],
                    incarnation: 1,
                },
                stack: LayerStackId::from_authority([62; 16]),
                stack_name: HistoryName::new("repository").unwrap(),
                branch: BranchId::from_authority([63; 16]),
                branch_name: HistoryName::new("main").unwrap(),
                scope_seed: [64; 32],
                deadline: Instant::now() + Duration::from_secs(15),
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
    let main = handles
        .history
        .branch_snapshot(BranchId::from_bytes(project.manifest.branch).unwrap())
        .unwrap()
        .unwrap();
    let fork = handles
        .history
        .fork(&ForkRequest {
            stack: main.branch.stack,
            branch: BranchId::from_authority([65; 16]),
            name: HistoryName::new("history").unwrap(),
            source: ForkSource::Layer(main.branch.base_layer),
        })
        .unwrap();
    let event=format!("{{\"event\":\"fork\",\"fields\":{{\"branch_id\":\"{}\",\"name\":\"history\",\"stack\":\"{}\",\"base_layer\":\"{}\",\"root\":\"{}\",\"head\":\"-\"}}}}\n",hex(fork.branch.id.as_slice()),hex(fork.branch.stack.as_slice()),hex(fork.branch.base_layer.as_slice()),hex(fork.effective_root.as_bytes()));
    fs::write(home.join("fork-event.json"), &event).unwrap();
    let descriptor = format!(
        "{}\thistory\t{}\t{}\t{}\t-\t{}\n",
        hex(fork.branch.id.as_slice()),
        hex(fork.branch.stack.as_slice()),
        hex(fork.branch.base_layer.as_slice()),
        hex(fork.effective_root.as_bytes()),
        reference::sdk_edit_common::sha256_hex(event.as_bytes())
    );
    fs::write(home.join("fork.tsv"), descriptor).unwrap();
    let storage = Storage::new(handles.storage.clone()).unwrap();
    let scope = InodeScope::from_object(main.scope);
    let mut full = format!("0\t-\t-\t{}\t-\n", hex(&project.manifest.root));
    let mut created = full.clone();
    let mut previous = None;
    let mut parent = None;
    let mut root = main.effective_root;
    let mut produced = 0;
    for step in 1..=repository_history::count(case).unwrap() {
        let oracle = home.join(format!("oracle-{step}.json"));
        fs::write(&oracle, b"{}\n").unwrap();
        // Full profile explicitly exercises a retained UpToDate mapping.
        if case != "deepseek-full" || step != 2 {
            let entries = vec![
                Entry::directory("."),
                Entry::file("file", Content::Literal(vec![(step % 251) as u8; 257])),
            ];
            let (candidate, bag) = constructed(scope, &entries);
            let save = storage.begin_save().unwrap();
            for object in bag.objects {
                save.accept(object).unwrap();
            }
            save.finish().unwrap();
            let snapshot = handles
                .history
                .branch_snapshot(fork.branch.id)
                .unwrap()
                .unwrap();
            let outcome = handles
                .history
                .commit_branch(&CommitRequest {
                    branch: fork.branch.id,
                    expected_head: snapshot.branch.head_commit,
                    expected_base: snapshot.branch.base_layer,
                    expected_root: snapshot.effective_root,
                    candidate_root: candidate,
                    profile: snapshot.profile,
                    scope: snapshot.scope,
                    second_parent: None,
                    meta: layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
                    force: false,
                })
                .unwrap();
            let CommitOutcome::Committed { record, .. } = outcome else {
                panic!("changed public candidate must createCommit")
            };
            root = record.root;
            parent = record.parent;
            previous = Some(record.id);
            produced += 1;
            created += &format!(
                "{produced}\t{}\t{}\t{}\t{}\n",
                hex(record.id.as_slice()),
                parent
                    .map(|id| hex(id.as_slice()))
                    .unwrap_or_else(|| "-".into()),
                hex(root.as_bytes()),
                oracle.display()
            );
        } else {
            let snapshot = handles
                .history
                .branch_snapshot(fork.branch.id)
                .unwrap()
                .unwrap();
            let outcome = handles
                .history
                .commit_branch(&CommitRequest {
                    branch: fork.branch.id,
                    expected_head: snapshot.branch.head_commit,
                    expected_base: snapshot.branch.base_layer,
                    expected_root: snapshot.effective_root,
                    candidate_root: snapshot.effective_root,
                    profile: snapshot.profile,
                    scope: snapshot.scope,
                    second_parent: None,
                    meta: layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
                    force: false,
                })
                .unwrap();
            assert!(
                matches!(outcome, CommitOutcome::UpToDate { root: retained, .. } if retained == root)
            );
        }
        full += &format!(
            "{step}\t{}\t{}\t{}\t{}\n",
            previous
                .map(|id| hex(id.as_slice()))
                .unwrap_or_else(|| "-".into()),
            parent
                .map(|id| hex(id.as_slice()))
                .unwrap_or_else(|| "-".into()),
            hex(root.as_bytes()),
            oracle.display()
        );
    }
    drop(storage);
    handles.seal().unwrap();
    fs::write(home.join("all.tsv"), full).unwrap();
    fs::write(home.join("created.tsv"), created).unwrap();
    Fixture { home }
}
fn prove(
    fixture: &Fixture,
    case: &str,
    label: &str,
    full: &str,
    created: &str,
    fork: &str,
) -> bool {
    let folder = fixture.home.join(label);
    fs::create_dir(&folder).unwrap();
    fs::copy(
        fixture.home.join("store.sqlite"),
        folder.join("store.sqlite"),
    )
    .unwrap();
    fs::write(folder.join("all.tsv"), full).unwrap();
    fs::write(folder.join("created.tsv"), created).unwrap();
    fs::write(folder.join("fork.tsv"), fork).unwrap();
    fs::copy(
        fixture.home.join("fork-event.json"),
        folder.join("fork-event.json"),
    )
    .unwrap();
    let args = args::Args {
        mode: "verify-repository".into(),
        socket: "/unused".into(),
        image: args::IMAGE.into(),
        volume: "unused".into(),
        executable: "/unused".into(),
        receipt: folder.join("proof.jsonl"),
        manifest: fixture.home.join("manifest"),
        installed_manifest: None,
        uid: 1,
        gid: 1,
        source: Some(folder.clone()),
        sealed: Some(folder.join("store.sqlite")),
        init_seconds: 15,
        environment: vec!["LAYERFS_CONSTRUCTION_WORKERS=1".into()],
        observation_scope: [67; 32],
        case: Some(case.into()),
        history_file: Some(folder.join("all.tsv")),
        history_step: None,
    };
    let mut events = events::Events::new(&args.receipt).unwrap();
    match repository_history::verify(&args, &mut events) {
        Ok(()) => {
            events
                .value("finished", "known successful external native proof")
                .unwrap();
            true
        }
        Err(error) => {
            fs::write(folder.join("error.txt"), error.to_string()).unwrap();
            false
        }
    }
}

#[test]
fn repository_actual_public_created_history_and_branch_only_derivation() {
    let case = "deepseek-stride10";
    let f = fixture(case, "created");
    let full = fs::read_to_string(f.home.join("all.tsv")).unwrap();
    let created = fs::read_to_string(f.home.join("created.tsv")).unwrap();
    let fork = fs::read_to_string(f.home.join("fork.tsv")).unwrap();
    assert!(prove(&f, case, "good", &full, &created, &fork));
    let original = layerfs_bridge::provision::StoreManifest::decode(
        &fs::read(f.home.join("manifest")).unwrap(),
    )
    .unwrap();
    let mut derived = layerfs_bridge::provision::StoreManifest::decode(
        &fs::read(f.home.join("good/derived.manifest")).unwrap(),
    )
    .unwrap();
    assert_ne!(derived.branch, original.branch);
    derived.branch = original.branch;
    assert_eq!(derived.encode().unwrap(), original.encode().unwrap());
    let bad = full.replacen("1\t", "01\t", 1);
    assert!(!prove(&f, case, "index", &bad, &created, &fork));
    let mut rows = full.lines().map(str::to_owned).collect::<Vec<_>>();
    let mut second = rows[2].split('\t').map(str::to_owned).collect::<Vec<_>>();
    second[2] = "-".into();
    rows[2] = second.join("\t");
    assert!(!prove(
        &f,
        case,
        "parent",
        &(rows.join("\n") + "\n"),
        &created,
        &fork
    ));
    assert!(!prove(
        &f,
        case,
        "census",
        &full,
        &created.replacen("1\t", "2\t", 1),
        &fork
    ));
    let bad_fork = fork.replacen("history", "other", 1);
    assert!(!prove(&f, case, "fork", &full, &created, &bad_fork));
}

#[test]
fn repository_actual_public_full_up_to_date_retains_prior_tuple_and_all_selected_roots() {
    let case = "deepseek-full";
    let f = fixture(case, "uptodate");
    let full = fs::read_to_string(f.home.join("all.tsv")).unwrap();
    let created = fs::read_to_string(f.home.join("created.tsv")).unwrap();
    let fork = fs::read_to_string(f.home.join("fork.tsv")).unwrap();
    assert_eq!(full.lines().count(), 158);
    assert_eq!(created.lines().count(), 157);
    assert!(prove(&f, case, "good", &full, &created, &fork));
    let mut rows = full.lines().map(str::to_owned).collect::<Vec<_>>();
    let mut repeated = rows[2].split('\t').map(str::to_owned).collect::<Vec<_>>();
    repeated[3] = "0".repeat(64);
    rows[2] = repeated.join("\t");
    assert!(!prove(
        &f,
        case,
        "wrong-retained-root",
        &(rows.join("\n") + "\n"),
        &created,
        &fork
    ));
}

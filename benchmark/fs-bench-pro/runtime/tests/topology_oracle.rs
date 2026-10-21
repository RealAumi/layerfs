//! Actual current public Stores/Forks/Commits qualify topology proof only.
//! Native object construction is a synthetic oracle fixture, never mounted work.
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
    BranchId, CommitOutcome, CommitRequest, ForkRequest, ForkSource, HistoryCatalog,
    HistoryCatalogConfig, HistoryName, LayerStackId,
};
use layerfs_persistence::{Handles, PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::{Storage, StoragePolicy};
use layerfs_telemetry::timer::Timing;
use reference::workspace_common::{Entry, EntryKind};
use std::{
    collections::{BTreeMap, BTreeSet},
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

fn temporary(label: &str) -> PathBuf {
    let home = std::env::temp_dir().join(format!("fsb-batch5-{label}-{}", std::process::id()));
    fs::create_dir(&home).unwrap();
    home
}
fn optional(id: Option<layerfs_history::CommitId>) -> String {
    id.map(|id| hex(id.as_slice()))
        .unwrap_or_else(|| "-".into())
}
fn compact(home: &Path) {
    let case = reference::v016_stages::COMPACT_CONVERGENT;
    let entries = edit_model::context_entries(case, "trunk", 0).unwrap();
    reference::workspace_common::create_fixture(&home.join("source"), &entries).unwrap();
    let prepared = Timing::disabled("external.topology.init", |timer| {
        ProjectApi::new().init(
            InitRequest {
                source: home.join("source"),
                store: PersistenceConfig::sqlite(home.join("store.sqlite"))
                    .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
                locator: "/layerfs-store/global/store.sqlite".into(),
                policy: StoragePolicy::frozen_default(),
                catalog: HistoryCatalogConfig {
                    binding_key: b"external-batch5-topology".to_vec(),
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
    fs::write(home.join("manifest"), prepared.manifest.encode().unwrap()).unwrap();
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(home.join("store.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &prepared.manifest.binding,
        prepared.manifest.cursor_key,
    )
    .unwrap();
    let initial = handles
        .history
        .branch_snapshot(BranchId::from_bytes(prepared.manifest.branch).unwrap())
        .unwrap()
        .unwrap();
    let scope = InodeScope::from_object(initial.scope);
    let storage = Storage::new(handles.storage.clone()).unwrap();
    let mut branches = Vec::new();
    let mut commits = Vec::new();
    branches.push(format!(
        "branch\tinitial\t{}\tmain\t{}\t{}\t-\t{}\t-\t{}\t-\t0",
        hex(initial.branch.id.as_slice()),
        hex(initial.branch.stack.as_slice()),
        hex(initial.branch.base_layer.as_slice()),
        hex(&prepared.manifest.root),
        hex(&prepared.manifest.root)
    ));
    let mut trunk = None;
    let mut trunk_fifth = None;
    for (ordinal, role) in ["trunk", "a", "b"].into_iter().enumerate() {
        let name = format!("v0.1.6-compact-{case}-{role}");
        let branch = handles
            .history
            .fork(&ForkRequest {
                stack: initial.branch.stack,
                branch: BranchId::from_authority([31 + ordinal as u8; 16]),
                name: HistoryName::new(&name).unwrap(),
                source: if role == "trunk" {
                    ForkSource::Layer(initial.branch.base_layer)
                } else {
                    ForkSource::Commit {
                        branch: trunk.unwrap(),
                        commit: trunk_fifth.unwrap(),
                    }
                },
            })
            .unwrap();
        let begun = branch.clone();
        for local in 1..=10 {
            let expected = edit_model::context_entries(case, role, local).unwrap();
            let (root, bag) = constructed(scope, &expected);
            let save = storage.begin_save().unwrap();
            for object in bag.objects {
                save.accept(object).unwrap();
            }
            save.finish().unwrap();
            let current = handles
                .history
                .branch_snapshot(branch.branch.id)
                .unwrap()
                .unwrap();
            let result = handles
                .history
                .commit_branch(&CommitRequest {
                    branch: current.branch.id,
                    expected_head: current.branch.head_commit,
                    expected_base: current.branch.base_layer,
                    expected_root: current.effective_root,
                    candidate_root: root,
                    profile: current.profile,
                    scope: current.scope,
                    second_parent: None,
                    meta: layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
                    force: false,
                })
                .unwrap();
            let CommitOutcome::Committed { record, .. } = result else {
                panic!("original compact edit must Commit")
            };
            if role == "trunk" && local == 5 {
                trunk_fifth = Some(record.id);
            }
            let chosen = local == 10 || role == "trunk" && local == 5;
            let path = home.join(format!("{role}-{local}.tsv"));
            if chosen {
                fs::write(
                    &path,
                    edit_model::context_manifest(case, role, local).unwrap(),
                )
                .unwrap();
            }
            commits.push(format!(
                "commit\t{role}\t{local}\t{}\t{}\t{}\t{}\t{}\t{}\t-",
                hex(record.id.as_slice()),
                hex(record.stack.as_slice()),
                hex(root.as_bytes()),
                optional(record.parent),
                hex(record.base_layer.as_slice()),
                if chosen {
                    path.display().to_string()
                } else {
                    "-".into()
                }
            ));
        }
        let final_snapshot = handles
            .history
            .branch_snapshot(branch.branch.id)
            .unwrap()
            .unwrap();
        branches.push(format!(
            "branch\t{role}\t{}\t{name}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
            hex(branch.branch.id.as_slice()),
            hex(initial.branch.stack.as_slice()),
            hex(initial.branch.base_layer.as_slice()),
            optional(begun.branch.head_commit),
            hex(begun.effective_root.as_bytes()),
            optional(final_snapshot.branch.head_commit),
            hex(final_snapshot.effective_root.as_bytes()),
            if role == "trunk" { "-" } else { "trunk" },
            if role == "trunk" { 0 } else { 5 }
        ));
        if role == "trunk" {
            trunk = Some(branch.branch.id);
        }
    }
    drop(storage);
    handles.seal().unwrap();
    fs::write(
        home.join("topology.tsv"),
        format!(
            "topology-v1\t{case}\n{}\n{}\n",
            branches.join("\n"),
            commits.join("\n")
        ),
    )
    .unwrap();
}
fn args(home: &Path, mode: &str, case: &str) -> args::Args {
    args::Args {
        mode: mode.into(),
        socket: "unused-offline".into(),
        image: args::IMAGE.into(),
        volume: "unused-offline".into(),
        executable: "unused-offline".into(),
        receipt: home.join(format!("{mode}.events.jsonl")),
        manifest: home.join("manifest"),
        installed_manifest: None,
        uid: 501,
        gid: 20,
        source: None,
        sealed: Some(home.join("proof.sqlite")),
        init_seconds: 120,
        environment: Vec::new(),
        observation_scope: [1; 32],
        case: Some(case.into()),
        history_file: Some(home.join("topology.tsv")),
        history_step: None,
    }
}
#[test]
fn actual_compact_public_graph_allows_only_equal_tuple_collapse_and_rejects_extra_branch() {
    let home = temporary("compact");
    compact(&home);
    let graph = fs::read_to_string(home.join("topology.tsv")).unwrap();
    let rows = workspace_oracle::parse_topology(&graph).unwrap();
    assert_eq!(rows.commits.len(), 30);
    // Both children share trunk6..10, then share their five new descendants.
    // Exact pure content/parent/base tuples therefore form a fifteen-node union.
    assert_eq!(
        rows.commits
            .iter()
            .map(|row| row.id)
            .collect::<BTreeSet<_>>()
            .len(),
        15
    );
    fs::copy(home.join("store.sqlite"), home.join("proof.sqlite")).unwrap();
    let options = args(
        &home,
        "verify-topology",
        reference::v016_stages::COMPACT_CONVERGENT,
    );
    let mut output = events::Events::new(&options.receipt).unwrap();
    workspace_oracle::verify_topology(&options, &mut output).unwrap();
    drop(output);
    let receipt = fs::read_to_string(&options.receipt).unwrap();
    assert!(receipt.contains("\"topology_acknowledgements\":30"));
    assert!(receipt.contains("\"topology_distinct_commits\":15"));
    assert!(receipt.contains("\"topology_branches\":4"));
    let manifest =
        layerfs_bridge::provision::StoreManifest::decode(&fs::read(home.join("manifest")).unwrap())
            .unwrap();
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(home.join("proof.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &manifest.binding,
        manifest.cursor_key,
    )
    .unwrap();
    let snapshot = handles
        .history
        .branch_snapshot(BranchId::from_bytes(manifest.branch).unwrap())
        .unwrap()
        .unwrap();
    handles
        .history
        .fork(&ForkRequest {
            stack: snapshot.branch.stack,
            branch: BranchId::from_authority([99; 16]),
            name: HistoryName::new("extra").unwrap(),
            source: ForkSource::Layer(snapshot.branch.base_layer),
        })
        .unwrap();
    handles.seal().unwrap();
    let mut rejected = events::Events::new(&home.join("extra.events.jsonl")).unwrap();
    assert!(workspace_oracle::verify_topology(&options, &mut rejected)
        .unwrap_err()
        .to_string()
        .contains("public Branch set"));
    fs::remove_dir_all(home).unwrap();
}
#[test]
fn historical_access_qualifies_exact_retained_root_without_extra_producer_payload_scope() {
    let home = temporary("access");
    compact(&home);
    let case = reference::historical_access::FORK_POINT;
    let manifest =
        layerfs_bridge::provision::StoreManifest::decode(&fs::read(home.join("manifest")).unwrap())
            .unwrap();
    let body = fs::read_to_string(home.join("topology.tsv")).unwrap();
    let mut graph = workspace_oracle::parse_topology(&body).unwrap();
    let chosen = graph
        .commits
        .iter()
        .find(|ack| ack.role == "trunk" && ack.local == 5)
        .unwrap()
        .clone();
    let source = graph.branches["trunk"].id;
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(home.join("store.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &manifest.binding,
        manifest.cursor_key,
    )
    .unwrap();
    let initial = handles
        .history
        .branch_snapshot(BranchId::from_bytes(manifest.branch).unwrap())
        .unwrap()
        .unwrap();
    let branch = handles
        .history
        .fork(&ForkRequest {
            stack: initial.branch.stack,
            branch: BranchId::from_authority([88; 16]),
            name: HistoryName::new(&format!("access-5-{case}")).unwrap(),
            source: ForkSource::Commit {
                branch: source,
                commit: chosen.id,
            },
        })
        .unwrap();
    handles.seal().unwrap();
    let mut lines = body
        .lines()
        .filter(|line| line.starts_with("topology-v1") || line.starts_with("branch"))
        .map(str::to_owned)
        .collect::<Vec<_>>();
    lines.push(format!(
        "branch\taccess\t{}\taccess-5-{case}\t{}\t{}\t{}\t{}\t{}\t{}\ttrunk\t5",
        hex(branch.branch.id.as_slice()),
        hex(initial.branch.stack.as_slice()),
        hex(initial.branch.base_layer.as_slice()),
        hex(chosen.id.as_slice()),
        hex(chosen.root.as_bytes()),
        hex(chosen.id.as_slice()),
        hex(chosen.root.as_bytes())
    ));
    for ack in &mut graph.commits {
        if ack.role != "trunk" || ack.local != 5 {
            ack.selected = "-".into();
        }
        lines.push(format!(
            "commit\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t-",
            ack.role,
            ack.local,
            hex(ack.id.as_slice()),
            hex(ack.stack.as_slice()),
            hex(ack.root.as_bytes()),
            optional(ack.parent),
            hex(ack.base.as_slice()),
            ack.selected
        ));
    }
    fs::write(home.join("topology.tsv"), lines.join("\n") + "\n").unwrap();
    fs::copy(home.join("store.sqlite"), home.join("proof.sqlite")).unwrap();
    let options = args(&home, "verify-access", case);
    let mut output = events::Events::new(&options.receipt).unwrap();
    workspace_oracle::verify_access(&options, &mut output).unwrap();
    drop(output);
    let receipt = fs::read_to_string(options.receipt).unwrap();
    assert_eq!(
        receipt
            .matches("\"event\":\"topology_root_verified\"")
            .count(),
        1
    );
    assert_eq!(
        receipt
            .matches("\"event\":\"access_expected_read\"")
            .count(),
        1
    );
    assert!(receipt.contains("\"verified_bytes\":65536"));
    assert!(receipt.contains("\"topology_branches\":5"));
    fs::remove_dir_all(home).unwrap();
}

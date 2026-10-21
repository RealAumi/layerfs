//! Synthetic public C1/C5 fixtures qualify an offline bounded oracle only.
//! No FUSE workload, production family sample or legacy accounting is claimed.
// Exact first-party C1 fixture helpers from topology_oracle.rs; private
// helper visibility and inner-doc include rules prevent a direct module reuse.
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

fn temporary(label: &str) -> PathBuf {
    let home = std::env::temp_dir().join(format!("fsb-batch5-{label}-{}", std::process::id()));
    fs::create_dir(&home).unwrap();
    home
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

#[allow(dead_code)]
#[path = "../../engine/recipes/dedup_input.rs"]
pub(crate) mod dedup_input;
#[path = "../src/store_footprint.rs"]
mod store_footprint;

#[test]
fn footprint_frozen_geometry_edit_target_and_clipped_range_are_exact() {
    for control in reference::store_footprint::CONTROLS {
        let plan = store_footprint::plan(control.id).unwrap();
        assert_eq!(plan.files.len() as u64, control.regular_files);
        assert_eq!(plan.logical_bytes, control.logical_bytes);
        assert_eq!(
            plan.directories,
            if control.regular_files == 100000 {
                1000
            } else {
                1
            }
        );
        let chosen = plan.files.iter().find(|file| file.size > 10).unwrap();
        assert_eq!(plan.edit_path, chosen.path);
        assert_eq!(plan.edit_size, chosen.size);
        assert_eq!(plan.edit_offset, 2654435761 % (chosen.size - 10));
        assert_eq!(plan.boundary_start, plan.edit_offset.saturating_sub(65536));
        assert_eq!(
            plan.boundary_end,
            plan.edit_size.min(plan.edit_offset + 10 + 65536)
        );
        assert!(plan.boundary_end - plan.boundary_start <= 131082);
        for (index, file) in plan.files.iter().enumerate() {
            assert_eq!(
                file.mtime_seconds,
                1700000000
                    + if control.kind == reference::store_footprint::Kind::MetadataCardinality {
                        index as i64 + 1
                    } else {
                        0
                    }
            );
        }
    }
}
fn acknowledgement() -> String {
    let stack = LayerStackId::from_authority([81; 16]);
    let branch = BranchId::from_authority([83; 16]);
    let initial = ObjectId::for_bytes(b"external footprint initial root");
    let final_root = ObjectId::for_bytes(b"external footprint final root");
    let base = layerfs_history::LayerId::derive(stack, None, initial);
    let commit = layerfs_history::CommitId::derive(
        final_root,
        None,
        base,
        None,
        &layerfs_history::CommitMeta {
            branch: Some(branch),
            ..layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace)
        },
    );
    format!("fs-bench-pro-store-footprint-ack-v1\nstore-footprint-unique-100-low-v1\ninit\t{}\t{}\t{}\t{}\ncommit\t{}\t{}\t-\t{}\t{}\n",
        hex(branch.as_slice()),hex(initial.as_bytes()),hex(base.as_slice()),hex(stack.as_slice()),
        hex(commit.as_slice()),hex(final_root.as_bytes()),hex(base.as_slice()),hex(stack.as_slice()))
}
#[test]
fn footprint_ack_rejects_changed_tuple_scope_extra_rows_and_noncanonical_identity() {
    let body = acknowledgement();
    let parsed = store_footprint::parse_acknowledgements(&body).unwrap();
    assert_eq!(parsed.case, "store-footprint-unique-100-low-v1");
    let rows = body.lines().map(str::to_owned).collect::<Vec<_>>();
    let init = rows[2].split('\t').collect::<Vec<_>>();
    let commit = rows[3].split('\t').collect::<Vec<_>>();
    for corrupt in [
        body.trim_end().into(),
        format!("{body}extra\n"),
        body.replace("\n", "\r\n"),
        body.replace(
            "store-footprint-unique-100-low-v1",
            "store-footprint-unknown",
        ),
        body.replace("\t-\t", &format!("\t{}\t", commit[1])),
        body.replace(commit[2], init[2]),
        body.replace(
            commit[1],
            &hex(layerfs_history::CommitId::derive(
                parsed.initial,
                None,
                parsed.base,
                None,
                &layerfs_history::CommitMeta {
                    branch: Some(parsed.branch),
                    ..layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace)
                },
            )
            .as_slice()),
        ),
        body.replace(init[1], "ff"),
        body.replace(commit[1], &commit[1].to_uppercase()),
    ] {
        assert!(
            store_footprint::parse_acknowledgements(&corrupt).is_err(),
            "{corrupt}"
        );
    }
}

fn fixture(home: &Path, corrupt_boundary: bool, extra_branch: bool) -> args::Args {
    let case = "store-footprint-unique-100-low-v1";
    let source = home.join("source");
    reference::create_store_footprint_fixture(&source, case, 100).unwrap();
    let planned = store_footprint::plan(case).unwrap();
    let prepared = Timing::disabled("external.footprint.init", |timer| {
        ProjectApi::new().init(
            InitRequest {
                source: source.clone(),
                store: PersistenceConfig::sqlite(home.join("store.sqlite"))
                    .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
                locator: "/layerfs-store/global/store.sqlite".into(),
                policy: StoragePolicy::frozen_default(),
                catalog: HistoryCatalogConfig {
                    binding_key: b"external-footprint-oracle".to_vec(),
                    cursor_key: [89; 32],
                    incarnation: 1,
                },
                stack: LayerStackId::from_authority([91; 16]),
                stack_name: HistoryName::new("project").unwrap(),
                branch: BranchId::from_authority([93; 16]),
                branch_name: HistoryName::new("main").unwrap(),
                scope_seed: [97; 32],
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
    let storage = Storage::new(handles.storage.clone()).unwrap();
    let mut entries = vec![Entry::directory("."), Entry::directory("d0000")];
    for file in &planned.files {
        let mut bytes = fs::read(source.join(&file.path)).unwrap();
        if file.path == planned.edit_path {
            let at = planned.edit_offset as usize;
            bytes[at..at + 10].copy_from_slice(reference::NAMESPACE_EDIT_MARKER);
            if corrupt_boundary {
                bytes[at] ^= 1;
            }
        }
        let mut entry = Entry::file(
            &file.path,
            reference::workspace_common::Content::Literal(bytes),
        );
        entry.mtime_seconds = if file.path == planned.edit_path {
            reference::NAMESPACE_MTIME_SECONDS
        } else {
            file.mtime_seconds
        };
        entries.push(entry);
    }
    entries.sort_by(|left, right| left.path.cmp(&right.path));
    let (root, bag) = constructed(InodeScope::from_object(initial.scope), &entries);
    let save = storage.begin_save().unwrap();
    for object in bag.objects {
        save.accept(object).unwrap();
    }
    save.finish().unwrap();
    let outcome = handles
        .history
        .commit_branch(&CommitRequest {
            branch: initial.branch.id,
            expected_head: None,
            expected_base: initial.branch.base_layer,
            expected_root: initial.effective_root,
            candidate_root: root,
            profile: initial.profile,
            scope: initial.scope,
            second_parent: None,
            meta: layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
            force: false,
        })
        .unwrap();
    let CommitOutcome::Committed { record: commit, .. } = outcome else {
        panic!("synthetic changed candidate must Commit")
    };
    if extra_branch {
        handles
            .history
            .fork(&ForkRequest {
                stack: initial.branch.stack,
                branch: BranchId::from_authority([103; 16]),
                name: HistoryName::new("extra-unacknowledged").unwrap(),
                source: ForkSource::Layer(initial.branch.base_layer),
            })
            .unwrap();
    }
    fs::write(home.join("history.tsv"),format!("fs-bench-pro-store-footprint-ack-v1\n{case}\ninit\t{}\t{}\t{}\t{}\ncommit\t{}\t{}\t-\t{}\t{}\n",
        hex(initial.branch.id.as_slice()),hex(initial.effective_root.as_bytes()),hex(initial.branch.base_layer.as_slice()),hex(initial.branch.stack.as_slice()),
        hex(commit.id.as_slice()),hex(root.as_bytes()),hex(commit.base_layer.as_slice()),hex(commit.stack.as_slice()))).unwrap();
    drop(storage);
    handles.seal().unwrap();
    let mut options = args(home, "verify-footprint", case);
    options.source = Some(source);
    options.sealed = Some(home.join("store.sqlite"));
    options.history_file = Some(home.join("history.tsv"));
    options
}
#[test]
fn footprint_real_typed_copy_proves_original_boundary_and_keeps_source_immutable() {
    let home = temporary("footprint-positive");
    let options = fixture(&home, false, false);
    let before = fs::read(home.join("store.sqlite")).unwrap();
    let original_ack = fs::read_to_string(options.history_file.as_ref().unwrap()).unwrap();
    let ack = store_footprint::parse_acknowledgements(&original_ack).unwrap();
    let plan = store_footprint::plan(options.case.as_deref().unwrap()).unwrap();
    let mut output = events::Events::new(&options.receipt).unwrap();
    store_footprint::verify(&options, &mut output).unwrap();
    drop(output);
    let record = fs::read_to_string(&options.receipt).unwrap();
    assert!(record.contains("store_footprint_verified"));
    assert!(record.contains("\"status\":\"PASS\""));
    assert!(record.contains("\"initial_paths\":102"));
    assert!(record.contains("\"provider_store_unchanged\":1"));
    assert!(record.contains(&format!("\"boundary_start\":{}", plan.boundary_start)));
    assert!(record.contains(&format!("\"boundary_end\":{}", plan.boundary_end)));
    assert!(record.contains("REQUIRED_SEPARATE_UNFILTERED_CLOSED_SQL"));
    for (field, expected) in [
        ("stack_id", hex(ack.stack.as_slice())),
        ("branch_id", hex(ack.branch.as_slice())),
        ("base_layer_id", hex(ack.base.as_slice())),
        ("final_head_commit_id", hex(ack.commit.as_slice())),
        ("final_head_root", hex(ack.final_root.as_bytes())),
        (
            "original_acknowledged_transcript_sha256",
            reference::sdk_edit_common::sha256_hex(original_ack.as_bytes()),
        ),
    ] {
        assert!(
            record.contains(&format!("\"{field}\":\"{expected}\"")),
            "{record}"
        );
    }
    let directory = options.receipt.with_extension("artifacts");
    let typed = directory.join("footprint-typed.sqlite");
    let typed_after = fs::read(&typed).unwrap();
    assert!(record.contains(&format!(
        "\"provider_store_path\":{}",
        events::quoted(&typed.display().to_string())
    )));
    assert!(record.contains(&format!(
        "\"provider_store_after_sha256\":\"{}\"",
        reference::sdk_edit_common::sha256_hex(&typed_after)
    )));
    assert!(record.contains(&format!(
        "\"provider_store_after_size\":{}",
        typed_after.len()
    )));
    for field in ["original_store_sha256", "original_store_after_sha256"] {
        assert!(record.contains(&format!(
            "\"{field}\":\"{}\"",
            reference::sdk_edit_common::sha256_hex(&before)
        )));
    }
    let projection = fs::read(directory.join("footprint-census.tsv")).unwrap();
    assert_eq!(
        projection,
        store_footprint::census_transcript(&ack).as_bytes()
    );
    assert!(record.contains(&format!(
        "\"acknowledged_transcript_sha256\":\"{}\"",
        reference::sdk_edit_common::sha256_hex(&projection)
    )));
    assert_eq!(fs::read(home.join("store.sqlite")).unwrap(), before);
    fs::remove_dir_all(home).unwrap();
}

#[test]
fn footprint_census_projection_is_exact_and_binds_actual_typed_acknowledgements() {
    let original = acknowledgement();
    let ack = store_footprint::parse_acknowledgements(&original).unwrap();
    let projection = store_footprint::census_transcript(&ack);
    assert_eq!(
        projection,
        format!(
            "0\t-\t-\t{}\toriginal-footprint-initial\n1\t{}\t-\t{}\toriginal-footprint-final-boundary\n",
            hex(ack.initial.as_bytes()), hex(ack.commit.as_slice()), hex(ack.final_root.as_bytes())
        )
    );
    assert_eq!(projection.lines().count(), 2);
    assert!(projection.lines().all(|row| row.split('\t').count() == 5));
    let changed_root = ObjectId::for_bytes(b"different canonical footprint root");
    let changed_commit = layerfs_history::CommitId::derive(
        changed_root,
        None,
        ack.base,
        None,
        &layerfs_history::CommitMeta {
            branch: Some(ack.branch),
            ..layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace)
        },
    );
    let changed = original
        .replace(
            &hex(ack.final_root.as_bytes()),
            &hex(changed_root.as_bytes()),
        )
        .replace(&hex(ack.commit.as_slice()), &hex(changed_commit.as_slice()));
    let changed_ack = store_footprint::parse_acknowledgements(&changed).unwrap();
    assert_ne!(
        reference::sdk_edit_common::sha256_hex(projection.as_bytes()),
        reference::sdk_edit_common::sha256_hex(
            store_footprint::census_transcript(&changed_ack).as_bytes()
        )
    );
}

#[test]
fn footprint_provider_identity_observes_changed_copy_and_refuses_original_tamper() {
    // Identity observation only; these byte fixtures do not qualify SQLite.
    let home = temporary("footprint-provider-identity");
    let original = home.join("original");
    let typed = home.join("typed");
    let content = b"immutable normalized identity fixture";
    fs::write(&original, content).unwrap();
    fs::copy(&original, &typed).unwrap();
    let before = (
        reference::sdk_edit_common::sha256_hex(content),
        content.len() as u64,
    );
    let unchanged = store_footprint::sealed_provider_identity(&original, &typed, &before).unwrap();
    assert!(unchanged.typed_unchanged);
    let changed = b"actual provider changed after the original was copied";
    fs::write(&typed, changed).unwrap();
    let observed = store_footprint::sealed_provider_identity(&original, &typed, &before).unwrap();
    assert!(!observed.typed_unchanged);
    assert_eq!(observed.original_after, before);
    assert_eq!(
        observed.typed_after,
        (
            reference::sdk_edit_common::sha256_hex(changed),
            changed.len() as u64
        )
    );
    fs::write(&original, b"unexpected original source mutation").unwrap();
    assert!(
        store_footprint::sealed_provider_identity(&original, &typed, &before)
            .unwrap_err()
            .to_string()
            .contains("original normalized source mutated")
    );
    fs::remove_dir_all(home).unwrap();
}

#[test]
fn footprint_canonical_ack_tamper_cannot_publish_a_census_projection() {
    let home = temporary("footprint-census-tamper");
    let options = fixture(&home, false, false);
    let original = fs::read_to_string(options.history_file.as_ref().unwrap()).unwrap();
    let ack = store_footprint::parse_acknowledgements(&original).unwrap();
    let other_root = ObjectId::for_bytes(b"canonical root not acknowledged by this Store");
    let other_commit = layerfs_history::CommitId::derive(
        other_root,
        None,
        ack.base,
        None,
        &layerfs_history::CommitMeta {
            branch: Some(ack.branch),
            ..layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace)
        },
    );
    let changed = original
        .replace(&hex(ack.final_root.as_bytes()), &hex(other_root.as_bytes()))
        .replace(&hex(ack.commit.as_slice()), &hex(other_commit.as_slice()));
    assert!(store_footprint::parse_acknowledgements(&changed).is_ok());
    fs::write(options.history_file.as_ref().unwrap(), changed).unwrap();
    let before = fs::read(options.sealed.as_ref().unwrap()).unwrap();
    let mut output = events::Events::new(&options.receipt).unwrap();
    let error = store_footprint::verify(&options, &mut output)
        .unwrap_err()
        .to_string();
    assert!(error.contains("actual CreatedCommit absent"), "{error}");
    drop(output);
    assert!(!options
        .receipt
        .with_extension("artifacts")
        .join("footprint-census.tsv")
        .exists());
    assert!(!fs::read_to_string(&options.receipt)
        .unwrap()
        .contains("store_footprint_verified"));
    assert_eq!(fs::read(options.sealed.as_ref().unwrap()).unwrap(), before);
    fs::remove_dir_all(home).unwrap();
}
#[test]
fn footprint_wrong_canonical_selected_bytes_are_rejected_without_mutating_source() {
    let home = temporary("footprint-corrupt");
    let options = fixture(&home, true, false);
    let before = fs::read(home.join("store.sqlite")).unwrap();
    let mut output = events::Events::new(&options.receipt).unwrap();
    let error = store_footprint::verify(&options, &mut output)
        .unwrap_err()
        .to_string();
    assert!(error.contains("clipped edit bytes differ"), "{error}");
    drop(output);
    assert_eq!(fs::read(home.join("store.sqlite")).unwrap(), before);
    assert!(!fs::read_to_string(&options.receipt)
        .unwrap()
        .contains("store_footprint_verified"));
    fs::remove_dir_all(home).unwrap();
}
#[test]
fn footprint_extra_actual_public_branch_is_rejected() {
    let home = temporary("footprint-extra");
    let options = fixture(&home, false, true);
    let before = fs::read(home.join("store.sqlite")).unwrap();
    let mut output = events::Events::new(&options.receipt).unwrap();
    let error = store_footprint::verify(&options, &mut output)
        .unwrap_err()
        .to_string();
    assert!(error.contains("topology/EOF differs"), "{error}");
    drop(output);
    assert_eq!(fs::read(home.join("store.sqlite")).unwrap(), before);
    fs::remove_dir_all(home).unwrap();
}

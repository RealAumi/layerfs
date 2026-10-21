//! Native authoring qualification of exact import plans and public Init ACKs.
//! This is not a mounted verifier, physical-sharing proof or timed family case.
#[allow(dead_code)]
#[path = "../src/project.rs"]
pub(crate) mod project;
pub(crate) use project::namespace::reference;
pub(crate) type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[allow(dead_code)]
#[path = "../src/args.rs"]
pub(crate) mod args;
#[allow(dead_code)]
#[path = "../../engine/recipes/dedup_input.rs"]
pub(crate) mod dedup_input;
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
#[path = "../src/fixture.rs"]
pub(crate) mod fixture;
#[allow(dead_code)]
#[path = "../src/runtime.rs"]
pub(crate) mod runtime;
#[allow(dead_code)]
#[path = "../src/workspace_oracle.rs"]
pub(crate) mod workspace_oracle;

use layerfs_api::{InitRequest, ProjectApi};
use layerfs_bridge::provision::StoreProfile;
use layerfs_content::ObjectId;
use layerfs_history::{BranchId, HistoryCatalogConfig, HistoryName, LayerStackId};
use layerfs_persistence::{PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::StoragePolicy;
use layerfs_telemetry::timer::Timing;
use std::{
    fs,
    path::PathBuf,
    time::{Duration, Instant},
};

pub(crate) fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[test]
fn project_import_cross_file_counts_cover_every_original_pattern_and_tier() {
    let original: Vec<_> = reference::dedup_cross_file::cases()
        .into_iter()
        .filter(|case| case.tier == 100 || case.id == "dedup-cross-file-anchor-1")
        .collect();
    assert_eq!(original.len(), 4);
    for selected in original {
        let plan = project::import_counts(&selected.id).unwrap().unwrap();
        assert_eq!(plan.family, "dedup_cross_file");
        assert_eq!(plan.files, selected.tier as u64);
        assert_eq!(plan.directories, 2);
        assert_eq!(plan.entries, selected.tier as u64 + 2);
        assert_eq!(plan.logical_bytes, selected.tier as u64 * 1_048_576);
    }
}

#[test]
fn project_import_cdc_counts_keep_reference_and_shifted_variant_lengths() {
    let original: Vec<_> = reference::dedup_cdc_locality::cases()
        .into_iter()
        .filter(|case| case.tier == 100)
        .collect();
    assert_eq!(original.len(), 5);
    for selected in original {
        let plan = project::import_counts(&selected.id).unwrap().unwrap();
        let per = match selected.kind {
            "insert" => 1_052_672,
            "delete" => 1_044_480,
            _ => 1_048_576,
        };
        assert_eq!(plan.family, "dedup_cdc_locality");
        assert_eq!(plan.files, selected.tier as u64 + 1);
        assert_eq!(plan.directories, 2);
        assert_eq!(plan.entries, selected.tier as u64 + 3);
        assert_eq!(plan.logical_bytes, 1_048_576 + selected.tier as u64 * per);
    }
    let boundary = project::import_counts("dedup-cdc-boundaries-proof")
        .unwrap()
        .unwrap();
    assert_eq!(
        (
            boundary.files,
            boundary.directories,
            boundary.entries,
            boundary.logical_bytes
        ),
        (60, 26, 86, 884_745)
    );
}

#[test]
fn project_import_footprint_counts_use_real_large_object_and_namespace_geometry() {
    for (id, files, directories, bytes) in [
        ("store-footprint-unique-100000", 100_000, 1001, 500_000_000),
        (
            "store-footprint-metadata-cardinality-100000",
            100_000,
            1001,
            500_000_000,
        ),
        ("store-footprint-large-object-500m", 100, 2, 500_000_000),
        ("store-footprint-unique-100-low-v1", 100, 2, 5_000_000),
        (
            "store-footprint-metadata-cardinality-100-low-v1",
            100,
            2,
            5_000_000,
        ),
    ] {
        let plan = project::import_counts(id).unwrap().unwrap();
        assert_eq!(plan.family, "store_footprint");
        assert_eq!(
            (
                plan.files,
                plan.directories,
                plan.entries,
                plan.logical_bytes
            ),
            (files, directories, files + directories, bytes)
        );
    }
}

#[test]
fn project_import_gate_leaves_namespace_and_nonimport_routes_unchanged() {
    for id in [
        "namespace-100-compact-v3",
        "namespace-100000",
        "namespace-10000-text-v1",
        "payload-create-1m-compact-v2",
        "v016-boundary-exact-v1",
        "dedup-cross-file-identical-1",
        "dedup-cross-file-unique-11",
        "store-footprint-large-object-made-up",
        "unknown-case",
    ] {
        assert_eq!(project::import_counts(id).unwrap(), None, "{id}");
    }
}

fn root() -> PathBuf {
    let parent = std::env::var_os("LAYERFS_PROJECT_IMPORT_TEST_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = parent.join(format!("project-import-ack-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    root
}

#[test]
fn project_import_real_disposable_init_ack_rejects_count_root_profile_and_identity_drift() {
    let root = root();
    let source = root.join("native");
    let case = "dedup-cross-file-anchor-1";
    reference::workspace_common::create_fixture(&source, &edit_model::entries(case, 0).unwrap())
        .unwrap();
    let request = InitRequest {
        source,
        store: PersistenceConfig::sqlite(root.join("store.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        locator: "/layerfs-store/global/store.sqlite".into(),
        policy: StoragePolicy::frozen_default(),
        catalog: HistoryCatalogConfig {
            binding_key: b"external-project-import-ack".to_vec(),
            cursor_key: [41; 32],
            incarnation: 1,
        },
        stack: LayerStackId::from_authority([43; 16]),
        stack_name: HistoryName::new("project").unwrap(),
        branch: BranchId::from_authority([47; 16]),
        branch_name: HistoryName::new("main").unwrap(),
        scope_seed: [53; 32],
        deadline: Instant::now() + Duration::from_secs(10),
    };
    let mut initialized = Timing::disabled("external.project.import", |timer| {
        ProjectApi::new().init(request, timer)
    })
    .0
    .unwrap();
    let plan = project::import_counts(case).unwrap().unwrap();
    project::validate_import_ack(plan, &initialized).unwrap();
    assert_eq!(initialized.manifest.profile, StoreProfile::Disposable);
    assert!(initialized.branch.branch.head_commit.is_none());
    assert!(initialized.branch.head_root.is_none());
    for suffix in ["-wal", "-shm", "-journal"] {
        assert!(!root.join(format!("store.sqlite{suffix}")).exists());
    }
    let wrong = ObjectId::for_bytes(b"external wrong acknowledged field");
    let mut rejected = 0;
    macro_rules! mutation {
        ($field:expr, $value:expr) => {{
            let old = $field.clone();
            $field = $value;
            assert!(project::validate_import_ack(plan, &initialized).is_err());
            $field = old;
            rejected += 1;
        }};
    }
    mutation!(initialized.initialized.entries, plan.entries + 1);
    mutation!(initialized.initialized.namespace_work.entries, 0);
    mutation!(initialized.initialized.namespace_work.unique_files, 0);
    mutation!(initialized.initialized.namespace_work.jobs, 0);
    mutation!(initialized.initialized.namespace_work.regular_aliases, 1);
    mutation!(initialized.branch.effective_root, wrong);
    mutation!(initialized.branch.base_root, wrong);
    mutation!(
        initialized.branch.head_root,
        Some(initialized.initialized.root)
    );
    mutation!(
        initialized.branch.branch.stack,
        LayerStackId::from_authority([59; 16])
    );
    mutation!(initialized.branch.scope, wrong);
    mutation!(initialized.branch.profile, wrong);
    mutation!(initialized.manifest.root, wrong.to_bytes());
    mutation!(
        initialized.manifest.branch,
        BranchId::from_authority([61; 16]).to_bytes()
    );
    mutation!(
        initialized.manifest.stack,
        LayerStackId::from_authority([67; 16]).to_bytes()
    );
    // This mutates a closed receipt value only; Durable is never executed.
    mutation!(initialized.manifest.profile, StoreProfile::Durable);
    mutation!(initialized.store.profile, SqlitePersistenceProfile::Durable);
    mutation!(initialized.manifest.bytes, initialized.store.bytes + 1);
    let mut wrong_plan = plan;
    wrong_plan.directories += 1;
    assert!(project::validate_import_ack(wrong_plan, &initialized).is_err());
    assert_eq!(rejected, 17);
    project::validate_import_ack(plan, &initialized).unwrap();

    // The runtime entrypoint must apply its original count guard after the
    // actual public Init, rather than reporting a successful incorrect input.
    let wrong_source = root.join("missing-original-file");
    let directories = edit_model::entries(case, 0)
        .unwrap()
        .into_iter()
        .filter(|entry| {
            matches!(
                entry.kind,
                reference::workspace_common::EntryKind::Directory
            )
        })
        .collect::<Vec<_>>();
    reference::workspace_common::create_fixture(&wrong_source, &directories).unwrap();
    let config = args::Args {
        mode: "init".into(),
        socket: "/unused".into(),
        image: args::IMAGE.into(),
        volume: "unused-native-test".into(),
        executable: "/unused".into(),
        receipt: root.join("wrong-count.events.jsonl"),
        manifest: root.join("wrong-count.manifest"),
        installed_manifest: None,
        uid: 1,
        gid: 1,
        source: Some(wrong_source),
        sealed: Some(root.join("wrong-count.sqlite")),
        init_seconds: 10,
        environment: vec!["LAYERFS_CONSTRUCTION_WORKERS=1".into()],
        observation_scope: [71; 32],
        case: Some(case.into()),
        history_file: None,
        history_step: None,
    };
    let mut events = events::Events::new(&config.receipt).unwrap();
    let refusal = project::initialize(&config, &mut events)
        .unwrap_err()
        .to_string();
    assert!(
        refusal.contains("acknowledged Init counts/Branch root differ"),
        "{refusal}"
    );
    assert!(!config.manifest.exists());
    assert!(!fs::read_to_string(&config.receipt)
        .unwrap()
        .contains("project_init"));
    drop(events);
    fs::remove_dir_all(root).unwrap();
}

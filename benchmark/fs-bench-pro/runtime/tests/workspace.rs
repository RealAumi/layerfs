//! Complete current-format persisted proof over independent frozen byte recipes.
#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
mod namespace;
use layerfs_api::{InitRequest, ProjectApi};
use layerfs_history::{BranchId, HistoryCatalogConfig, HistoryName, LayerStackId};
use layerfs_persistence::{PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::StoragePolicy;
use layerfs_telemetry::timer::Timing;
use std::{
    fs,
    io::Write,
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

fn proof(root: &Path) -> bool {
    let mut child = Command::new(env!("CARGO_BIN_EXE_layerfs-r7-runtime"))
        .args([
            "verify-workspace",
            "--socket",
            "/unused",
            "--volume",
            "unused",
            "--daemon",
            "/unused",
            "--case",
            "payload-create-1m-compact-v2",
            "--uid",
            "1",
            "--gid",
            "1",
        ])
        .arg("--manifest")
        .arg(root.join("manifest"))
        .arg("--sealed")
        .arg(root.join("store.sqlite"))
        .arg("--receipt")
        .arg(root.join("proof.jsonl"))
        .stdout(Stdio::from(
            fs::File::create(root.join("proof.stdout")).unwrap(),
        ))
        .stderr(Stdio::from(
            fs::File::create(root.join("proof.stderr")).unwrap(),
        ))
        .env("LAYERFS_CONSTRUCTION_WORKERS", "1")
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status.success();
        }
        if Instant::now() >= deadline {
            child.kill().unwrap();
            let stop = Instant::now() + Duration::from_secs(1);
            while Instant::now() < stop {
                if child.try_wait().unwrap().is_some() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(5));
            }
            panic!("independent original proof child exceeded bounded deadline");
        }
        std::thread::sleep(Duration::from_millis(5));
    }
}

fn prepared(name: &str, wrong: bool) -> std::path::PathBuf {
    let root =
        std::env::temp_dir().join(format!("fsb-workspace-proof-{name}-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let source = root.join("source");
    let case =
        namespace::reference::workspace_registry::resolve("payload-create-1m-compact-v2").unwrap();
    let entries = namespace::reference::workspace_registry::expected(&case, 1, 1).unwrap();
    namespace::reference::workspace_common::create_fixture(&source, &entries).unwrap();
    if wrong {
        fs::OpenOptions::new()
            .write(true)
            .open(source.join("payload.bin"))
            .unwrap()
            .write_all(b"wrong bytes")
            .unwrap();
        let entry = entries.iter().find(|e| e.path == "payload.bin").unwrap();
        namespace::reference::workspace_common::set_metadata(&source.join("payload.bin"), entry)
            .unwrap();
    }
    let request = InitRequest {
        source,
        store: PersistenceConfig::sqlite(root.join("store.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        locator: "/layerfs-store/global/store.sqlite".into(),
        policy: StoragePolicy::frozen_default(),
        catalog: HistoryCatalogConfig {
            binding_key: b"fsb-independent-proof".to_vec(),
            cursor_key: [23; 32],
            incarnation: 1,
        },
        stack: LayerStackId::from_authority([21; 16]),
        stack_name: HistoryName::new("project").unwrap(),
        branch: BranchId::from_authority([22; 16]),
        branch_name: HistoryName::new("main").unwrap(),
        scope_seed: [24; 32],
        deadline: Instant::now() + Duration::from_secs(5),
    };
    let project = Timing::disabled("test.init", |timer| ProjectApi::new().init(request, timer))
        .0
        .unwrap();
    fs::write(root.join("manifest"), project.manifest.encode().unwrap()).unwrap();
    root
}

#[test]
fn workspace_graph_full_bytes_and_names_match_independent_recipe() {
    let root = prepared("valid", false);
    assert!(proof(&root));
    assert!(fs::read_to_string(root.join("proof.jsonl"))
        .unwrap()
        .contains("\"verified_bytes\":1048576"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn workspace_graph_rejects_corrupted_imported_bytes_with_matching_metadata() {
    let root = prepared("wrong", true);
    assert!(!proof(&root));
    assert!(fs::read_to_string(root.join("proof.stderr"))
        .unwrap()
        .contains("persisted exact bytes differ"));
    fs::remove_dir_all(root).unwrap();
}

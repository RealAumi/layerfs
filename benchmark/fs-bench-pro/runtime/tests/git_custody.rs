//! Offline Git hybrid proof: raw index custody never supplies working-source bytes.
//! Synthetic .git here qualifies only this oracle, never Git semantics or a sample.
#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
mod namespace;
use layerfs_api::{InitRequest, ProjectApi};
use layerfs_history::{BranchId, HistoryCatalogConfig, HistoryName, LayerStackId};
use layerfs_persistence::{PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::StoragePolicy;
use layerfs_telemetry::timer::Timing;
use namespace::reference::workspace_common::{Content, Entry};
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
            "git-tool-1-compact-v2",
            "--uid",
            "1",
            "--gid",
            "1",
        ])
        .arg("--manifest")
        .arg(root.join("manifest"))
        .arg("--sealed")
        .arg(root.join("store.sqlite"))
        .arg("--source-copy")
        .arg(root.join("precommit.tsv"))
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
    let stop = Instant::now() + Duration::from_secs(10);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status.success();
        }
        if Instant::now() >= stop {
            child.kill().unwrap();
            let killed = Instant::now() + Duration::from_secs(1);
            while Instant::now() < killed {
                if child.try_wait().unwrap().is_some() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(5));
            }
            panic!("Git hybrid oracle child exceeded bounded10s deadline");
        }
        std::thread::sleep(Duration::from_millis(5));
    }
}

fn prepared(
    name: &str,
    wrong_index: bool,
    wrong_source: bool,
    replace_source: bool,
    no_index: bool,
) -> std::path::PathBuf {
    let root = std::env::temp_dir().join(format!("fsb-git-custody-{name}-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let source = root.join("source");
    let case = namespace::reference::workspace_registry::resolve("git-tool-1-compact-v2").unwrap();
    let mut entries = namespace::reference::workspace_registry::expected(&case, 1, 1).unwrap();
    let repository = vec![
        Entry::directory("."),
        Entry::directory(".git"),
        Entry::file(
            ".git/index",
            Content::Literal(b"raw index includes every stat-cache byte".to_vec()),
        ),
    ];
    let mut custody = repository.clone();
    if replace_source {
        custody.push(
            entries
                .iter()
                .find(|entry| {
                    entry.path.starts_with("tracked/")
                        && matches!(
                            entry.kind,
                            namespace::reference::workspace_common::EntryKind::File(_)
                        )
                })
                .unwrap()
                .clone(),
        );
        custody.push(Entry::directory("tracked"));
    }
    if no_index {
        custody.retain(|entry| entry.path != ".git/index");
    }
    fs::write(
        root.join("precommit.tsv"),
        namespace::reference::workspace_common::manifest(&custody).unwrap(),
    )
    .unwrap();
    entries.extend(repository.into_iter().filter(|entry| entry.path != "."));
    namespace::reference::workspace_common::create_fixture(&source, &entries).unwrap();
    if wrong_index || wrong_source {
        let path = if wrong_index {
            ".git/index"
        } else {
            entries
                .iter()
                .find(|entry| {
                    entry.path.starts_with("tracked/")
                        && matches!(
                            entry.kind,
                            namespace::reference::workspace_common::EntryKind::File(_)
                        )
                })
                .unwrap()
                .path
                .as_str()
        };
        fs::OpenOptions::new()
            .write(true)
            .open(source.join(path))
            .unwrap()
            .write_all(b"wrong bytes")
            .unwrap();
        namespace::reference::workspace_common::set_metadata(
            &source.join(path),
            entries.iter().find(|entry| entry.path == path).unwrap(),
        )
        .unwrap();
    }
    let request = InitRequest {
        source,
        store: PersistenceConfig::sqlite(root.join("store.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        locator: "/layerfs-store/global/store.sqlite".into(),
        policy: StoragePolicy::frozen_default(),
        catalog: HistoryCatalogConfig {
            binding_key: b"fsb-git-hybrid-proof".to_vec(),
            cursor_key: [33; 32],
            incarnation: 1,
        },
        stack: LayerStackId::from_authority([31; 16]),
        stack_name: HistoryName::new("project").unwrap(),
        branch: BranchId::from_authority([32; 16]),
        branch_name: HistoryName::new("main").unwrap(),
        scope_seed: [34; 32],
        deadline: Instant::now() + Duration::from_secs(10),
    };
    let project = Timing::disabled("test.git-custody.init", |timer| {
        ProjectApi::new().init(request, timer)
    })
    .0
    .unwrap();
    fs::write(root.join("manifest"), project.manifest.encode().unwrap()).unwrap();
    root
}

#[test]
fn complete_raw_index_and_independent_source_pass_authenticated_graph() {
    let root = prepared("valid", false, false, false, false);
    assert!(proof(&root));
    assert!(fs::read_to_string(root.join("proof.jsonl"))
        .unwrap()
        .contains("workspace_verified"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn changed_raw_index_stat_bytes_fail_complete_custody_digest() {
    let root = prepared("index", true, false, false, false);
    assert!(!proof(&root));
    assert!(fs::read_to_string(root.join("proof.stderr"))
        .unwrap()
        .contains("persisted custody digest differs"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn custody_cannot_replace_independent_working_source() {
    let root = prepared("source-replace", false, false, true, false);
    assert!(!proof(&root));
    assert!(fs::read_to_string(root.join("proof.stderr"))
        .unwrap()
        .contains("may not replace independent working source"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn wrong_working_source_is_not_hidden_by_valid_git_custody() {
    let root = prepared("source", false, true, false, false);
    assert!(!proof(&root));
    assert!(fs::read_to_string(root.join("proof.stderr"))
        .unwrap()
        .contains("persisted exact bytes differ"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn missing_raw_index_cannot_be_accepted_as_complete_repository() {
    let root = prepared("missing-index", false, false, false, true);
    assert!(!proof(&root));
    assert!(fs::read_to_string(root.join("proof.stderr"))
        .unwrap()
        .contains("repository/index/cap differs"));
    fs::remove_dir_all(root).unwrap();
}

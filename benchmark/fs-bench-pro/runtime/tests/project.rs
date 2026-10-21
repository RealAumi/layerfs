//! Public host Init is separate from its independent native-content proof.
#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
mod namespace;
use std::{
    fs,
    io::Write,
    os::unix::fs::MetadataExt,
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

fn run(mode: &str, root: &Path) -> bool {
    let stdout = fs::File::create(root.join(format!("{mode}.stdout"))).unwrap();
    let stderr = fs::File::create(root.join(format!("{mode}.stderr"))).unwrap();
    let info = root.metadata().unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_layerfs-r7-runtime"))
        .args([
            mode,
            "--socket",
            "/unused",
            "--volume",
            "unused",
            "--daemon",
            "/unused",
            "--case",
            "namespace-100-compact-v3",
            "--init-seconds",
            "10",
        ])
        .arg("--receipt")
        .arg(root.join(format!("{mode}.jsonl")))
        .arg("--manifest")
        .arg(root.join("manifest"))
        .arg("--source-copy")
        .arg(root.join("source"))
        .arg("--sealed")
        .arg(root.join("store.sqlite"))
        .arg("--uid")
        .arg(info.uid().max(1).to_string())
        .arg("--gid")
        .arg(info.gid().to_string())
        .env("LAYERFS_CONSTRUCTION_WORKERS", "1")
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(12);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status.success();
        }
        if Instant::now() >= deadline {
            child.kill().unwrap();
            let exit_stop = Instant::now() + Duration::from_secs(1);
            while Instant::now() < exit_stop {
                if child.try_wait().unwrap().is_some() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(5));
            }
            panic!("original harness child exceeded bounded test deadline: {mode}");
        }
        std::thread::sleep(Duration::from_millis(5));
    }
}

fn root(name: &str) -> std::path::PathBuf {
    let path = std::env::temp_dir().join(format!("fsb-init-test-{name}-{}", std::process::id()));
    fs::create_dir(&path).unwrap();
    namespace::generate(&path.join("source"), "namespace-100-compact-v3").unwrap();
    path
}

#[test]
fn sdk_init_sealed_public_init_reopens_and_verifies_original_samples() {
    let home = root("complete");
    assert!(run("init", &home));
    assert!(run("verify-init", &home));
    let receipt = fs::read_to_string(home.join("verify-init.jsonl")).unwrap();
    assert!(receipt.contains("project_verified"));
    assert!(receipt.contains("\"status\":\"PASS\""));
    for suffix in ["-wal", "-shm", "-journal"] {
        assert!(!home.join(format!("store.sqlite{suffix}")).exists());
    }
    fs::remove_dir_all(home).unwrap();
}

#[test]
fn sdk_init_independent_oracle_refuses_imported_bytes_that_violate_frozen_fixture() {
    let home = root("wrong-bytes");
    let plan = namespace::reference::namespace_plan("namespace-100-compact-v3").unwrap();
    let index = namespace::samples(&plan)
        .into_iter()
        .find(|i| plan.files[*i].size > 0)
        .unwrap();
    let file = home.join("source").join(&plan.files[index].relative_path);
    fs::OpenOptions::new()
        .write(true)
        .open(&file)
        .unwrap()
        .write_all(b"invalid frozen bytes")
        .unwrap();
    namespace::reference::set_namespace_metadata(&file, false).unwrap();
    assert!(run("init", &home));
    assert!(!run("verify-init", &home));
    assert!(fs::read_to_string(home.join("verify-init.stderr"))
        .unwrap()
        .contains("independent bytes mismatch"));
    fs::remove_dir_all(home).unwrap();
}

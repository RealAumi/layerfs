//! H28 source qualification, never an actual Docker installation or benchmark.
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

use layerfs_bridge::provision::{StoreManifest, StoreProfile};
use layerfs_persistence::SqlitePersistenceProfile;
use std::{
    fs,
    io::Write,
    os::unix::{fs::PermissionsExt, net::UnixStream},
    path::PathBuf,
    time::{Duration, Instant},
};
pub(crate) fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

struct Fixture {
    root: PathBuf,
}
impl Fixture {
    fn new(label: &str) -> Self {
        let root = std::env::temp_dir().join(format!("fsb-h28-{label}-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        Self { root }
    }
    fn args(&self, mode: &str) -> args::Args {
        args::Args {
            mode: mode.into(),
            socket: "/unused".into(),
            image: args::IMAGE.into(),
            volume: "unused-h28-native".into(),
            executable: "/unused".into(),
            receipt: self.root.join("events.jsonl"),
            manifest: self.root.join("host.manifest"),
            uid: 1,
            gid: 1,
            source: Some(self.root.join("source")),
            sealed: Some(self.root.join("store.sqlite")),
            init_seconds: 10,
            environment: vec!["LAYERFS_CONSTRUCTION_WORKERS=1".into()],
            observation_scope: [71; 32],
            case: Some("dedup-cross-file-anchor-1".into()),
            history_file: None,
            history_step: None,
            installed_manifest: (mode == "init-install")
                .then(|| self.root.join("installed.manifest")),
        }
    }
    fn source(&self, config: &args::Args) {
        reference::workspace_common::create_fixture(
            config.source.as_ref().unwrap(),
            &edit_model::entries(config.case.as_deref().unwrap(), 0).unwrap(),
        )
        .unwrap();
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if std::thread::panicking() {
            eprintln!("RETAINED_FAILED_H28_FIXTURE={}", self.root.display());
        } else {
            fs::remove_dir_all(&self.root).unwrap();
        }
    }
}

#[test]
fn h28_input_is_one_bounded_exact_frame_eof_invalid_and_deadline_refuse() {
    for (bytes, valid) in [
        (b"install\n".as_slice(), true),
        (b"INSTALL\n", false),
        (b"installx", false),
        (b"install", false),
        (b"", false),
    ] {
        let (mut writer, mut reader) = UnixStream::pair().unwrap();
        writer.write_all(bytes).unwrap();
        drop(writer);
        assert_eq!(
            project::wait_install(&mut reader, Instant::now() + Duration::from_millis(100)).is_ok(),
            valid
        );
    }
    let (_writer, mut reader) = UnixStream::pair().unwrap();
    let start = Instant::now();
    assert!(
        project::wait_install(&mut reader, start + Duration::from_millis(20))
            .unwrap_err()
            .to_string()
            .contains("deadline")
    );
    assert!(start.elapsed() < Duration::from_secs(1));
}

#[test]
fn h28_installed_output_missing_existing_aliases_refused_before_init() {
    let fixture = Fixture::new("outputs");
    let mut config = fixture.args("init-install");
    assert!(project::install_output(&config).is_ok());
    let original = config.installed_manifest.clone();
    config.installed_manifest = None;
    assert!(project::install_output(&config).is_err());
    config.installed_manifest = Some(config.manifest.clone());
    assert!(project::install_output(&config).is_err());
    config.installed_manifest = config.sealed.clone();
    assert!(project::install_output(&config).is_err());
    config.installed_manifest = original;
    fs::write(config.installed_manifest.as_ref().unwrap(), b"existing").unwrap();
    assert!(project::install_output(&config).is_err());
    assert!(!config.manifest.exists());
    assert!(!config.sealed.as_ref().unwrap().exists());
}

#[test]
fn h28_actual_sealed_project_passes_once_after_original_init_ack_and_bounded_hold() {
    let fixture = Fixture::new("actual");
    let config = fixture.args("init-install");
    fixture.source(&config);
    let (mut writer, mut reader) = UnixStream::pair().unwrap();
    writer.write_all(b"install\n").unwrap();
    let mut events = events::Events::new(&config.receipt).unwrap();
    let mut calls = 0;
    project::initialize_install_with(
        &config,
        &mut events,
        &mut reader,
        |args, actual, out, _events| {
            calls += 1;
            assert_eq!(calls, 1);
            let receipt = fs::read_to_string(&args.receipt)?;
            assert_eq!(receipt.matches("\"event\":\"project_init\"").count(), 1);
            assert!(receipt.contains("\"event\":\"project_install_waiting\""));
            assert!(receipt.contains("\"profile\":\"Disposable/WAL/OFF\""));
            assert!(receipt.contains("\"manifest_sha256\""));
            assert!(receipt.contains("\"branch\""));
            let host = fs::read(&args.manifest)?;
            assert_eq!(host, actual.manifest.encode()?);
            assert_eq!(actual.manifest.daemon_sqlite, None);
            assert_eq!(actual.store.profile, SqlitePersistenceProfile::Disposable);
            assert_eq!(actual.manifest.root, actual.initialized.root.to_bytes());
            assert_eq!(actual.store.path, *args.sealed.as_ref().unwrap());
            assert_eq!(
                actual.manifest.bytes,
                fs::metadata(&actual.store.path)?.len()
            );
            project::install_ready(actual)?;
            // The closure is a protocol-boundary mock; no successful daemon install
            // or populated daemon_sqlite is asserted by this native authoring test.
            fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(out)?
                .write_all(b"mock installer called once")?;
            assert_eq!(fs::read(&args.manifest)?, host);
            Ok(())
        },
    )
    .unwrap();
    assert_eq!(calls, 1);
    drop(events);
    let body = fs::read_to_string(&config.receipt).unwrap();
    let init = body
        .lines()
        .find(|line| line.contains("\"event\":\"project_init\""))
        .unwrap();
    assert!(init.contains("\"span\":{\"clock_id\":\"monotonic\""));
    assert!(init.contains("\"entries\":3"));
    assert!(init.contains("public Init acknowledged; sole Store consumed by seal; no daemon/mount"));
    assert_eq!(
        fs::metadata(&config.manifest).unwrap().permissions().mode() & 0o777,
        0o600
    );
    assert_eq!(
        StoreManifest::decode(&fs::read(&config.manifest).unwrap())
            .unwrap()
            .daemon_sqlite,
        None
    );
}

#[test]
fn h28_old_init_ack_unchanged_and_closed_non_disposable_or_installed_values_refuse() {
    let fixture = Fixture::new("old");
    let config = fixture.args("init");
    fixture.source(&config);
    let mut events = events::Events::new(&config.receipt).unwrap();
    let mut actual = project::initialize_sealed(&config, &mut events).unwrap();
    drop(events);
    project::install_ready(&actual).unwrap();
    // Closed receipt mutations only; Durable is never executed.
    actual.manifest.profile = StoreProfile::Durable;
    assert!(project::install_ready(&actual).is_err());
    actual.manifest.profile = StoreProfile::Disposable;
    actual.store.profile = SqlitePersistenceProfile::Durable;
    assert!(project::install_ready(&actual).is_err());
    actual.store.profile = SqlitePersistenceProfile::Disposable;
    actual.manifest.daemon_sqlite = Some("3.53.2".into());
    assert!(project::install_ready(&actual).is_err());
    actual.manifest.daemon_sqlite = None;
    let body = fs::read_to_string(&config.receipt).unwrap();
    assert_eq!(body.matches("\"event\":\"project_init\"").count(), 1);
    assert!(!body.contains("project_install"));
    assert_eq!(
        fs::read(&config.manifest).unwrap(),
        actual.manifest.encode().unwrap()
    );
    assert!(
        include_str!("../src/project.rs").contains("initialize_sealed(args, events).map(|_| ())")
    );
    assert!(include_str!("../src/fixture.rs").contains("runtime::start(args, project, events)"));
    assert!(include_str!("../src/fixture.rs")
        .contains("original create installation acknowledgement missing"));
    assert!(
        include_str!("../src/runtime.rs").contains("Some(project) => api.create(request, project)")
    );
}

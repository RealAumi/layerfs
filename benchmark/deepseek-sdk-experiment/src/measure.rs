//! Issue 323: first-party public SDK functional driver, no direct runtime/control operations.
use layerfs_api::{
    InitRequest, ManagedSandbox, MountedWorkspace, ProjectApi, SandboxApi, SandboxCreate,
    WorkspaceApi,
};
use layerfs_bridge::{
    daemon_setup::{DaemonLimits, DaemonSetup},
    duplex,
};
use layerfs_history::{
    BranchId, CommitHistoryRequest, CommitStagedOutcome, ForkRequest, ForkSource,
    HistoryCatalogConfig, HistoryName, LayerStackId, Page, WorkspaceId,
};
use layerfs_persistence::{PersistenceConfig, SqlitePersistenceProfile};
use layerfs_sandbox::backend::docker::{Docker, SandboxRequest};
use layerfs_storage::StoragePolicy;
use layerfs_telemetry::timer::Timing;
use std::{
    error::Error,
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;
#[derive(Debug)]
struct RetainedFailure<T: std::fmt::Debug>(T);
impl<T: std::fmt::Debug> std::fmt::Display for RetainedFailure<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:?}", self.0)
    }
}
impl<T: std::fmt::Debug> Error for RetainedFailure<T> {}
fn retain<T: std::fmt::Debug + 'static>(failure: T) -> Box<dyn Error> {
    Box::new(RetainedFailure(failure))
}
struct Log(File, File);
impl Log {
    fn event(&mut self, phase: &str, value: impl std::fmt::Debug) -> Result<()> {
        writeln!(self.0, "{phase}\t{value:?}")?;
        self.0.flush()?;
        println!("{phase}\t{value:?}");
        Ok(())
    }
    fn elapsed(&mut self, phase: &str, ns: u128, ok: bool) -> Result<()> {
        writeln!(self.1, "{phase}\t{ns}\t{ok}")?;
        self.1.flush()?;
        Ok(())
    }
}
fn key() -> Result<[u8; 32]> {
    Ok(duplex::generate_keypair()?.public)
}
fn branch() -> Result<BranchId> {
    let bytes = key()?;
    let mut id = [0; 16];
    id.copy_from_slice(&bytes[..16]);
    Ok(BranchId::from_authority(id))
}
fn setup(
    volume: &str,
    daemon: &Path,
    installed: Option<layerfs_bridge::provision::StoreManifest>,
) -> Result<SandboxCreate> {
    let controller = duplex::generate_keypair()?;
    let peer = duplex::generate_keypair()?;
    Ok(SandboxCreate {
        deployment: SandboxRequest {
            image: std::env::var("ISSUE323_IMAGE").unwrap_or_else(|_| {
                "sha256:378b799ef43343fc64008b6a5ef456dd6bf0cb8f6ea4cec72e7b42dfc17d2cd6".into()
            }),
            store_volume: volume.into(),
            port: 30421,
        },
        setup: DaemonSetup {
            listen: "0.0.0.0:30421".into(),
            private_key: peer.private,
            control_peer: controller.public,
            store: "/layerfs-store/global/store.sqlite".into(),
            overlay: "/layerfs-local/overlay/overlay.sqlite".into(),
            mounts: "/workspaces".into(),
            command_uid: 501,
            command_gid: 20,
            limits: DaemonLimits {
                connections: 4,
                handshake_ms: 2000,
                cache_bytes: 8 * 1024 * 1024,
                namespaces: 8,
                pager_kib: 1024,
                serial_low_water: 256,
            },
            existing_store: installed,
        },
        executable: daemon.into(),
        controller_private: controller.private,
        daemon_peer: peer.public,
        startup_wait: Duration::from_secs(3),
        connect_host: None,
    })
}
fn mounted(
    owner: &mut ManagedSandbox,
    id: BranchId,
    phase: &str,
    log: &mut Log,
) -> Result<MountedWorkspace> {
    let workspace = WorkspaceId::from_authority(key()?)?;
    log.event("WorkspaceApi.mount.attempt", (phase, id))?;
    let clock = Instant::now();
    let result = WorkspaceApi::new(owner).mount(workspace, id);
    let ns = clock.elapsed().as_nanos();
    log.elapsed(phase, ns, result.is_ok())?;
    let value = result.map_err(retain)?;
    log.event("WorkspaceApi.mount.ack", (&value.bound, &value.ready))?;
    Ok(value)
}
fn command(
    owner: &ManagedSandbox,
    mount: &MountedWorkspace,
    case: &Path,
    name: &str,
    label: &str,
    root: &str,
    log: &mut Log,
) -> Result<()> {
    let script = fs::read_to_string(case.join("workloads").join(format!("{name}.sh")))?;
    let argv = vec![
        "/bin/bash".into(),
        "-eu".into(),
        "-o".into(),
        "pipefail".into(),
        "-c".into(),
        script,
    ];
    let env = vec![
        "LAYERFS_CONSTRUCTION_WORKERS=1".into(),
        format!("ISSUE323_FS_ROOT={root}"),
    ];
    let mut stdout = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(case.join("run-1").join(format!("{label}.stdout")))?;
    let mut stderr = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(case.join("run-1").join(format!("{label}.stderr")))?;
    log.event(
        "WorkspaceApi.exec.attempt",
        (label, root, &mount.ready.directory, false),
    )?;
    let all = Instant::now();
    let clock = Instant::now();
    let created = WorkspaceApi::exec(owner, mount, argv, env, false);
    let create_ns = clock.elapsed().as_nanos();
    let created = match created {
        Ok(v) => v,
        Err(e) => {
            log.elapsed(&format!("exec.create.{label}"), create_ns, false)?;
            return Err(retain(e));
        }
    };
    let clock = Instant::now();
    let started = created.start();
    let start_ns = clock.elapsed().as_nanos();
    let attached = match started {
        Ok(v) => v,
        Err(e) => {
            log.elapsed(&format!("exec.start.{label}"), start_ns, false)?;
            return Err(retain(e));
        }
    };
    let (_input, output, handle) = attached.into_parts().map_err(retain)?;
    let clock = Instant::now();
    let copied = output.copy_to(&mut stdout, &mut stderr);
    let stream_ns = clock.elapsed().as_nanos();
    let clock = Instant::now();
    let inspected = handle.inspect();
    let inspect_ns = clock.elapsed().as_nanos();
    let total_ns = all.elapsed().as_nanos();
    log.elapsed(&format!("exec.create.{label}"), create_ns, true)?;
    log.elapsed(&format!("exec.start.{label}"), start_ns, true)?;
    log.elapsed(&format!("exec.streams.{label}"), stream_ns, copied.is_ok())?;
    log.elapsed(
        &format!("exec.inspect.{label}"),
        inspect_ns,
        inspected.is_ok(),
    )?;
    log.elapsed(
        &format!("exec.complete.{label}"),
        total_ns,
        copied.is_ok() && inspected.is_ok(),
    )?;
    let progress = copied.map_err(retain)?;
    let status = inspected.map_err(retain)?;
    log.event("ExecHandle.inspect.ack", (label, progress, &status))?;
    if status.known_root_exit() != Some(0) {
        return Err(format!("original command result {label}: {status:?}").into());
    }
    Ok(())
}
fn terminal(
    owner: &mut ManagedSandbox,
    mount: &MountedWorkspace,
    phase: &str,
    log: &mut Log,
) -> Result<()> {
    let clock = Instant::now();
    let result = WorkspaceApi::new(owner).unmount(mount.bound.token, false);
    let ns = clock.elapsed().as_nanos();
    log.elapsed(phase, ns, result.is_ok())?;
    if result?.is_some() {
        return Err("normal unmount returned force result".into());
    }
    log.event("WorkspaceApi.unmount.ack", mount.bound.token)
}
fn experiment(case: &Path, input: &Path, volume: &str, daemon: &Path, log: &mut Log) -> Result<()> {
    let api = ProjectApi::new();
    let seed = key()?;
    let mut stack = [0; 16];
    stack.copy_from_slice(&seed[..16]);
    let stack = LayerStackId::from_authority(stack);
    let initial = branch()?;
    let request = InitRequest {
        source: input.into(),
        store: PersistenceConfig::sqlite(case.join("run-1/sealed.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        locator: "/layerfs-store/global/store.sqlite".into(),
        policy: StoragePolicy::frozen_default(),
        catalog: HistoryCatalogConfig {
            binding_key: b"issue323-operation-diagnostic".to_vec(),
            cursor_key: duplex::generate_keypair()?.private,
            incarnation: 1,
        },
        stack,
        stack_name: HistoryName::new("deepseek-harness")?,
        branch: initial,
        branch_name: HistoryName::new("bootstrap")?,
        scope_seed: key()?,
        deadline: Instant::now() + Duration::from_secs(90),
    };
    log.event(
        "ProjectApi.init.attempt",
        "diagnostic; complete root; Disposable",
    )?;
    let mut ns = 0;
    let result = Timing::disabled("operation-diagnostic", |timer| {
        let clock = Instant::now();
        let result = api.init(request, timer);
        ns = clock.elapsed().as_nanos();
        result
    })
    .0;
    log.elapsed("project.init", ns, result.is_ok())?;
    let project = result?;
    log.event(
        "ProjectApi.init.ack",
        (
            &project.initialized.root,
            project.initialized.entries,
            project.store.bytes,
            &project.store.sqlite_version,
        ),
    )?;
    use std::os::unix::fs::MetadataExt;
    let meta = fs::metadata(&project.store.path)?;
    log.event("storage.sealed_store", (meta.len(), meta.blocks() * 512))?;
    let sandbox = SandboxApi::new(Docker::new(
        "/Users/yifanxu/.docker/run/docker.sock",
        Duration::from_secs(3),
    )?);
    let request = setup(volume, daemon, None)?;
    log.event("SandboxApi.create.attempt", &request.deployment.image)?;
    let clock = Instant::now();
    let result = sandbox.create(request, &project);
    let ns = clock.elapsed().as_nanos();
    log.elapsed("sandbox.create_install", ns, result.is_ok())?;
    let mut owner = result?;
    log.event(
        "SandboxApi.create.ack",
        (owner.runtime.identity().to_string(), &owner.startup.phase),
    )?;
    if let Some(installed) = &owner.installed {
        log.event(
            "install.work",
            (
                &installed.work,
                &installed.manifest.host_sqlite,
                &installed.manifest.daemon_sqlite,
            ),
        )?;
    }
    let page = Page {
        cursor: None,
        limit: 16,
    };
    let clock = Instant::now();
    let result = api.branches(&mut owner, stack, page);
    let ns = clock.elapsed().as_nanos();
    log.elapsed("project.branches", ns, result.is_ok())?;
    log.event("ProjectApi.branches.ack", result?)?;
    let selected = branch()?;
    let request = ForkRequest {
        stack,
        branch: selected,
        name: HistoryName::new("measured")?,
        source: ForkSource::Layer(project.branch.branch.base_layer),
    };
    let clock = Instant::now();
    let result = api.fork(&mut owner, request);
    let ns = clock.elapsed().as_nanos();
    log.elapsed("project.fork", ns, result.is_ok())?;
    log.event("ProjectApi.fork.ack", result?)?;
    let mount = mounted(&mut owner, selected, "workspace.mount", log)?;
    command(
        &owner,
        &mount,
        case,
        "native-clone",
        "setup-native-clone",
        "/layerfs-store/native-run",
        log,
    )?;
    command(
        &owner,
        &mount,
        case,
        "native-census",
        "setup-native-census",
        "/layerfs-store/native-run",
        log,
    )?;
    for name in ["read", "mutation", "compile"] {
        for (arm, root) in [("native", "/layerfs-store/native-run"), ("fuse", ".")] {
            command(
                &owner,
                &mount,
                case,
                name,
                &format!("{arm}-{name}"),
                root,
                log,
            )?;
        }
    }
    let token = mount.bound.token;
    let clock = Instant::now();
    let result = WorkspaceApi::new(&mut owner).commit(token);
    let ns = clock.elapsed().as_nanos();
    log.elapsed("workspace.commit_changed", ns, result.is_ok())?;
    let record = match result? {
        CommitStagedOutcome::Committed(v) => v,
        other => return Err(format!("expected original changed Commit: {other:?}").into()),
    };
    log.event("WorkspaceApi.commit.ack", &record)?;
    let clock = Instant::now();
    let result = WorkspaceApi::new(&mut owner).status(token);
    let ns = clock.elapsed().as_nanos();
    log.elapsed("workspace.status", ns, result.is_ok())?;
    log.event("WorkspaceApi.status.ack", result?)?;
    command(
        &owner,
        &mount,
        case,
        "verify",
        "verify-native",
        "/layerfs-store/native-run",
        log,
    )?;
    command(&owner, &mount, case, "verify", "verify-fuse", ".", log)?;
    terminal(&mut owner, &mount, "workspace.unmount", log)?;
    let fresh = mounted(&mut owner, selected, "workspace.mount_fresh", log)?;
    if fresh.bound.binding.effective_root != record.root {
        return Err("original remount root differs".into());
    }
    command(
        &owner,
        &fresh,
        case,
        "verify-fresh",
        "verify-fuse-fresh",
        ".",
        log,
    )?;
    let request = CommitHistoryRequest {
        branch: selected,
        start: Some(record.id),
        cursor: None,
        limit: 16,
    };
    let clock = Instant::now();
    let result = api.commits(&mut owner, request);
    let ns = clock.elapsed().as_nanos();
    log.elapsed("project.commits", ns, result.is_ok())?;
    let page = result?;
    if page.records != vec![record.clone()] {
        return Err("exact history differs".into());
    }
    log.event("ProjectApi.commits.ack", page)?;
    let clock = Instant::now();
    let result = WorkspaceApi::new(&mut owner).commit(fresh.bound.token);
    let ns = clock.elapsed().as_nanos();
    log.elapsed("workspace.commit_uptodate", ns, result.is_ok())?;
    let unchanged = result?;
    if !matches!(unchanged,CommitStagedOutcome::UpToDate {root,..} if root==record.root) {
        return Err("original UpToDate differs".into());
    }
    log.event("WorkspaceApi.commit.original", unchanged)?;
    terminal(&mut owner, &fresh, "workspace.unmount_final", log)?;
    log.event(
        "SandboxApi.close.attempt",
        owner.runtime.identity().to_string(),
    )?;
    let clock = Instant::now();
    let result = sandbox.close(owner);
    let ns = clock.elapsed().as_nanos();
    log.elapsed("sandbox.close", ns, result.is_ok())?;
    result?;
    log.event(
        "SandboxApi.close.ack",
        "SDK stop/delete; borrowed volume retained",
    )?;
    log.event(
        "DIAGNOSTIC",
        "functional PASS; numeric cache INCOMPLETE/INELIGIBLE; no speed ratio",
    )
}
fn main() -> Result<()> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 4 {
        return Err("args: fresh-case prepared-input empty-volume sealed-daemon".into());
    }
    let case = PathBuf::from(&args[0]);
    fs::create_dir(case.join("run-1"))?;
    let mut log = Log(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(case.join("run-1/sdk-calls.tsv"))?,
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(case.join("run-1/timings.tsv"))?,
    );
    let result = experiment(
        &case,
        Path::new(&args[1]),
        &args[2],
        Path::new(&args[3]),
        &mut log,
    );
    if let Err(error) = &result {
        log.event(
            "DIAGNOSTIC.FAIL",
            format!("original={error}; no replay/automatic cleanup; original owners retained"),
        )?;
    }
    result
}

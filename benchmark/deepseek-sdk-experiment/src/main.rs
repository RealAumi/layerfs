//! Issue 323: first-party public SDK functional driver, no direct runtime/control operations.
use layerfs_api::{
    InitRequest, ManagedSandbox, MountedWorkspace, OperationCause, ProjectApi, SandboxApi,
    SandboxCreate, SealedProject, WorkspaceApi,
};
use layerfs_bridge::{
    control::ControlCode,
    daemon_setup::{DaemonLimits, DaemonSetup},
    duplex,
};
use layerfs_history::{
    BranchId, CommitHistoryRequest, CommitRecord, CommitStagedOutcome, ForkRequest, ForkSource,
    HistoryCatalogConfig, HistoryName, LayerStackId, Page, WorkspaceId,
};
use layerfs_persistence::{PersistenceConfig, SqlitePersistenceProfile};
use layerfs_sandbox::backend::docker::{Docker, ExecHandle, RuntimeOutput, SandboxRequest};
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
type Running = (RuntimeOutput, ExecHandle);
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
struct Log(File);
impl Log {
    fn event(&mut self, phase: &str, value: impl std::fmt::Debug) -> Result<()> {
        writeln!(self.0, "{phase}\t{value:?}")?;
        self.0.flush()?;
        println!("{phase}\t{value:?}");
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
            image: "sha256:378b799ef43343fc64008b6a5ef456dd6bf0cb8f6ea4cec72e7b42dfc17d2cd6".into(),
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
fn create(
    api: &SandboxApi,
    project: &SealedProject,
    request: SandboxCreate,
    log: &mut Log,
) -> Result<ManagedSandbox> {
    log.event(
        "SandboxApi.create.attempt",
        "original SDK create/install or reopen",
    )?;
    let owner = api.create(request, project)?;
    log.event(
        "SandboxApi.create.ack",
        (
            owner.runtime.identity().to_string(),
            &owner.startup.phase,
            owner.installed.is_some(),
        ),
    )?;
    Ok(owner)
}
fn mount(owner: &mut ManagedSandbox, id: BranchId, log: &mut Log) -> Result<MountedWorkspace> {
    log.event("WorkspaceApi.mount.attempt", id)?;
    let mounted = WorkspaceApi::new(owner)
        .mount(WorkspaceId::from_authority(key()?)?, id)
        .map_err(retain)?;
    log.event("WorkspaceApi.mount.ack", (&mounted.bound, &mounted.ready))?;
    Ok(mounted)
}
fn start(
    owner: &ManagedSandbox,
    mounted: &MountedWorkspace,
    script: &str,
    log: &mut Log,
) -> Result<Running> {
    log.event(
        "WorkspaceApi.exec.attempt",
        "ordinary mounted Bash; explicit test watchdog in script",
    )?;
    let created = WorkspaceApi::exec(
        owner,
        mounted,
        vec![
            "/bin/bash".into(),
            "-eu".into(),
            "-o".into(),
            "pipefail".into(),
            "-c".into(),
            script.into(),
        ],
        vec!["LAYERFS_CONSTRUCTION_WORKERS=1".into()],
        false,
    )
    .map_err(retain)?;
    log.event("ExecCreated.start.attempt", "returned SDK handle")?;
    let attached = created.start().map_err(retain)?;
    let (_input, output, handle) = attached.into_parts().map_err(retain)?;
    Ok((output, handle))
}
fn finish(running: Running, label: &str, out: &Path, log: &mut Log) -> Result<()> {
    let (output, handle) = running;
    let mut stdout = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(out.join(format!("{label}.stdout")))?;
    let mut stderr = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(out.join(format!("{label}.stderr")))?;
    let streams = output.copy_to(&mut stdout, &mut stderr).map_err(retain)?;
    let status = handle.inspect().map_err(retain)?;
    log.event("ExecHandle.inspect.ack", (label, streams, &status))?;
    if status.known_root_exit() != Some(0) {
        return Err(format!("nonzero or unknown original command {label}: {status:?}").into());
    }
    Ok(())
}
fn command(
    owner: &ManagedSandbox,
    mounted: &MountedWorkspace,
    label: &str,
    out: &Path,
    log: &mut Log,
) -> Result<()> {
    let script = fs::read_to_string(
        out.parent()
            .ok_or("output parent")?
            .join("workloads")
            .join(format!("{label}.sh")),
    )?;
    finish(start(owner, mounted, &script, log)?, label, out, log)
}
fn commit(
    owner: &mut ManagedSandbox,
    mounted: &MountedWorkspace,
    label: &str,
    log: &mut Log,
) -> Result<CommitRecord> {
    log.event("WorkspaceApi.commit.attempt", label)?;
    match WorkspaceApi::new(owner).commit(mounted.bound.token)? {
        CommitStagedOutcome::Committed(record) => {
            log.event("WorkspaceApi.commit.ack", (label, &record))?;
            Ok(record)
        }
        other => Err(format!("expected changed Commit at {label}, got {other:?}").into()),
    }
}
fn unmount(owner: &mut ManagedSandbox, mounted: &MountedWorkspace, log: &mut Log) -> Result<()> {
    log.event("WorkspaceApi.unmount.attempt", mounted.bound.token)?;
    let outcome = WorkspaceApi::new(owner).unmount(mounted.bound.token, false)?;
    if outcome.is_some() {
        return Err("unexpected forced outcome on normal unmount".into());
    }
    log.event("WorkspaceApi.unmount.ack", mounted.bound.token)
}
fn status(owner: &mut ManagedSandbox, mounted: &MountedWorkspace, log: &mut Log) -> Result<()> {
    let state = WorkspaceApi::new(owner).status(mounted.bound.token)?;
    log.event("WorkspaceApi.status.ack", state)
}
fn experiment(out: &Path, source: &Path, volume: &str, daemon: &Path, log: &mut Log) -> Result<()> {
    let project_api = ProjectApi::new();
    let stack_seed = key()?;
    let mut stack = [0; 16];
    stack.copy_from_slice(&stack_seed[..16]);
    let stack = LayerStackId::from_authority(stack);
    let initial = branch()?;
    let request = InitRequest {
        source: source.into(),
        store: PersistenceConfig::sqlite(out.join("sealed.sqlite"))
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        locator: "/layerfs-store/global/store.sqlite".into(),
        policy: StoragePolicy::frozen_default(),
        catalog: HistoryCatalogConfig {
            binding_key: b"issue323-sdk-only".to_vec(),
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
        "complete prepared source; explicit Disposable; fresh output",
    )?;
    let project = Timing::disabled("sdk-functional-init", |timer| {
        project_api.init(request, timer)
    })
    .0?;
    log.event(
        "ProjectApi.init.ack",
        (
            &project.initialized.root,
            project.initialized.entries,
            &project.initialized.namespace_work,
            project.store.bytes,
        ),
    )?;
    let api = SandboxApi::new(Docker::new(
        "/Users/yifanxu/.docker/run/docker.sock",
        Duration::from_secs(3),
    )?);
    let mut owner = create(&api, &project, setup(volume, daemon, None)?, log)?;
    let installed = owner
        .installed
        .as_ref()
        .ok_or("SDK create did not acknowledge installation")?
        .manifest
        .clone();
    let list = project_api.branches(
        &mut owner,
        stack,
        Page {
            cursor: None,
            limit: 16,
        },
    )?;
    if !list.records.iter().any(|r| r.id == initial) {
        return Err("SDK Branch list omitted bootstrap".into());
    }
    log.event("ProjectApi.branches.ack", &list)?;
    let test_branch = branch()?;
    let forked = project_api.fork(
        &mut owner,
        ForkRequest {
            stack,
            branch: test_branch,
            name: HistoryName::new("sdk-experiment")?,
            source: ForkSource::Layer(project.branch.branch.base_layer),
        },
    )?;
    if forked.effective_root != project.initialized.root {
        return Err("fork root differs from acknowledged Init".into());
    }
    log.event("ProjectApi.fork.ack", &forked)?;
    let mut mounted = mount(&mut owner, test_branch, log)?;
    command(&owner, &mounted, "verify-initial", out, log)?;
    status(&mut owner, &mounted, log)?;
    log.event(
        "CASE.E01",
        "PASS: Init/install/list/fork/mount and initial independent content checks",
    )?;
    command(&owner, &mounted, "edit-source", out, log)?;
    let c1 = commit(&mut owner, &mounted, "E02-source", log)?;
    command(&owner, &mounted, "verify-source", out, log)?;
    unmount(&mut owner, &mounted, log)?;
    mounted = mount(&mut owner, test_branch, log)?;
    command(&owner, &mounted, "verify-source-fresh", out, log)?;
    let unchanged = WorkspaceApi::new(&mut owner).commit(mounted.bound.token)?;
    if !matches!(unchanged,CommitStagedOutcome::UpToDate{root,..} if root==c1.root) {
        return Err(format!("no-change result {unchanged:?}").into());
    }
    log.event("WorkspaceApi.commit.UpToDate.ack", unchanged)?;
    log.event(
        "CASE.E02",
        "PASS: source edit, Commit, normal remount, exact content, UpToDate",
    )?;
    command(&owner, &mounted, "small-files", out, log)?;
    let c2 = commit(&mut owner, &mounted, "M01-burst", log)?;
    if c2.parent != Some(c1.id) {
        return Err("second Commit parent differs".into());
    }
    unmount(&mut owner, &mounted, log)?;
    mounted = mount(&mut owner, test_branch, log)?;
    command(&owner, &mounted, "verify-small-fresh", out, log)?;
    log.event(
        "CASE.M01",
        "PASS: 256 created,64 renamed,64 deleted;192 exact fresh files",
    )?;
    command(&owner, &mounted, "large-patch", out, log)?;
    let c3 = commit(&mut owner, &mounted, "M02-patch", log)?;
    command(&owner, &mounted, "verify-large", out, log)?;
    command(&owner, &mounted, "later-edit", out, log)?;
    let c4 = commit(&mut owner, &mounted, "M02-later", log)?;
    if c3.parent != Some(c2.id) || c4.parent != Some(c3.id) {
        return Err("later Commit chain differs".into());
    }
    unmount(&mut owner, &mounted, log)?;
    mounted = mount(&mut owner, test_branch, log)?;
    command(&owner, &mounted, "verify-final-fresh", out, log)?;
    let history = project_api.commits(
        &mut owner,
        CommitHistoryRequest {
            branch: test_branch,
            start: Some(c4.id),
            cursor: None,
            limit: 16,
        },
    )?;
    if history.records.iter().map(|r| r.id).collect::<Vec<_>>() != vec![c4.id, c3.id, c2.id, c1.id]
    {
        return Err(format!("unexpected SDK history {history:?}").into());
    }
    log.event("ProjectApi.commits.ack", history)?;
    log.event(
        "CASE.M02",
        "PASS: full 9144216B hash after4096B patch, later edit, fresh mount and4Commit ancestry",
    )?;
    unmount(&mut owner, &mounted, log)?;
    log.event(
        "SandboxApi.close.attempt",
        owner.runtime.identity().to_string(),
    )?;
    api.close(owner)?;
    log.event("SandboxApi.close.ack", "stopped and deleted by SDK")?;
    let mut owner = create(&api, &project, setup(volume, daemon, Some(installed))?, log)?;
    let mounted = mount(&mut owner, test_branch, log)?;
    command(&owner, &mounted, "verify-reopen", out, log)?;
    log.event(
        "CASE.E03",
        "PASS: SDK close/reopen existing installation; full expected modified state",
    )?;
    let holder_script = fs::read_to_string(
        out.parent()
            .ok_or("output parent")?
            .join("workloads/holder.sh"),
    )?;
    let holder = start(&owner, &mounted, &holder_script, log)?;
    command(&owner, &mounted, "holder-ready", out, log)?;
    let refusal = WorkspaceApi::new(&mut owner)
        .unmount(mounted.bound.token, false)
        .expect_err("live holder must refuse unmount");
    if !matches!(&refusal.cause,OperationCause::Remote(r) if r.code==ControlCode::Busy) {
        return Err(format!("unexpected unmount refusal {refusal:?}").into());
    }
    log.event("WorkspaceApi.unmount.expectedBusy", refusal)?;
    status(&mut owner, &mounted, log)?;
    command(&owner, &mounted, "holder-release", out, log)?;
    finish(holder, "holder", out, log)?;
    unmount(&mut owner, &mounted, log)?;
    log.event(
        "CASE.H01",
        "PASS: Busy preserves mount; explicit holder release, then normal unmount",
    )?;
    log.event(
        "SandboxApi.close.attempt",
        owner.runtime.identity().to_string(),
    )?;
    api.close(owner)?;
    log.event(
        "SandboxApi.close.ack",
        "stopped/deleted; no direct Docker lifecycle calls",
    )?;
    log.event(
        "CAMPAIGN",
        "SCOPED_PASS; M03/M04/H02/H03/H04 NOT_RUN; zero performance samples",
    )
}
fn main() -> Result<()> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() != 4 {
        return Err(
            "args: fresh-output prepared-source existing-empty-volume sealed-daemon".into(),
        );
    }
    let out = PathBuf::from(&args[0]);
    fs::create_dir(&out)?;
    let mut log = Log(OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(out.join("sdk-calls.tsv"))?);
    let result = experiment(
        &out,
        Path::new(&args[1]),
        &args[2],
        Path::new(&args[3]),
        &mut log,
    );
    if let Err(error) = &result {
        log.event("CAMPAIGN.FAIL",format!("original={error}; retained resources are not automatically replayed/closed/deleted"))?;
    }
    result
}

//! Issue 323: first-party public SDK functional driver, no direct runtime/control operations.
use layerfs_api::{
    InitRequest, ManagedSandbox, MountedWorkspace, ProjectApi, SandboxApi, SandboxCreate,
    SealedProject, WorkspaceApi,
};
use layerfs_bridge::{
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
    log.event("SandboxApi.create.image", &request.deployment.image)?;
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
    finish_expected(running, label, out, log, 0)
}
fn finish_expected(
    running: Running,
    label: &str,
    out: &Path,
    log: &mut Log,
    expected: i32,
) -> Result<()> {
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
    if status.known_root_exit() != Some(expected) {
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

fn history(
    owner: &mut ManagedSandbox,
    id: BranchId,
    records: &[CommitRecord],
    log: &mut Log,
) -> Result<()> {
    let page = ProjectApi::new().commits(
        owner,
        CommitHistoryRequest {
            branch: id,
            start: Some(records[0].id),
            cursor: None,
            limit: 16,
        },
    )?;
    log.event("ProjectApi.commits.ack", &page)?;
    if page.records != records {
        return Err("exact history differs".into());
    }
    Ok(())
}
fn body(out: &Path, name: &str) -> Result<String> {
    Ok(fs::read_to_string(
        out.parent()
            .ok_or("parent")?
            .join("workloads")
            .join(format!("{name}.sh")),
    )?)
}
fn close(api: &SandboxApi, owner: ManagedSandbox, log: &mut Log) -> Result<()> {
    log.event(
        "SandboxApi.close.attempt",
        owner.runtime.identity().to_string(),
    )?;
    api.close(owner)?;
    log.event(
        "SandboxApi.close.ack",
        "stopped/deleted by SDK; borrowed volume retained",
    )
}
fn sustained(
    api: &SandboxApi,
    mut owner: ManagedSandbox,
    id: BranchId,
    out: &Path,
    log: &mut Log,
) -> Result<()> {
    let mounted = mount(&mut owner, id, log)?;
    let mut records: Vec<CommitRecord> = Vec::new();
    for cycle in 0..6 {
        let label = format!("mutate-{cycle}");
        let running = start(&owner, &mounted, &body(out, &label)?, log)?;
        if cycle == 2 {
            finish_expected(running, &label, out, log, 23)?;
        } else {
            finish(running, &label, out, log)?;
        }
        let record = commit(&mut owner, &mounted, &format!("H04-cycle-{cycle}"), log)?;
        if record.parent != records.last().map(|r| r.id) {
            return Err("cycle parent differs".into());
        }
        records.push(record);
        command(&owner, &mounted, &format!("verify-{cycle}"), out, log)?;
        status(&mut owner, &mounted, log)?;
    }
    unmount(&mut owner, &mounted, log)?;
    let fresh = mount(&mut owner, id, log)?;
    if fresh.bound.binding.effective_root != records.last().ok_or("records")?.root {
        return Err("final root differs".into());
    }
    command(&owner, &fresh, "verify-final", out, log)?;
    records.reverse();
    history(&mut owner, id, &records, log)?;
    let outcome = WorkspaceApi::new(&mut owner).commit(fresh.bound.token)?;
    log.event("WorkspaceApi.commit.original", &outcome)?;
    if !matches!(outcome, CommitStagedOutcome::UpToDate { root, .. } if root == records[0].root) {
        return Err("final UpToDate differs".into());
    }
    unmount(&mut owner, &fresh, log)?;
    close(api, owner, log)?;
    log.event("CHECKPOINT", "H04 PASS: six cycles, expected command exit23 retained, exact frontiers/history, normal cleanup")
}
fn isolation(
    api: &SandboxApi,
    mut owner: ManagedSandbox,
    project: &SealedProject,
    stack: LayerStackId,
    first: BranchId,
    out: &Path,
    log: &mut Log,
) -> Result<()> {
    let second = branch()?;
    let forked = ProjectApi::new().fork(
        &mut owner,
        ForkRequest {
            stack,
            branch: second,
            name: HistoryName::new("isolation-second")?,
            source: ForkSource::Layer(project.branch.branch.base_layer),
        },
    )?;
    log.event("ProjectApi.fork.ack", &forked)?;
    let a = mount(&mut owner, first, log)?;
    let b = mount(&mut owner, second, log)?;
    let ar = start(&owner, &a, &body(out, "mutate-a")?, log)?;
    let br = start(&owner, &b, &body(out, "mutate-b")?, log)?;
    finish(ar, "mutate-a", out, log)?;
    finish(br, "mutate-b", out, log)?;
    // Ordinary-process monotonic intervals are from the same Linux kernel.
    let interval = |name: &str| -> Result<(u128, u128)> {
        let text = fs::read_to_string(out.join(format!("{name}.stdout")))?;
        let values = text
            .split_whitespace()
            .map(str::parse::<u128>)
            .collect::<std::result::Result<Vec<_>, _>>()?;
        if values.len() != 2 {
            return Err("interval shape".into());
        }
        Ok((values[0], values[1]))
    };
    let ai = interval("mutate-a")?;
    let bi = interval("mutate-b")?;
    log.event("H03.ordinary_process_intervals", (ai, bi))?;
    if ai.0.max(bi.0) >= ai.1.min(bi.1) {
        return Err("ordinary commands did not overlap".into());
    }
    let ca = commit(&mut owner, &a, "H03-branch-a", log)?;
    let cb = commit(&mut owner, &b, "H03-branch-b", log)?;
    if ca.parent.is_some() || cb.parent.is_some() || ca.root == cb.root {
        return Err("isolated first Commits differ".into());
    }
    command(&owner, &a, "verify-a", out, log)?;
    command(&owner, &b, "verify-b", out, log)?;
    history(&mut owner, first, &[ca.clone()], log)?;
    history(&mut owner, second, &[cb.clone()], log)?;
    unmount(&mut owner, &a, log)?;
    unmount(&mut owner, &b, log)?;
    let a = mount(&mut owner, first, log)?;
    let b = mount(&mut owner, second, log)?;
    if a.bound.binding.effective_root != ca.root || b.bound.binding.effective_root != cb.root {
        return Err("isolation remount roots differ".into());
    }
    command(&owner, &a, "verify-a-fresh", out, log)?;
    command(&owner, &b, "verify-b-fresh", out, log)?;
    unmount(&mut owner, &a, log)?;
    unmount(&mut owner, &b, log)?;
    close(api, owner, log)?;
    log.event("CHECKPOINT","H03 PASS: two Branches/Workspaces, verified command overlap, distinct saved bytes/history and cleanup")
}
fn concurrent(
    api: &SandboxApi,
    mut owner: ManagedSandbox,
    stack: LayerStackId,
    id: BranchId,
    out: &Path,
    log: &mut Log,
) -> Result<()> {
    let mounted = mount(&mut owner, id, log)?;
    command(&owner, &mounted, "mutate", out, log)?;
    let script = fs::read_to_string(out.parent().ok_or("parent")?.join("workloads/writer.py"))?;
    log.event(
        "WorkspaceApi.exec.attempt",
        ("H02 writer", "stdin explicitly enabled"),
    )?;
    let created = WorkspaceApi::exec(
        &owner,
        &mounted,
        vec![
            "/usr/bin/timeout".into(),
            "15s".into(),
            "python3".into(),
            "-u".into(),
            "-c".into(),
            script,
        ],
        vec!["LAYERFS_CONSTRUCTION_WORKERS=1".into()],
        true,
    )
    .map_err(retain)?;
    log.event("ExecCreated.start.attempt", "returned public handle")?;
    let attached = created.start().map_err(retain)?;
    let (mut input, output, handle) = attached.into_parts().map_err(retain)?;
    let (send, receive) = std::sync::mpsc::channel();
    let started = Instant::now();
    let (c1, ended, writer_end) = std::thread::scope(|scope| -> Result<_> {
        let writer = scope.spawn(move || {
            (|| -> Result<Instant> {
                receive.recv_timeout(Duration::from_secs(2))?;
                std::thread::sleep(Duration::from_millis(100));
                input.write_all(b"write-later\n")?;
                let receipt = input.close().map_err(retain)?;
                // stdin completion is retained separately from actual command exit.
                let mut worker_log = Log(OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(out.join("writer-calls.tsv"))?);
                worker_log.event("RuntimeInput.close.ack", receipt)?;
                finish((output, handle), "writer", out, &mut worker_log)?;
                Ok(Instant::now())
            })()
            .map_err(|e| e.to_string())
        });
        send.send(())?;
        let result = commit(&mut owner, &mounted, "H02-captured-before-later-write", log);
        let ended = Instant::now();
        // Always join the bounded writer, including an original Commit failure.
        let writer_end = writer
            .join()
            .map_err(|_| "writer thread panic")?
            .map_err(|e| e.to_string())?;
        Ok((result?, ended, writer_end))
    })?;
    log.event(
        "H02.verified_overlap",
        (
            started.elapsed().as_nanos(),
            writer_end.duration_since(started).as_nanos(),
            ended.duration_since(started).as_nanos(),
        ),
    )?;
    if writer_end >= ended {
        return Err(
            "H02 interleaving prerequisite: writer exit not observed before Commit result".into(),
        );
    }
    command(&owner, &mounted, "verify-later", out, log)?;
    let frozen = branch()?;
    let forked = ProjectApi::new().fork(
        &mut owner,
        ForkRequest {
            stack,
            branch: frozen,
            name: HistoryName::new("captured-frontier")?,
            source: ForkSource::Commit {
                branch: id,
                commit: c1.id,
            },
        },
    )?;
    log.event("ProjectApi.fork.ack", &forked)?;
    let captured = mount(&mut owner, frozen, log)?;
    command(&owner, &captured, "verify-captured", out, log)?;
    unmount(&mut owner, &captured, log)?;
    let c2 = commit(&mut owner, &mounted, "H02-later-active", log)?;
    if c2.parent != Some(c1.id) {
        return Err("H02 second parent differs".into());
    }
    command(&owner, &mounted, "verify-later-installed", out, log)?;
    history(&mut owner, id, &[c2.clone(), c1], log)?;
    unmount(&mut owner, &mounted, log)?;
    let fresh = mount(&mut owner, id, log)?;
    if fresh.bound.binding.effective_root != c2.root {
        return Err("H02 final root differs".into());
    }
    command(&owner, &fresh, "verify-later-fresh", out, log)?;
    unmount(&mut owner, &fresh, log)?;
    close(api, owner, log)?;
    log.event("CHECKPOINT","H02 PASS: exact captured root excludes later write, writer exit before Commit reply, active bytes retained through install and second Commit/remount")
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
    let case = out
        .parent()
        .and_then(Path::file_name)
        .and_then(|v| v.to_str())
        .ok_or("case directory")?;
    if case == "H04" {
        return sustained(&api, owner, test_branch, out, log);
    }
    if case == "H03" {
        return isolation(&api, owner, &project, stack, test_branch, out, log);
    }
    if case == "H02" {
        return concurrent(&api, owner, stack, test_branch, out, log);
    }
    let mut mounted = mount(&mut owner, test_branch, log)?;
    command(&owner, &mounted, "mutate", out, log)?;
    if case.starts_with("M03-") {
        command(&owner, &mounted, "test", out, log)?;
        command(&owner, &mounted, "verify-before", out, log)?;
    }
    let record = commit(&mut owner, &mounted, "checkpoint", log)?;
    if record.parent.is_some() {
        return Err("fresh Branch Commit has unexpected parent".into());
    }
    command(&owner, &mounted, "verify", out, log)?;
    status(&mut owner, &mounted, log)?;
    unmount(&mut owner, &mounted, log)?;
    mounted = mount(&mut owner, test_branch, log)?;
    if mounted.bound.binding.effective_root != record.root {
        return Err("remounted root differs".into());
    }
    command(&owner, &mounted, "verify-fresh", out, log)?;
    let history = project_api.commits(
        &mut owner,
        CommitHistoryRequest {
            branch: test_branch,
            start: Some(record.id),
            cursor: None,
            limit: 16,
        },
    )?;
    log.event("ProjectApi.commits.ack", &history)?;
    if history.records != vec![record.clone()] {
        return Err("exact one-Commit history differs".into());
    }
    let unchanged = WorkspaceApi::new(&mut owner).commit(mounted.bound.token)?;
    log.event("WorkspaceApi.commit.original", &unchanged)?;
    if !matches!(unchanged, CommitStagedOutcome::UpToDate { root, .. } if root == record.root) {
        return Err("no-change Commit differs".into());
    }
    unmount(&mut owner, &mounted, log)?;
    log.event(
        "SandboxApi.close.attempt",
        owner.runtime.identity().to_string(),
    )?;
    api.close(owner)?;
    log.event(
        "SandboxApi.close.ack",
        "stopped/deleted by SDK; borrowed volume retained",
    )?;
    log.event(
        "CHECKPOINT",
        "PASS: exact workload oracle, same/fresh mount, history and cleanup",
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

use crate::{args::Args, events::Events, Result};
use layerfs_api::{ManagedSandbox, MountedWorkspace, SandboxApi, SandboxCreate, WorkspaceApi};
use layerfs_bridge::{
    daemon_setup::{DaemonLimits, DaemonSetup},
    duplex,
    provision::StoreManifest,
};
use layerfs_sandbox::{
    backend::docker::{Docker, ExecRequest},
    CommandIdentity,
};
use std::{
    fs,
    net::{SocketAddr, TcpStream},
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

pub fn start(
    args: &Args,
    project: &layerfs_api::SealedProject,
    events: &mut Events,
) -> Result<ManagedSandbox> {
    Ok(start_inner(args, None, Some(project), events)?.0)
}

/// Private authentication material retained only for original extra channels.
pub struct RuntimeKeys {
    controller_private: [u8; 32],
    daemon_peer: [u8; 32],
    endpoint: Option<SocketAddr>,
}

pub fn start_with_keys(
    args: &Args,
    manifest: Option<StoreManifest>,
    events: &mut Events,
) -> Result<(ManagedSandbox, RuntimeKeys)> {
    start_inner(args, manifest, None, events)
}
fn start_inner(
    args: &Args,
    manifest: Option<StoreManifest>,
    project: Option<&layerfs_api::SealedProject>,
    events: &mut Events,
) -> Result<(ManagedSandbox, RuntimeKeys)> {
    let controller = duplex::generate_keypair()?;
    let daemon = duplex::generate_keypair()?;
    let setup = DaemonSetup {
        listen: "0.0.0.0:30421".into(),
        private_key: daemon.private,
        control_peer: controller.public,
        store: "/layerfs-store/global/store.sqlite".into(),
        overlay: "/layerfs-local/overlay/overlay.sqlite".into(),
        mounts: "/workspaces".into(),
        command_uid: args.uid,
        command_gid: args.gid,
        // OwnerConfig::default() and the current S8 immutable-cache allowance,
        // frozen here. They are never enlarged in response to a measurement.
        limits: DaemonLimits {
            connections: 4,
            handshake_ms: 2000,
            cache_bytes: 8 * 1024 * 1024,
            namespaces: 16,
            pager_kib: 1024,
            serial_low_water: 256,
        },
        existing_store: manifest,
    };
    events.value("sandbox_create_attempt", &format!("volume={} image={} executable={} acknowledged_container=UNAVAILABLE until original create returns", args.volume,args.image,args.executable.display()))?;
    let begun = Instant::now();
    let api = SandboxApi::new(Docker::new(&args.socket, Duration::from_secs(3))?);
    let request = SandboxCreate {
        deployment: layerfs_sandbox::backend::docker::SandboxRequest {
            image: args.image.clone(),
            store_volume: args.volume.clone(),
            port: 30421,
        },
        setup,
        executable: args.executable.clone(),
        controller_private: controller.private,
        daemon_peer: daemon.public,
        startup_wait: Duration::from_secs(3),
    };
    let owner = match project {
        Some(project) => api.create(request, project),
        None => layerfs_api::internal::start(&api, request),
    }.map_err(|error| format!("sandbox original failure phase={:?} cause={:?} acknowledged_container={}; private request omitted",error.phase,error.cause,error.sandbox.as_ref().map(|runtime|runtime.identity().to_string()).unwrap_or_else(||"UNAVAILABLE".into())))?;
    let elapsed = events.span(begun);
    let instance = crate::hex(&owner.startup.instance);
    events.fields(
        "daemon_setup",
        Some(elapsed),
        &format!(
            "startup={:?} handshake={:?}",
            owner.startup, owner.handshake
        ),
        &[
            ("container", owner.runtime.identity().to_string()),
            ("daemon_instance", instance),
        ],
    )?;
    Ok((
        owner,
        RuntimeKeys {
            controller_private: controller.private,
            daemon_peer: daemon.public,
            endpoint: None,
        },
    ))
}

/// Authenticate once with the existing authority and acknowledge Hello through
/// the public ManagedSandbox facade. No connection replacement or retry.
pub fn extra_control(
    owner: &mut ManagedSandbox,
    keys: &mut RuntimeKeys,
) -> Result<layerfs_api::internal::Control> {
    let endpoint = match keys.endpoint {
        Some(value) => value,
        None => {
            let value = owner
                .runtime
                .endpoint()
                .map_err(|error| format!("extra channel endpoint {error:?}"))?;
            keys.endpoint = Some(value);
            value
        }
    };
    let wait = Duration::from_secs(3);
    let stream = TcpStream::connect_timeout(&endpoint, wait)?;
    stream.set_read_timeout(Some(wait))?;
    stream.set_write_timeout(Some(wait))?;
    let connection = duplex::initiate(stream, &keys.controller_private, keys.daemon_peer)?;
    connection.clear_io_waits()?;
    let mut control = layerfs_api::internal::Control::new(connection);
    std::mem::swap(layerfs_api::internal::control(owner), &mut control);
    let hello = layerfs_api::internal::sandbox_status(owner, true);
    std::mem::swap(layerfs_api::internal::control(owner), &mut control);
    let status = hello.map_err(|failure| format!("extra channel original Hello {failure:?}"))?;
    if status.instance != owner.startup.instance || status.phase != owner.startup.phase {
        return Err("extra channel same daemon incarnation/phase required".into());
    }
    Ok(control)
}

pub enum Directory<'a> {
    Mounted(&'a MountedWorkspace),
    Host(&'a str, CommandIdentity),
}
/// One ordinary runtime Bash; the mounted convenience adds no daemon registration.
/// Streams go directly to files, with no output-sized resident collection.
pub fn command(
    owner: &ManagedSandbox,
    body: &str,
    location: Directory<'_>,
    label: &str,
    observer: bool,
    environment: &[String],
    events: &mut Events,
) -> Result<()> {
    let directory = match &location {
        Directory::Mounted(workspace) => workspace.ready.directory.as_str(),
        Directory::Host(directory, _) => directory,
    };
    command_created(
        &owner.runtime.identity().to_string(),
        body,
        directory,
        label,
        observer,
        environment,
        |arguments| {
            if observer {
                owner.runtime.create_exec(ExecRequest {
                    identity: CommandIdentity { uid: 0, gid: 0 },
                    arguments,
                    environment: vec![],
                    directory: directory.into(),
                    stdin: false,
                })
            } else {
                match location {
                    Directory::Mounted(workspace) => {
                        WorkspaceApi::exec(owner, workspace, arguments, environment.to_vec(), false)
                    }
                    Directory::Host(directory, identity) => layerfs_api::internal::exec(
                        &owner.runtime,
                        identity,
                        arguments,
                        environment.to_vec(),
                        directory.into(),
                        false,
                    ),
                }
            }
            .map_err(|error| format!("external exec create {error:?}").into())
        },
        None,
        events,
    )
}

pub fn concurrent_command(
    sandbox: &layerfs_sandbox::backend::docker::Sandbox,
    identity: CommandIdentity,
    body: &str,
    directory: &str,
    environment: &[String],
    work: (u64, u64),
    events: &mut Events,
) -> Result<()> {
    if identity.uid == 0 {
        return Err("parallel ordinary command identity must be nonroot".into());
    }
    command_created(
        &sandbox.identity().to_string(),
        body,
        directory,
        "command",
        false,
        environment,
        |arguments| {
            layerfs_api::internal::exec(
                sandbox,
                identity,
                arguments,
                environment.to_vec(),
                directory.into(),
                false,
            )
            .map_err(|error| format!("external parallel exec create {error:?}").into())
        },
        Some(work),
        events,
    )
}

fn command_created(
    container_identity: &str,
    body: &str,
    directory: &str,
    label: &str,
    observer: bool,
    environment: &[String],
    create: impl FnOnce(Vec<String>) -> Result<layerfs_sandbox::backend::docker::ExecCreated>,
    work: Option<(u64, u64)>,
    events: &mut Events,
) -> Result<()> {
    let (stdout_path, mut stdout) = events.output(label, "stdout")?;
    let (stderr_path, mut stderr) = events.output(label, "stderr")?;
    let arguments = vec![
        "/bin/bash".into(),
        "-o".into(),
        "pipefail".into(),
        "-c".into(),
        body.into(),
    ];
    let hash = crate::hex(layerfs_storage::port::ObjectKey::for_bytes(body.as_bytes()).as_bytes());
    events.value("command_admission", &format!("container={container_identity} directory={directory} label={label} command_sha256={hash} observer={observer} environment={environment:?}"))?;
    let begun = Instant::now();
    let created = create(arguments)?;
    let create_span = events.span(begun);
    let (container, exec) = created.identity();
    events.fields(
        "exec_created",
        Some(create_span),
        "original acknowledged Exec ID",
        &[
            ("container", container.to_string()),
            ("exec", exec.to_string()),
            ("command_sha256", hash.clone()),
        ],
    )?;
    events.value("exec_start_attempt", &format!("container={container} exec={exec}; one original Start; timeout custody retained; no automatic cancellation"))?;
    let start_begun = Instant::now();
    let attached = created.start().map_err(|error| {
        format!("external exec start container={container} exec={exec} original_custody={error:?}")
    })?;
    let start_span = events.span(start_begun);
    events.phase(
        "exec_start",
        Some(start_span),
        &format!("container={container} exec={exec}"),
    )?;
    let (_input, output, handle) = attached
        .into_parts()
        .map_err(|error| format!("external exec streams {error:?}"))?;
    let stream_begun = Instant::now();
    let progress = output.copy_to(&mut stdout, &mut stderr).map_err(|error| {
        format!(
            "external stream disposal container={container} exec={exec} original_custody={error:?}"
        )
    })?;
    let stream_span = events.span(stream_begun);
    events.phase("streams", Some(stream_span), &format!("container={container} exec={exec} delivered={progress:?}; EOF establishes transport completion only"))?;
    let inspect_begun = Instant::now();
    let inspected = handle.inspect().map_err(|error| {
        format!("external status container={container} exec={exec} original_custody={error:?}")
    })?;
    let inspect_span = events.span(inspect_begun);
    let elapsed = events.span(begun);
    events.phase("exec_status", Some(inspect_span), &format!("container={container} exec={exec} inspection={inspected:?}; actual_exit_time=UNAVAILABLE"))?;
    let counts = work
        .map(|(send, receive)| {
            vec![
                ("control_send_records_before", send),
                ("control_send_records_after", send),
                ("control_receive_records_before", receive),
                ("control_receive_records_after", receive),
            ]
        })
        .unwrap_or_default();
    events.numeric_fields(label, Some(elapsed), &format!("actual_exit_time=UNAVAILABLE inspection={inspected:?}; complete runtime span includes acknowledged-id custody publication; inner operation spans exclude formatting"), &[("container",container.to_string()),("exec",exec.to_string()),("command_sha256",hash),("stdout",stdout_path.display().to_string()),("stderr",stderr_path.display().to_string()),("exit_code",inspected.known_root_exit().map(|value|value.to_string()).unwrap_or_else(||"UNAVAILABLE".into())),("registered_execs","0".into())], &counts)?;
    if inspected.known_root_exit() != Some(0) {
        return Err(format!("original external command exit: {inspected:?}").into());
    }
    Ok(())
}

pub fn body(path: &Path) -> Result<String> {
    Ok(fs::read_to_string(path)?)
}

pub fn snapshot(owner: &ManagedSandbox, socket: &str, events: &mut Events) -> Result<()> {
    // Observer-only root identity reads the daemon's protected files. It
    // acquires no filesystem owner and makes no mutation or cache hint.
    let body = "set -e; printf 'DAEMON_STATUS\\n'; cat /proc/1/status; printf 'BACKING_BYTES\\n'; for base in /layerfs-store/global/store.sqlite /layerfs-local/overlay/*.sqlite; do for suffix in '' -wal -shm -journal; do p=$base$suffix; if test -e \"$p\"; then stat -c '%n %s %b %B' \"$p\"; else printf '%s ABSENT\\n' \"$p\"; fi; done; done; printf 'OWN_CONTAINER_CGROUP\\n'; for p in /sys/fs/cgroup/memory.stat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak; do if test -r \"$p\"; then printf '%s\\n' \"$p\"; cat \"$p\"; else printf '%s UNAVAILABLE\\n' \"$p\"; fi; done; printf 'DAEMON_THREADS\\n'; for t in /proc/1/task/*; do printf 'THREAD\\t%s\\t%s\\t%s\\t%s\\t%s\\n' \"${t##*/}\" \"$(cat \"$t/comm\" 2>/dev/null)\" \"$(cat \"$t/schedstat\" 2>/dev/null)\" \"$(awk '/ctxt_switches/{printf \"%s \", $2}' \"$t/status\" 2>/dev/null)\" \"$(sed 's/.*) //' \"$t/stat\" 2>/dev/null | awk '{print $8,$12,$13,$37}')\"; done; printf 'CGROUP_CPU\\n'; cat /sys/fs/cgroup/cpu.stat 2>/dev/null || true; printf 'KERNEL\\t%s\\t%s\\n' \"$(uname -r)\" \"$(nproc)\"";
    let (stdout_path, stdout) = events.output("external_snapshot", "stdout")?;
    let (stderr_path, stderr) = events.output("external_snapshot", "stderr")?;
    events.value("external_snapshot_attempt", &format!("container={} executor=docker-cli user=0:0 read_only=true; original SDK root-command refusal is preserved",owner.runtime.identity()))?;
    let begun = Instant::now();
    let mut child = Command::new("docker")
        .args([
            "--host",
            &format!("unix://{socket}"),
            "exec",
            "--user",
            "0:0",
            &owner.runtime.identity().to_string(),
            "/bin/bash",
            "-o",
            "pipefail",
            "-c",
            body,
        ])
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()?;
    events.value(
        "external_snapshot_started",
        &format!(
            "container={} host_pid={}; host timeout does not establish Docker exec cancellation",
            owner.runtime.identity(),
            child.id()
        ),
    )?;
    let status = child.wait()?;
    let span = events.span(begun);
    events.fields(
        "external_snapshot",
        Some(span),
        &format!("status={status:?}"),
        &[
            ("container", owner.runtime.identity().to_string()),
            ("stdout", stdout_path.display().to_string()),
            ("stderr", stderr_path.display().to_string()),
        ],
    )?;
    if !status.success() {
        return Err(format!("original external snapshot failed {status:?}").into());
    }
    Ok(())
}

/// Explicit original stop/delete; the returned error retains the typed SDK custody.
pub fn close(owner: ManagedSandbox, socket: &str) -> Result<()> {
    SandboxApi::new(Docker::new(socket, Duration::from_secs(3))?)
        .close(owner)
        .map_err(|error| error as Box<dyn std::error::Error>)
}

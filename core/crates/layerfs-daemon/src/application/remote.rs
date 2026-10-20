//! Opt-in remote assembly; commands remain owned by the external executor.
use crate::{control::Service, store::WorkspaceBackend, Owner, OwnerConfig};
use layerfs_bridge::{
    control::{Answer, Call, DaemonPhase, DaemonStatus, Reply, Request, SdkValue},
    duplex,
};
use layerfs_remote_store::{
    wire::{error, Result},
    Client, Config,
};
use std::{
    net::TcpListener,
    path::Path,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    time::Duration,
};

pub fn run(path: &Path) -> Result<()> {
    super::config::secure_process().map_err(error)?;
    super::config::private_directory(path.parent().ok_or_else(|| error("config parent"))?, false)
        .map_err(error)?;
    let config = Config::read(path)?;
    let uid = config.number("uid")?;
    let gid = config.number("gid")?;
    if uid == 0 || gid == 0 || uid == nix::unistd::Uid::effective().as_raw() {
        return Err(error("command/daemon identities"));
    }
    let mounts = Path::new(config.get("mounts")?);
    for key in ["overlay", "cache"] {
        let backing = Path::new(config.get(key)?);
        if !backing.is_absolute() || backing.starts_with(mounts) {
            return Err(error("protected backing path"));
        }
        super::config::private_directory(
            backing.parent().ok_or_else(|| error("backing parent"))?,
            true,
        )
        .map_err(error)?;
    }
    if config.get("overlay")? == config.get("cache")? || path.starts_with(mounts) {
        return Err(error("separate config/cache/overlay"));
    }
    let client = Client::connect(&config)?;
    let owner = Owner::start(
        Path::new(config.get("overlay")?),
        layerfs_overlay::ProfileConfig::default(),
        OwnerConfig::default(),
    )
    .map_err(error)?;
    let kernel = super::filesystem::assemble_at(config.get("mounts")?, uid, gid)
        .map_err(error)?
        .ok_or_else(|| error("Linux FUSE required"))?;
    let service = Arc::new(Service::with_kernel(
        WorkspaceBackend::remote(client.clone(), 64 * 1024 * 1024),
        &owner,
        kernel,
    ));
    let listener = TcpListener::bind(config.get("listen")?).map_err(error)?;
    let private = config.key("private_key")?;
    let peer = duplex::public_key(&config.key("token")?).map_err(error)?;
    let instance = duplex::generate_keypair().map_err(error)?.public;
    let overlay_version = owner.profile().sqlite_version.clone();
    let active = Arc::new(AtomicUsize::new(0));
    println!(
        "REMOTE_DAEMON_READY {}",
        listener.local_addr().map_err(error)?
    );
    for stream in listener.incoming() {
        let stream = stream.map_err(error)?;
        if active
            .fetch_update(Ordering::AcqRel, Ordering::Relaxed, |n| {
                (n < 8).then_some(n + 1)
            })
            .is_err()
        {
            continue;
        }
        let service = service.clone();
        let client = client.clone();
        let active = active.clone();
        let version = overlay_version.clone();
        std::thread::spawn(move || {
            let result: Result<()> = (|| {
                stream
                    .set_read_timeout(Some(Duration::from_secs(10)))
                    .map_err(error)?;
                let settings = stream.try_clone().map_err(error)?;
                let mut connection = duplex::accept(stream, &private, peer).map_err(error)?;
                settings.set_read_timeout(None).map_err(error)?;
                loop {
                    let call = Call::decode(connection.receive.receive().map_err(error)?)
                        .map_err(error)?;
                    let end = matches!(&call.request, Request::EndSession);
                    let reply = match &call.request {
                        Request::Hello(_) => Some(Reply::Hello(DaemonStatus {
                            instance,
                            phase: DaemonPhase::ControlReady,
                            overlay_sqlite: Some(version.clone()),
                            store_sqlite: None,
                        })),
                        Request::Sdk(call) if call.method == "operator.remote.stats" => {
                            Some(Reply::Sdk(SdkValue::map([
                                (
                                    "roundTrips",
                                    SdkValue::Int(client.round_trips().min(i64::MAX as u64) as i64),
                                ),
                                ("uploadedObjects", SdkValue::Int(client.uploaded().0 as i64)),
                                ("uploadedBytes", SdkValue::Int(client.uploaded().1 as i64)),
                            ])))
                        }
                        _ => None,
                    };
                    if let Some(reply) = reply {
                        connection
                            .send
                            .send(&Answer { id: call.id, reply }.encode().map_err(error)?)
                            .map_err(error)?;
                    } else {
                        service
                            .serve_control_call(&mut connection, call)
                            .map_err(error)?;
                    }
                    if end {
                        return Ok(());
                    }
                }
            })();
            if let Err(e) = result {
                eprintln!("remote control ended: {e}");
            }
            active.fetch_sub(1, Ordering::Release);
        });
    }
    drop(service);
    owner.stop().map_err(error)
}

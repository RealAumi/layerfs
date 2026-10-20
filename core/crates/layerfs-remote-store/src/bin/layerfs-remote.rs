//! Explicit mount/control helper; it never launches an agent command.
use layerfs_bridge::{
    control::{
        Answer, Call, CommitControl, Reply, Request, SdkCall, SdkValue, UnmountControl,
        WorkspaceToken,
    },
    duplex,
};
use layerfs_history::{BranchId, WorkspaceId};
use layerfs_remote_store::{
    config::{hex, unhex},
    wire::{error, Result},
    Config,
};
use std::{
    net::TcpStream,
    path::Path,
    time::{Duration, Instant},
};
fn run() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() < 3 {
        return Err(error("usage: layerfs-remote <config> mount <branch-id> | commit/unmount <workspace-id> <namespace> | stats"));
    }
    let config = Config::read(Path::new(&args[1]))?;
    let address = config.get("control")?.parse().map_err(error)?;
    let stream = TcpStream::connect_timeout(&address, Duration::from_secs(5)).map_err(error)?;
    stream
        .set_read_timeout(Some(Duration::from_secs(30)))
        .map_err(error)?;
    let started = Instant::now();
    let mut connection = duplex::initiate(
        stream,
        &config.key("token")?,
        duplex::public_key(&config.key("private_key")?).map_err(error)?,
    )
    .map_err(error)?;
    let mut next = 0;
    let mut call = |request| -> Result<Reply> {
        next += 1;
        connection
            .send
            .send(&Call { id: next, request }.encode().map_err(error)?)
            .map_err(error)?;
        let answer = Answer::decode(connection.receive.receive().map_err(error)?).map_err(error)?;
        if answer.id != next {
            return Err(error("control correlation"));
        }
        Ok(answer.reply)
    };
    let arg = |n| {
        args.get(n)
            .map(String::as_str)
            .ok_or_else(|| error("missing argument"))
    };
    let token = || -> Result<WorkspaceToken> {
        Ok(WorkspaceToken {
            workspace: WorkspaceId::from_authority(
                unhex(arg(3)?)?
                    .try_into()
                    .map_err(|_| error("workspace width"))?,
            )
            .map_err(error)?,
            namespace: arg(4)?.parse().map_err(error)?,
        })
    };
    let result = match args[2].as_str() {
        "mount" => {
            let branch = BranchId::from_bytes(
                unhex(arg(3)?)?
                    .try_into()
                    .map_err(|_| error("branch width"))?,
            )
            .map_err(error)?;
            let workspace =
                WorkspaceId::from_authority(duplex::generate_keypair().map_err(error)?.public)
                    .map_err(error)?;
            let token = match call(Request::Mount { workspace, branch })? {
                Reply::Bound { token, .. } => token,
                other => return Err(error(format!("mount: {other:?}"))),
            };
            let reply = call(Request::Attach(token))?;
            if let Reply::Ready(ready) = &reply {
                println!(
                    "path={} workspace={} namespace={}",
                    ready.directory,
                    hex(&token.workspace.to_bytes()),
                    token.namespace
                );
            }
            reply
        }
        "commit" => call(Request::Commit(CommitControl {
            token: token()?,
            force: false,
            message: Some("remote explicit Commit".into()),
        }))?,
        "unmount" => call(Request::Unmount(UnmountControl {
            token: token()?,
            discard: args.get(5).is_some_and(|v| v == "discard"),
        }))?,
        "stats" => call(Request::Sdk(SdkCall {
            method: "operator.remote.stats".into(),
            args: SdkValue::Null,
        }))?,
        _ => return Err(error("unknown control")),
    };
    println!("{result:?}\nwall_ns={}", started.elapsed().as_nanos());
    call(Request::EndSession)?;
    if matches!(result, Reply::Refused(_) | Reply::Retained(_)) {
        return Err(error("control refused; original result printed"));
    }
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}

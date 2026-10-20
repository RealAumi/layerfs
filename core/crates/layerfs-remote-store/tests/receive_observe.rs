//! External observation through the existing authenticated control Status API.
use layerfs_bridge::{
    control::{Answer, Call, Reply, Request, WorkspaceToken},
    duplex,
};
use layerfs_history::WorkspaceId;
use layerfs_remote_store::{config::unhex, Config};
use std::{net::TcpStream, path::Path, time::Duration};
#[test]
#[ignore = "explicit local measurement fixture required"]
fn observe() {
    let config = Config::read(Path::new("/state/daemon.setup")).unwrap();
    let stream = TcpStream::connect(config.get("control").unwrap()).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    stream
        .set_write_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let mut channel = duplex::initiate(
        stream,
        &config.key("token").unwrap(),
        duplex::public_key(&config.key("private_key").unwrap()).unwrap(),
    )
    .unwrap();
    let token = WorkspaceToken {
        workspace: WorkspaceId::from_authority(
            unhex(&std::env::var("LFS_WS").unwrap())
                .unwrap()
                .try_into()
                .unwrap(),
        )
        .unwrap(),
        namespace: std::env::var("LFS_NS").unwrap().parse().unwrap(),
    };
    channel
        .send
        .send(
            &Call {
                id: 1,
                request: Request::Status(token),
            }
            .encode()
            .unwrap(),
        )
        .unwrap();
    let answer = Answer::decode(channel.receive.receive().unwrap()).unwrap();
    assert_eq!(answer.id, 1);
    let Reply::Status(status) = answer.reply else {
        panic!("{answer:?}")
    };
    println!("FUSE_WORK {:?}", status.kernel.unwrap().work.unwrap());
    channel
        .send
        .send(
            &Call {
                id: 2,
                request: Request::EndSession,
            }
            .encode()
            .unwrap(),
        )
        .unwrap();
    let answer = Answer::decode(channel.receive.receive().unwrap()).unwrap();
    assert_eq!(answer.id, 2);
}

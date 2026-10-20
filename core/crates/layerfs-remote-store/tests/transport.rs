//! Actual authenticated channels: fragmentation, admission and corrupt-object rejection.
use layerfs_bridge::duplex;
use layerfs_content::ObjectId;
use layerfs_remote_store::{
    config::hex,
    wire::{self, Decode, Encode},
    Client, Config,
};
use layerfs_store_service::store::RemoteStore;
use std::{
    fs,
    net::{TcpListener, TcpStream},
    os::unix::fs::PermissionsExt,
    thread,
    time::Duration,
};
fn bounded(stream: TcpStream) -> TcpStream {
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    stream
        .set_write_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    stream
}
fn accept(listener: &TcpListener) -> TcpStream {
    listener.set_nonblocking(true).unwrap();
    let until = std::time::Instant::now() + Duration::from_secs(3);
    loop {
        match listener.accept() {
            Ok((stream, _)) => return stream,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(std::time::Instant::now() < until, "accept deadline");
                thread::sleep(Duration::from_millis(5));
            }
            Err(e) => panic!("accept: {e}"),
        }
    }
}
#[test]
fn fragments_cross_noise_records_and_reject_a_bad_offset() {
    let server = duplex::generate_keypair().unwrap();
    let client = duplex::generate_keypair().unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let worker = thread::spawn(move || {
        let socket = accept(&listener);
        let mut channel = duplex::accept(bounded(socket), &server.private, client.public).unwrap();
        let bytes = wire::receive(&mut channel).unwrap();
        assert_eq!(bytes.len(), 180_001);
        assert!(bytes.iter().all(|b| *b == 42));
        channel.send.send(b"LFRS\x01\x00\x00\x00\x01").unwrap();
        channel.send.send(&[0, 0, 0, 1, 42]).unwrap();
    });
    let mut channel = duplex::initiate(
        bounded(TcpStream::connect(address).unwrap()),
        &client.private,
        server.public,
    )
    .unwrap();
    wire::send(&mut channel, &vec![42; 180_001]).unwrap();
    assert!(wire::receive(&mut channel)
        .unwrap_err()
        .detail
        .contains("offset"));
    worker.join().unwrap();
}
#[test]
fn wrong_canonical_identity_is_not_cached_or_replayed() {
    let server = duplex::generate_keypair().unwrap();
    let token = duplex::generate_keypair().unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let directory = std::env::temp_dir().join(format!("remote-identity-{}", std::process::id()));
    fs::create_dir(&directory).unwrap();
    let path = directory.join("config");
    fs::write(
        &path,
        format!(
            "server={address}\nserver_key={}\ntoken={}\ncache={}\n",
            hex(&server.public),
            hex(&token.private),
            directory.join("cache.sqlite").display()
        ),
    )
    .unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
    let worker = thread::spawn(move || {
        let mut read =
            duplex::accept(bounded(accept(&listener)), &server.private, token.public).unwrap();
        let _write =
            duplex::accept(bounded(accept(&listener)), &server.private, token.public).unwrap();
        let request = wire::receive(&mut read).unwrap();
        let mut input = Decode(&request);
        let id = input.number().unwrap();
        assert_eq!(input.byte().unwrap(), wire::OBJECTS);
        assert_eq!(wire::ids(&mut input).unwrap().len(), 1);
        input.finish().unwrap();
        let mut reply = Encode::new();
        reply.number(id);
        reply.byte(0);
        reply.number(1);
        reply.blob(b"wrong bytes");
        wire::send(&mut read, &reply.0).unwrap();
    });
    let client = Client::connect(&Config::read(&path).unwrap()).unwrap();
    let error = client
        .objects(&[ObjectId::for_bytes(b"wanted bytes")])
        .unwrap_err();
    assert!(error.detail.contains("identity"), "{error}");
    assert_eq!(client.round_trips(), 1);
    worker.join().unwrap();
    drop(client);
    let cache = rusqlite::Connection::open(directory.join("cache.sqlite")).unwrap();
    let n: i64 = cache
        .query_row("SELECT count(*) FROM objects", [], |r| r.get(0))
        .unwrap();
    assert_eq!(n, 0);
    drop(cache);
    fs::remove_dir_all(directory).unwrap();
}

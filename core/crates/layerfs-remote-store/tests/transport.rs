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
    // macOS inherits O_NONBLOCK from the readiness-polled listener.
    stream.set_nonblocking(false).unwrap();
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

// The real client's upload walk: a rejected second window leaves the first
// acknowledged window remote, keeps every local object, and quarantines writes.
fn upload_fault(drop_reply: bool) {
    use layerfs_content::filesystem::attributes::portable::PortableMetadata;
    use layerfs_content::filesystem::{
        build_filesystem, scope_for_seed, DirectoryUpdate, FilesystemInput, FilesystemObjects,
        FilesystemResources, InodeUpdate, PathName,
    };
    use layerfs_content::inode_leaf::{InodeKind, InodeMetadata, InodeValue};
    use layerfs_content::{
        construct_bytes, ConstructionPolicy, ContentResult, FinalizedConsumer, FinalizedObject,
    };
    use layerfs_history::{
        BranchId, BranchRecord, BranchSnapshot, CommitVia, HistoryName, LayerId, LayerStackId,
    };
    use layerfs_store_service::store::{publish::CandidateInput, CommitOptions, RemoteBuild};
    use layerfs_telemetry::timer::Timing;
    struct Sink<'a>(&'a dyn RemoteBuild);
    impl FinalizedConsumer for Sink<'_> {
        fn accept(&mut self, o: FinalizedObject) -> ContentResult<()> {
            self.0.accept(o).unwrap();
            Ok(())
        }
    }
    let server = duplex::generate_keypair().unwrap();
    let token = duplex::generate_keypair().unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let dir = std::env::temp_dir().join(format!(
        "cxi-upload-fault-{}-{drop_reply}",
        std::process::id()
    ));
    fs::create_dir(&dir).unwrap();
    let setup = dir.join("config");
    fs::write(
        &setup,
        format!(
            "server={address}\nserver_key={}\ntoken={}\ncache={}\n",
            hex(&server.public),
            hex(&token.private),
            dir.join("cache.sqlite").display()
        ),
    )
    .unwrap();
    fs::set_permissions(&setup, fs::Permissions::from_mode(0o600)).unwrap();
    let worker = thread::spawn(move || {
        let _read =
            duplex::accept(bounded(accept(&listener)), &server.private, token.public).unwrap();
        let mut write =
            duplex::accept(bounded(accept(&listener)), &server.private, token.public).unwrap();
        let mut uploaded = Vec::new();
        for window in 0..2 {
            let bytes = wire::receive(&mut write).unwrap();
            let mut input = Decode(&bytes);
            let id = input.number().unwrap();
            assert_eq!(input.byte().unwrap(), wire::LACKING);
            let ids = wire::ids(&mut input).unwrap();
            input.finish().unwrap();
            assert!(ids.len() <= 512);
            let mut out = Encode::new();
            out.number(id);
            out.byte(0);
            out.raw(&vec![1; ids.len()]);
            wire::send(&mut write, &out.0).unwrap();
            let bytes = wire::receive(&mut write).unwrap();
            let mut input = Decode(&bytes);
            let id = input.number().unwrap();
            assert_eq!(input.byte().unwrap(), wire::UPLOAD);
            input.take(32).unwrap();
            input.take(32).unwrap();
            let count = input.number().unwrap();
            assert_eq!(count as usize, ids.len());
            for expected in &ids {
                let object = ObjectId::from_bytes(input.take(32).unwrap()).unwrap();
                assert_eq!(*expected, object);
                input.byte().unwrap();
                let body = input.blob(wire::MAX_OBJECT).unwrap();
                assert!(!body
                    .windows(b"IGNORED-SECRET".len())
                    .any(|w| w == b"IGNORED-SECRET"));
            }
            input.finish().unwrap();
            let mut out = Encode::new();
            out.number(id);
            if window == 0 {
                out.byte(0);
                uploaded.extend(ids);
            } else if drop_reply {
                break;
            } else {
                out.byte(1);
                out.text("injected second upload refusal");
            }
            wire::send(&mut write, &out.0).unwrap();
        }
        uploaded
    });
    let client = Client::connect(&Config::read(&setup).unwrap()).unwrap();
    let build = client.build().unwrap();
    let policy = ConstructionPolicy::frozen_default();
    let mut sink = Sink(build.as_ref());
    let file = |bytes: &[u8], sink: &mut Sink<'_>| {
        Timing::disabled("upload.test", |t| {
            construct_bytes(policy, &policy.capacities(), bytes, sink, t.child("file"))
        })
        .0
        .unwrap()
        .root
    };
    let ignored = file(b"IGNORED-SECRET", &mut sink);
    let metadata = InodeMetadata::Inline(PortableMetadata {
        mode: 0o755,
        mtime_seconds: 1700000000,
        mtime_nanoseconds: 0,
    });
    let mut inodes = vec![InodeUpdate {
        serial: 1,
        value: InodeValue {
            kind: InodeKind::Directory,
            namespace_ref_count: 0,
            content_root: ignored,
            metadata_root: metadata,
        },
    }];
    let mut names = Vec::new();
    for i in 0..600 {
        let root = file(format!("kept-{i}").as_bytes(), &mut sink);
        let serial = i + 2;
        inodes.push(InodeUpdate {
            serial,
            value: InodeValue {
                kind: InodeKind::RegularFile,
                namespace_ref_count: 0,
                content_root: root,
                metadata_root: metadata,
            },
        });
        names.push((PathName::new(&format!("f{i:04}")).unwrap(), Some(serial)));
    }
    let scope = scope_for_seed([0x16; 32]);
    let dirs = [DirectoryUpdate {
        parent: 1,
        changes: names,
    }];
    let fresh: Vec<_> = (1..602).collect();
    let input = FilesystemInput {
        base: None,
        scope,
        root_serial: 1,
        directories: &dirs,
        inodes: &inodes,
        new_inodes: &fresh,
        resources: FilesystemResources::default(),
    };
    let root = build_filesystem(
        &mut FilesystemObjects::new_with_accepted(build.reader(), &mut sink, build.reader()),
        &input,
        None,
    )
    .unwrap()
    .root;
    let binding = BranchSnapshot {
        branch: BranchRecord {
            forked_from: None,
            id: BranchId::from_authority([1; 16]),
            stack: LayerStackId::from_authority([2; 16]),
            name: HistoryName::new("main").unwrap(),
            base_layer: LayerId::from_bytes([0x32; 33]).unwrap(),
            head_commit: None,
        },
        head_root: None,
        base_root: root.0,
        effective_root: root.0,
        scope: scope.object(),
        profile: layerfs_content::filesystem::profile_id(),
    };
    let candidate = CandidateInput {
        binding,
        root,
        options: CommitOptions::default(),
        via: CommitVia::Workspace,
        conflicts: vec![],
    };
    let error = build.publish(&candidate).err().unwrap();
    if !drop_reply {
        assert!(error.detail.contains("second upload refusal"));
    }
    assert_eq!(error.unknown, drop_reply);
    let acknowledged = worker.join().unwrap();
    assert_eq!(acknowledged.len(), 512);
    let calls = client.round_trips();
    let next = client.build().unwrap().publish(&candidate).err().unwrap();
    assert!(next.detail.contains("quarantined"));
    assert_eq!(client.round_trips(), calls);
    assert!(build
        .reader()
        .read_canonical(ignored)
        .unwrap()
        .windows(14)
        .any(|b| b == b"IGNORED-SECRET"));
    let cache = rusqlite::Connection::open(dir.join("cache.sqlite")).unwrap();
    let (remote, local): (i64, i64) = cache
        .query_row("SELECT sum(remote=1),sum(remote=0) FROM objects", [], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })
        .unwrap();
    assert_eq!(remote, 512);
    assert!(local > 0);
    let secret_remote: i64 = cache
        .query_row(
            "SELECT remote FROM objects WHERE id=?",
            [ignored.as_bytes().as_slice()],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(secret_remote, 0);
    drop(cache);
    drop(build);
    drop(client);
    fs::remove_dir_all(dir).unwrap();
}

#[test]
fn upload_window_failure_keeps_local_objects_and_never_sends_unreachable_bytes() {
    upload_fault(false);
}
#[test]
fn upload_lost_ack_keeps_local_objects_and_quarantines_without_replay() {
    upload_fault(true);
}

#[test]
fn production_style_blocking_listener_returns_blocking_sockets() {
    use nix::fcntl::{fcntl, FcntlArg, OFlag};
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let client =
        TcpStream::connect_timeout(&listener.local_addr().unwrap(), Duration::from_secs(3))
            .unwrap();
    let (accepted, _) = listener.accept().unwrap();
    let flags = OFlag::from_bits_truncate(fcntl(&accepted, FcntlArg::F_GETFL).unwrap());
    assert!(!flags.contains(OFlag::O_NONBLOCK));
    drop(client);
}

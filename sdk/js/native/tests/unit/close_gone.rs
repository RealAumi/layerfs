//! `sandbox.close` of a Sandbox whose container the Engine no longer has: its
//! records go under its locks, and nothing else counts as gone. Included by
//! sandbox.rs, so it reaches the private close paths.
use super::{close, close_gone};
use layerfs_bridge::control::SdkValue;
use std::{
    io::{BufRead, BufReader, Write},
    os::unix::{fs::DirBuilderExt, net::UnixListener},
    path::{Path, PathBuf},
    sync::atomic::{AtomicUsize, Ordering},
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

const CID: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const ID: &str = "_service.proj";
static NEXT: AtomicUsize = AtomicUsize::new(0);

/// A private LayerFS home with the service Sandbox of project `proj` recorded
/// as running in container CID, behind the Engine socket `docker.sock`.
fn home() -> PathBuf {
    let home = std::env::temp_dir().join(format!(
        "layerfs-close-gone-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    let private = |path: &Path| std::fs::DirBuilder::new().mode(0o700).create(path).unwrap();
    private(&home);
    private(&home.join("_sandboxes"));
    private(&home.join("_sandboxes").join(ID));
    private(&home.join("proj"));
    let bytes = |n: u8| SdkValue::Bytes(vec![n; 32]);
    crate::discovery::save(
        &home.join("_sandboxes").join(ID).join("sandbox.record"),
        SdkValue::map([
            ("id", SdkValue::text(ID)),
            ("project", SdkValue::text("proj")),
            ("container", SdkValue::text(CID)),
            (
                "docker",
                SdkValue::text(home.join("docker.sock").to_str().unwrap()),
            ),
            (
                "image",
                SdkValue::text(format!("sha256:{}", "a".repeat(64))),
            ),
            ("volume", SdkValue::text("lfs-test-borrowed")),
            ("volumes", SdkValue::List(vec![])),
            ("secret", bytes(1)),
            ("peer", bytes(2)),
            ("instance", bytes(3)),
        ]),
    )
    .unwrap();
    crate::discovery::save(
        &home.join("proj").join("service.record"),
        SdkValue::map([("id", SdkValue::text(ID))]),
    )
    .unwrap();
    home
}

/// The Engine at `home/docker.sock`, answering one request with `status` and `body`.
fn engine(home: &Path, status: u16, body: &str) -> JoinHandle<String> {
    let listener = UnixListener::bind(home.join("docker.sock")).unwrap();
    listener.set_nonblocking(true).unwrap();
    let response = format!(
        "HTTP/1.1 {status} test\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
        body.len()
    );
    thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(3);
        let stream = loop {
            match listener.accept() {
                Ok((stream, _)) => break stream,
                Err(e)
                    if e.kind() == std::io::ErrorKind::WouldBlock && Instant::now() < deadline =>
                {
                    thread::sleep(Duration::from_millis(2))
                }
                Err(e) => panic!("bounded engine admission: {e}"),
            }
        };
        stream.set_nonblocking(false).unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let mut reader = BufReader::new(stream.try_clone().unwrap());
        let mut request = String::new();
        loop {
            let mut line = String::new();
            if reader.read_line(&mut line).unwrap() == 0 || line == "\r\n" {
                break;
            }
            request.push_str(&line);
        }
        (&stream).write_all(response.as_bytes()).unwrap();
        request
    })
}

fn args(home: &Path) -> SdkValue {
    SdkValue::map([
        ("sandbox", SdkValue::text(ID)),
        ("home", SdkValue::text(home.to_str().unwrap())),
    ])
}

#[test]
fn a_gone_container_closes_by_removing_its_records() {
    let home = home();
    let engine = engine(
        &home,
        404,
        &format!(r#"{{"message":"No such container: {CID}"}}"#),
    );
    let closed = close(&args(&home)).unwrap();
    assert_eq!(closed.get_text("kind"), Some("Closed"));
    assert_eq!(closed.get_text("id"), Some(ID));
    assert!(engine
        .join()
        .unwrap()
        .starts_with(&format!("GET /v1.54/containers/{CID}/json")));
    assert!(
        !home.join("_sandboxes").join(ID).exists(),
        "its name is free again"
    );
    assert!(!home.join("proj").join("service.record").exists());
    std::fs::remove_dir_all(home).unwrap();
}

#[test]
fn another_404_is_a_failure_that_removes_nothing() {
    let home = home();
    let engine = engine(&home, 404, r#"{"message":"page not found"}"#);
    let refusal = close(&args(&home)).unwrap_err();
    assert_eq!(refusal.code, "Failed");
    engine.join().unwrap();
    assert!(home
        .join("_sandboxes")
        .join(ID)
        .join("sandbox.record")
        .exists());
    assert!(home.join("proj").join("service.record").exists());
    std::fs::remove_dir_all(home).unwrap();
}

#[test]
fn a_name_created_again_with_another_container_is_left_alone() {
    let home = home();
    let other = "c".repeat(64);
    let refusal = close_gone(&args(&home), &other).unwrap_err();
    assert_eq!(refusal.code, "Busy");
    assert!(home
        .join("_sandboxes")
        .join(ID)
        .join("sandbox.record")
        .exists());
    assert!(home.join("proj").join("service.record").exists());
    std::fs::remove_dir_all(home).unwrap();
}

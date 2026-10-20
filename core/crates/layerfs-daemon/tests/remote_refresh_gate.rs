//! Prerequisite for the remote Store: server-side edits install on a live mount.
#![cfg(target_os = "linux")]
#[allow(dead_code)]
#[path = "../../layerfs-api/tests/support/installed_store.rs"]
mod installed;
#[allow(dead_code)]
#[path = "support/mounted.rs"]
mod mounted;
#[allow(dead_code)]
#[path = "../../layerfs-api/tests/support/sdk.rs"]
mod sdk;

use layerfs_bridge::control::{Reply, SdkValue};
use layerfs_history::{BranchId, HistoryName, LayerStackId};
use std::{fs, os::unix::fs::MetadataExt, path::Path, process::Command};

fn write(f: &sdk::Fixture, path: &str, content: &str) {
    f.call(
        "fs.write",
        vec![
            ("branch", SdkValue::text("work")),
            ("path", SdkValue::text(path)),
            ("content", SdkValue::text(content)),
        ],
    );
}

#[test]
fn server_edits_refresh_clean_and_dirty_mount_and_root_can_create() {
    assert_eq!(nix::unistd::Uid::effective().as_raw(), 0);
    let f = sdk::Fixture::new("remote-refresh-gate", |path| {
        fs::write(path.join("server"), "before\n").unwrap();
        fs::write(path.join("local"), "before\n").unwrap();
        2
    });
    f.fork("work");
    let branch = BranchId::named(
        LayerStackId::from_authority([23; 16]),
        &HistoryName::new("work").unwrap(),
    );
    let directory = f.host.directory.join("kernel");
    fs::create_dir(&directory).unwrap();
    let h = mounted::Harness::new(f.service.store.clone(), &directory, branch);
    let ready = h.mount(81);
    let path = Path::new(&ready.directory);
    // Populate the kernel's data/attribute caches before the server changes it.
    assert_eq!(fs::read_to_string(path.join("server")).unwrap(), "before\n");
    write(&f, "/server", "server-clean\n");
    let clean = h.try_commit(ready.token).unwrap();
    assert!(
        matches!(clean.reply, Reply::MergeCommitted(_)),
        "{:?}",
        clean.reply
    );
    assert_eq!(
        fs::read_to_string(path.join("server")).unwrap(),
        "server-clean\n"
    );
    println!("PASS clean moved head installs and invalidates cached content");

    fs::write(path.join("local"), "local-dirty\n").unwrap();
    write(&f, "/server", "server-dirty\n");
    let dirty = h.try_commit(ready.token).unwrap();
    assert!(
        matches!(dirty.reply, Reply::MergeCommitted(_)),
        "{:?}",
        dirty.reply
    );
    assert_eq!(
        fs::read_to_string(path.join("server")).unwrap(),
        "server-dirty\n"
    );
    assert_eq!(
        fs::read_to_string(path.join("local")).unwrap(),
        "local-dirty\n"
    );
    println!("PASS server edits plus disjoint local edits install together");

    let touch = Command::new("touch")
        .arg(path.join("root-created"))
        .status()
        .unwrap();
    assert!(touch.success());
    fs::write(path.join("root-created"), "root wrote\n").unwrap();
    let cat = Command::new("cat")
        .arg(path.join("root-created"))
        .output()
        .unwrap();
    assert!(cat.status.success());
    assert_eq!(cat.stdout, b"root wrote\n");
    let metadata = fs::metadata(path.join("root-created")).unwrap();
    assert_eq!(
        (metadata.uid(), metadata.gid()),
        (mounted::COMMAND, mounted::COMMAND)
    );
    println!(
        "PASS root touch/write/cat; projected owner={}:{}",
        metadata.uid(),
        metadata.gid()
    );
    h.try_commit(ready.token).unwrap();
    h.unmount(&ready);
    h.stop();
    f.cleanup();
}

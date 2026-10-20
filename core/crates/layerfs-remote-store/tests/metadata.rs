//! Metadata traversal excludes payload and reuses only a fully populated root.
use layerfs_content::{
    filesystem::{
        attributes::PortableMetadata,
        inode::{encode_inode_page, InodePage},
    },
    inode_leaf::{InodeKind, InodeMetadata, InodeValue},
    ObjectId,
};
use layerfs_remote_store::metadata::{self, DIRECTORY, INODES, ROOT};
#[test]
fn inode_wave_separates_lengths_from_namespace_children() {
    let kinds = [
        InodeKind::Directory,
        InodeKind::RegularFile,
        InodeKind::Symlink,
    ];
    let entries = kinds
        .iter()
        .enumerate()
        .map(|(n, &kind)| {
            (
                n as u64 + 1,
                InodeValue {
                    kind,
                    namespace_ref_count: 1,
                    content_root: ObjectId::for_bytes(&[n as u8]),
                    metadata_root: InodeMetadata::Inline(PortableMetadata {
                        mode: 0o777,
                        mtime_seconds: 1,
                        mtime_nanoseconds: 2,
                    }),
                },
            )
        })
        .collect();
    let bytes = encode_inode_page(&InodePage::Leaf { entries }).unwrap();
    let (children, files) = metadata::expand(INODES, &bytes).unwrap();
    assert_eq!(children, vec![(DIRECTORY, ObjectId::for_bytes(&[0]))]);
    assert_eq!(files, vec![ObjectId::for_bytes(&[1])]);
    assert!(metadata::expand(ROOT, &bytes).is_err());
    let payload = layerfs_content::encode_whole_file_payload(b"not namespace metadata").unwrap();
    for kind in [ROOT, INODES, DIRECTORY] {
        assert!(metadata::expand(kind, &payload).is_err());
    }
}
#[test]
#[ignore = "owned two-container server and private /state/control.setup required"]
fn remote_generation_is_verified_metadata_only_and_reused() {
    use layerfs_history::{BranchId, HistoryName, LayerStackId};
    use layerfs_remote_store::{Client, Config};
    use layerfs_store_service::store::RemoteStore;
    use std::{fs, os::unix::fs::PermissionsExt, path::Path};
    let text = fs::read_to_string("/state/control.setup").unwrap();
    let text = text
        .lines()
        .map(|line| {
            if line.starts_with("cache=") {
                "cache=/state/metadata-test.sqlite"
            } else {
                line
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    fs::write("/state/metadata-test.setup", text).unwrap();
    fs::set_permissions(
        "/state/metadata-test.setup",
        fs::Permissions::from_mode(0o600),
    )
    .unwrap();
    let client =
        Client::connect(&Config::read(Path::new("/state/metadata-test.setup")).unwrap()).unwrap();
    let branch = BranchId::named(
        LayerStackId::from_authority([23; 16]),
        &HistoryName::new("work").unwrap(),
    );
    let root = client.snapshot(branch).unwrap().effective_root;
    let first = client.round_trips();
    assert!(first > 2, "fixture must require paged metadata");
    assert_eq!(client.snapshot(branch).unwrap().effective_root, root);
    assert_eq!(
        client.round_trips(),
        first + 1,
        "completed immutable root must not refill"
    );
    let db = rusqlite::Connection::open("/state/metadata-test.sqlite").unwrap();
    let mut q = db.prepare("SELECT id,body FROM objects").unwrap();
    let rows = q
        .query_map([], |r| {
            Ok((r.get::<_, Vec<u8>>(0)?, r.get::<_, Vec<u8>>(1)?))
        })
        .unwrap();
    let mut count = 0;
    for row in rows {
        let (id, bytes) = row.unwrap();
        assert_eq!(ObjectId::for_bytes(&bytes).as_bytes().as_slice(), id);
        assert!(
            [ROOT, INODES, DIRECTORY]
                .into_iter()
                .any(|kind| metadata::expand(kind, &bytes).is_ok()),
            "payload was prefetched"
        );
        count += 1;
    }
    assert!(
        count > metadata::WINDOW,
        "fixture must cross a metadata window"
    );
    let lengths: i64 = db
        .query_row("SELECT count(*) FROM lengths", [], |r| r.get(0))
        .unwrap();
    assert!(
        lengths > 4096,
        "fixture must cross a file-length provider window"
    );
    println!("METADATA_VERIFIED objects={count} lengths={lengths} requests={first}");
}

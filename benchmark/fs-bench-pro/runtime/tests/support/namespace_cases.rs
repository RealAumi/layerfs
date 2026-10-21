//! Refusal and page-boundary fixtures for the independent namespace proof.
use super::*;

#[test]
fn bounded_traversal_keeps_whole_path_limits() {
    for (depth, width) in [(257, 1), (18, 240)] {
        let mut entries = vec![Entry::directory(".")];
        let component = "a".repeat(width);
        let mut path = String::new();
        for _ in 0..depth {
            if !path.is_empty() {
                path.push('/');
            }
            path.push_str(&component);
            entries.push(Entry::directory(path.clone()));
        }
        assert!(matches!(
            layerfs_content::LogicalPath::new(&path),
            Err(ContentError::PathLimitExceeded)
        ));
        let (root, bag) = constructed(
            layerfs_content::filesystem::root::scope_for_seed([95; 32]),
            &entries,
        );
        let error = workspace_oracle::verify_tree(&bag, root, &entries, false, None, true)
            .err()
            .expect("whole-path limit must remain required");
        assert!(matches!(
            error.downcast_ref::<ContentError>(),
            Some(ContentError::PathLimitExceeded)
        ));
    }
}

#[test]
fn bounded_traversal_refuses_missing_serial_provider_and_wrong_kind() {
    use layerfs_content::filesystem::{
        directory::{decode_directory_page, encode_directory_page, DirectoryPage},
        root::FilesystemRoot,
    };
    let (root, mut bag, entries) = tiny_scratch_fixture();
    let parsed = FilesystemRoot::decode(&bag.bytes[&root]).unwrap();
    let mut tree = layerfs_content::filesystem::FilesystemRead::new(
        &bag,
        layerfs_content::filesystem::FilesystemRootId(root),
    )
    .unwrap();
    let original = tree
        .resolve_inode(parsed.root_inode().serial())
        .unwrap()
        .value
        .content_root;
    let DirectoryPage::Leaf {
        entries: mut bindings,
    } = decode_directory_page(&bag.bytes[&original]).unwrap()
    else {
        panic!("small fixture requires directory leaf")
    };
    bindings[0].1 = 999;
    let directory =
        bag.put(encode_directory_page(&DirectoryPage::Leaf { entries: bindings }).unwrap());
    let missing = rewrite_test_inode(root, &mut bag, parsed.root_inode().serial(), |inode| {
        inode.content_root = directory
    });
    let error = workspace_oracle::verify_tree(&bag, missing, &entries, false, None, true)
        .err()
        .expect("listed missing inode must fail");
    assert!(error
        .to_string()
        .contains("serial missing from inode table"));
    let (root, mut bag, entries) = tiny_scratch_fixture();
    let parsed = FilesystemRoot::decode(&bag.bytes[&root]).unwrap();
    bag.bytes.remove(&parsed.inode_table());
    let error = workspace_oracle::verify_tree(&bag, root, &entries, false, None, true)
        .err()
        .expect("provider loss must fail");
    assert!(matches!(
        error.downcast_ref::<ContentError>(),
        Some(ContentError::MissingObject)
    ));
    let (root, mut bag, entries) = tiny_scratch_fixture();
    let wrong = rewrite_test_inode(root, &mut bag, 2, |inode| {
        inode.kind = InodeKind::RegularFile
    });
    assert!(workspace_oracle::verify_tree(&bag, wrong, &entries, false, None, true).is_err());
}

fn rewrite_test_inode(
    root: ObjectId,
    bag: &mut Bag,
    serial: u64,
    change: impl FnOnce(&mut InodeValue),
) -> ObjectId {
    use layerfs_content::filesystem::{
        inode::codec::{decode_inode_page, encode_inode_page, InodePage},
        root::FilesystemRoot,
    };
    let root = FilesystemRoot::decode(&bag.bytes[&root]).unwrap();
    let mut page = decode_inode_page(&bag.bytes[&root.inode_table()]).unwrap();
    let InodePage::Leaf { entries } = &mut page else {
        panic!("small fixture requires one inode leaf")
    };
    change(
        &mut entries
            .iter_mut()
            .find(|entry| entry.0 == serial)
            .unwrap()
            .1,
    );
    let table = bag.put(encode_inode_page(&page).unwrap());
    bag.put(root.with_inode_table(table).encode().unwrap())
}

#[test]
fn bounded_traversal_keeps_point_lookup_child_level_refusal() {
    use layerfs_content::filesystem::{
        directory::{decode_directory_page, encode_directory_page, DirectoryPage},
        root::FilesystemRoot,
    };
    let mut entries = vec![Entry::directory(".")];
    for index in 0..28 {
        entries.push(Entry::file(
            format!("{}{:04}", "a".repeat(236), index),
            Content::Literal(vec![index as u8]),
        ));
    }
    let (root, mut bag) = constructed(
        layerfs_content::filesystem::root::scope_for_seed([93; 32]),
        &entries,
    );
    assert!(workspace_oracle::verify_tree(&bag, root, &entries, false, None, true).is_ok());
    let mut tree = layerfs_content::filesystem::FilesystemRead::new(
        &bag,
        layerfs_content::filesystem::FilesystemRootId(root),
    )
    .unwrap();
    let directory = tree
        .resolve(&layerfs_content::LogicalPath::new("").unwrap())
        .unwrap()
        .value
        .content_root;
    let DirectoryPage::Leaf { entries: bindings } =
        decode_directory_page(&bag.bytes[&directory]).unwrap()
    else {
        panic!("small source fixture requires one directory leaf")
    };
    let mut children = Vec::new();
    let mut subtree_bytes = 0;
    for half in bindings.chunks(14) {
        let leaf = DirectoryPage::Leaf {
            entries: half.to_vec(),
        };
        let canonical = encode_directory_page(&leaf).unwrap();
        assert!(layerfs_content::filesystem::directory::codec::filled_page(
            canonical.len()
        ));
        subtree_bytes += leaf.subtree_bytes();
        let maximum = half.last().unwrap().0.clone();
        children.push((maximum, bag.put(canonical)));
    }
    let page = DirectoryPage::Branch {
        level: 2,
        subtree_count: 28,
        subtree_bytes,
        children,
    };
    let directory = bag.put(encode_directory_page(&page).unwrap());
    let serial = FilesystemRoot::decode(&bag.bytes[&root])
        .unwrap()
        .root_inode()
        .serial();
    let root = rewrite_test_inode(root, &mut bag, serial, |inode| {
        inode.content_root = directory
    });
    let mut tree = layerfs_content::filesystem::FilesystemRead::new(
        &bag,
        layerfs_content::filesystem::FilesystemRootId(root),
    )
    .unwrap();
    assert!(
        tree.list_inode(serial, None, 128, 16384).is_ok(),
        "listing alone lacks the point lookup level check"
    );
    assert!(tree
        .resolve(&layerfs_content::LogicalPath::new(&entries[1].path).unwrap())
        .unwrap_err()
        .to_string()
        .contains("directory child summary"));
    let error = workspace_oracle::verify_tree(&bag, root, &entries, false, None, true)
        .err()
        .expect("point child summary must remain required");
    assert!(error.to_string().contains("directory child summary"));
}

#[test]
fn bounded_traversal_keeps_page_membership_and_symlink_checks() {
    let mut entries = vec![Entry::directory("."), Entry::directory("dir")];
    for index in 0..129 {
        entries.push(Entry::file(
            format!("dir/file-{index:03}"),
            Content::Literal(vec![index as u8]),
        ));
    }
    entries.push(Entry::symlink("dir/link", "file-000"));
    let scope = layerfs_content::filesystem::root::scope_for_seed([94; 32]);
    let (root, bag) = constructed(scope, &entries);
    let proof = workspace_oracle::verify_tree(&bag, root, &entries, false, None, true).unwrap();
    assert_eq!(proof.paths, 132);
    assert_eq!(proof.bytes, 129);
    let mut wrong = entries.clone();
    wrong.last_mut().unwrap().kind = EntryKind::Symlink("wrong-target".into());
    let (root, bag) = constructed(scope, &wrong);
    assert!(workspace_oracle::verify_tree(&bag, root, &entries, false, None, true).is_err());
    let mut extra = entries.clone();
    extra.push(Entry::file("dir/unexpected", Content::Literal(vec![1])));
    let (root, bag) = constructed(scope, &extra);
    assert!(workspace_oracle::verify_tree(&bag, root, &entries, false, None, true).is_err());
    let omitted = entries
        .iter()
        .filter(|entry| entry.path != "dir/file-000")
        .cloned()
        .collect::<Vec<_>>();
    let (root, bag) = constructed(scope, &omitted);
    assert!(workspace_oracle::verify_tree(&bag, root, &entries, false, None, true).is_err());
}

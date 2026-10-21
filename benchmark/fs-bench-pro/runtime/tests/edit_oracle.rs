//! External authenticated current-format examples for independent edit proofs.
#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
mod namespace;
use namespace::reference;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[path = "../src/edit_oracle.rs"]
mod edit_oracle;

use layerfs_content::{
    file::mapping::{self, ChildDescriptor, ExtentNode, ExtentSlice, FileState},
    filesystem::{
        directory::codec::{encode_directory_page, DirectoryPage},
        inode::codec::{encode_inode_page, InodePage},
        root::{profile_id, scope_for_seed, FilesystemRoot},
        PathName,
    },
    object::{
        inode_leaf::{InodeKind, InodeValue},
        AuthenticatedObjects,
    },
    ContentError, ContentResult, ObjectId,
};
use reference::sdk_edit_common::{ReplacementKind, Scenario};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Default)]
struct Objects(BTreeMap<ObjectId, Vec<u8>>);
impl Objects {
    fn put(&mut self, bytes: Vec<u8>) -> ObjectId {
        let id = ObjectId::for_bytes(&bytes);
        self.0.insert(id, bytes);
        id
    }
    fn payload(&mut self, byte: u8, length: usize) -> ObjectId {
        self.put(mapping::encode_chunk_object(&vec![byte; length]).unwrap())
    }
    fn file(&mut self, extents: Vec<ExtentSlice>) -> ObjectId {
        let length = extents.iter().map(|e| u64::from(e.logical_length())).sum();
        let count = extents.len() as u64;
        let node = self.put(
            mapping::encode_node(
                &ExtentNode::Leaf {
                    subtree_logical_bytes: length,
                    extents,
                },
                true,
            )
            .unwrap(),
        );
        self.state(node, length, count, 0)
    }
    fn state(
        &mut self,
        mapping_root: ObjectId,
        logical_len: u64,
        extent_count: u64,
        tree_level: u8,
    ) -> ObjectId {
        self.put(
            mapping::encode_file_state(FileState {
                logical_len,
                extent_count,
                tree_level,
                profile_id: mapping::profile_id(),
                mapping_root,
            })
            .unwrap(),
        )
    }
    fn tree(&mut self, file: ObjectId, serial: u64, scope: u8) -> ObjectId {
        let directory = self.put(
            encode_directory_page(&DirectoryPage::Leaf {
                entries: vec![(PathName::new("payload.bin").unwrap(), serial)],
            })
            .unwrap(),
        );
        let table = self.put(
            encode_inode_page(&InodePage::Leaf {
                entries: vec![
                    (1, inode(InodeKind::Directory, directory, 0)),
                    (serial, inode(InodeKind::RegularFile, file, 1)),
                ],
            })
            .unwrap(),
        );
        self.put(
            FilesystemRoot::new(profile_id(), scope_for_seed([scope; 32]), 1, table)
                .unwrap()
                .encode()
                .unwrap(),
        )
    }
}
impl AuthenticatedObjects for Objects {
    fn read_canonical_batch(&self, ids: &[ObjectId]) -> ContentResult<Vec<Vec<u8>>> {
        ids.iter()
            .map(|id| {
                let bytes = self.0.get(id).ok_or(ContentError::MissingObject)?;
                if ObjectId::for_bytes(bytes) != *id {
                    return Err(ContentError::IdentityMismatch);
                }
                Ok(bytes.clone())
            })
            .collect()
    }
}
fn inode(kind: InodeKind, content_root: ObjectId, namespace_ref_count: u64) -> InodeValue {
    InodeValue {
        kind,
        namespace_ref_count,
        content_root,
        metadata_root: ObjectId::for_bytes(b"unused test metadata"),
    }
}
fn extent(id: ObjectId, source: u32, length: u32) -> ExtentSlice {
    ExtentSlice::new(id, source, length).unwrap()
}
fn scenario(
    family: &'static str,
    initial: u64,
    start: u64,
    delete: u64,
    replacement: u64,
) -> Scenario {
    Scenario {
        family_id: family,
        id: "independent-current-mapping-example".into(),
        operation_key: "example",
        fixture_bytes: initial,
        start,
        delete_len: delete,
        replacement_kind: ReplacementKind::Inline,
        replacement_len: replacement,
        payload_seed: 1,
        payload_sha256: "unused in mapping subproof",
        final_bytes: initial - delete + replacement,
        plan_sha256: "unused in mapping subproof".into(),
    }
}

#[test]
fn edit_oracle_canonical_counts_reject_wrong_initial_and_final_at_every_original_case() {
    for scenario in reference::edit_canonical_chunk_count::registry() {
        let wanted = reference::edit_canonical_chunk_count::expected(&scenario);
        edit_oracle::require_canonical_counts(&scenario, wanted.initial_count, wanted.final_count)
            .unwrap();
        assert!(edit_oracle::require_canonical_counts(
            &scenario,
            wanted.initial_count + 1,
            wanted.final_count
        )
        .unwrap_err()
        .to_string()
        .contains("canonical chunk counts differ"));
        assert!(edit_oracle::require_canonical_counts(
            &scenario,
            wanted.initial_count,
            wanted.final_count + 1
        )
        .unwrap_err()
        .to_string()
        .contains("canonical chunk counts differ"));
    }
}

#[test]
fn edit_oracle_complete_membership_accepts_exact_and_rejects_unreachable_or_missing_rows() {
    let mut objects = Objects::default();
    let unused = ObjectId::for_bytes(b"unused content");
    let mut rows = vec![
        (1, inode(InodeKind::Directory, unused, 0)),
        (2, inode(InodeKind::RegularFile, unused, 1)),
    ];
    let table = objects.put(
        encode_inode_page(&InodePage::Leaf {
            entries: rows.clone(),
        })
        .unwrap(),
    );
    let root = FilesystemRoot::new(profile_id(), scope_for_seed([3; 32]), 1, table).unwrap();
    edit_oracle::require_complete_membership(&objects, root, &BTreeSet::from([1, 2])).unwrap();
    assert!(
        edit_oracle::require_complete_membership(&objects, root, &BTreeSet::from([1, 2, 3]))
            .unwrap_err()
            .to_string()
            .contains("missing")
    );
    rows.push((3, inode(InodeKind::RegularFile, unused, 1)));
    let table = objects.put(encode_inode_page(&InodePage::Leaf { entries: rows }).unwrap());
    let root = root.with_inode_table(table);
    assert!(
        edit_oracle::require_complete_membership(&objects, root, &BTreeSet::from([1, 2]))
            .unwrap_err()
            .to_string()
            .contains("unreachable")
    );
}

#[test]
fn edit_oracle_insert_retains_all_initial_payload_ids_and_inode_identity() {
    let mut objects = Objects::default();
    let old = objects.payload(1, 64);
    let replacement = objects.payload(2, 16);
    let original = objects.file(vec![extent(old, 0, 64)]);
    let final_file = objects.file(vec![
        extent(old, 0, 32),
        extent(replacement, 0, 16),
        extent(old, 32, 32),
    ]);
    let initial = objects.tree(original, 2, 3);
    let final_root = objects.tree(final_file, 2, 3);
    let plan = scenario("edit_length_changing", 64, 32, 0, 16);
    edit_oracle::verify_edit(&objects, initial, final_root, &plan).unwrap();
    let moved_inode = objects.tree(final_file, 3, 3);
    assert!(
        edit_oracle::verify_edit(&objects, initial, moved_inode, &plan)
            .unwrap_err()
            .to_string()
            .contains("inode identity")
    );
    let moved_scope = objects.tree(final_file, 2, 4);
    assert!(
        edit_oracle::verify_edit(&objects, initial, moved_scope, &plan)
            .unwrap_err()
            .to_string()
            .contains("inode identity")
    );
    let substituted = objects.payload(3, 80);
    let substituted_file = objects.file(vec![extent(substituted, 0, 80)]);
    let substituted_root = objects.tree(substituted_file, 2, 3);
    assert!(
        edit_oracle::verify_edit(&objects, initial, substituted_root, &plan)
            .unwrap_err()
            .to_string()
            .contains("untouched payload")
    );
}

#[test]
fn edit_oracle_deletion_retains_only_wholly_untouched_initial_extents() {
    let mut objects = Objects::default();
    let deleted = objects.payload(1, 32);
    let retained = objects.payload(2, 32);
    let original = objects.file(vec![extent(deleted, 0, 32), extent(retained, 0, 32)]);
    let final_file = objects.file(vec![extent(retained, 0, 32)]);
    let initial = objects.tree(original, 2, 3);
    let final_root = objects.tree(final_file, 2, 3);
    let plan = scenario("edit_length_changing", 64, 0, 32, 0);
    edit_oracle::verify_edit(&objects, initial, final_root, &plan).unwrap();
    let substituted = objects.payload(3, 32);
    let substituted_file = objects.file(vec![extent(substituted, 0, 32)]);
    let substituted_root = objects.tree(substituted_file, 2, 3);
    assert!(
        edit_oracle::verify_edit(&objects, initial, substituted_root, &plan)
            .unwrap_err()
            .to_string()
            .contains("untouched payload")
    );
}

#[test]
fn edit_oracle_capped_unchanged_suffix_keeps_exact_shifted_source_offsets() {
    let mut objects = Objects::default();
    let old = objects.payload(1, 64);
    let replacement = objects.payload(2, 32);
    let original = objects.file(vec![extent(old, 0, 64)]);
    let final_file = objects.file(vec![
        extent(old, 0, 16),
        extent(replacement, 0, 32),
        extent(old, 32, 32),
    ]);
    let initial = objects.tree(original, 2, 3);
    let final_root = objects.tree(final_file, 2, 3);
    let plan = scenario("edit_length_changing_capped", 64, 16, 16, 32);
    edit_oracle::verify_edit(&objects, initial, final_root, &plan).unwrap();
    let bad_file = objects.file(vec![
        extent(old, 0, 16),
        extent(replacement, 0, 32),
        extent(old, 0, 32),
    ]);
    let bad_root = objects.tree(bad_file, 2, 3);
    assert!(edit_oracle::verify_edit(&objects, initial, bad_root, &plan)
        .unwrap_err()
        .to_string()
        .contains("source-offset transcript"));
}

#[test]
fn edit_oracle_mapping_walk_rejects_child_summary_and_complete_state_mismatch() {
    let mut objects = Objects::default();
    let extents = (0..128)
        .map(|byte| {
            let id = objects.payload(byte, 1);
            extent(id, 0, 1)
        })
        .collect::<Vec<_>>();
    let left = objects.put(
        mapping::encode_node(
            &ExtentNode::Leaf {
                subtree_logical_bytes: 64,
                extents: extents[..64].to_vec(),
            },
            false,
        )
        .unwrap(),
    );
    let right = objects.put(
        mapping::encode_node(
            &ExtentNode::Leaf {
                subtree_logical_bytes: 64,
                extents: extents[64..].to_vec(),
            },
            false,
        )
        .unwrap(),
    );
    let mapping = objects.put(
        mapping::encode_node(
            &ExtentNode::Branch {
                level: 1,
                subtree_logical_bytes: 128,
                subtree_extent_count: 128,
                children: vec![
                    ChildDescriptor {
                        cumulative_logical_end: 64,
                        cumulative_extent_end: 64,
                        child_object_id: left,
                    },
                    ChildDescriptor {
                        cumulative_logical_end: 128,
                        cumulative_extent_end: 128,
                        child_object_id: right,
                    },
                ],
            },
            true,
        )
        .unwrap(),
    );
    let file = objects.state(mapping, 128, 128, 1);
    let initial = objects.tree(file, 2, 3);
    let plan = scenario("edit_length_preserving", 128, 64, 1, 1);
    edit_oracle::verify_edit(&objects, initial, initial, &plan).unwrap();
    let wrong_mapping = objects.put(
        mapping::encode_node(
            &ExtentNode::Branch {
                level: 1,
                subtree_logical_bytes: 128,
                subtree_extent_count: 128,
                children: vec![
                    ChildDescriptor {
                        cumulative_logical_end: 65,
                        cumulative_extent_end: 64,
                        child_object_id: left,
                    },
                    ChildDescriptor {
                        cumulative_logical_end: 128,
                        cumulative_extent_end: 128,
                        child_object_id: right,
                    },
                ],
            },
            true,
        )
        .unwrap(),
    );
    let wrong_file = objects.state(wrong_mapping, 128, 128, 1);
    let wrong_root = objects.tree(wrong_file, 2, 3);
    assert!(
        edit_oracle::verify_edit(&objects, initial, wrong_root, &plan)
            .unwrap_err()
            .to_string()
            .contains("parent/child totals")
    );
    let wrong_count_file = objects.state(mapping, 128, 129, 1);
    let wrong_count_root = objects.tree(wrong_count_file, 2, 3);
    assert!(
        edit_oracle::verify_edit(&objects, initial, wrong_count_root, &plan)
            .unwrap_err()
            .to_string()
            .contains("parent/child totals")
    );
}

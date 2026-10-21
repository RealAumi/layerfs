//! Independent declared inode classes of the original BA schedule.
#[path = "../../engine/recipes/edit_model.rs"]
mod edit_model;
#[allow(dead_code)]
#[path = "../../workload/main.rs"]
mod reference;

use reference::file_size_transition::{ALIAS, ALIAS_ROUNDTRIP, TARGET};
use reference::workspace_common::EntryKind;

#[test]
fn initial_and_four_alias_mutations_keep_one_inode_class() {
    let lengths = [131071, 131072, 131073, 131072, 131071];
    for (step, length) in lengths.into_iter().enumerate() {
        let entries = edit_model::entries(ALIAS_ROUNDTRIP, step).unwrap();
        let target = entries.iter().find(|entry| entry.path == TARGET).unwrap();
        let alias = entries.iter().find(|entry| entry.path == ALIAS).unwrap();
        assert!(matches!(&alias.kind, EntryKind::Hardlink(path) if path == TARGET));
        assert!(matches!(&target.kind, EntryKind::File(content) if content.len() == length));
    }
}

#[test]
fn final_atomic_save_splits_names_and_keeps_original_alias_bytes() {
    let before = edit_model::entries(ALIAS_ROUNDTRIP, 4).unwrap();
    let after = edit_model::entries(ALIAS_ROUNDTRIP, 5).unwrap();
    let bytes = |entries: &[reference::workspace_common::Entry], name: &str| match &entries
        .iter()
        .find(|entry| entry.path == name)
        .unwrap()
        .kind
    {
        EntryKind::File(content) => {
            let mut bytes = Vec::new();
            content.write_to(&mut bytes).unwrap();
            bytes
        }
        _ => panic!("declared final name must be a separate regular inode"),
    };
    assert_eq!(bytes(&before, TARGET), bytes(&after, ALIAS));
    assert_eq!(bytes(&after, ALIAS).len(), 131071);
    assert_eq!(bytes(&after, TARGET).len(), 131072);
}

#[test]
fn alias_state_after_declared_schedule_is_refused() {
    assert!(edit_model::entries(ALIAS_ROUNDTRIP, 6).is_err());
}

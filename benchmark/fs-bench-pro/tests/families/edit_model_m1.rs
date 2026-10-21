//! Original M1 recipe states, selective proof scope and ordered P-3 members.
#[allow(dead_code)]
#[path = "../../engine/recipes/edit_model.rs"]
mod edit_model;
#[allow(dead_code)]
#[path = "../../workload/main.rs"]
mod reference;
#[path = "../../engine/recipes/sdk_edit_model.rs"]
mod sdk_edit_model;

use edit_model::m1_state;
use reference::workspace_common::{Content, Entry, EntryKind};
use sdk_edit_model::sdk_step;
use std::collections::BTreeMap;

const SMALL: &str = "v016-mixed-development-100mb-5000-k10-v1";
const LARGE: &str = "v016-mixed-development-500mb-30000-k10-v1";

fn file<'a>(entries: &'a [Entry], path: &str) -> &'a Content {
    match &entries
        .iter()
        .find(|entry| entry.path == path)
        .unwrap()
        .kind
    {
        EntryKind::File(content) => content,
        _ => panic!("declared regular target required"),
    }
}

fn bytes(content: &Content, start: u64, length: usize) -> Vec<u8> {
    let mut value = vec![0; length];
    assert_eq!(content.read_at(start, &mut value).unwrap(), length);
    value
}

#[test]
fn m1_initial_census_includes_destination_and_scratch_directories() {
    for (id, regular, directories, logical) in [
        (SMALL, 4_984, 64, 99_934_464),
        (LARGE, 29_984, 314, 499_934_464),
    ] {
        let state = m1_state(id, 0, Some(&BTreeMap::new())).unwrap();
        assert_eq!(state.entries.len(), regular + directories);
        assert_eq!(state.ranges.len(), regular);
        assert_eq!(state.directory_modes.len(), directories - 1);
        assert!(state.file_modes.is_empty());
        assert!(state.file_mtimes.is_empty());
        assert!(state.required_created_directory_modes.is_empty());
        assert_eq!(
            state
                .entries
                .iter()
                .filter_map(|entry| match &entry.kind {
                    EntryKind::File(content) => Some(content.len()),
                    _ => None,
                })
                .sum::<u64>(),
            logical
        );
    }
}

#[test]
fn m1_stage2_pair_preserves_original_order_ranges_and_bytes() {
    let initial = m1_state(SMALL, 0, None).unwrap();
    let after = m1_state(SMALL, 2, None).unwrap();
    let fixture = reference::v016_common::load_fixture(&reference::v016_common::L100, 1).unwrap();
    let members = sdk_step(SMALL, 2).unwrap();
    assert_eq!(members.len(), 2);
    assert_eq!(members[0].edit.path, fixture.roles.edit.sdk_insert);
    assert_eq!(members[1].edit.path, fixture.roles.edit.sdk_delete);
    for (index, member) in members.iter().enumerate() {
        let before = file(&initial.entries, &member.edit.path);
        let next = file(&after.entries, &member.edit.path);
        let offset = ((before.len() / 2) / 8) * 8;
        assert_eq!(member.edit.start, offset);
        assert_eq!(member.before_len, before.len());
        assert_eq!(member.after_len, next.len());
        assert_eq!(bytes(next, 0, 4_096), bytes(before, 0, 4_096));
        if index == 0 {
            assert_eq!(member.edit.delete_len, 0);
            assert_eq!(member.edit.replacement.len(), 256);
            assert_eq!(next.len(), before.len() + 256);
            let marker = reference::dedup_workloads::content(
                "mixed_load_bearing",
                "v016-sdk-stage2",
                1,
                2,
                "insert-c1",
                256,
            )
            .unwrap();
            assert_eq!(member.edit.replacement, bytes(&marker, 0, 256));
            assert_eq!(bytes(next, offset, 256), member.edit.replacement);
            assert_eq!(bytes(next, offset + 256, 512), bytes(before, offset, 512));
        } else {
            assert_eq!(member.edit.delete_len, 256);
            assert!(member.edit.replacement.is_empty());
            assert_eq!(next.len(), before.len() - 256);
            assert_eq!(bytes(next, offset, 512), bytes(before, offset + 256, 512));
        }
        assert_eq!(
            after.ranges[&member.edit.path],
            vec![
                (offset - 4_096, 8_192),
                (0, 4_096),
                (next.len() - 4_096, 4_096),
            ]
        );
    }
    let reversed = sdk_step(SMALL, 7).unwrap();
    assert_eq!(reversed[0].edit.delete_len, 256);
    assert!(reversed[0].edit.replacement.is_empty());
    assert_eq!(reversed[1].edit.delete_len, 0);
    assert_eq!(reversed[1].edit.replacement.len(), 256);
    for member in reversed {
        assert_eq!(
            member.after_len,
            file(&initial.entries, &member.edit.path).len()
        );
        assert_eq!(member.metadata.path, member.edit.path);
    }
    for step in [0, 1, 3, 4, 5, 6, 8, 9, 10, 11] {
        assert!(sdk_step(SMALL, step).is_err());
    }
}

#[test]
fn m1_selective_scope_keeps_exact_boundary_and_changed_anchor_contracts() {
    let state = m1_state(SMALL, 2, None).unwrap();
    let fixture = reference::v016_common::load_fixture(&reference::v016_common::L100, 1).unwrap();
    let below = &fixture.roles.boundary_below;
    let above = &fixture.roles.boundary_above;
    assert_eq!(file(&state.entries, below).len(), 131_072);
    assert!(state.ranges[below].is_empty());
    assert_eq!(file(&state.entries, above).len(), 131_072);
    assert!(state.ranges[above].is_empty());
    let anchor = &fixture.roles.edit.anchor_overwrite;
    let offset = reference::v016_stages::anchor_offset(1, fixture.len(anchor).unwrap());
    assert_eq!(state.ranges[anchor], vec![(offset, 4_096), (0, 4_096)]);
    let unchanged = fixture
        .entries
        .iter()
        .find(|entry| {
            matches!(&entry.kind, EntryKind::File(content) if content.len() >= 1_048_576)
                && entry.path != *anchor
                && entry.path != fixture.roles.edit.sdk_insert
                && entry.path != fixture.roles.edit.sdk_delete
        })
        .unwrap();
    assert_eq!(
        state.ranges[&unchanged.path],
        vec![(0, file(&state.entries, &unchanged.path).len())]
    );
    assert!(state.file_modes.is_empty());
    assert!(state.file_mtimes.is_empty());
}

#[test]
fn m1_intermediate_link_classes_and_explicit_attributes_survive_then_disappear() {
    let fourth = m1_state(SMALL, 4, None).unwrap();
    let fifth = m1_state(SMALL, 5, None).unwrap();
    assert_eq!(
        fourth
            .entries
            .iter()
            .filter(|entry| matches!(entry.kind, EntryKind::Hardlink(_)))
            .count(),
        8
    );
    assert_eq!(
        fourth
            .entries
            .iter()
            .filter(|entry| matches!(entry.kind, EntryKind::Symlink(_)))
            .count(),
        4
    );
    assert_eq!(fourth.entries.len(), 5_060);
    assert_eq!(fifth.entries.len(), 5_048);
    assert!(fifth
        .entries
        .iter()
        .all(|entry| !matches!(entry.kind, EntryKind::Hardlink(_) | EntryKind::Symlink(_))));
    assert_eq!(fourth.file_modes.len(), 16);
    assert!(fourth.file_modes.values().all(|mode| *mode == 0o600));
    assert_eq!(fourth.file_mtimes.len(), 16);
    assert!(fourth
        .file_mtimes
        .values()
        .all(|value| *value == (1_700_000_010, 123_456_789)));
    assert_eq!(
        fourth
            .directory_modes
            .values()
            .filter(|mode| **mode == 0o700)
            .count(),
        4
    );
    let ninth = m1_state(SMALL, 9, None).unwrap();
    assert!(ninth.file_modes.values().all(|mode| *mode == 0o640));
    assert!(ninth
        .file_mtimes
        .values()
        .all(|value| *value == (1_700_000_020, 123_456_789)));
}

#[test]
fn m1_actual_scope_requires_original_live_created_directory_modes() {
    assert!(m1_state(SMALL, 3, Some(&BTreeMap::new())).is_err());
    let materialization = m1_state(SMALL, 10, None).unwrap();
    assert_eq!(materialization.required_created_directory_modes.len(), 17);
    let observed: BTreeMap<_, _> = materialization
        .required_created_directory_modes
        .iter()
        .map(|path| (path.clone(), 0o755))
        .collect();
    let actual = m1_state(SMALL, 10, Some(&observed)).unwrap();
    assert_eq!(actual.entries.len(), 5_048);
    let tsv = edit_model::m1_scope_tsv(&actual).unwrap();
    assert!(tsv.starts_with("original-m1-selective-scope-v1\n"));
    assert_eq!(tsv.lines().count(), actual.entries.len() + 2);
    assert!(tsv
        .lines()
        .skip(2)
        .all(|line| line.split('\t').count() == 8));
    let mut invalid = observed;
    *invalid.values_mut().next().unwrap() = 0o4755;
    assert!(m1_state(SMALL, 10, Some(&invalid)).is_err());
    assert!(m1_state(SMALL, 11, None).is_err());
    assert!(!edit_model::is_m1("v016-workspace-two-100mb-5000-k10-v1"));
}

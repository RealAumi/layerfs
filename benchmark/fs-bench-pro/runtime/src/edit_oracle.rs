//! Independent current-format inode membership and retained edit mappings.
use crate::{reference::sdk_edit_common::Scenario, Result};
use layerfs_content::{
    file::{mapping, FileView},
    filesystem::{
        inode::read::{rows_after, InodeReadWork, InodeTable},
        FilesystemRead, FilesystemRoot, FilesystemRootId, LogicalPath,
    },
    object::{inode_leaf::InodeKind, AuthenticatedObjects, ObjectId},
};
use layerfs_telemetry::timer::Timing;
use std::{collections::BTreeSet, ops::Range};

/// Every inode-table row must belong to the complete reachable namespace.
pub fn require_complete_membership(
    reader: &dyn AuthenticatedObjects,
    root: FilesystemRoot,
    reachable: &BTreeSet<u64>,
) -> Result<()> {
    let table = InodeTable {
        root: root.inode_table(),
        root_serial: root.root_inode().serial(),
    };
    let mut found = BTreeSet::new();
    let mut after = None;
    let mut work = InodeReadWork::default();
    loop {
        let rows = rows_after(reader, table, after, &mut work)?;
        if rows.is_empty() {
            break;
        }
        for (serial, value) in rows {
            if after.is_some_and(|prior| serial <= prior) || !found.insert(serial) {
                return Err("duplicate or unordered persisted inode-table serial".into());
            }
            value.validate(serial == table.root_serial)?;
            if !reachable.contains(&serial) {
                return Err("unreachable persisted inode-table row".into());
            }
            after = Some(serial);
        }
    }
    if &found != reachable || !found.contains(&table.root_serial) {
        return Err("missing persisted inode-table membership".into());
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct Slice {
    start: u64,
    end: u64,
    payload: ObjectId,
    source: u64,
}

/// Reconnect identity, complete mapping grammar and original retention rules.
pub fn verify_edit(
    reader: &dyn AuthenticatedObjects,
    initial_root: ObjectId,
    final_root: ObjectId,
    scenario: &Scenario,
) -> Result<()> {
    let delete_end = scenario
        .start
        .checked_add(scenario.delete_len)
        .ok_or("original edit range overflow")?;
    if delete_end > scenario.fixture_bytes
        || scenario
            .fixture_bytes
            .checked_sub(scenario.delete_len)
            .and_then(|length| length.checked_add(scenario.replacement_len))
            != Some(scenario.final_bytes)
    {
        return Err("original edit lengths/range differ".into());
    }
    let path = LogicalPath::new("payload.bin")?;
    let mut initial = FilesystemRead::new(reader, FilesystemRootId(initial_root))?;
    let mut final_tree = FilesystemRead::new(reader, FilesystemRootId(final_root))?;
    let before = initial.resolve(&path)?;
    let after = final_tree.resolve(&path)?;
    if before.serial != after.serial || initial.root().scope() != final_tree.root().scope() {
        return Err("persisted edit changed the initial inode identity".into());
    }
    if before.value.kind != InodeKind::RegularFile || after.value.kind != InodeKind::RegularFile {
        return Err("persisted edit payload inode is not regular".into());
    }
    let base = slices(reader, before.value.content_root, scenario.fixture_bytes)?;
    let final_mapping = slices(reader, after.value.content_root, scenario.final_bytes)?;
    require_canonical_counts(scenario, base.len() as u64, final_mapping.len() as u64)?;
    let required = base
        .iter()
        .filter(|slice| {
            scenario.delete_len == 0 || slice.end <= scenario.start || slice.start >= delete_end
        })
        .map(|slice| slice.payload)
        .collect::<BTreeSet<_>>();
    let actual = final_mapping
        .iter()
        .map(|slice| slice.payload)
        .collect::<BTreeSet<_>>();
    if !required.is_subset(&actual) {
        return Err("persisted edit lost an original untouched payload object".into());
    }
    if scenario.family_id == "edit_length_changing_capped" {
        unchanged(&base, &final_mapping, 0..scenario.start, 0)?;
        unchanged(
            &base,
            &final_mapping,
            delete_end..scenario.fixture_bytes,
            scenario
                .start
                .checked_add(scenario.replacement_len)
                .ok_or("original edit suffix position overflow")?,
        )?;
    }
    Ok(())
}

/// The canonical family's frozen count property remains a strict check.
pub fn require_canonical_counts(scenario: &Scenario, initial: u64, final_count: u64) -> Result<()> {
    if scenario.family_id == crate::reference::edit_canonical_chunk_count::FAMILY_ID {
        let wanted = crate::reference::edit_canonical_chunk_count::expected(scenario);
        if initial != wanted.initial_count || final_count != wanted.final_count {
            return Err(format!(
                "canonical chunk counts differ: initial {initial}/{} final {final_count}/{}",
                wanted.initial_count, wanted.final_count
            )
            .into());
        }
    }
    Ok(())
}

fn slices(reader: &dyn AuthenticatedObjects, root: ObjectId, length: u64) -> Result<Vec<Slice>> {
    let view = Timing::disabled("independent.edit.mapping", |timer| {
        FileView::open(reader, root, timer.child("open"))
    })
    .0?;
    if view.logical_len() != length {
        return Err("persisted edit initial/final file length differs".into());
    }
    let state = view
        .file_state()?
        .ok_or("original SDK mapping retention requires current chunked representation")?;
    if state.profile_id != mapping::profile_id() {
        return Err("persisted edit mapping profile differs".into());
    }
    let mut pending = vec![(
        state.mapping_root,
        true,
        state.tree_level,
        state.logical_len,
        state.extent_count,
    )];
    let mut result = Vec::new();
    let mut offset = 0_u64;
    while let Some((id, root_page, level, bytes, count)) = pending.pop() {
        let node = mapping::decode_node_with_context(&reader.read_canonical(id)?, root_page)?;
        if (node.level(), node.logical_len(), node.extent_count()) != (level, bytes, count) {
            return Err("persisted edit mapping parent/child totals differ".into());
        }
        match node {
            mapping::ExtentNode::Leaf { extents, .. } => {
                for extent in extents {
                    let end = offset
                        .checked_add(u64::from(extent.logical_length()))
                        .ok_or("persisted edit mapping length overflow")?;
                    result.push(Slice {
                        start: offset,
                        end,
                        payload: extent.payload_object_id(),
                        source: u64::from(extent.source_offset()),
                    });
                    offset = end;
                }
            }
            mapping::ExtentNode::Branch { children, .. } => {
                let mut previous_bytes = 0;
                let mut previous_count = 0;
                let mut next = Vec::with_capacity(children.len());
                for child in children {
                    next.push((
                        child.child_object_id,
                        false,
                        level.checked_sub(1).ok_or("persisted edit mapping depth")?,
                        child.cumulative_logical_end - previous_bytes,
                        child.cumulative_extent_end - previous_count,
                    ));
                    previous_bytes = child.cumulative_logical_end;
                    previous_count = child.cumulative_extent_end;
                }
                pending.extend(next.into_iter().rev());
            }
        }
    }
    if offset != state.logical_len || result.len() as u64 != state.extent_count {
        return Err("persisted edit complete mapping totals differ".into());
    }
    Ok(result)
}

fn unchanged(
    base: &[Slice],
    final_mapping: &[Slice],
    range: Range<u64>,
    target: u64,
) -> Result<()> {
    for original in base {
        let start = original.start.max(range.start);
        let end = original.end.min(range.end);
        if start >= end {
            continue;
        }
        let mut position = target
            .checked_add(start - range.start)
            .ok_or("persisted unchanged range position overflow")?;
        let mut source = original.source + start - original.start;
        let mut remaining = end - start;
        let mut index = final_mapping.partition_point(|slice| slice.end <= position);
        while remaining != 0 {
            let actual = final_mapping
                .get(index)
                .ok_or("persisted unchanged mapping slice missing")?;
            if position < actual.start || position >= actual.end {
                return Err("persisted unchanged mapping slice gap".into());
            }
            if actual.payload != original.payload
                || actual.source + position - actual.start != source
            {
                return Err("persisted unchanged payload/source-offset transcript differs".into());
            }
            let count = remaining.min(actual.end - position);
            position += count;
            source += count;
            remaining -= count;
            index += 1;
        }
    }
    Ok(())
}

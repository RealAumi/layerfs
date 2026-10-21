//! Original product-neutral semantic states and independent verification scopes.
use crate::reference;
use reference::sdk_edit_common::{ReplacementKind, Scenario};
use reference::workspace_common::{Content, Entry, EntryKind};
use reference::{v016_common as v016, v016_stages as stages};
use std::collections::{BTreeMap, BTreeSet};

pub fn scenario(id: &str) -> Option<Scenario> {
    reference::edit_length_preserving::registry()
        .into_iter()
        .chain(reference::edit_length_changing::registry())
        .chain(reference::edit_canonical_chunk_count::registry())
        .chain(reference::edit_length_changing_capped::registry())
        .find(|row| row.id == id)
}

/// Complete expected tree, including the canonical family's final byte digest.
pub fn entries(id: &str, step: usize) -> reference::Result<Vec<Entry>> {
    let entries = descriptors(id, step)?;
    let canonical = scenario(id)
        .filter(|row| row.family_id == reference::edit_canonical_chunk_count::FAMILY_ID);
    if let (1, Some(row)) = (step, canonical) {
        if original_fixture_hash(&entries)?
            != reference::edit_canonical_chunk_count::expected(&row).final_sha256
        {
            return Err("original canonical final byte digest differs".into());
        }
    }
    Ok(entries)
}

/// The same tree without generating its bytes. The timed writer needs only the
/// metadata descriptors; preparation, verification and the oracle keep the
/// digest check through `entries`.
pub fn descriptors(id: &str, step: usize) -> reference::Result<Vec<Entry>> {
    if is_m1(id) {
        return Ok(m1_state(id, step, None)?.entries);
    }
    let Some(row) = scenario(id) else {
        let case = reference::workspace_registry::resolve(id)?;
        let mut entries = reference::workspace_registry::expected(&case, 1, step)?;
        // The frozen boundary oracle flattens aliases for its byte reader.
        // Native trees and current inode proofs must retain the declared class
        // until the final atomic save replaces only the target name.
        if id == reference::file_size_transition::ALIAS_ROUNDTRIP && step < 5 {
            entries
                .iter_mut()
                .find(|entry| entry.path == reference::file_size_transition::ALIAS)
                .ok_or("original boundary alias missing")?
                .kind = EntryKind::Hardlink(reference::file_size_transition::TARGET.to_owned());
        }
        return Ok(entries);
    };
    if step > 1 {
        return Err("original SDK edit has only initial and one final state".into());
    }
    if row
        .start
        .checked_add(row.delete_len)
        .is_none_or(|end| end > row.fixture_bytes)
        || row.final_bytes != row.fixture_bytes - row.delete_len + row.replacement_len
    {
        return Err("original SDK scenario algebra differs".into());
    }
    let initial = Content::Seed {
        seed: reference::edit_length_changing_capped::GENERATOR_SEED,
        len: row.fixture_bytes,
    };
    let content = if step == 0 {
        initial
    } else {
        let replacement = match row.replacement_kind {
            ReplacementKind::Inline => {
                let bytes = reference::sdk_edit_common::replacement_bytes(&row);
                if bytes.len() as u64 != row.replacement_len
                    || reference::sdk_edit_common::sha256_hex(&bytes) != row.payload_sha256
                {
                    return Err("original SDK inline payload seal differs".into());
                }
                Content::Literal(bytes)
            }
            ReplacementKind::Zero => Content::Zero {
                len: row.replacement_len,
            },
        };
        initial.splice(row.start, row.delete_len, replacement)?
    };
    if content.len()
        != if step == 0 {
            row.fixture_bytes
        } else {
            row.final_bytes
        }
    {
        return Err("original SDK expected file length differs".into());
    }
    let entries = vec![Entry::directory("."), Entry::file("payload.bin", content)];
    reference::workspace_common::validate_entries(&entries)?;
    Ok(entries)
}

pub fn original_fixture_hash(entries: &[Entry]) -> reference::Result<String> {
    let EntryKind::File(content) = &entries[1].kind else {
        return Err("SDK fixture file descriptor missing".into());
    };
    content.digest()
}

// Product-neutral M1 shadow and declared ranges transcribed from the frozen
// src/v016_oracle.rs; no Store, SDK operation, current-format decoder or I/O.
#[derive(Clone)]
enum Shadow {
    File(Content),
    Ranged {
        len: u64,
        content: Content,
        ranges: Vec<(u64, u64)>,
    },
}

impl Shadow {
    fn len(&self) -> u64 {
        match self {
            Self::File(content) => content.len(),
            Self::Ranged { len, .. } => *len,
        }
    }
    fn content(&self) -> &Content {
        match self {
            Self::File(content) | Self::Ranged { content, .. } => content,
        }
    }
}

struct ShadowState {
    aliases: BTreeMap<String, String>,
    symlinks: BTreeMap<String, String>,
    required_created: BTreeSet<String>,
    paths: BTreeMap<String, Shadow>,
    /// Every declared directory of the current state, following the stage-3
    /// moves, so the directory inventory is checked against the declared
    /// namespace rather than the pristine fixture.
    directories: BTreeSet<String>,
    /// Explicit file modes after the attribute stages.
    modes: BTreeMap<String, u32>,
    /// Explicit mtimes after the attribute stages, in whole seconds.
    mtimes: BTreeMap<String, i64>,
    /// Explicit directory modes after the attribute stages.
    directory_modes: BTreeMap<String, u32>,
}

/// One path's declared state: a full recipe at or below the exact 128 KiB
/// boundary, or a declared length plus the ranges the verifier reads back above
/// it. The threshold is exact: 131,072 B enters the chunked path.
fn declared(path: &str, content: Content) -> (String, Shadow) {
    let len = content.len();
    if len <= v016::BOUNDARY_EXACT {
        (path.to_owned(), Shadow::File(content))
    } else {
        (
            path.to_owned(),
            Shadow::Ranged {
                len,
                content,
                // A file whose declared content is unchanged is proved by its
                // full declared-range read.
                ranges: vec![(0, len)],
            },
        )
    }
}

fn shadow_from_fixture(fixture: &v016::LoadFixture) -> ShadowState {
    let mut paths = BTreeMap::new();
    let mut directories = BTreeSet::new();
    let mut directory_modes = BTreeMap::new();
    for entry in &fixture.entries {
        if entry.path == "." {
            continue;
        }
        match &entry.kind {
            EntryKind::File(content) => {
                let (path_key, state) = declared(&entry.path, content.clone());
                paths.insert(path_key, state);
            }
            EntryKind::Directory => {
                directories.insert(entry.path.clone());
                directory_modes.insert(entry.path.clone(), entry.mode);
            }
            EntryKind::Hardlink(_) | EntryKind::Symlink(_) => {}
        }
    }
    ShadowState {
        aliases: BTreeMap::new(),
        symlinks: BTreeMap::new(),
        required_created: BTreeSet::new(),
        paths,
        directories,
        modes: BTreeMap::new(),
        mtimes: BTreeMap::new(),
        directory_modes,
    }
}

fn ranged(len: u64, content: Content, ranges: Vec<(u64, u64)>) -> Shadow {
    Shadow::Ranged {
        len,
        content,
        ranges,
    }
}

impl ShadowState {
    /// Relocate every declared path below `source` to `destination`, which is
    /// what a real rename does to the whole subtree.
    fn remap_prefix(&mut self, source: &str, destination: &str) {
        let prefix = format!("{source}/");
        let moved_directories: Vec<String> = self
            .directories
            .iter()
            .filter(|path| path.starts_with(&prefix))
            .map(|path| format!("{destination}/{}", &path[prefix.len()..]))
            .collect();
        self.directories.retain(|path| !path.starts_with(&prefix));
        // The moved subtree's own root is a namespace entry too, so the exact
        // source path moves with its descendants.
        if self.directories.remove(source) {
            self.directories.insert(destination.to_owned());
        }
        self.directories.extend(moved_directories);
        if let Some(mode) = self.directory_modes.remove(source) {
            self.directory_modes.insert(destination.to_owned(), mode);
        }
        let moved_modes: Vec<(String, u32)> = self
            .directory_modes
            .iter()
            .filter(|(path, _)| path.starts_with(&prefix))
            .map(|(path, value)| (format!("{destination}/{}", &path[prefix.len()..]), *value))
            .collect();
        self.directory_modes
            .retain(|path, _| !path.starts_with(&prefix));
        for (path, value) in moved_modes {
            self.directory_modes.insert(path, value);
        }
        let moved: Vec<(String, Shadow)> = self
            .paths
            .iter()
            .filter(|(path, _)| path.starts_with(&prefix))
            .map(|(path, state)| {
                (
                    format!("{destination}/{}", &path[prefix.len()..]),
                    state.clone(),
                )
            })
            .collect();
        self.paths.retain(|path, _| !path.starts_with(&prefix));
        for (path, state) in moved {
            self.paths.insert(path, state);
        }
        let modes: Vec<(String, u32)> = self
            .modes
            .iter()
            .filter(|(path, _)| path.starts_with(&prefix))
            .map(|(path, value)| (format!("{destination}/{}", &path[prefix.len()..]), *value))
            .collect();
        self.modes.retain(|path, _| !path.starts_with(&prefix));
        for (path, value) in modes {
            self.modes.insert(path, value);
        }
        let mtimes: Vec<(String, i64)> = self
            .mtimes
            .iter()
            .filter(|(path, _)| path.starts_with(&prefix))
            .map(|(path, value)| (format!("{destination}/{}", &path[prefix.len()..]), *value))
            .collect();
        self.mtimes.retain(|path, _| !path.starts_with(&prefix));
        for (path, value) in mtimes {
            self.mtimes.insert(path, value);
        }
    }
}

fn stage2_recipe(
    fixture: &v016::LoadFixture,
    ordinal: usize,
    role: &str,
    len: u64,
) -> reference::Result<Content> {
    reference::dedup_workloads::content(
        v016::FAMILY_MIXED,
        "v016-stage2",
        fixture.seed,
        ordinal,
        role,
        len,
    )
}

/// Stage 1: unlink/recreate 64 selected 4 KiB files with the cycle's cohort.
fn apply_stage1(
    fixture: &v016::LoadFixture,
    cycle: usize,
    branch_salt: &str,
    shadow: &mut ShadowState,
) -> reference::Result<()> {
    let cohort = v016::cohort_for_cycle(cycle)?;
    let prior = stages::prior_visits(cycle, cohort)?;
    for slot in 0..v016::REFRESH_FILES_PER_COHORT {
        let index = stages::refresh_pool_index(cohort, slot);
        let path = fixture
            .roles
            .refresh_pool
            .get(index)
            .ok_or("v0.1.6 shadow refresh path")?
            .clone();
        let content = stages::stage1_content(fixture, cycle, cohort, slot, prior, branch_salt)?;
        let (path, state) = declared(&path, content);
        shadow.paths.insert(path, state);
    }
    Ok(())
}

fn splice_of(
    shadow: &ShadowState,
    path: &str,
    start: u64,
    delete_len: u64,
    replacement: Content,
) -> reference::Result<Content> {
    shadow
        .paths
        .get(path)
        .ok_or_else(|| format!("v0.1.6 shadow target absent: {path}"))?
        .content()
        .splice(start, delete_len, replacement)
}

/// Stage 2 POSIX operations, in the declared order of the sixteen targets.
fn apply_stage2(
    fixture: &v016::LoadFixture,
    cycle: usize,
    shadow: &mut ShadowState,
) -> reference::Result<()> {
    let tiny_offset = stages::tiny_pwrite_offset(cycle);
    for (ordinal, path) in fixture.roles.edit.tiny_pwrite.iter().enumerate() {
        let marker = stage2_recipe(
            fixture,
            ordinal * 8 + cycle,
            &format!("tiny-pwrite-c{cycle}"),
            256,
        )?;
        let updated = splice_of(shadow, path, tiny_offset, 256, marker)?;
        let (path, state) = declared(path, updated);
        shadow.paths.insert(path, state);
    }
    let medium = fixture.roles.edit.medium_overwrite.clone();
    let len = shadow
        .paths
        .get(&medium)
        .ok_or("v0.1.6 shadow medium")?
        .len();
    let offset = ((len / 2) / 8) * 8;
    let marker = stage2_recipe(fixture, cycle, &format!("medium-midpoint-c{cycle}"), 256)?;
    let updated = splice_of(shadow, &medium, offset, 256, marker)?;
    let (path, state) = declared(&medium, updated);
    shadow.paths.insert(path, state);
    // The net-zero append/truncate probe leaves the declared content unchanged.
    let tail = fixture.roles.edit.medium_replace_tail.clone();
    let len = shadow.paths.get(&tail).ok_or("v0.1.6 shadow tail")?.len();
    let marker = stage2_recipe(fixture, cycle, &format!("medium-tail-c{cycle}"), 4_096)?;
    let updated = splice_of(shadow, &tail, len - 4_096, 4_096, marker)?;
    let (path, state) = declared(&tail, updated);
    shadow.paths.insert(path, state);
    let anchor = fixture.roles.edit.anchor_overwrite.clone();
    let anchor_len = shadow
        .paths
        .get(&anchor)
        .ok_or("v0.1.6 shadow anchor")?
        .len();
    let anchor_offset = stages::anchor_offset(cycle, anchor_len);
    let marker = stage2_recipe(fixture, cycle, &format!("anchor-c{cycle}"), 4_096)?;
    let updated = splice_of(shadow, &anchor, anchor_offset, 4_096, marker)?;
    shadow.paths.insert(
        anchor,
        ranged(
            anchor_len,
            updated,
            vec![(anchor_offset, 4_096), (0, 4_096)],
        ),
    );
    // Boundary pair: shrink before growth, aggregate neutral at cycle end.
    let (below, above) = stages::boundary_lengths(cycle);
    for (path, target) in [
        (fixture.roles.boundary_below.clone(), below),
        (fixture.roles.boundary_above.clone(), above),
    ] {
        let current = shadow
            .paths
            .get(&path)
            .ok_or("v0.1.6 shadow boundary")?
            .content()
            .clone();
        let len = current.len();
        let updated = match target.cmp(&len) {
            std::cmp::Ordering::Greater => {
                let growth = stage2_recipe(
                    fixture,
                    cycle,
                    &format!("boundary-grow-c{cycle}"),
                    target - len,
                )?;
                current.splice(len, 0, growth)?
            }
            std::cmp::Ordering::Less => current.slice(0, target)?,
            std::cmp::Ordering::Equal => current,
        };
        let (path, state) = declared(&path, updated);
        shadow.paths.insert(path, state);
    }
    Ok(())
}

/// Stage 2 SDK half: one ordered single-file insertion and one deletion.
fn apply_sdk_stage2(
    fixture: &v016::LoadFixture,
    cycle: usize,
    shadow: &mut ShadowState,
) -> reference::Result<()> {
    let plan = stages::stage2_plan(fixture, cycle)?;
    let mut calls = 0usize;
    for (_, operation) in plan {
        if !stages::is_sdk_row(&operation) {
            continue;
        }
        let (target, kind, offset) = stages::sdk_edit_target(fixture, cycle, &operation)?;
        let updated = if kind == "insert" {
            let marker = reference::dedup_workloads::content(
                v016::FAMILY_MIXED,
                "v016-sdk-stage2",
                fixture.seed,
                cycle * 2 + calls,
                &format!("insert-c{cycle}"),
                256,
            )?;
            splice_of(shadow, &target, offset, 0, marker)?
        } else {
            splice_of(shadow, &target, offset, 256, Content::Zero { len: 0 })?
        };
        let len = updated.len();
        let mut ranges = Vec::new();
        let mut push = |start: u64, length: u64| {
            let start = start.min(len);
            let end = (start + length).min(len);
            if start < end {
                ranges.push((start, end - start));
            }
        };
        push(offset.saturating_sub(4_096), 8_192);
        push(0, 4_096);
        push(len.saturating_sub(4_096), 4_096);
        shadow.paths.insert(target, ranged(len, updated, ranges));
        calls += 1;
    }
    if calls != stages::STAGE2_SDK_CALLS {
        return Err("v0.1.6 shadow SDK call count".into());
    }
    Ok(())
}

/// The link-bearing parents of one cycle, in the same shape the POSIX helper
/// creates: cycle 1 moves both movable subtrees under the destination parents,
/// and each later cycle toggles back or forth.
fn link_layout(fixture: &v016::LoadFixture, cycle: usize) -> (String, String) {
    if cycle % 2 == 1 {
        (
            fixture.roles.move_dest[0].clone(),
            fixture.roles.move_dest[1].clone(),
        )
    } else {
        (String::new(), String::new())
    }
}

fn link_name(parent: &str, name: &str) -> String {
    if parent.is_empty() {
        name.to_owned()
    } else {
        format!("{parent}/{name}")
    }
}

/// Stage 4: the hardlink aliases, the symlinks and the four attribute rules.
fn apply_stage4(
    fixture: &v016::LoadFixture,
    cycle: usize,
    branch_tag: u64,
    shadow: &mut ShadowState,
) -> reference::Result<()> {
    let (link_parent, symlink_parent) = link_layout(fixture, cycle);
    for index in 0..v016::HARDLINK_TARGETS {
        shadow
            .paths
            .remove(&link_name(&link_parent, &format!("hl{index:02}")));
    }
    for index in 0..v016::HARDLINK_TARGETS {
        shadow
            .aliases
            .remove(&link_name(&link_parent, &format!("hl{index:02}")));
    }
    for index in 0..v016::SYMLINK_COUNT {
        shadow
            .paths
            .remove(&link_name(&symlink_parent, &format!("sl{index:02}")));
    }
    for index in 0..v016::SYMLINK_COUNT {
        shadow
            .symlinks
            .remove(&link_name(&symlink_parent, &format!("sl{index:02}")));
    }
    for (index, target) in fixture.roles.link_targets.iter().enumerate() {
        shadow.aliases.insert(
            link_name(&link_parent, &format!("hl{index:02}")),
            target.clone(),
        );
    }
    for (index, (_, target, kind)) in stages::symlink_rows(fixture).into_iter().enumerate() {
        let value = match kind {
            v016::SymlinkKind::Resolvable if symlink_parent.is_empty() => {
                target.trim_start_matches("../").to_owned()
            }
            _ => target,
        };
        shadow
            .symlinks
            .insert(link_name(&symlink_parent, &format!("sl{index:02}")), value);
    }
    // The explicit attribute mtime is epoch + 10*cycle + branch_tag, so the
    // declaration follows the branch that performed the stage.
    let mtime = v016::attribute_mtime(cycle, branch_tag);
    for path in v016::attribute_targets(fixture)? {
        shadow
            .modes
            .insert(path.clone(), v016::attribute_mode(cycle, true));
        shadow.mtimes.insert(path, mtime);
    }
    // Four 64-byte writes on the four distinct 4 KiB alias targets.
    for (index, target) in stages::alias_probe_paths(fixture).iter().enumerate() {
        let marker = reference::dedup_workloads::content(
            v016::FAMILY_MIXED,
            "v016-stage4",
            fixture.seed,
            index,
            &format!("alias-probe-c{cycle}"),
            stages::ALIAS_PROBE_BYTES,
        )?;
        let offset = 64 * index as u64;
        let updated = splice_of(shadow, target, offset, stages::ALIAS_PROBE_BYTES, marker)?;
        let (path, state) = declared(target, updated);
        shadow.paths.insert(path, state);
    }
    for path in stages::attribute_directories(fixture, cycle) {
        shadow
            .directory_modes
            .insert(path, v016::attribute_mode(cycle, false));
    }
    Ok(())
}

/// Stage 5: the subtree recreation, the four atomic saves and the link removals.
/// The recreated deletion root is a new directory on the live filesystem, so its
/// declared mode is the live mode the helper measured, not the stage-4 chmod and
/// not an assumed default.
fn apply_stage5(
    fixture: &v016::LoadFixture,
    cycle: usize,
    branch_salt: &str,
    shadow: &mut ShadowState,
    observed: &BTreeMap<String, u32>,
) -> reference::Result<()> {
    let deletion_root = fixture.roles.deletion_root.clone();
    shadow.required_created.insert(deletion_root.clone());
    shadow.directory_modes.insert(
        deletion_root.clone(),
        observed_directory_mode(observed, &deletion_root)?,
    );
    let (link_parent, symlink_parent) = link_layout(fixture, cycle);
    for index in 0..v016::DELETION_SUBTREE_FILES {
        let path = fixture
            .roles
            .deletion
            .get(index)
            .ok_or("v0.1.6 shadow subtree path")?
            .clone();
        let content = stages::subtree_content(fixture, cycle, index, branch_salt)?;
        let (path, state) = declared(&path, content);
        shadow.paths.insert(path, state);
    }
    for (index, destination) in stages::save_destinations(fixture).iter().enumerate() {
        let content = reference::dedup_workloads::content(
            v016::FAMILY_MIXED,
            "v016-stage5",
            fixture.seed,
            index,
            &format!("atomic-save-c{cycle}-{index}"),
            v016::TINY,
        )?;
        let (path, state) = declared(destination, content);
        shadow.paths.insert(path, state);
    }
    for index in 0..v016::HARDLINK_TARGETS {
        shadow
            .paths
            .remove(&link_name(&link_parent, &format!("hl{index:02}")));
    }
    for index in 0..v016::HARDLINK_TARGETS {
        shadow
            .aliases
            .remove(&link_name(&link_parent, &format!("hl{index:02}")));
    }
    for index in 0..v016::SYMLINK_COUNT {
        shadow
            .paths
            .remove(&link_name(&symlink_parent, &format!("sl{index:02}")));
    }
    for index in 0..v016::SYMLINK_COUNT {
        shadow
            .symlinks
            .remove(&link_name(&symlink_parent, &format!("sl{index:02}")));
    }
    Ok(())
}

/// Stage 3: the scratch-directory replacement and the two populated directory
/// moves. A move relocates every declared descendant, so the shadow's paths are
/// remapped rather than re-declared under the old root. The live mode of every
/// created directory is the mode the workload measured on the live filesystem,
/// never an assumed runtime default.
fn apply_stage3(
    fixture: &v016::LoadFixture,
    cycle: usize,
    shadow: &mut ShadowState,
    observed: &BTreeMap<String, u32>,
) -> reference::Result<()> {
    let (remove, create) = stages::scratch_names(fixture, cycle);
    if remove.len() != v016::SCRATCH_DIRS || create.len() != v016::SCRATCH_DIRS {
        return Err("v0.1.6 scratch directory cardinality".into());
    }
    for path in &remove {
        shadow.directory_modes.remove(path);
        shadow.directories.remove(path);
    }
    for path in &create {
        shadow.required_created.insert(path.clone());
        let mode = observed_directory_mode(observed, path)?;
        shadow.directories.insert(path.clone());
        shadow.directory_modes.insert(path.clone(), mode);
    }
    for (source, destination) in stages::move_rows(fixture, cycle) {
        if source == destination {
            continue;
        }
        shadow.remap_prefix(&source, &destination);
    }
    Ok(())
}

/// One directory the stage helper created, with the live mode it measured.
fn observed_directory_mode(observed: &BTreeMap<String, u32>, path: &str) -> reference::Result<u32> {
    Ok(observed
        .get(path)
        .copied()
        .unwrap_or(v016::DEFAULT_DIRECTORY_MODE))
}

/// Independent materialization recipes and the original M1 proof obligations.
/// Unspecified automatic metadata in `entries` is only a native fixture value;
/// actual M1 proof consumes these explicit maps and ranges instead.
pub struct M1State {
    pub entries: Vec<Entry>,
    pub ranges: BTreeMap<String, Vec<(u64, u64)>>,
    pub file_modes: BTreeMap<String, u32>,
    pub file_mtimes: BTreeMap<String, (i64, u32)>,
    pub directory_modes: BTreeMap<String, u32>,
    pub required_created_directory_modes: BTreeSet<String>,
}

pub fn is_m1(id: &str) -> bool {
    matches!(stages::mixed_case(id), Ok(Some(case)) if case.topology == stages::Topology::Sequential)
}

fn apply_m1_prefix(
    fixture: &v016::LoadFixture,
    shadow: &mut ShadowState,
    steps: usize,
    cycle_start: usize,
    tag: u64,
    salt: &str,
    observed: &BTreeMap<String, u32>,
) -> reference::Result<()> {
    for completed in 1..=steps {
        let cycle = (completed - 1) / stages::STAGES + cycle_start;
        match stages::Stage::from_ordinal((completed - 1) % stages::STAGES + 1)? {
            stages::Stage::Refresh => apply_stage1(fixture, cycle, salt, shadow)?,
            stages::Stage::Edits => {
                apply_stage2(fixture, cycle, shadow)?;
                apply_sdk_stage2(fixture, cycle, shadow)?;
            }
            stages::Stage::Directories => apply_stage3(fixture, cycle, shadow, observed)?,
            stages::Stage::AttrsLinks => apply_stage4(fixture, cycle, tag, shadow)?,
            stages::Stage::InodeSubtree => apply_stage5(fixture, cycle, salt, shadow, observed)?,
        }
    }
    Ok(())
}

fn require_created_modes(
    required: &BTreeSet<String>,
    observed: &BTreeMap<String, u32>,
) -> reference::Result<()> {
    for path in required {
        let mode = observed
            .get(path)
            .ok_or_else(|| format!("original helper created mode missing: {path}"))?;
        if mode & !0o1777 != 0 {
            return Err("original helper created mode outside frozen mode envelope".into());
        }
    }
    Ok(())
}

/// Original sequential M1 state after `step` acknowledged Commits. Passing
/// `None` is materialization-only; actual proof must supply sealed helper modes.
pub fn m1_state(
    id: &str,
    step: usize,
    created_modes: Option<&BTreeMap<String, u32>>,
) -> reference::Result<M1State> {
    let case = stages::mixed_case(id)?.ok_or("original M1 case required")?;
    if case.topology != stages::Topology::Sequential || step > case.k {
        return Err("original sequential M1 step outside declared schedule".into());
    }
    let tier = match case.tier {
        "L100" => &v016::L100,
        "L500" => &v016::L500,
        _ => return Err("original M1 tier differs".into()),
    };
    let fixture = v016::load_fixture(tier, 1)?;
    let mut shadow = shadow_from_fixture(&fixture);
    let empty = BTreeMap::new();
    let observed = created_modes.unwrap_or(&empty);
    apply_m1_prefix(&fixture, &mut shadow, step, 1, 0, "branch0", observed)?;
    if let Some(observed) = created_modes {
        require_created_modes(&shadow.required_created, observed)?;
    }
    finish_m1(tier, shadow)
}

fn finish_m1(tier: &v016::LoadTier, shadow: ShadowState) -> reference::Result<M1State> {
    let file_mtimes = shadow
        .mtimes
        .iter()
        .map(|(path, seconds)| (path.clone(), (*seconds, v016::ATTRIBUTE_MTIME_NS)))
        .collect::<BTreeMap<_, _>>();
    let mut entries = vec![Entry::directory(".")];
    for path in &shadow.directories {
        let mut entry = Entry::directory(path.clone());
        entry.mode = *shadow
            .directory_modes
            .get(path)
            .ok_or("original directory mode missing")?;
        entries.push(entry);
    }
    let mut ranges = BTreeMap::new();
    for (path, state) in &shadow.paths {
        let mut entry = Entry::file(path.clone(), state.content().clone());
        if let Some(mode) = shadow.modes.get(path) {
            entry.mode = *mode;
        }
        if let Some((seconds, nanos)) = file_mtimes.get(path) {
            entry.mtime_seconds = *seconds;
            entry.mtime_nanoseconds = *nanos;
        }
        let covered = match state {
            // Frozen declared_content_root checks 1..131071; empty/exact 128KiB
            // Shadow::File paths are type+length-only in that original oracle.
            Shadow::File(content) if content.len() > 0 && content.len() < v016::BOUNDARY_EXACT => {
                vec![(0, content.len())]
            }
            Shadow::File(_) => Vec::new(),
            Shadow::Ranged { ranges, .. } => ranges.clone(),
        };
        ranges.insert(path.clone(), covered);
        entries.push(entry);
    }
    for (path, target) in &shadow.aliases {
        let mut alias = Entry::hardlink(path.clone(), target.clone());
        if let Some(mode) = shadow.modes.get(target) {
            alias.mode = *mode;
        }
        if let Some((seconds, nanos)) = file_mtimes.get(target) {
            alias.mtime_seconds = *seconds;
            alias.mtime_nanoseconds = *nanos;
        }
        ranges.insert(
            path.clone(),
            ranges
                .get(target)
                .ok_or("original alias target absent")?
                .clone(),
        );
        entries.push(alias);
    }
    for (path, target) in &shadow.symlinks {
        entries.push(Entry::symlink(path.clone(), target.clone()));
    }
    entries.sort_by(|a, b| a.path.cmp(&b.path));
    // The decimal 100MB/500MB M1 high-water envelope includes its initial
    // fixture plus 16 reserved names and 65,536 bytes. Ordinary per-file and
    // aggregate fixture guards remain separate and unchanged.
    let names = entries
        .iter()
        .filter(|entry| !matches!(entry.kind, EntryKind::Directory))
        .count();
    let bytes = entries
        .iter()
        .map(|entry| match &entry.kind {
            EntryKind::File(content) => Ok(content.len()),
            EntryKind::Hardlink(target) => shadow
                .paths
                .get(target)
                .map(Shadow::len)
                .ok_or("original alias missing referent"),
            EntryKind::Symlink(target) => Ok(target.len() as u64),
            EntryKind::Directory => Ok(0),
        })
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .sum::<u64>();
    if names > tier.max_paths()
        || bytes > tier.max_bytes()
        || shadow.directories.len() > tier.max_dirs()
    {
        return Err("original M1 live envelope differs".into());
    }
    Ok(M1State {
        entries,
        ranges,
        file_modes: shadow.modes,
        file_mtimes,
        directory_modes: shadow.directory_modes,
        required_created_directory_modes: shadow.required_created,
    })
}

/// Canonical TSV of selective current-proof obligations; no expected bytes are
/// acquired from the product. Content recipes remain in `M1State.entries`.
pub fn m1_scope_tsv(state: &M1State) -> reference::Result<String> {
    use std::fmt::Write;
    let mut output = String::from("original-m1-selective-scope-v1\npath\tkind\tlength\tmode\tmtime_seconds\tmtime_nanoseconds\tranges\ttarget\n");
    for entry in &state.entries {
        let (kind, len) = match &entry.kind {
            EntryKind::File(content) => ("file", content.len()),
            EntryKind::Hardlink(target) => {
                let target = state
                    .entries
                    .iter()
                    .find(|entry| &entry.path == target)
                    .ok_or("original scope alias target missing")?;
                let EntryKind::File(content) = &target.kind else {
                    return Err("original scope alias type differs".into());
                };
                ("hardlink", content.len())
            }
            EntryKind::Symlink(target) => ("symlink", target.len() as u64),
            EntryKind::Directory => ("directory", 0),
        };
        let mode = state
            .file_modes
            .get(&entry.path)
            .or_else(|| state.directory_modes.get(&entry.path))
            .map(|mode| format!("{mode:o}"))
            .unwrap_or_else(|| "-".into());
        let (seconds, nanos) = state
            .file_mtimes
            .get(&entry.path)
            .map(|(seconds, nanos)| (seconds.to_string(), nanos.to_string()))
            .unwrap_or_else(|| ("-".into(), "-".into()));
        let ranges = state
            .ranges
            .get(&entry.path)
            .map(|ranges| {
                ranges
                    .iter()
                    .map(|(offset, len)| format!("{offset}:{len}"))
                    .collect::<Vec<_>>()
                    .join(",")
            })
            .unwrap_or_default();
        let target = match &entry.kind {
            EntryKind::Hardlink(target) | EntryKind::Symlink(target) => target.as_str(),
            _ => "-",
        };
        writeln!(
            &mut output,
            "{}\t{kind}\t{len}\t{mode}\t{seconds}\t{nanos}\t{ranges}\t{target}",
            entry.path
        )?;
    }
    Ok(output)
}

pub type ContextCreatedModes = BTreeMap<String, BTreeMap<String, u32>>;

/// Roles are selected from the frozen case registry, never receipt metadata.
pub fn context_roles(id: &str) -> reference::Result<Vec<&'static str>> {
    if let Some(case) = stages::mixed_case(id)? {
        return match case.topology {
            stages::Topology::Branch => Ok(vec!["trunk", "a", "b"]),
            stages::Topology::Concurrent => Ok(vec!["0", "1"]),
            stages::Topology::Four => Ok(vec!["0", "1", "2", "3"]),
            _ => Err("original contextual M1 topology required".into()),
        };
    }
    let compact = stages::compact_case(id)?.ok_or("original contextual case required")?;
    Ok(compact
        .roles()
        .into_iter()
        .map(stages::CompactRole::of)
        .collect())
}

pub fn context_limit(id: &str, role: &str) -> reference::Result<usize> {
    if !context_roles(id)?.contains(&role) {
        return Err("original contextual role is not declared".into());
    }
    Ok(match stages::mixed_case(id)? {
        Some(case) if role != "trunk" => case.k,
        _ => stages::COMPACT_TRUNK_COMMITS,
    })
}

pub fn is_context_m1(id: &str) -> bool {
    matches!(stages::mixed_case(id), Ok(Some(case)) if case.topology != stages::Topology::Sequential)
}

pub(crate) fn context_m1_parameters(
    id: &str,
    role: &str,
) -> reference::Result<(stages::MixedCase, u64, usize)> {
    context_limit(id, role)?;
    let case = stages::mixed_case(id)?.ok_or("original contextual M1 required")?;
    let tag = match case.topology {
        stages::Topology::Branch => match role {
            "trunk" => 0,
            "a" => 1,
            "b" => 2,
            _ => return Err("original branch role differs".into()),
        },
        stages::Topology::Concurrent | stages::Topology::Four => role.parse()?,
        _ => return Err("original contextual M1 topology required".into()),
    };
    let cycle_start = if case.topology == stages::Topology::Branch && role != "trunk" {
        2
    } else {
        1
    };
    Ok((case, tag, cycle_start))
}

/// `None` is native materialization only. Actual proofs supply role-bound maps;
/// inherited trunk observations never get overwritten by a child's own map.
pub fn context_m1_state(
    id: &str,
    role: &str,
    step: usize,
    created_modes: Option<&ContextCreatedModes>,
) -> reference::Result<M1State> {
    if step > context_limit(id, role)? {
        return Err("original contextual local step outside schedule".into());
    }
    let (case, tag, cycle_start) = context_m1_parameters(id, role)?;
    let tier = if case.tier == "L100" {
        &v016::L100
    } else {
        &v016::L500
    };
    let fixture = v016::load_fixture(tier, 1)?;
    let mut shadow = shadow_from_fixture(&fixture);
    let empty = BTreeMap::new();
    let mut inherited_required = BTreeSet::new();
    if cycle_start == 2 {
        let inherited = created_modes
            .and_then(|maps| maps.get("trunk"))
            .unwrap_or(&empty);
        apply_m1_prefix(&fixture, &mut shadow, 5, 1, 0, "branch0", inherited)?;
        if created_modes.is_some() {
            require_created_modes(&shadow.required_created, inherited)?;
        }
        inherited_required = std::mem::take(&mut shadow.required_created);
    }
    let own = created_modes
        .and_then(|maps| maps.get(role))
        .unwrap_or(&empty);
    apply_m1_prefix(
        &fixture,
        &mut shadow,
        step,
        cycle_start,
        tag,
        &format!("branch{tag}"),
        own,
    )?;
    if created_modes.is_some() {
        require_created_modes(&shadow.required_created, own)?;
    }
    shadow.required_created.extend(inherited_required);
    finish_m1(tier, shadow)
}

pub(crate) fn compact_role(
    id: &str,
    role: &str,
) -> reference::Result<(stages::CompactCase, stages::CompactRole)> {
    context_limit(id, role)?;
    let case = stages::compact_case(id)?.ok_or("original compact case required")?;
    let role = case
        .roles()
        .into_iter()
        .find(|item| item.of() == role)
        .ok_or("original compact role missing")?;
    Ok((case, role))
}

fn compact_entries(id: &str, role: &str, step: usize) -> reference::Result<Vec<Entry>> {
    let (compact, selected) = compact_role(id, role)?;
    if step > context_limit(id, role)? {
        return Err("original compact local step outside schedule".into());
    }
    reference::branch_development::compact_expected_at(1, compact, selected, step)
}

pub fn context_entries(id: &str, role: &str, step: usize) -> reference::Result<Vec<Entry>> {
    if is_context_m1(id) {
        Ok(context_m1_state(id, role, step, None)?.entries)
    } else {
        compact_entries(id, role, step)
    }
}

pub fn context_manifest(id: &str, role: &str, step: usize) -> reference::Result<String> {
    if is_context_m1(id) {
        m1_scope_tsv(&context_m1_state(id, role, step, None)?)
    } else {
        reference::workspace_common::manifest(&context_entries(id, role, step)?)
    }
}

/// Strict original role/name domains; future cumulative rows may be present,
/// but actual selected-state verification still requires its own observations.
pub fn parse_context_created_modes(id: &str, body: &str) -> reference::Result<ContextCreatedModes> {
    if !is_context_m1(id) {
        return Err("original contextual M1 mode observations required".into());
    }
    let mut lines = body.lines();
    if lines.next() != Some("original-context-created-modes-v1")
        || lines.next() != Some("role\tpath\tmode")
    {
        return Err("context created modes header differs".into());
    }
    let domains = context_roles(id)?
        .into_iter()
        .map(|role| {
            Ok((
                role,
                context_m1_state(id, role, context_limit(id, role)?, None)?
                    .required_created_directory_modes,
            ))
        })
        .collect::<reference::Result<BTreeMap<_, _>>>()?;
    let mut maps = ContextCreatedModes::new();
    for line in lines {
        let fields = line.split('\t').collect::<Vec<_>>();
        if fields.len() != 3
            || fields[1].is_empty()
            || fields[1].contains(['\0', '\\', '\r'])
            || fields[1]
                .split('/')
                .any(|part| matches!(part, "" | "." | ".."))
            || fields[2].is_empty()
            || !fields[2].bytes().all(|byte| matches!(byte, b'0'..=b'7'))
            || !domains
                .get(fields[0])
                .is_some_and(|domain| domain.contains(fields[1]))
        {
            return Err("context created mode is malformed or undeclared".into());
        }
        let mode = u32::from_str_radix(fields[2], 8)?;
        if mode & !0o1777 != 0
            || maps
                .entry(fields[0].to_owned())
                .or_default()
                .insert(fields[1].to_owned(), mode)
                .is_some()
        {
            return Err("context created mode duplicate or outside frozen envelope".into());
        }
    }
    Ok(maps)
}

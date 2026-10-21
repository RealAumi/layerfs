//! Original ordinary-writer SDK edit plans and native fixture hash requirements.
//! Verification consumers use edit_model; writers and fixtures import this adapter.
use crate::edit_model::{
    compact_role, context_entries, context_limit, context_m1_parameters, entries, is_context_m1,
    is_m1, scenario,
};
use crate::reference;
use reference::workspace_common::{Entry, EntryKind, SdkEdit};
use reference::{dedup_workloads as dedup, v016_common as v016, v016_stages as stages};

pub fn fixture_sha256(id: &str) -> reference::Result<Option<&'static str>> {
    scenario(id)
        .map(|row| {
            reference::sdk_edit_common::fixture_index(row.fixture_bytes)
                .map(|index| reference::sdk_edit_common::FIXTURE_SHA256[index])
                .ok_or_else(|| "original SDK fixture size has no frozen digest".into())
        })
        .transpose()
}

/// Original named edit member and its exact declared input/output length.
pub struct SdkSplice {
    pub edit: SdkEdit,
    pub before_len: u64,
    pub after_len: u64,
    pub metadata: Entry,
}

/// STEP is the 1-based Commit/state ordinal. This is original recipe algebra,
/// not a product edit implementation; writers perform ordinary Unix calls.
pub fn sdk_step(id: &str, step: usize) -> reference::Result<Vec<SdkSplice>> {
    if step == 0 {
        return Err("original SDK step is1-based".into());
    }
    let case = reference::workspace_registry::resolve(id)?;
    let edits = if case.family == "file_size_transition" {
        use reference::file_size_transition::{self as boundary, BoundaryOp};
        let plan = boundary::plan(id)?;
        if plan.alias {
            return Err("original BA uses unchanged native alias helper".into());
        }
        let operation = boundary::operations(&case)?
            .get(step - 1)
            .cloned()
            .ok_or("boundary SDK step outside schedule")?;
        let before = boundary::declared_length(&case, step - 1)?;
        let (start, delete_len, replacement) = match operation {
            BoundaryOp::Overwrite { offset, len, visit } => {
                (offset, len, boundary::replacement(&case, 1, visit, len)?)
            }
            BoundaryOp::Append { len, visit } => {
                (before, 0, boundary::replacement(&case, 1, visit, len)?)
            }
            BoundaryOp::Remove { len, .. } => (before - len, len, Vec::new()),
            _ => return Err("original nonalias SDK boundary operation required".into()),
        };
        vec![SdkEdit {
            path: boundary::TARGET.to_owned(),
            start,
            delete_len,
            replacement,
        }]
    } else if case.family == "dedup_branch_history" {
        if !dedup::is_sdk(&case) && !(reference::v016_hn::is_hn(id) && (step - 1) % 5 == 1) {
            return Err("original dedup SDK step required".into());
        }
        reference::dedup_branch_history::edits(&case, 1, step - 1)?
    } else if is_m1(id) {
        let plan = stages::mixed_case(id)?.ok_or("original M1 required")?;
        if step > plan.k || (step - 1) % 5 != 1 {
            return Err("original M1 P-3 pair occurs only at stage 2".into());
        }
        let fixture = v016::load_fixture(
            if plan.tier == "L100" {
                &v016::L100
            } else {
                &v016::L500
            },
            1,
        )?;
        let cycle = (step - 1) / 5 + 1;
        m1_sdk_edits(&fixture, cycle)?
    } else {
        return Err("original named SDK history case required".into());
    };
    sdk_splices(entries(id, step - 1)?, edits)
}

fn sdk_splices(before: Vec<Entry>, edits: Vec<SdkEdit>) -> reference::Result<Vec<SdkSplice>> {
    let mut result = Vec::new();
    for edit in edits {
        let metadata = before
            .iter()
            .find(|entry| entry.path == edit.path)
            .ok_or("original named SDK target absent")?
            .clone();
        let EntryKind::File(content) = &metadata.kind else {
            return Err("original named SDK target is not a regular file".into());
        };
        let before_len = content.len();
        if edit
            .start
            .checked_add(edit.delete_len)
            .is_none_or(|end| end > before_len)
        {
            return Err("original named SDK range outside declared input".into());
        }
        let after_len = before_len
            .checked_sub(edit.delete_len)
            .and_then(|len| len.checked_add(edit.replacement.len() as u64))
            .ok_or("original named SDK length overflow")?;
        result.push(SdkSplice {
            edit,
            before_len,
            after_len,
            metadata,
        });
    }
    Ok(result)
}

fn m1_sdk_edits(fixture: &v016::LoadFixture, cycle: usize) -> reference::Result<Vec<SdkEdit>> {
    let mut result = Vec::new();
    for (_, operation) in stages::stage2_plan(&fixture, cycle)? {
        if !stages::is_sdk_row(&operation) {
            continue;
        }
        let (path, kind, start) = stages::sdk_edit_target(&fixture, cycle, &operation)?;
        let replacement = if kind == "insert" {
            let content = dedup::content(
                v016::FAMILY_MIXED,
                "v016-sdk-stage2",
                1,
                cycle * 2 + result.len(),
                &format!("{kind}-c{cycle}"),
                256,
            )?;
            let mut bytes = Vec::new();
            content.write_to(&mut bytes)?;
            bytes
        } else {
            Vec::new()
        };
        result.push(SdkEdit {
            path,
            start,
            delete_len: if kind == "delete" { 256 } else { 0 },
            replacement,
        });
    }
    if result.len() != stages::STAGE2_SDK_CALLS {
        return Err("original M1 SDK cardinality differs".into());
    }
    Ok(result)
}

pub fn context_sdk_step(id: &str, role: &str, step: usize) -> reference::Result<Vec<SdkSplice>> {
    if step == 0 || step > context_limit(id, role)? {
        return Err("original contextual SDK step outside schedule".into());
    }
    let edits = if is_context_m1(id) {
        let (case, _, cycle_start) = context_m1_parameters(id, role)?;
        if (step - 1) % stages::STAGES != 1 {
            return Err("original contextual M1 SDK pair occurs only at stage2".into());
        }
        let fixture = v016::load_fixture(
            if case.tier == "L100" {
                &v016::L100
            } else {
                &v016::L500
            },
            1,
        )?;
        m1_sdk_edits(&fixture, (step - 1) / stages::STAGES + cycle_start)?
    } else {
        let (case, selected) = compact_role(id, role)?;
        let ancestral = case.fork_ancestry(selected) + step;
        let mut replacement = Vec::new();
        stages::compact_payload(
            v016::FAMILY_BRANCH,
            1,
            ancestral,
            stages::compact_salt(case, selected),
        )?
        .write_to(&mut replacement)?;
        vec![SdkEdit {
            path: reference::v016_compact::s_medium_path(0),
            start: stages::compact_offset(ancestral)?,
            delete_len: 256,
            replacement,
        }]
    };
    sdk_splices(context_entries(id, role, step - 1)?, edits)
}

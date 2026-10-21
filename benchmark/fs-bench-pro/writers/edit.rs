//! Bounded ordinary Unix splice writes for the frozen SDK-edit definitions.
#[path = "../engine/recipes/boundary_metadata.rs"]
mod boundary_metadata;
#[path = "../engine/recipes/edit_model.rs"]
mod edit_model;
#[allow(dead_code)]
#[path = "../workload/main.rs"]
mod reference;
#[path = "../engine/recipes/sdk_edit_model.rs"]
mod sdk_edit_model;

use reference::sdk_edit_common::{self, ReplacementKind, Scenario};
use std::fs::{File, OpenOptions};
use std::io;
use std::os::fd::IntoRawFd;
use std::os::unix::fs::FileExt;
use std::path::Path;

const SCRATCH_BYTES: usize = 65_536;

unsafe extern "C" {
    fn close(fd: i32) -> i32;
}

#[derive(Default)]
struct Progress {
    read_calls: u64,
    write_calls: u64,
    read_bytes: u64,
    write_bytes: u64,
    truncate_calls: u64,
}

struct Splice {
    start: u64,
    delete_len: u64,
    replacement_len: u64,
    fixture_bytes: u64,
    final_bytes: u64,
}

impl From<&Scenario> for Splice {
    fn from(case: &Scenario) -> Self {
        Self {
            start: case.start,
            delete_len: case.delete_len,
            replacement_len: case.replacement_len,
            fixture_bytes: case.fixture_bytes,
            final_bytes: case.final_bytes,
        }
    }
}

fn read_exact_at(
    file: &File,
    mut output: &mut [u8],
    mut offset: u64,
    work: &mut Progress,
) -> io::Result<()> {
    while !output.is_empty() {
        work.read_calls += 1;
        let count = file.read_at(output, offset)?;
        if count == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "original suffix read returned zero",
            ));
        }
        work.read_bytes += count as u64;
        offset += count as u64;
        output = &mut output[count..];
    }
    Ok(())
}

fn write_exact_at(
    file: &File,
    mut input: &[u8],
    mut offset: u64,
    work: &mut Progress,
) -> io::Result<()> {
    while !input.is_empty() {
        work.write_calls += 1;
        let count = file.write_at(input, offset)?;
        if count == 0 {
            return Err(io::Error::new(
                io::ErrorKind::WriteZero,
                "original positional write returned zero",
            ));
        }
        work.write_bytes += count as u64;
        offset += count as u64;
        input = &input[count..];
    }
    Ok(())
}

fn checked_close(file: File) -> io::Result<()> {
    let fd = file.into_raw_fd();
    // SAFETY: this descriptor is owned and consumed here. Close is attempted
    // exactly once, including EINTR; an uncertain failure is never resent.
    if unsafe { close(fd) } == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

fn splice(
    file: &File,
    case: &Splice,
    replacement: &[u8],
    work: &mut Progress,
) -> reference::Result<()> {
    let deleted_end = case
        .start
        .checked_add(case.delete_len)
        .ok_or("edit range overflow")?;
    let wanted_len = case
        .fixture_bytes
        .checked_sub(case.delete_len)
        .and_then(|len| len.checked_add(case.replacement_len))
        .ok_or("edit final length overflow")?;
    if deleted_end > case.fixture_bytes
        || wanted_len != case.final_bytes
        || file.metadata()?.len() != case.fixture_bytes
    {
        return Err("original scenario range/final length/fixture length differs".into());
    }
    let suffix_len = case.fixture_bytes - deleted_end;
    let mut scratch = vec![0; SCRATCH_BYTES];
    if case.replacement_len > case.delete_len {
        let growth = case.replacement_len - case.delete_len;
        file.set_len(case.final_bytes)?;
        work.truncate_calls += 1;
        let mut remaining = suffix_len;
        while remaining != 0 {
            let take = remaining.min(SCRATCH_BYTES as u64) as usize;
            let from = deleted_end + remaining - take as u64;
            read_exact_at(file, &mut scratch[..take], from, work)?;
            write_exact_at(file, &scratch[..take], from + growth, work)?;
            remaining -= take as u64;
        }
    } else if case.replacement_len < case.delete_len {
        let mut copied = 0;
        while copied != suffix_len {
            let take = (suffix_len - copied).min(SCRATCH_BYTES as u64) as usize;
            read_exact_at(file, &mut scratch[..take], deleted_end + copied, work)?;
            write_exact_at(
                file,
                &scratch[..take],
                case.start + case.replacement_len + copied,
                work,
            )?;
            copied += take as u64;
        }
    }
    write_exact_at(file, replacement, case.start, work)?;
    if case.final_bytes < case.fixture_bytes {
        file.set_len(case.final_bytes)?;
        work.truncate_calls += 1;
    }
    Ok(())
}

fn apply(id: &str) -> reference::Result<()> {
    let case = edit_model::scenario(id).ok_or("unknown original SDK edit case")?;
    let replacement = match case.replacement_kind {
        ReplacementKind::Inline => sdk_edit_common::replacement_bytes(&case),
        ReplacementKind::Zero => vec![0; usize::try_from(case.replacement_len)?],
    };
    if replacement.len() as u64 != case.replacement_len
        || sdk_edit_common::sha256_hex(&replacement) != case.payload_sha256
    {
        return Err("original replacement length/hash differs".into());
    }
    let entries = edit_model::descriptors(id, 1)?;
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .open("payload.bin")?;
    let mut work = Progress::default();
    let original = (|| -> reference::Result<()> {
        splice(&file, &Splice::from(&case), &replacement, &mut work)?;
        for name in ["payload.bin", "."] {
            let entry = entries
                .iter()
                .find(|entry| entry.path == name)
                .ok_or("original metadata descriptor missing")?;
            reference::workspace_common::set_metadata(Path::new(name), entry)?;
        }
        Ok(())
    })();
    let closed = checked_close(file);
    eprintln!("ordinary_edit_reads={} ordinary_edit_read_bytes={} ordinary_edit_writes={} ordinary_edit_write_bytes={} ordinary_edit_truncates={} scratch_window_bytes={SCRATCH_BYTES}",
        work.read_calls, work.read_bytes, work.write_calls, work.write_bytes, work.truncate_calls);
    if let Err(error) = original {
        if let Err(close_error) = closed {
            eprintln!("independent_close_failure={close_error}");
        }
        return Err(error);
    }
    closed?;
    println!("mutation_status=pass\ncase={}\nedit_plan_sha256={}\nreplacement_sha256={}\ninitial_bytes={}\nfinal_bytes={}",
        case.id, case.plan_sha256, case.payload_sha256, case.fixture_bytes, case.final_bytes);
    Ok(())
}

fn apply_workspace(id: &str) -> reference::Result<()> {
    use reference::workspace_common::{self as common, EntryKind};
    let case = reference::workspace_registry::resolve(id)?;
    if case.family != "workspace_change_locality" || case.kind != "workspace-distributed-sdk-edit" {
        return Err("original distributed locality edit case required".into());
    }
    let edits = reference::ordinary_workloads::sdk_edits(&case, 1)?;
    let entries = reference::workspace_registry::fixture(&case, 1)?;
    let by_path: std::collections::BTreeMap<_, _> = entries
        .iter()
        .map(|entry| (entry.path.as_str(), entry))
        .collect();
    if edits.len() != case.tier {
        return Err("original distributed edit count differs".into());
    }
    let mut work = Progress::default();
    for edit in &edits {
        let entry = by_path
            .get(edit.path.as_str())
            .ok_or("original SDK target absent")?;
        let EntryKind::File(content) = &entry.kind else {
            return Err("original SDK target is not a regular file".into());
        };
        if edit.start != 0 || edit.delete_len != 4096 || edit.replacement.len() != 4096 {
            return Err("original distributed edit range/replacement differs".into());
        }
        let file = OpenOptions::new().write(true).open(&edit.path)?;
        let changed = (|| -> reference::Result<()> {
            if file.metadata()?.len() != content.len() {
                return Err("original distributed target fixture length differs".into());
            }
            write_exact_at(&file, &edit.replacement, edit.start, &mut work)?;
            common::set_metadata(Path::new(&edit.path), entry)?;
            Ok(())
        })();
        let closed = checked_close(file);
        if let Err(error) = changed {
            if let Err(close_error) = closed {
                eprintln!("independent_close_failure={close_error}");
            }
            return Err(error);
        }
        closed?;
    }
    common::set_metadata(
        Path::new("."),
        by_path.get(".").ok_or("original root metadata missing")?,
    )?;
    eprintln!("ordinary_edit_writes={} ordinary_edit_write_bytes={} ordinary_edit_truncates={} ordinary_edit_reads={} ordinary_edit_read_bytes={}",
        work.write_calls, work.write_bytes, work.truncate_calls, work.read_calls, work.read_bytes);
    println!("mutation_status=pass\ncase={}\noriginal_sdk_edit_members={}\nreplacement_bytes={}\nreplacement_definition=original-sdk_edits-seed1-XOR0x5a",
        case.id, edits.len(), work.write_bytes);
    Ok(())
}

fn realtime() -> reference::Result<boundary_metadata::Timestamp> {
    let value = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?;
    Ok(boundary_metadata::Timestamp {
        seconds: i64::try_from(value.as_secs())?,
        nanoseconds: value.subsec_nanos(),
    })
}

/// One unchanged ordinary-helper attempt, with read-only timestamp custody.
fn apply_boundary_alias(step: usize, helper: &Path) -> reference::Result<()> {
    use std::os::unix::fs::MetadataExt;
    if step != boundary_metadata::STEP {
        return Err("automatic parent mtime wrapper only accepts alias step5".into());
    }
    let before = std::fs::symlink_metadata(boundary_metadata::PATH)?;
    if !before.is_dir() {
        return Err("original alias parent is not a directory".into());
    }
    let initial = boundary_metadata::Timestamp {
        seconds: before.mtime(),
        nanoseconds: u32::try_from(before.mtime_nsec())?,
    };
    if initial.seconds != reference::file_size_transition::DECLARED_MTIME_SECONDS
        || initial.nanoseconds != 0
    {
        return Err("original alias parent mtime differs before helper attempt".into());
    }
    let started = realtime()?;
    let status = std::process::Command::new(helper)
        .args(["v016-boundary-alias", "1", "5"])
        .status()?;
    if !status.success() {
        return Err(format!("unchanged alias helper failed once: {status}").into());
    }
    let after = std::fs::symlink_metadata(boundary_metadata::PATH)?;
    let finished = realtime()?;
    if !after.is_dir() || (before.dev(), before.ino()) != (after.dev(), after.ino()) {
        return Err("original alias parent identity changed".into());
    }
    let custody = boundary_metadata::Custody {
        initial,
        started,
        finished,
        observed: boundary_metadata::Timestamp {
            seconds: after.mtime(),
            nanoseconds: u32::try_from(after.mtime_nsec())?,
        },
    };
    let body = custody.encode();
    boundary_metadata::parse(reference::file_size_transition::ALIAS_ROUNDTRIP, &body)?;
    print!("{body}");
    Ok(())
}

fn verify_boundary_alias(id: &str, step: usize, custody: &Path) -> reference::Result<()> {
    let body = std::fs::read_to_string(custody)?;
    let timestamp = boundary_metadata::parse(id, &body)?;
    let entries = boundary_metadata::entries(id, step, timestamp)?;
    for (key, value) in reference::workspace_common::verify_native(Path::new("."), &entries)? {
        println!("{key}={value}");
    }
    println!(
        "parent_mtime_custody_sha256={}",
        sdk_edit_common::sha256_hex(body.as_bytes())
    );
    println!("parent_mtime_custody_scope=alias-state5-data-mtime-only-exact-nanoseconds");
    Ok(())
}

fn apply_sdk_step(id: &str, step: usize, member: Option<usize>) -> reference::Result<()> {
    apply_sdk_members(id, step, member, sdk_edit_model::sdk_step(id, step)?)
}

fn apply_sdk_members(
    id: &str,
    step: usize,
    member: Option<usize>,
    edits: Vec<sdk_edit_model::SdkSplice>,
) -> reference::Result<()> {
    use reference::workspace_common::{self as common, EntryKind};
    if step == 0 {
        return Err("original SDK step is one-based".into());
    }
    if edits.is_empty() || member.is_some_and(|value| value == 0 || value > edits.len()) {
        return Err("original SDK step/member has no declared edit".into());
    }
    let mut work = Progress::default();
    let mut completed = 0;
    let mut replacement_bytes = 0;
    for (index, selected) in edits.iter().enumerate() {
        if member.is_some_and(|value| value != index + 1) {
            continue;
        }
        let edit = &selected.edit;
        if selected.metadata.path != edit.path
            || !matches!(selected.metadata.kind, EntryKind::File(_))
        {
            return Err("original SDK target metadata descriptor differs".into());
        }
        let plan = Splice {
            start: edit.start,
            delete_len: edit.delete_len,
            replacement_len: edit.replacement.len() as u64,
            fixture_bytes: selected.before_len,
            final_bytes: selected.after_len,
        };
        let file = OpenOptions::new().read(true).write(true).open(&edit.path)?;
        let changed = (|| -> reference::Result<()> {
            splice(&file, &plan, &edit.replacement, &mut work)?;
            common::set_metadata(Path::new(&edit.path), &selected.metadata)?;
            Ok(())
        })();
        let closed = checked_close(file);
        if let Err(error) = changed {
            if let Err(close_error) = closed {
                eprintln!("independent_close_failure={close_error}");
            }
            return Err(error);
        }
        closed?;
        completed += 1;
        replacement_bytes += edit.replacement.len() as u64;
        println!("sdk_member={}\npath={}\nstart={}\ndelete_len={}\nreplacement_len={}\ninitial_bytes={}\nfinal_bytes={}",
            index + 1, edit.path, plan.start, plan.delete_len, plan.replacement_len,
            plan.fixture_bytes, plan.final_bytes);
    }
    eprintln!("ordinary_edit_reads={} ordinary_edit_read_bytes={} ordinary_edit_writes={} ordinary_edit_write_bytes={} ordinary_edit_truncates={} scratch_window_bytes={SCRATCH_BYTES}",
        work.read_calls, work.read_bytes, work.write_calls, work.write_bytes, work.truncate_calls);
    println!("mutation_status=pass\ncase={id}\nstep={step}\noriginal_sdk_edit_members={completed}\nreplacement_bytes={replacement_bytes}");
    Ok(())
}

fn safe_relative(path: &str) -> bool {
    !path.is_empty()
        && !path.contains(['\0', '\\', '\t', '\r', '\n'])
        && path.split('/').all(|part| !matches!(part, "" | "." | ".."))
}

fn read_prepared(path: &Path) -> reference::Result<Vec<u8>> {
    let file = File::open(path)?;
    let read = (|| -> reference::Result<Vec<u8>> {
        let mut bytes = vec![0; usize::try_from(file.metadata()?.len())?];
        let mut work = Progress::default();
        read_exact_at(&file, &mut bytes, 0, &mut work)?;
        eprintln!(
            "prepared_artifact_read_calls={} prepared_artifact_read_bytes={}",
            work.read_calls, work.read_bytes
        );
        Ok(bytes)
    })();
    let closed = checked_close(file);
    match read {
        Err(error) => {
            if let Err(close_error) = closed {
                eprintln!("independent_prepared_close_failure={close_error}");
            }
            Err(error)
        }
        Ok(bytes) => {
            closed?;
            Ok(bytes)
        }
    }
}

fn prepare_sdk_step(id: &str, step: usize, folder: &Path) -> reference::Result<()> {
    prepare_step_payloads(id, None, step, folder, sdk_edit_model::sdk_step(id, step)?)
}

fn prepare_context_step(id: &str, role: &str, step: usize, folder: &Path) -> reference::Result<()> {
    prepare_step_payloads(
        id,
        Some(role),
        step,
        folder,
        sdk_edit_model::context_sdk_step(id, role, step)?,
    )
}

fn prepare_step_payloads(
    id: &str,
    role: Option<&str>,
    step: usize,
    folder: &Path,
    edits: Vec<sdk_edit_model::SdkSplice>,
) -> reference::Result<()> {
    use std::fmt::Write;
    if edits.is_empty() {
        return Err("original SDK step has no declared edit".into());
    }
    std::fs::create_dir(folder)?;
    let mut descriptor = if let Some(role) = role {
        format!(
        "original-context-step-payloads-v1\ncase\t{id}\nrole\t{role}\nstep\t{step}\nmembers\t{}\n",
        edits.len()
    )
    } else {
        format!(
            "original-sdk-step-payloads-v1\ncase\t{id}\nstep\t{step}\nmembers\t{}\n",
            edits.len()
        )
    };
    for (index, selected) in edits.iter().enumerate() {
        if !safe_relative(&selected.edit.path) || selected.metadata.path != selected.edit.path {
            return Err("original prepared SDK target path differs".into());
        }
        let filename = format!("member-{}.bin", index + 1);
        std::fs::write(folder.join(&filename), &selected.edit.replacement)?;
        writeln!(
            &mut descriptor,
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{:o}\t{}\t{}\t{}",
            index + 1,
            selected.edit.path,
            selected.edit.start,
            selected.edit.delete_len,
            selected.before_len,
            selected.after_len,
            selected.edit.replacement.len(),
            sdk_edit_common::sha256_hex(&selected.edit.replacement),
            selected.metadata.mode,
            selected.metadata.mtime_seconds,
            selected.metadata.mtime_nanoseconds,
            filename
        )?;
    }
    std::fs::write(folder.join("descriptor.tsv"), &descriptor)?;
    let digest = sdk_edit_common::sha256_hex(descriptor.as_bytes());
    if let Some(role) = role {
        println!("{{\"case\":\"{id}\",\"role\":\"{role}\",\"step\":{step},\"members\":{},\"descriptor_sha256\":\"{digest}\",\"scope\":\"untimed original contextual payload and target geometry\"}}", edits.len());
        return Ok(());
    }
    println!("{{\"case\":\"{id}\",\"step\":{step},\"members\":{},\"descriptor_sha256\":\"{digest}\",\"scope\":\"untimed original sdk_step payload and target geometry\"}}", edits.len());
    Ok(())
}

fn apply_prepared_sdk_step(
    id: &str,
    step: usize,
    descriptor: &Path,
    wanted_digest: &str,
    member: Option<usize>,
) -> reference::Result<()> {
    apply_prepared_step(id, None, step, descriptor, wanted_digest, member)
}

fn apply_prepared_step(
    id: &str,
    role: Option<&str>,
    step: usize,
    descriptor: &Path,
    wanted_digest: &str,
    member: Option<usize>,
) -> reference::Result<()> {
    use reference::workspace_common::{Content, Entry, SdkEdit};
    let case = reference::workspace_registry::resolve(id)?;
    let eligible = if let Some(role) = role {
        step > 0
            && step <= edit_model::context_limit(id, role)?
            && (!edit_model::is_context_m1(id) || step % 5 == 2)
    } else if edit_model::is_m1(id) {
        let plan = reference::v016_stages::mixed_case(id)?.ok_or("original M1 case missing")?;
        step > 0 && step <= plan.k && step % 5 == 2
    } else if case.family == "file_size_transition" {
        let plan = reference::file_size_transition::plan(id)?;
        !plan.alias && step > 0 && step <= plan.commits
    } else if case.family == "dedup_branch_history" {
        step > 0
            && step <= reference::workspace_registry::steps(&case)
            && (reference::dedup_workloads::is_sdk(&case)
                || (reference::v016_hn::is_hn(id) && step % 5 == 2))
    } else {
        false
    };
    if !eligible {
        return Err("original prepared SDK case/step is not declared".into());
    }
    // This seal is generated outside the timer from the exact original model
    // and embedded in the helper-sealed command. No recipe is regenerated here.
    let bytes = read_prepared(descriptor)?;
    if wanted_digest.len() != 64
        || !wanted_digest
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        || sdk_edit_common::sha256_hex(&bytes) != wanted_digest
    {
        return Err("original prepared SDK descriptor seal differs".into());
    }
    let text = std::str::from_utf8(&bytes)?;
    let mut lines = text.lines();
    let schema = if role.is_some() {
        "original-context-step-payloads-v1"
    } else {
        "original-sdk-step-payloads-v1"
    };
    if step == 0
        || lines.next() != Some(schema)
        || lines.next() != Some(format!("case\t{id}").as_str())
    {
        return Err("original prepared SDK case/step/header differs".into());
    }
    if role.is_some_and(|role| lines.next() != Some(format!("role\t{role}").as_str()))
        || lines.next() != Some(format!("step\t{step}").as_str())
    {
        return Err("original prepared context role/step header differs".into());
    }
    let count = lines
        .next()
        .and_then(|row| row.strip_prefix("members\t"))
        .ok_or("original prepared SDK member count missing")?
        .parse::<usize>()?;
    if count == 0
        || member.is_some_and(|value| value == 0 || value > count)
        || role.is_some() && count != if edit_model::is_context_m1(id) { 2 } else { 1 }
    {
        return Err("original prepared SDK member outside schedule".into());
    }
    let mut edits = Vec::new();
    for (index, line) in lines.enumerate() {
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 12
            || fields[0].parse::<usize>()? != index + 1
            || !safe_relative(fields[1])
            || fields[11] != format!("member-{}.bin", index + 1)
        {
            return Err("original prepared SDK row/path/member differs".into());
        }
        let start = fields[2].parse::<u64>()?;
        let delete_len = fields[3].parse::<u64>()?;
        let before_len = fields[4].parse::<u64>()?;
        let after_len = fields[5].parse::<u64>()?;
        let replacement_len = fields[6].parse::<u64>()?;
        let mode = u32::from_str_radix(fields[8], 8)?;
        let seconds = fields[9].parse::<i64>()?;
        let nanos = fields[10].parse::<u32>()?;
        if mode & !0o7777 != 0
            || nanos >= 1_000_000_000
            || start
                .checked_add(delete_len)
                .is_none_or(|end| end > before_len)
            || before_len
                .checked_sub(delete_len)
                .and_then(|len| len.checked_add(replacement_len))
                != Some(after_len)
        {
            return Err("original prepared SDK geometry/metadata differs".into());
        }
        let replacement = read_prepared(
            descriptor
                .parent()
                .ok_or("SDK descriptor parent absent")?
                .join(fields[11])
                .as_path(),
        )?;
        if replacement.len() as u64 != replacement_len
            || sdk_edit_common::sha256_hex(&replacement) != fields[7]
        {
            return Err("original prepared SDK payload length/hash differs".into());
        }
        let mut metadata = Entry::file(fields[1], Content::Zero { len: before_len });
        metadata.mode = mode;
        metadata.mtime_seconds = seconds;
        metadata.mtime_nanoseconds = nanos;
        edits.push(sdk_edit_model::SdkSplice {
            edit: SdkEdit {
                path: fields[1].to_owned(),
                start,
                delete_len,
                replacement,
            },
            before_len,
            after_len,
            metadata,
        });
    }
    if edits.len() != count {
        return Err("original prepared SDK member cardinality differs".into());
    }
    apply_sdk_members(id, step, member, edits)?;
    if let Some(role) = role {
        println!("context_role={role}");
    }
    Ok(())
}

fn main() -> reference::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    match args.as_slice() {
        [_, mode, step, helper] if mode == "apply-boundary-alias" => {
            apply_boundary_alias(step.parse()?, Path::new(helper))
        }
        [_, mode, id] if mode == "apply" => apply(id),
        [_, mode, id] if mode == "apply-workspace" => apply_workspace(id),
        [_, mode, id, step] if mode == "apply-sdk-step" => apply_sdk_step(id, step.parse()?, None),
        [_, mode, id, step, member] if mode == "apply-sdk-step" => {
            apply_sdk_step(id, step.parse()?, Some(member.parse()?))
        }
        [_, mode, id, step, folder] if mode == "prepare-sdk-step" => {
            prepare_sdk_step(id, step.parse()?, Path::new(folder))
        }
        [_, mode, id, role, step, folder] if mode == "prepare-context-step" => {
            prepare_context_step(id, role, step.parse()?, Path::new(folder))
        }
        [_, mode, id, role, step, descriptor, digest] if mode == "apply-context-step-prepared" => {
            apply_prepared_step(id, Some(role), step.parse()?, Path::new(descriptor), digest, None)
        }
        [_, mode, id, role, step, descriptor, digest, member] if mode == "apply-context-step-prepared" => {
            apply_prepared_step(id, Some(role), step.parse()?, Path::new(descriptor), digest, Some(member.parse()?))
        }
        [_, mode, id, step, descriptor, digest] if mode == "apply-sdk-step-prepared" => {
            apply_prepared_sdk_step(id, step.parse()?, Path::new(descriptor), digest, None)
        }
        [_, mode, id, step, descriptor, digest, member] if mode == "apply-sdk-step-prepared" => {
            apply_prepared_sdk_step(id, step.parse()?, Path::new(descriptor), digest, Some(member.parse()?))
        }
        [_, mode, id, step] if mode == "m1-scope" => {
            let state = edit_model::m1_state(id, step.parse()?, None)?;
            print!("{}", edit_model::m1_scope_tsv(&state)?);
            Ok(())
        }
        [_, mode, manifest] if mode == "verify-manifest" => {
            let entries =
                reference::workspace_common::decode_manifest(&std::fs::read_to_string(manifest)?)?;
            for (key, value) in
                reference::workspace_common::verify_native(Path::new("."), &entries)?
            {
                println!("{key}={value}");
            }
            println!("manifest_provenance=sealed-independent-original-source-SHA256");
            Ok(())
        }
        [_, mode, id, step] if mode == "verify" => {
            let entries = edit_model::entries(id, step.parse()?)?;
            for (key, value) in
                reference::workspace_common::verify_native(Path::new("."), &entries)?
            {
                println!("{key}={value}");
            }
            Ok(())
        }
        [_, mode, id, step, custody] if mode == "verify" => {
            verify_boundary_alias(id, step.parse()?, Path::new(custody))
        }
        _ => Err("apply CASE | apply-workspace CASE | apply-sdk-step CASE STEP [MEMBER] | prepare-sdk-step CASE STEP FRESH_FOLDER | apply-sdk-step-prepared CASE STEP DESCRIPTOR SHA256 [MEMBER] | verify CASE STEP | verify-manifest MANIFEST required".into()),
    }
}

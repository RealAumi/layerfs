//! Native-only fixture/expectation materialization from frozen ordinary recipes.
#[allow(dead_code)]
mod dedup_input;
mod edit_model;
#[allow(dead_code)]
#[path = "../../workload/main.rs"]
mod reference;
mod sdk_edit_model;
use std::os::unix::fs::MetadataExt;
use std::{
    collections::BTreeMap,
    fs,
    io::{Read, Seek, SeekFrom},
    path::Path,
};

fn verify_m1(id: &str, step: usize, root: &Path, modes: &Path) -> reference::Result<()> {
    if !edit_model::is_m1(id) {
        return Err("original M1 selective case required".into());
    }
    let case = reference::v016_stages::mixed_case(id)?.ok_or("original M1 case missing")?;
    // The frozen verifier accepts the sealed final cumulative observation map
    // at earlier checkpoints. Only names from this case's declared domain may
    // appear; the selected state still requires every relevant observation.
    let domain = edit_model::m1_state(id, case.k, None)?.required_created_directory_modes;
    let mode_text = fs::read_to_string(modes)?;
    let mut created_modes = BTreeMap::new();
    for line in mode_text.lines() {
        let (path, mode) = line
            .split_once('\t')
            .ok_or("created mode TSV requires two columns")?;
        if path.is_empty()
            || path.split('/').any(|part| matches!(part, "" | "." | ".."))
            || path.contains(['\0', '\\', '\t', '\r'])
            || mode.is_empty()
            || !mode.bytes().all(|byte| matches!(byte, b'0'..=b'7'))
            || !domain.contains(path)
            || u32::from_str_radix(mode, 8)? & !0o1777 != 0
            || created_modes
                .insert(path.to_owned(), u32::from_str_radix(mode, 8)?)
                .is_some()
        {
            return Err("created mode observation is malformed, duplicate or undeclared".into());
        }
    }
    let state = edit_model::m1_state(id, step, Some(&created_modes))?;
    verify_m1_state(id, step, root, &mode_text, state)
}

fn verify_m1_state(
    id: &str,
    step: usize,
    root: &Path,
    mode_text: &str,
    state: edit_model::M1State,
) -> reference::Result<()> {
    use reference::workspace_common::{self as common, EntryKind};
    let expected = state
        .entries
        .iter()
        .map(|entry| (entry.path.as_str(), entry))
        .collect::<BTreeMap<_, _>>();
    let mut class_names = BTreeMap::<&str, u64>::new();
    for entry in &state.entries {
        let class = match &entry.kind {
            EntryKind::File(_) => entry.path.as_str(),
            EntryKind::Hardlink(target) => target.as_str(),
            _ => continue,
        };
        *class_names.entry(class).or_default() += 1;
    }
    let mut class_inodes = BTreeMap::new();
    let mut inode_classes = BTreeMap::new();
    let mut actual = vec![0; common::SCRATCH_BYTES];
    let mut wanted = vec![0; common::SCRATCH_BYTES];
    let mut checked_bytes = 0u64;
    let mut inspect = |relative: &str,
                       path: &Path,
                       metadata: fs::Metadata|
     -> reference::Result<()> {
        let entry = expected
            .get(relative)
            .ok_or("original M1 selective namespace differs")?;
        let (class, content) = match &entry.kind {
            EntryKind::Directory if metadata.is_dir() => {
                if let Some(mode) = state.directory_modes.get(&entry.path) {
                    if metadata.mode() & 0o7777 != *mode {
                        return Err(format!(
                            "original M1 declared directory mode differs: {}",
                            entry.path
                        )
                        .into());
                    }
                }
                return Ok(());
            }
            EntryKind::Symlink(target) if metadata.file_type().is_symlink() => {
                if fs::read_link(path)?.to_str() != Some(target.as_str())
                    || metadata.len() != target.len() as u64
                {
                    return Err(format!(
                        "original M1 symlink target/length differs: {}",
                        entry.path
                    )
                    .into());
                }
                return Ok(());
            }
            EntryKind::File(content) if metadata.is_file() => (entry.path.as_str(), content),
            EntryKind::Hardlink(target) if metadata.is_file() => {
                let EntryKind::File(content) = &expected
                    .get(target.as_str())
                    .ok_or("M1 alias target absent")?
                    .kind
                else {
                    return Err("M1 alias target must be canonical regular file".into());
                };
                (target.as_str(), content)
            }
            _ => return Err(format!("original M1 selective kind differs: {}", entry.path).into()),
        };
        if metadata.len() != content.len() || metadata.nlink() != class_names[class] {
            return Err(format!("original M1 length/link count differs: {}", entry.path).into());
        }
        let inode = (metadata.dev(), metadata.ino());
        if class_inodes
            .insert(class, inode)
            .is_some_and(|prior| prior != inode)
            || inode_classes
                .insert(inode, class)
                .is_some_and(|prior| prior != class)
        {
            return Err("original M1 canonical inode classes differ".into());
        }
        if state
            .file_modes
            .get(class)
            .is_some_and(|mode| metadata.mode() & 0o7777 != *mode)
            || state
                .file_mtimes
                .get(class)
                .is_some_and(|(seconds, nanos)| {
                    metadata.mtime() != *seconds || metadata.mtime_nsec() != i64::from(*nanos)
                })
        {
            return Err(
                format!("original M1 declared file metadata differs: {}", entry.path).into(),
            );
        }
        let ranges = state
            .ranges
            .get(&entry.path)
            .ok_or("original M1 regular coverage absent")?;
        // Empty ranges at zero/exact128KiB are explicit original length/type
        // coverage, not an instruction to replace the oracle with full reads.
        if ranges.is_empty() {
            return Ok(());
        }
        let mut file = fs::File::open(path)?;
        for &(offset, len) in ranges {
            if offset
                .checked_add(len)
                .is_none_or(|end| end > content.len())
            {
                return Err("original M1 declared range outside file".into());
            }
            file.seek(SeekFrom::Start(offset))?;
            let mut done = 0;
            while done < len {
                let count = (len - done).min(actual.len() as u64) as usize;
                file.read_exact(&mut actual[..count])?;
                if content.read_at(offset + done, &mut wanted[..count])? != count {
                    return Err("original M1 independent content range is short".into());
                }
                if actual[..count] != wanted[..count] {
                    return Err(format!(
                        "original M1 declared byte range differs: {} offset{}",
                        entry.path,
                        offset + done
                    )
                    .into());
                }
                done += count as u64;
                checked_bytes = checked_bytes
                    .checked_add(count as u64)
                    .ok_or("M1 checked bytes overflow")?;
            }
        }
        Ok(())
    };
    let mut paths = vec![".".to_owned()];
    let root_path = root.join(".");
    inspect(".", &root_path, fs::symlink_metadata(&root_path)?)?;
    let mut directories = vec![root.to_owned()];
    while let Some(directory) = directories.pop() {
        for item in fs::read_dir(directory)? {
            let path = item?.path();
            let relative = path
                .strip_prefix(root)?
                .to_str()
                .ok_or("non-UTF8 fixture path")?
                .to_owned();
            let metadata = fs::symlink_metadata(&path)?;
            let directory = metadata.is_dir();
            // Membership in the canonical expected map authenticates the
            // relative name before it is visited or used as a directory.
            inspect(&relative, &path, metadata)?;
            if directory {
                directories.push(path);
            }
            paths.push(relative);
        }
    }
    paths.sort();
    if paths
        != state
            .entries
            .iter()
            .map(|entry| entry.path.clone())
            .collect::<Vec<_>>()
    {
        return Err("original M1 selective namespace differs".into());
    }
    let scope = edit_model::m1_scope_tsv(&state)?;
    let scope_digest = reference::sdk_edit_common::sha256_hex(scope.as_bytes());
    let modes_digest = reference::sdk_edit_common::sha256_hex(mode_text.as_bytes());
    println!("{{\"case\":\"{id}\",\"seed\":1,\"step\":{step},\"verification_status\":\"pass\",\"scope\":\"original-m1-selective-scope-v1\",\"scope_digest\":\"{scope_digest}\",\"created_modes_digest\":\"{modes_digest}\",\"entries\":{},\"checked_range_bytes\":{checked_bytes}}}", state.entries.len());
    Ok(())
}

fn verify_context(
    id: &str,
    role: &str,
    step: usize,
    root: &Path,
    modes: &str,
) -> reference::Result<()> {
    if edit_model::is_context_m1(id) {
        let body = fs::read_to_string(modes)?;
        let observations = edit_model::parse_context_created_modes(id, &body)?;
        let state = edit_model::context_m1_state(id, role, step, Some(&observations))?;
        verify_m1_state(id, step, root, &body, state)?;
    } else {
        if modes != "-" {
            return Err("original compact context requires modes sentinel".into());
        }
        let entries = edit_model::context_entries(id, role, step)?;
        reference::workspace_common::verify_native(root, &entries)?;
    }
    let scope = edit_model::context_manifest(id, role, step)?;
    let digest = reference::sdk_edit_common::sha256_hex(scope.as_bytes());
    println!("{{\"case\":\"{id}\",\"role\":\"{role}\",\"step\":{step},\"verification_status\":\"pass\",\"context_manifest_sha256\":\"{digest}\"}}");
    Ok(())
}

fn materialize_context(id: &str, role: &str, step: usize, root: &Path) -> reference::Result<()> {
    use reference::workspace_common as common;
    let manifest = root.with_extension("manifest.tsv");
    let scope = root.with_extension("scope.tsv");
    if root.exists() || manifest.exists() || scope.exists() {
        return Err("fresh contextual root/manifest/scope required".into());
    }
    let entries = edit_model::context_entries(id, role, step)?;
    let complete_manifest = common::manifest(&entries)?;
    let scoped_manifest = edit_model::context_manifest(id, role, step)?;
    common::create_fixture(root, &entries)?;
    fs::write(&manifest, &complete_manifest)?;
    if edit_model::is_context_m1(id) {
        fs::write(&scope, &scoped_manifest)?;
    }
    let manifest_digest = reference::sdk_edit_common::sha256_hex(complete_manifest.as_bytes());
    let scope_digest = reference::sdk_edit_common::sha256_hex(scoped_manifest.as_bytes());
    let recipe = common::recipe_identity(&entries)?;
    let bytes = common::validate_entries(&entries)?;
    println!("{{\"case\":\"{id}\",\"role\":\"{role}\",\"step\":{step},\"seed\":1,\"manifest_sha256\":\"{manifest_digest}\",\"context_manifest_sha256\":\"{scope_digest}\",\"recipe_sha256\":\"{recipe}\",\"entries\":{},\"logical_bytes\":{bytes}}}", entries.len());
    Ok(())
}

fn prepare_context_discard(id: &str, folder: &Path) -> reference::Result<()> {
    use reference::{dedup_workloads, v016_common as v016, v016_stages as stages};
    let case = stages::mixed_case(id)?.ok_or("original two-worker case required")?;
    if case.topology != stages::Topology::Concurrent || folder.exists() {
        return Err("fresh original two-worker discard witness required".into());
    }
    let tier = if case.tier == "L100" {
        &v016::L100
    } else {
        &v016::L500
    };
    let fixture = v016::load_fixture(tier, 1)?;
    let path = fixture
        .roles
        .refresh_pool
        .get(v016::REFRESH_FILES_PER_COHORT)
        .ok_or("original refresh-cohort discard witness missing")?;
    let content = dedup_workloads::content(
        v016::FAMILY_MIXED,
        "v016-discard",
        1,
        0,
        "discarded-mutation",
        256,
    )?;
    let mut bytes = Vec::new();
    content.write_to(&mut bytes)?;
    if bytes.len() != 256 {
        return Err("original discard witness length differs".into());
    }
    let hex = bytes
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let body = format!("original-context-discard-witness-v1\n{id}\t0\t{path}\t{hex}\n");
    fs::create_dir(folder)?;
    fs::write(folder.join("witness.tsv"), &body)?;
    let payload_digest = reference::sdk_edit_common::sha256_hex(&bytes);
    let descriptor_digest = reference::sdk_edit_common::sha256_hex(body.as_bytes());
    println!("{{\"case\":\"{id}\",\"role\":\"0\",\"path\":\"{path}\",\"bytes\":256,\"payload_sha256\":\"{payload_digest}\",\"descriptor_sha256\":\"{descriptor_digest}\"}}");
    Ok(())
}

fn main() -> reference::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if let [_, mode, id, step, root] = args.as_slice() {
        if mode == "import-qualified" {
            let step = step.parse::<usize>()?;
            let qualified = dedup_input::qualify_native(id, step, Path::new(root))?;
            fn quoted(value: &str) -> String {
                let mut out = String::from("\"");
                for character in value.chars() {
                    match character {
                        '"' => out.push_str("\\\""),
                        '\\' => out.push_str("\\\\"),
                        '\n' => out.push_str("\\n"),
                        '\r' => out.push_str("\\r"),
                        '\t' => out.push_str("\\t"),
                        c if c.is_control() => out.push_str(&format!("\\u{:04x}", u32::from(c))),
                        c => out.push(c),
                    }
                }
                out.push('"');
                out
            }
            let receipt = qualified
                .receipt
                .iter()
                .map(|(key, value)| format!("{}:{}", quoted(key), quoted(value)))
                .collect::<Vec<_>>()
                .join(",");
            let transcripts = qualified
                .transcripts
                .iter()
                .map(|(path, chunks)| {
                    let chunks = chunks
                        .iter()
                        .map(|chunk| {
                            format!(
                                "{{\"logical_start\":{},\"len\":{},\"raw_sha256\":{}}}",
                                chunk.logical_start,
                                chunk.len,
                                quoted(&chunk.raw_sha256)
                            )
                        })
                        .collect::<Vec<_>>()
                        .join(",");
                    format!("{}:[{chunks}]", quoted(path))
                })
                .collect::<Vec<_>>()
                .join(",");
            println!("{{\"schema\":\"fs-bench-pro-independent-dedup-input-v1\",\"status\":\"PASS\",\"case\":{},\"step\":{step},\"regular_files\":{},\"logical_bytes\":{},\"transcript_sha256\":{},\"receipt\":{{{receipt}}},\"transcripts\":{{{transcripts}}}}}", quoted(id), qualified.files, qualified.logical_bytes, quoted(&qualified.transcript_sha256));
            return Ok(());
        }
    }
    if let [_, mode, id, folder] = args.as_slice() {
        if mode == "prepare-context-discard" {
            return prepare_context_discard(id, Path::new(folder));
        }
    }
    if let [_, mode, id, role, step, root] = args.as_slice() {
        if mode == "materialize-context" {
            return materialize_context(id, role, step.parse()?, Path::new(root));
        }
    }
    if let [_, mode, id, role, step, root, modes] = args.as_slice() {
        if mode == "verify-context" {
            return verify_context(id, role, step.parse()?, Path::new(root), modes);
        }
    }
    if let [_, mode, id, step, root, modes] = args.as_slice() {
        if mode == "verify-m1-step" {
            return verify_m1(id, step.parse()?, Path::new(root), Path::new(modes));
        }
    }
    let (mode, id, step, root) = match args.as_slice() {
        [_, mode, id, root]
            if matches!(mode.as_str(), "fixture" | "expected" | "git-fixture-check") =>
        {
            (mode.as_str(), id.as_str(), usize::from(mode == "expected"), Path::new(root))
        }
        [_, mode, id, step, root]
            if matches!(mode.as_str(), "expected-step" | "verify-step") =>
        {
            let step = step.parse::<usize>()?;
            let maximum = if edit_model::is_m1(id) {
                reference::v016_stages::mixed_case(id)?.ok_or("original M1 case missing")?.k
            } else { match edit_model::scenario(id) {
                Some(_) => 1,
                None => reference::workspace_registry::steps(&reference::workspace_registry::resolve(id)?),
            }};
            if step > maximum {
                return Err("native expected step outside original declared history prefix".into());
            }
            if mode == "verify-step" && step > 0
                && reference::workspace_registry::resolve(id).is_ok_and(|case| case.family == "mixed_load_bearing")
            {
                return Err("actual mixed workload requires original selective verification coverage, not a generic full-tree verifier".into());
            }
            (mode.as_str(), id.as_str(), step, Path::new(root))
        }
        _ => return Err("fixture|expected CASE FRESH_NATIVE_ROOT, git-fixture-check CASE EXISTING_NATIVE_ROOT, or expected-step|verify-step CASE STEP ROOT required".into()),
    };
    let entries = if mode == "git-fixture-check" {
        let case = reference::workspace_registry::resolve(id)?;
        let entries = reference::ordinary_workloads::prepared_git_entries(root, &case, 1)?;
        reference::workspace_common::verify_native(root, &entries)?;
        entries
    } else {
        let entries = edit_model::entries(id, step)?;
        if mode == "verify-step" {
            reference::workspace_common::verify_native(root, &entries)?;
        } else {
            if root.exists() {
                return Err("fresh native output required".into());
            }
            if mode == "expected-step" && root.with_extension("manifest.tsv").exists() {
                return Err("existing native manifest replacement refused".into());
            }
            reference::workspace_common::create_fixture(root, &entries)?;
        }
        entries
    };
    if mode == "fixture" {
        if let Some(wanted) = sdk_edit_model::fixture_sha256(id)? {
            if edit_model::original_fixture_hash(&entries)? != wanted {
                return Err("original SDK fixture digest differs from frozen seal".into());
            }
        }
    }
    let manifest = reference::workspace_common::manifest(&entries)?;
    let manifest_path = if mode == "git-fixture-check" {
        root.with_extension("git.manifest.tsv")
    } else {
        root.with_extension("manifest.tsv")
    };
    if mode != "verify-step" {
        fs::write(manifest_path, &manifest)?;
    }
    let bytes = reference::workspace_common::validate_entries(&entries)?;
    let files = entries
        .iter()
        .filter(|entry| {
            matches!(
                entry.kind,
                reference::workspace_common::EntryKind::File(_)
                    | reference::workspace_common::EntryKind::Hardlink(_)
            )
        })
        .count();
    let digest = reference::sdk_edit_common::sha256_hex(manifest.as_bytes());
    let recipe = reference::workspace_common::recipe_identity(&entries)?;
    let verified = if matches!(mode, "git-fixture-check" | "verify-step") {
        ",\"verification_status\":\"pass\""
    } else {
        ""
    };
    let checkpoint = if matches!(mode, "expected-step" | "verify-step") {
        format!(",\"step\":{step}")
    } else {
        String::new()
    };
    println!("{{\"case\":\"{id}\",\"seed\":1,\"files\":{files},\"entries\":{},\"logical_bytes\":{bytes},\"fixture_digest\":\"{digest}\",\"recipe_identity\":\"{recipe}\"{verified}{checkpoint}}}",
        entries.len());
    Ok(())
}

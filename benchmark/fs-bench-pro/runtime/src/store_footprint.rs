//! Original Store-footprint topology, initial census and clipped edit proof.
//! Global physical SQL census and fresh FUSE boundary/cleanup remain separate.
use crate::{args::Args, events::Events, reference, Result};
use layerfs_bridge::provision::{StoreManifest, StoreProfile};
use layerfs_content::{
    file::FileView,
    filesystem::{
        attributes::read::{read_portable, AttributeReadWork},
        FilesystemRead, FilesystemRootId, LogicalPath,
    },
    inode_leaf::InodeKind,
    AuthenticatedObjects, ObjectId,
};
use layerfs_history::{
    BranchId, CatalogId, CommitHistoryRequest, CommitId, HistoryCatalog, LayerHistoryRequest,
    LayerId, LayerStackId, Page,
};
use layerfs_persistence::{Handles, PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::Storage;
use layerfs_telemetry::timer::Timing;
use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    fs,
    io::{Read, Seek, SeekFrom, Write},
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::Path,
    time::Instant,
};

#[derive(Clone, Debug)]
pub struct FilePlan {
    pub path: String,
    pub size: u64,
    pub mtime_seconds: i64,
}
#[derive(Clone, Debug)]
pub struct Plan {
    pub files: Vec<FilePlan>,
    pub directories: u64,
    pub logical_bytes: u64,
    pub edit_path: String,
    pub edit_size: u64,
    pub edit_offset: u64,
    pub boundary_start: u64,
    pub boundary_end: u64,
}
pub fn plan(case: &str) -> Result<Plan> {
    use reference::store_footprint::{self as footprint, Kind};
    let control = footprint::control(case)?;
    let (directories, files) = if control.kind == Kind::LargeObject {
        let count = if control.infra_tier == 100_000 {
            100
        } else {
            control.infra_tier.min(100)
        };
        let size = if control.infra_tier == 100_000 {
            5_000_000
        } else {
            1_000_000
        };
        (
            1,
            (0..count)
                .map(|index| FilePlan {
                    path: format!("d0000/file-{index:05}.bin"),
                    size,
                    mtime_seconds: reference::NAMESPACE_MTIME_SECONDS,
                })
                .collect::<Vec<_>>(),
        )
    } else {
        let id = match control.infra_tier {
            100 => "namespace-100-compact-v3",
            10_000 => "namespace-10000",
            100_000 => "namespace-100000",
            _ => return Err("original footprint namespace geometry absent".into()),
        };
        let namespace = reference::namespace_plan(id)?;
        (
            namespace.scenario.data_directories,
            namespace
                .files
                .into_iter()
                .enumerate()
                .map(|(index, file)| FilePlan {
                    path: file.relative_path,
                    size: file.size,
                    mtime_seconds: reference::NAMESPACE_MTIME_SECONDS
                        + if control.kind == Kind::MetadataCardinality {
                            index as i64 + 1
                        } else {
                            0
                        },
                })
                .collect(),
        )
    };
    let logical_bytes = files.iter().map(|file| file.size).sum();
    if files.len() as u64 != control.regular_files || logical_bytes != control.logical_bytes {
        return Err("original footprint file/byte census differs".into());
    }
    let edit = files
        .iter()
        .find(|file| file.size > reference::NAMESPACE_EDIT_MARKER.len() as u64)
        .ok_or("original footprint edit target absent")?;
    let edit_path = edit.path.clone();
    let edit_size = edit.size;
    let edit_offset = reference::namespace_edit_offset(edit_size)?;
    Ok(Plan {
        files,
        directories,
        logical_bytes,
        edit_path,
        edit_size,
        edit_offset,
        boundary_start: edit_offset.saturating_sub(65536),
        boundary_end: edit_size
            .min(edit_offset + reference::NAMESPACE_EDIT_MARKER.len() as u64 + 65536),
    })
}

#[derive(Clone, Debug)]
pub struct Acknowledgements {
    pub case: String,
    pub branch: BranchId,
    pub initial: ObjectId,
    pub base: LayerId,
    pub stack: LayerStackId,
    pub commit: CommitId,
    pub final_root: ObjectId,
}
fn bytes<const N: usize>(text: &str) -> Result<[u8; N]> {
    if text.len() != N * 2
        || !text
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err("footprint acknowledgement requires exact lowercase tagged identity".into());
    }
    let mut result = [0; N];
    for (index, byte) in result.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&text[index * 2..index * 2 + 2], 16)?;
    }
    Ok(result)
}
pub fn parse_acknowledgements(body: &str) -> Result<Acknowledgements> {
    if !body.ends_with('\n') || body.contains(['\r', '\0']) {
        return Err("footprint four-line LF acknowledgement required".into());
    }
    let rows = body.lines().collect::<Vec<_>>();
    if rows.len() != 4 || rows[0] != "fs-bench-pro-store-footprint-ack-v1" {
        return Err("footprint four-line acknowledgement schema differs".into());
    }
    reference::store_footprint::control(rows[1])?;
    let init = rows[2].split('\t').collect::<Vec<_>>();
    let commit = rows[3].split('\t').collect::<Vec<_>>();
    if init.len() != 5
        || init[0] != "init"
        || commit.len() != 6
        || commit[0] != "commit"
        || commit[3] != "-"
    {
        return Err("footprint exact Init/CreatedCommit rows and absent parent required".into());
    }
    let ack = Acknowledgements {
        case: rows[1].into(),
        branch: BranchId::from_bytes(bytes(init[1])?)?,
        initial: ObjectId::from_bytes(&bytes::<32>(init[2])?)?,
        base: LayerId::from_bytes(bytes(init[3])?)?,
        stack: LayerStackId::from_bytes(bytes(init[4])?)?,
        commit: CommitId::from_bytes(bytes(commit[1])?)?,
        final_root: ObjectId::from_bytes(&bytes::<32>(commit[2])?)?,
    };
    if ack.base != LayerId::from_bytes(bytes(commit[4])?)?
        || ack.stack != LayerStackId::from_bytes(bytes(commit[5])?)?
        || ack.commit
            != CommitId::derive(
                ack.final_root,
                None,
                ack.base,
                None,
                &layerfs_history::CommitMeta {
                    branch: Some(ack.branch),
                    ..layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace)
                },
            )
        || ack.initial == ack.final_root
    {
        return Err("footprint canonical exact five-field Commit/Init binding differs".into());
    }
    Ok(ack)
}

/// Projection of the validated Init and CreatedCommit acknowledgements for the
/// separate unfiltered closed-Store census. Scope labels are not manifest paths.
pub fn census_transcript(ack: &Acknowledgements) -> String {
    format!(
        "0\t-\t-\t{}\toriginal-footprint-initial\n1\t{}\t-\t{}\toriginal-footprint-final-boundary\n",
        crate::hex(ack.initial.as_bytes()),
        crate::hex(ack.commit.as_slice()),
        crate::hex(ack.final_root.as_bytes())
    )
}

pub fn expected_boundary(source: &Path, plan: &Plan) -> Result<Vec<u8>> {
    let mut file = fs::File::open(source.join(&plan.edit_path))?;
    let before = file.metadata()?;
    if before.len() != plan.edit_size || !before.is_file() {
        return Err("original footprint native edit target type/length differs".into());
    }
    let mut expected = vec![0; (plan.boundary_end - plan.boundary_start) as usize];
    file.seek(SeekFrom::Start(plan.boundary_start))?;
    file.read_exact(&mut expected)?;
    let after = file.metadata()?;
    if (
        before.dev(),
        before.ino(),
        before.len(),
        before.mtime(),
        before.mtime_nsec(),
    ) != (
        after.dev(),
        after.ino(),
        after.len(),
        after.mtime(),
        after.mtime_nsec(),
    ) {
        return Err("original footprint native edit target changed during range read".into());
    }
    let at = (plan.edit_offset - plan.boundary_start) as usize;
    expected[at..at + reference::NAMESPACE_EDIT_MARKER.len()]
        .copy_from_slice(reference::NAMESPACE_EDIT_MARKER);
    Ok(expected)
}

/// Complete original initial names/kinds/metadata/lengths, with no independent
/// unselected payload comparison. All inode-table rows must be reachable once.
pub fn initial_census(
    reader: &dyn AuthenticatedObjects,
    root: ObjectId,
    plan: &Plan,
) -> Result<u64> {
    let expected = plan
        .files
        .iter()
        .map(|file| (file.path.as_str(), file))
        .collect::<BTreeMap<_, _>>();
    let directories = (0..plan.directories)
        .map(|index| format!("d{index:04}"))
        .chain(std::iter::once(".".into()))
        .collect::<BTreeSet<_>>();
    let mut tree = FilesystemRead::new(reader, FilesystemRootId(root))?;
    let mut attributes = AttributeReadWork::default();
    let mut pending = VecDeque::from([".".to_owned()]);
    let mut seen = BTreeSet::new();
    let mut inodes = BTreeSet::new();
    let mut logical_bytes = 0;
    while let Some(path) = pending.pop_front() {
        if !seen.insert(path.clone()) {
            return Err("duplicate footprint initial path".into());
        }
        let logical = LogicalPath::new(if path == "." { "" } else { &path })?;
        let resolved = tree.resolve(&logical)?;
        let required_references = if path == "." { 0 } else { 1 };
        if !inodes.insert(resolved.serial)
            || resolved.value.namespace_ref_count != required_references
        {
            return Err("original footprint initial inode classes/links differ".into());
        }
        let value = resolved.value;
        let metadata = read_portable(reader, value.metadata_root, value.kind, &mut attributes)?;
        let file = expected.get(path.as_str());
        let kind = if file.is_some() {
            InodeKind::RegularFile
        } else if directories.contains(&path) {
            InodeKind::Directory
        } else {
            return Err("unexpected footprint initial path".into());
        };
        let mode = if file.is_some() {
            reference::NAMESPACE_FILE_MODE
        } else {
            reference::NAMESPACE_DIRECTORY_MODE
        };
        let mtime = file.map_or(reference::NAMESPACE_MTIME_SECONDS, |file| {
            file.mtime_seconds
        });
        if value.kind != kind
            || metadata.mode != mode
            || metadata.mtime_seconds != mtime
            || metadata.mtime_nanoseconds != 0
        {
            return Err(format!("original footprint initial metadata/kind differs: {path}").into());
        }
        if let Some(file) = file {
            Timing::disabled("footprint.initial.length", |timer| -> Result<()> {
                let view = FileView::open(reader, value.content_root, timer.child("open"))?;
                if view.logical_len() != file.size {
                    return Err("original footprint initial file length differs".into());
                }
                crate::workspace_oracle::verify_mapping(reader, &view)?;
                Ok(())
            })
            .0?;
            logical_bytes += file.size;
        } else {
            let mut after = None;
            loop {
                let page = tree.list(&logical, after.as_ref(), 128, 16384)?;
                for (name, _) in page.entries {
                    pending.push_back(if path == "." {
                        name.as_str().into()
                    } else {
                        format!("{path}/{}", name.as_str())
                    });
                }
                after = page.continuation;
                if after.is_none() {
                    break;
                }
            }
        }
    }
    if seen.len() != plan.files.len() + directories.len() || logical_bytes != plan.logical_bytes {
        return Err("original footprint complete initial census differs".into());
    }
    crate::edit_oracle::require_complete_membership(reader, tree.root(), &inodes)?;
    Ok(seen.len() as u64)
}

fn file_identity(path: &Path) -> Result<(String, u64)> {
    let mut input = fs::File::open(path)?;
    let mut hash = reference::Sha256::new();
    let mut length = 0;
    let mut buffer = [0; 65536];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
        length += count as u64;
    }
    if input.metadata()?.len() != length {
        return Err("footprint provider changed during identity read".into());
    }
    Ok((crate::hex(&hash.finish()), length))
}

#[derive(Debug)]
pub struct ProviderIdentity {
    pub original_after: (String, u64),
    pub typed_after: (String, u64),
    pub typed_unchanged: bool,
}

/// Called only after the typed Handles have sealed. Observe that actual copy,
/// separately rejecting any mutation of the original normalized input.
pub fn sealed_provider_identity(
    original: &Path,
    typed: &Path,
    before: &(String, u64),
) -> Result<ProviderIdentity> {
    let original_after = file_identity(original)?;
    if &original_after != before {
        return Err("footprint original normalized source mutated during typed proof".into());
    }
    let typed_after = file_identity(typed)?;
    Ok(ProviderIdentity {
        typed_unchanged: &typed_after == before,
        original_after,
        typed_after,
    })
}

pub fn verify(args: &Args, events: &mut Events) -> Result<()> {
    let case = args
        .case
        .as_deref()
        .ok_or("exact footprint --case required")?;
    let plan = plan(case)?;
    let source = args
        .source
        .as_ref()
        .ok_or("original immutable native --source-copy required")?;
    let body = fs::read_to_string(
        args.history_file
            .as_ref()
            .ok_or("exact footprint --history-file required")?,
    )?;
    let ack = parse_acknowledgements(&body)?;
    let manifest = StoreManifest::decode(&fs::read(&args.manifest)?)?;
    if ack.case != case
        || manifest.profile != StoreProfile::Disposable
        || ack.branch.to_bytes() != manifest.branch
        || ack.stack.to_bytes() != manifest.stack
        || ack.initial.to_bytes() != manifest.root
    {
        return Err("footprint original case/manifest/Init acknowledgement differs".into());
    }
    let sealed = args
        .sealed
        .as_ref()
        .ok_or("normalized closed measured --sealed Store required")?;
    for suffix in ["-wal", "-shm", "-journal"] {
        if std::path::PathBuf::from(format!("{}{suffix}", sealed.display())).exists() {
            return Err("footprint normalized source has sidecars".into());
        }
    }
    let before = file_identity(sealed)?;
    let begun = Instant::now();
    let typed = events.directory.join("footprint-typed.sqlite");
    if typed.exists() {
        return Err("fresh footprint typed proof copy required".into());
    }
    fs::copy(sealed, &typed)?;
    if file_identity(&typed)? != before {
        return Err("footprint independent typed copy differs".into());
    }
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(&typed).with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &manifest.binding,
        manifest.cursor_key,
    )?;
    let catalog = handles.history.catalog_id();
    let incarnation = handles.history.incarnation();
    if catalog != CatalogId::derive(&manifest.binding)?
        || handles.profile().persistence != SqlitePersistenceProfile::Disposable
        || handles.profile().journal_mode.to_ascii_lowercase() != "wal"
        || handles.profile().synchronous != 0
    {
        return Err("footprint actual public provider/catalog/profile differs".into());
    }
    let stack = handles
        .history
        .layer_stack(ack.stack)?
        .ok_or("footprint original stack absent")?;
    let snapshot = handles
        .history
        .branch_snapshot(ack.branch)?
        .ok_or("footprint original Branch absent")?;
    let layer = handles
        .history
        .layer(ack.base)?
        .ok_or("footprint genesis Layer absent")?;
    let commit = handles
        .history
        .commit(ack.commit)?
        .ok_or("footprint actual CreatedCommit absent")?;
    if snapshot.branch.stack != ack.stack
        || snapshot.branch.base_layer != ack.base
        || snapshot.base_root != ack.initial
        || snapshot.branch.head_commit != Some(ack.commit)
        || snapshot.head_root != Some(ack.final_root)
        || snapshot.effective_root != ack.final_root
        || snapshot.profile != layerfs_content::filesystem::profile_id()
        || stack.profile != snapshot.profile
        || stack.scope != snapshot.scope
        || stack.head_layer != ack.base
        || layer.stack != ack.stack
        || layer.root != ack.initial
        || layer.parent.is_some()
        || layer.source_branch.is_some()
        || layer.source_commit.is_some()
        || (
            commit.id,
            commit.root,
            commit.parent,
            commit.base_layer,
            commit.stack,
        ) != (ack.commit, ack.final_root, None, ack.base, ack.stack)
    {
        return Err("footprint actual exact root/Branch/Commit/genesis tuple differs".into());
    }
    let page = Page {
        limit: 128,
        cursor: None,
    };
    let stacks = handles.history.layer_stacks(&page)?;
    let branches = handles.history.branches(ack.stack, &page)?;
    let layers = handles.history.layer_history(&LayerHistoryRequest {
        stack: ack.stack,
        start: Some(ack.base),
        cursor: None,
        limit: 128,
    })?;
    let commits = handles.history.commit_history(&CommitHistoryRequest {
        branch: ack.branch,
        start: Some(ack.commit),
        cursor: None,
        limit: 128,
    })?;
    if stacks.records != [stack]
        || stacks.continuation.is_some()
        || branches.records != [snapshot.branch.clone()]
        || branches.continuation.is_some()
        || layers.records != [layer]
        || layers.continuation.is_some()
        || commits.records != [commit]
        || commits.continuation.is_some()
    {
        return Err("footprint complete public topology/EOF differs; global SQL census remains separately mandatory".into());
    }
    let storage = Storage::new(handles.storage.clone())?;
    let reader = storage.reader()?;
    let paths = initial_census(&reader, ack.initial, &plan)?;
    let wanted = expected_boundary(source, &plan)?;
    let mut tree = FilesystemRead::new(&reader, FilesystemRootId(ack.final_root))?;
    let inode = tree.resolve(&LogicalPath::new(&plan.edit_path)?)?.value;
    let metadata = read_portable(
        &reader,
        inode.metadata_root,
        inode.kind,
        &mut AttributeReadWork::default(),
    )?;
    if inode.kind != InodeKind::RegularFile
        || inode.namespace_ref_count != 1
        || metadata.mode != reference::NAMESPACE_FILE_MODE
        || metadata.mtime_seconds != reference::NAMESPACE_MTIME_SECONDS
        || metadata.mtime_nanoseconds != 0
    {
        return Err("footprint final selected-file kind/metadata differs".into());
    }
    let actual = Timing::disabled("footprint.final.boundary", |timer| -> Result<Vec<u8>> {
        let view = FileView::open(&reader, inode.content_root, timer.child("open"))?;
        if view.logical_len() != plan.edit_size {
            return Err("footprint final selected-file size differs".into());
        }
        let mut bytes = Vec::with_capacity(wanted.len());
        view.read_range(
            &reader,
            plan.boundary_start..plan.boundary_end,
            &mut bytes,
            timer,
        )?;
        Ok(bytes)
    })
    .0?;
    if actual != wanted {
        return Err("footprint exact original clipped edit bytes differ".into());
    }
    drop(tree);
    drop(reader);
    drop(storage);
    handles.seal()?;
    let provider = sealed_provider_identity(sealed, &typed, &before)?;
    let projection = census_transcript(&ack);
    let projection_path = events.directory.join("footprint-census.tsv");
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&projection_path)?
        .write_all(projection.as_bytes())?;
    events.numeric_fields("store_footprint_verified",Some(events.span(begun)),"complete initial names/kinds/metadata/length/inode census; exact final reachable Commit/Branch/root and original clipped selected-file byte proof; fresh FUSE and global SQL census separately mandatory",
        &[("status","PASS".into()),("case",case.into()),("initial_root",crate::hex(ack.initial.as_bytes())),("final_root",crate::hex(ack.final_root.as_bytes())),("selected_path",plan.edit_path.clone()),
          ("stack_id",crate::hex(ack.stack.as_slice())),("branch_id",crate::hex(ack.branch.as_slice())),("base_layer_id",crate::hex(ack.base.as_slice())),("final_head_commit_id",crate::hex(ack.commit.as_slice())),("final_head_root",crate::hex(ack.final_root.as_bytes())),
          ("acknowledged_transcript_sha256",reference::sdk_edit_common::sha256_hex(projection.as_bytes())),("census_transcript_path",projection_path.display().to_string()),("original_acknowledged_transcript_sha256",reference::sdk_edit_common::sha256_hex(body.as_bytes())),("acknowledged_transcript_derivation","canonical two-row five-column projection of validated four-line Init/CreatedCommit ACKs; original-footprint-initial/original-footprint-final-boundary are scope labels".into()),
          ("boundary_sha256",reference::sdk_edit_common::sha256_hex(&actual)),("global_profile","Disposable/WAL/OFF".into()),("provider_validation","current-public-schema-source-binding-validated".into()),("catalog_id",crate::hex(catalog.as_slice())),("binding_sha256",reference::sdk_edit_common::sha256_hex(&manifest.binding)),
          ("provider_store_sha256",before.0.clone()),("provider_store_after_sha256",provider.typed_after.0),("provider_store_path",typed.display().to_string()),("provider_store_source_path",sealed.display().to_string()),("provider_store_copy_scope","independent exact normalized input copy; actual typed provider observed after Handles.seal".into()),
          ("original_store_sha256",before.0),("original_store_after_sha256",provider.original_after.0),("global_commit_census","REQUIRED_SEPARATE_UNFILTERED_CLOSED_SQL".into()),
          ("omissions","initial unselected payload equality and full final namespace/payload equality are not claimed; typed helper does not infer FUSE/Gone/Stop or retired spool/candidate counters".into())],
        &[("initial_paths",paths),("initial_files",plan.files.len() as u64),("initial_logical_bytes",plan.logical_bytes),("boundary_start",plan.boundary_start),("boundary_end",plan.boundary_end),("file_size",plan.edit_size),("verified_bytes",actual.len() as u64),
          ("catalog_incarnation",incarnation),("provider_store_size",before.1),("provider_store_after_size",provider.typed_after.1),("provider_store_unchanged",u64::from(provider.typed_unchanged)),("original_store_size",before.1),("original_store_after_size",provider.original_after.1),("original_store_unchanged",1)])?;
    Ok(())
}

//! Offline independent current-format graph and complete semantic tree proof.
#[allow(dead_code)]
#[path = "../../engine/recipes/boundary_metadata.rs"]
mod boundary_metadata;
#[path = "namespace_walk.rs"]
mod namespace_walk;
use crate::{args::Args, events::Events, project::namespace::reference, Result};
use layerfs_bridge::provision::StoreManifest;
use layerfs_content::object::{AuthenticatedObjects, ObjectId};
use layerfs_content::{
    file::{mapping, FileContent, FileView},
    filesystem::{
        attributes::read::{read_portable, AttributeReadWork},
        FilesystemRead, FilesystemRootId, LogicalPath,
    },
    inode_leaf::InodeKind,
};
use layerfs_history::{BranchId, CatalogId, CommitId, HistoryCatalog, LayerStackId};
use layerfs_persistence::{Handles, PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::{port::PackPersistence, Storage};
use layerfs_telemetry::timer::Timing;
use reference::workspace_common::{Content, Entry, EntryKind};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::Path,
    time::Instant,
};

pub fn verify(args: &Args, events: &mut Events) -> Result<()> {
    let case = args.case.as_deref().ok_or("--case required")?;
    if reference::workspace_registry::resolve(case)
        .is_ok_and(|selected| selected.family == "dedup_workspace_reuse")
    {
        if args.mode == "verify-membership" {
            return Err(
                "workspace reuse requires its full initial/final byte and storage proof".into(),
            );
        }
        return verify_dedup_store(args, events, DedupProof::ReuseFinal);
    }
    let entries = match reference::workspace_registry::resolve(case) {
        Ok(selected) if selected.kind == "git-tool" => git_hybrid_entries(
            case,
            args.source
                .as_deref()
                .ok_or("Git proof requires exact precommit --source-copy custody manifest")?,
        )?,
        _ => {
            if args.source.is_some() {
                return Err(
                    "precommit custody is only accepted by frozen Git workflow proof".into(),
                );
            }
            crate::edit_model::entries(case, 1)?
        }
    };
    let manifest = StoreManifest::decode(&fs::read(&args.manifest)?)?;
    let config = PersistenceConfig::sqlite(args.sealed.as_ref().ok_or("--sealed required")?)
        .with_sqlite_profile(SqlitePersistenceProfile::Disposable);
    let begun = Instant::now();
    let handles = Handles::open_writable(config, &manifest.binding, manifest.cursor_key)?;
    let snapshot = handles
        .history
        .branch_snapshot(BranchId::from_bytes(manifest.branch)?)?
        .ok_or("persisted Branch missing")?;
    let storage = Storage::new(handles.storage.clone())?;
    let reader = storage.reader()?;
    let (paths, verified_bytes, _) = verify_entries(
        &reader,
        snapshot.effective_root,
        &entries,
        args.mode == "verify-membership",
    )?;
    if args.mode != "verify-membership" {
        if let Some(scenario) = crate::edit_model::scenario(case) {
            crate::edit_oracle::verify_edit(
                &reader,
                layerfs_content::object::ObjectId::from_bytes(&manifest.root)?,
                snapshot.effective_root,
                &scenario,
            )?;
        }
    }
    let root = crate::hex(&snapshot.effective_root.to_bytes());
    drop(reader);
    drop(storage);
    handles.seal()?;
    events.numeric_fields("workspace_verified", Some(events.span(begun)), "independent current typed/authenticated reads; complete names/kinds/metadata/link classes and inode-table membership; membership-only mode reuses prior byte proof, full mode checks every payload byte and applicable original edit identity/retention; no retired format substituted", &[("status", "PASS".into()), ("root", root)], &[("paths", paths), ("verified_bytes", verified_bytes), ("membership_only", u64::from(args.mode == "verify-membership"))])?;
    Ok(())
}

/// Fresh import's public Store half; the controller separately proves native FUSE reads.
pub fn verify_import(args: &Args, events: &mut Events) -> std::result::Result<(), String> {
    verify_dedup_store(args, events, DedupProof::Import).map_err(|error| error.to_string())
}

/// Original outside-operation pristine payload attribution, on a separate typed copy.
pub fn verify_reuse_initial(args: &Args, events: &mut Events) -> std::result::Result<(), String> {
    verify_dedup_store(args, events, DedupProof::ReuseInitial).map_err(|error| error.to_string())
}

#[derive(Clone, Copy)]
enum DedupProof {
    Import,
    ReuseInitial,
    ReuseFinal,
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub struct DedupSpan {
    pub payload: ObjectId,
    pub source: u64,
    pub len: u64,
    pub payload_len: u64,
}

#[derive(Clone, Debug)]
pub struct DedupFile {
    pub root: ObjectId,
    pub spans: Vec<DedupSpan>,
}

struct OriginalBytes<'a> {
    content: &'a Content,
    offset: u64,
}
impl Read for OriginalBytes<'_> {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        let read = self
            .content
            .read_at(self.offset, buffer)
            .map_err(|error| std::io::Error::other(error.to_string()))?;
        self.offset += read as u64;
        Ok(read)
    }
}

fn dedup_case(id: &str) -> Result<reference::workspace_common::Case> {
    let selected = reference::workspace_registry::resolve(id)?;
    if !matches!(
        selected.family,
        "dedup_cross_file" | "dedup_cdc_locality" | "dedup_workspace_reuse"
    ) {
        return Err("exact original dedup import/reuse case required".into());
    }
    Ok(selected)
}

/// Decode every current span, validating public grammar and authenticated payload lengths.
pub fn dedup_spans(reader: &dyn AuthenticatedObjects, root: ObjectId) -> Result<Vec<DedupSpan>> {
    let view = Timing::disabled("independent.dedup.mapping", |timer| {
        FileView::open(reader, root, timer.child("open"))
    })
    .0?;
    verify_mapping(reader, &view)?;
    if let Some(bytes) = view.whole_file_bytes()? {
        return Ok(vec![DedupSpan {
            payload: root,
            source: 0,
            len: bytes.len() as u64,
            payload_len: bytes.len() as u64,
        }]);
    }
    let state = view
        .file_state()?
        .ok_or("dedup current file state missing")?;
    let mut pending = vec![(state.mapping_root, true)];
    let mut spans = Vec::new();
    while let Some((id, root_page)) = pending.pop() {
        match mapping::decode_node_with_context(&reader.read_canonical(id)?, root_page)? {
            mapping::ExtentNode::Leaf { extents, .. } => {
                for extent in extents {
                    let payload = reader.read_canonical(extent.payload_object_id())?;
                    let value = layerfs_content::object::decode_bytes_object(&payload)?;
                    let bytes = mapping::decode_chunk_payload(value)?;
                    if u64::from(extent.source_offset()) + u64::from(extent.logical_length())
                        > bytes.len() as u64
                    {
                        return Err("dedup current payload slice exceeds actual raw payload".into());
                    }
                    spans.push(DedupSpan {
                        payload: extent.payload_object_id(),
                        source: extent.source_offset().into(),
                        len: extent.logical_length().into(),
                        payload_len: bytes.len() as u64,
                    });
                }
            }
            mapping::ExtentNode::Branch { children, .. } => {
                pending.extend(
                    children
                        .into_iter()
                        .rev()
                        .map(|child| (child.child_object_id, false)),
                );
            }
        }
    }
    Ok(spans)
}

/// Original partitions independently derive current canonical IDs, never retired extent IDs.
pub fn verify_dedup_files(
    reader: &dyn AuthenticatedObjects,
    id: &str,
    step: usize,
    files: &BTreeMap<String, FileIdentity>,
) -> Result<BTreeMap<String, DedupFile>> {
    let selected = dedup_case(id)?;
    if step > usize::from(selected.family == "dedup_workspace_reuse") {
        return Err("original dedup state outside initial/final schedule".into());
    }
    let expected = crate::dedup_input::expected(id, step)?;
    crate::dedup_input::validate_contract(id, step, &expected)?;
    let entries = crate::edit_model::entries(id, step)?;
    let mut actual = BTreeMap::new();
    for entry in entries {
        let EntryKind::File(content) = entry.kind else {
            continue;
        };
        let identity = files
            .get(&entry.path)
            .ok_or("dedup exact file identity missing")?;
        let spans = dedup_spans(reader, identity.content_root)?;
        let mut adapted = Vec::new();
        let mut partitions = Vec::new();
        let mut position = 0_u64;
        crate::dedup_input::scan(
            OriginalBytes {
                content: &content,
                offset: 0,
            },
            |bytes| {
                let payload = mapping::encode_chunk_object(bytes)?;
                adapted.push(DedupSpan {
                    payload: ObjectId::for_bytes(&payload),
                    source: 0,
                    len: bytes.len() as u64,
                    payload_len: bytes.len() as u64,
                });
                partitions.push((
                    position,
                    bytes.len() as u64,
                    reference::sdk_edit_common::sha256_hex(bytes),
                ));
                position += bytes.len() as u64;
                Ok(())
            },
        )?;
        let chunks = expected
            .get(&entry.path)
            .ok_or("independent dedup input transcript missing")?;
        if partitions
            != chunks
                .iter()
                .map(|chunk| (chunk.logical_start, chunk.len, chunk.raw_sha256.clone()))
                .collect::<Vec<_>>()
            || position != content.len()
        {
            return Err("independent dedup source partition transcript differs".into());
        }
        if content.len() > 0 && content.len() < 131_072 {
            // Original CDC shape still qualifies the input; current storage uses one WholeFile.
            let mut bytes = Vec::new();
            content.write_to(&mut bytes)?;
            let canonical = layerfs_content::file::encode_whole_file_payload(&bytes)?;
            adapted = vec![DedupSpan {
                payload: ObjectId::for_bytes(&canonical),
                source: 0,
                len: content.len(),
                payload_len: content.len(),
            }];
        }
        if spans != adapted {
            return Err(format!(
                "dedup current ordered payload spans differ from independent source: {}",
                entry.path
            )
            .into());
        }
        actual.insert(
            entry.path,
            DedupFile {
                root: identity.content_root,
                spans,
            },
        );
    }
    if actual.len() != files.len() || actual.len() != expected.len() {
        return Err("dedup exact complete file transcript membership differs".into());
    }
    require_dedup_storage(id, step, &actual)?;
    Ok(actual)
}

fn payload_union<'a>(
    files: impl Iterator<Item = &'a DedupFile>,
) -> Result<BTreeMap<ObjectId, u64>> {
    let mut union = BTreeMap::new();
    for file in files {
        for span in &file.spans {
            if span.source != 0 || span.len != span.payload_len || span.len == 0 {
                return Err("original fresh dedup construction has partial payload span".into());
            }
            if union
                .insert(span.payload, span.payload_len)
                .is_some_and(|old| old != span.payload_len)
            {
                return Err("dedup payload ID has inconsistent actual lengths".into());
            }
        }
    }
    Ok(union)
}

/// Profile-specific semantic obligations; storage ratios are diagnostic, never thresholds.
pub fn require_dedup_storage(
    id: &str,
    step: usize,
    files: &BTreeMap<String, DedupFile>,
) -> Result<()> {
    let case = dedup_case(id)?;
    if step > usize::from(case.family == "dedup_workspace_reuse") {
        return Err("dedup storage state outside original initial/final schedule".into());
    }
    let expected_names = crate::edit_model::entries(id, step)?
        .into_iter()
        .filter(|entry| matches!(entry.kind, EntryKind::File(_)))
        .map(|entry| entry.path)
        .collect::<BTreeSet<_>>();
    if files.keys().cloned().collect::<BTreeSet<_>>() != expected_names {
        return Err("dedup storage exact original file membership differs".into());
    }
    payload_union(files.values())?;
    if case.family == "dedup_cross_file" {
        let anchor = files
            .get("files/f0000.dat")
            .ok_or("cross-file anchor missing")?;
        let mut bases = BTreeMap::new();
        for i in 0..case.tier {
            let file = files
                .get(&format!("files/f{i:04}.dat"))
                .ok_or("cross-file original member missing")?;
            let ordinal = match case.kind {
                "anchor" | "identical" => 0,
                "unique" => i,
                "mixed" => 3 * (i / 4) + (i % 4).saturating_sub(1),
                _ => return Err("cross-file original profile required".into()),
            };
            if case.kind == "identical" && (file.spans != anchor.spans || file.root != anchor.root)
            {
                return Err("identical cross-file mappings/content roots differ".into());
            }
            if bases
                .insert(ordinal, file)
                .is_some_and(|old: &DedupFile| old.spans != file.spans)
            {
                return Err("mixed cross-file original exact pair differs".into());
            }
        }
        let occurrences = bases.values().map(|file| file.spans.len()).sum::<usize>();
        if payload_union(bases.values().copied())?.len() != occurrences {
            return Err("unintended duplicate chunk in distinct cross-file bases".into());
        }
    } else if case.family == "dedup_workspace_reuse" {
        let n = reference::dedup_workspace_reuse::base_file_count(&case)?;
        let base = files
            .iter()
            .filter(|(path, _)| path.starts_with("base/"))
            .map(|(_, file)| file)
            .collect::<Vec<_>>();
        if base.len() != n
            || payload_union(base.iter().copied())?.len()
                != base.iter().map(|file| file.spans.len()).sum::<usize>()
        {
            return Err("workspace reuse base count/internal payload uniqueness differs".into());
        }
        let added = files
            .iter()
            .filter(|(path, _)| path.starts_with("added/"))
            .map(|(_, file)| file)
            .collect::<Vec<_>>();
        if step > 1 || added.len() != if step == 0 { 0 } else { case.tier } {
            return Err("workspace reuse addition cardinality differs".into());
        }
        let p = payload_union(base.iter().copied())?;
        let a = payload_union(added.iter().copied())?;
        if case.kind == "unique"
            && (a.keys().any(|id| p.contains_key(id))
                || a.len() != added.iter().map(|file| file.spans.len()).sum::<usize>())
        {
            return Err("unique workspace additions intersect base or duplicate internally".into());
        }
        if case.kind == "local"
            && added
                .iter()
                .map(|file| &file.spans)
                .collect::<BTreeSet<_>>()
                .len()
                != added.len()
        {
            return Err("local workspace addition complete mappings are not distinct".into());
        }
        if case.kind == "exact" {
            if a.keys().any(|id| !p.contains_key(id)) {
                return Err("exact additions inserted new regular payload".into());
            }
            for i in 0..added.len() {
                let file = &files[&format!("added/a{i:04}.dat")];
                let before = &files[&format!("base/b{:04}.dat", i % n)];
                if file.spans != before.spans || file.root != before.root {
                    return Err(
                        "exact addition did not reuse selected base mapping/content root".into(),
                    );
                }
            }
        }
    }
    Ok(())
}

fn verify_dedup_store(args: &Args, events: &mut Events, proof_mode: DedupProof) -> Result<()> {
    let begun = Instant::now();
    let id = args.case.as_deref().ok_or("exact dedup --case required")?;
    let case = dedup_case(id)?;
    if matches!(proof_mode, DedupProof::Import)
        != matches!(case.family, "dedup_cross_file" | "dedup_cdc_locality")
        || args.source.is_some()
        || (args.history_file.is_some() && !matches!(proof_mode, DedupProof::ReuseFinal))
        || args.history_step.is_some()
    {
        return Err("dedup import/reuse mode or independent source scope differs".into());
    }
    let manifest = StoreManifest::decode(&fs::read(&args.manifest)?)?;
    if manifest.profile != layerfs_bridge::provision::StoreProfile::Disposable {
        return Err("dedup requires explicit Disposable manifest".into());
    }
    let sealed = args
        .sealed
        .as_ref()
        .ok_or("dedup separate closed --sealed copy required")?;
    let before = file_identity(sealed)?;
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(sealed).with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &manifest.binding,
        manifest.cursor_key,
    )?;
    let catalog = handles.history.catalog_id();
    let incarnation = handles.history.incarnation();
    let branch = BranchId::from_bytes(manifest.branch)?;
    let stack = LayerStackId::from_bytes(manifest.stack)?;
    let initial = ObjectId::from_bytes(&manifest.root)?;
    let snapshot = handles
        .history
        .branch_snapshot(branch)?
        .ok_or("dedup persisted original Branch missing")?;
    let base = handles
        .history
        .layer(snapshot.branch.base_layer)?
        .ok_or("dedup initial Layer missing")?;
    let stack_record = handles
        .history
        .layer_stack(stack)?
        .ok_or("dedup original LayerStack missing")?;
    if catalog != CatalogId::derive(&manifest.binding)?
        || snapshot.base_root != initial
        || base.root != initial
        || snapshot.branch.stack != stack
        || base.stack != stack
        || stack_record.scope != snapshot.scope
        || stack_record.profile != snapshot.profile
        || handles.profile().persistence != SqlitePersistenceProfile::Disposable
        || !handles.profile().journal_mode.eq_ignore_ascii_case("wal")
        || handles.profile().synchronous != 0
    {
        return Err(
            "dedup public provider/initial root/Branch/stack/profile binding differs".into(),
        );
    }
    let step = usize::from(matches!(proof_mode, DedupProof::ReuseFinal));
    let mut acknowledgement_hash = None;
    if step == 0 && (snapshot.branch.head_commit.is_some() || snapshot.effective_root != initial) {
        return Err("dedup pristine initial Branch has a Commit or moved root".into());
    }
    if step == 1 {
        let head = snapshot
            .branch
            .head_commit
            .ok_or("workspace reuse requires its one actual Commit")?;
        let commit = handles
            .history
            .commit(head)?
            .ok_or("workspace reuse actual Commit missing")?;
        if commit.parent.is_some()
            || head
                != CommitId::derive(
                    commit.root,
                    commit.parent,
                    commit.base_layer,
                    commit.second_parent,
                    &commit.meta,
                )
            || commit.stack != stack
            || commit.root != snapshot.effective_root
            || commit.base_layer != base.id
        {
            return Err("workspace reuse actual first Commit/root/base binding differs".into());
        }
        let page = handles
            .history
            .commit_history(&layerfs_history::CommitHistoryRequest {
                branch,
                start: Some(head),
                cursor: None,
                limit: 32,
            })?;
        if page.records != vec![commit.clone()] || page.continuation.is_some() {
            return Err(
                "workspace reuse actual public single-Commit history did not reach exact EOF"
                    .into(),
            );
        }
        acknowledgement_hash = Some(reuse_acknowledgement(args, initial, &commit)?);
    }
    let storage = Storage::new(handles.storage.clone())?;
    let reader = storage.reader()?;
    let mut paths = 0;
    let mut bytes = 0;
    let mut initial_files = None;
    let mut final_map = BTreeMap::new();
    for state in 0..=step {
        let root = if state == 0 {
            initial
        } else {
            snapshot.effective_root
        };
        if FilesystemRead::new(&reader, FilesystemRootId(root))?
            .root()
            .scope()
            .object()
            != snapshot.scope
        {
            return Err("dedup filesystem allocation scope differs from public stack".into());
        }
        let tree = verify_tree(
            &reader,
            root,
            &crate::edit_model::entries(id, state)?,
            false,
            None,
            true,
        )?;
        paths += tree.paths;
        bytes += tree.bytes;
        final_map = verify_dedup_files(&reader, id, state, &tree.files)?;
        if state == 0 {
            initial_files = Some(tree.files);
        } else {
            for (path, identity) in initial_files
                .as_ref()
                .ok_or("reuse pristine identities missing")?
            {
                if tree.files.get(path) != Some(identity) {
                    return Err("reuse changed pristine base file inode/content identity".into());
                }
            }
        }
    }
    let diagnostics =
        crate::dedup_input::validate_contract(id, step, &crate::dedup_input::expected(id, step)?)?;
    let union = payload_union(final_map.values())?;
    let positive_whole = final_map
        .values()
        .filter(|file| file.spans.len() == 1 && file.spans[0].len < 131_072)
        .count();
    let empty = final_map
        .values()
        .filter(|file| file.spans.is_empty())
        .count();
    if case.kind == "boundaries" && (positive_whole, empty) != (54, 6) {
        return Err(
            "CDC boundaries require54 current WholeFile positives and6 canonical empties".into(),
        );
    }
    let diagnostic_fields = diagnostics
        .iter()
        .map(|(key, value)| (key.as_str(), value.clone()))
        .collect::<Vec<_>>();
    events.fields("dedup_input_diagnostics", None, "independent original CDC partition/sharing observations; diagnostics are not acceptance ratios or legacy encoded object IDs", &diagnostic_fields)?;
    let final_head = snapshot
        .branch
        .head_commit
        .map(|head| crate::hex(head.as_slice()))
        .unwrap_or_else(|| "-".into());
    drop(reader);
    drop(storage);
    handles.seal()?;
    let after = file_identity(sealed)?;
    let store_allocated = std::os::unix::fs::MetadataExt::blocks(&fs::metadata(sealed)?)
        .checked_mul(512)
        .ok_or("dedup Store allocation overflow")?;
    let event = match proof_mode {
        DedupProof::Import => "project_verified",
        DedupProof::ReuseInitial => "reuse_initial_verified",
        DedupProof::ReuseFinal => "workspace_verified",
    };
    let mut fields = vec![
        ("status", "PASS".into()),
        ("case", id.into()),
        ("root", crate::hex(snapshot.effective_root.as_bytes())),
        ("initial_root", crate::hex(initial.as_bytes())),
        (
            "final_head_root",
            crate::hex(snapshot.effective_root.as_bytes()),
        ),
        ("final_head_commit_id", final_head),
        (
            "provider_validation",
            "current-public-schema-source-binding-validated".into(),
        ),
        ("catalog_id", crate::hex(catalog.as_slice())),
        (
            "binding_sha256",
            reference::sdk_edit_common::sha256_hex(&manifest.binding),
        ),
        ("stack_id", crate::hex(stack.as_slice())),
        ("branch_id", crate::hex(branch.as_slice())),
        ("base_layer_id", crate::hex(base.id.as_slice())),
        ("provider_store_sha256", before.0.clone()),
        ("provider_store_after_sha256", after.0.clone()),
    ];
    if let Some(hash) = acknowledgement_hash {
        fields.push(("acknowledged_transcript_sha256", hash));
    }
    events.numeric_fields(event, Some(events.span(begun)), "complete original independent bytes/metadata/inode census; current public authenticated payload grammar and explicitly adapted original CDC partitions/identity reuse. Final reuse binds the original actual initial/ACK transcript and public History EOF. Fresh Init provenance, FUSE/native Fork/mount/End/Gone/Stop and global SQL Commit census are separately bound controller obligations, not inferred here",
        &fields,
        &[("paths",paths),("verified_paths",paths),("verified_bytes",bytes),("roots",(step+1) as u64),("commits",step as u64),("verified_files",final_map.len() as u64),("distinct_payload_count",union.len() as u64),("distinct_payload_bytes",union.values().sum()),("positive_whole_files",positive_whole as u64),("empty_files",empty as u64),("catalog_incarnation",incarnation),("store_logical_bytes",after.1),("store_allocated_bytes",store_allocated),("provider_store_size",before.1),("provider_store_after_size",after.1),("provider_store_unchanged",u64::from(before==after))])?;
    Ok(())
}

fn reuse_acknowledgement(
    args: &Args,
    initial: ObjectId,
    commit: &layerfs_history::CommitRecord,
) -> Result<String> {
    let body = fs::read_to_string(
        args.history_file
            .as_ref()
            .ok_or("reuse final requires actual two-row --history-file acknowledgement")?,
    )?;
    let rows = body.lines().collect::<Vec<_>>();
    if rows.len() != 2 || !body.ends_with('\n') || body.contains(['\r', '\0']) {
        return Err("reuse acknowledgement requires canonical two-row LF transcript".into());
    }
    for (step, row) in rows.into_iter().enumerate() {
        let fields = row.split('\t').collect::<Vec<_>>();
        let root = if step == 0 { initial } else { commit.root };
        let id = if step == 0 {
            "-".into()
        } else {
            crate::hex(commit.id.as_slice())
        };
        if fields.len() != 5
            || fields[0] != step.to_string()
            || fields[1] != id
            || fields[2] != "-"
            || fields[3] != crate::hex(root.as_bytes())
            || fields[4] == "-"
        {
            return Err("reuse actual initial/Commit/parent/root acknowledgement differs".into());
        }
        let expected = reference::workspace_common::manifest(&crate::edit_model::entries(
            args.case.as_deref().ok_or("reuse exact case required")?,
            step,
        )?)?;
        if fs::read_to_string(fields[4])? != expected {
            return Err(
                "reuse acknowledged selected manifest differs from independent original state"
                    .into(),
            );
        }
    }
    Ok(reference::sdk_edit_common::sha256_hex(body.as_bytes()))
}

fn git_hybrid_entries(case: &str, custody: &Path) -> Result<Vec<Entry>> {
    let selected = reference::workspace_registry::resolve(case)?;
    if selected.kind != "git-tool" || selected.family != "git_tool_workflow" {
        return Err("frozen Git workflow case required for repository custody".into());
    }
    let body = fs::read_to_string(custody)?;
    let repository = reference::workspace_common::decode_manifest(&body)?;
    if reference::workspace_common::manifest(&repository)? != body {
        return Err("Git precommit manifest must be canonical complete custody".into());
    }
    let mut entries = crate::edit_model::entries(case, 1)?;
    let independent_root = entries
        .iter()
        .find(|entry| entry.path == ".")
        .ok_or("independent Git root missing")?
        .clone();
    let mut has_repository = false;
    let mut has_index = false;
    let mut logical_bytes = reference::workspace_common::validate_entries(&entries)?;
    for entry in repository {
        if entry.path == "." {
            if !matches!(entry.kind, EntryKind::Directory)
                || entry.mode != independent_root.mode
                || entry.mtime_seconds != independent_root.mtime_seconds
                || entry.mtime_nanoseconds != independent_root.mtime_nanoseconds
            {
                return Err("Git custody root differs from independent source root".into());
            }
            continue;
        }
        if entry.path != ".git" && !entry.path.starts_with(".git/") {
            return Err("Git custody may not replace independent working source".into());
        }
        match &entry.kind {
            EntryKind::Directory => has_repository |= entry.path == ".git",
            EntryKind::File(Content::Digest { len, sha256 }) => {
                if sha256.len() != 64
                    || !sha256
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
                {
                    return Err("Git custody requires complete SHA-256 bytes".into());
                }
                has_index |= entry.path == ".git/index";
                logical_bytes = logical_bytes
                    .checked_add(*len)
                    .ok_or("Git complete byte overflow")?;
            }
            _ => return Err("Git custody requires original regular files/directories".into()),
        }
        entries.push(entry);
    }
    if !has_repository || !has_index || logical_bytes > 256 * 1024 * 1024 {
        return Err("Git complete repository/index/cap differs".into());
    }
    reference::workspace_common::validate_entries(&entries)?;
    Ok(entries)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FileIdentity {
    pub serial: u64,
    pub content_root: ObjectId,
    pub references: u64,
}

pub struct VerifiedTree {
    pub paths: u64,
    pub bytes: u64,
    pub file_roots: BTreeSet<ObjectId>,
    pub files: BTreeMap<String, FileIdentity>,
}

fn verify_entries(
    reader: &dyn AuthenticatedObjects,
    root: ObjectId,
    entries: &[Entry],
    membership_only: bool,
) -> Result<(u64, u64, BTreeSet<ObjectId>)> {
    let proof = verify_tree(reader, root, entries, membership_only, None, false)?;
    Ok((proof.paths, proof.bytes, proof.file_roots))
}

/// Current public semantic proof with optional original M1 selective scope.
pub fn verify_tree(
    reader: &dyn AuthenticatedObjects,
    root: ObjectId,
    entries: &[Entry],
    membership_only: bool,
    m1: Option<&crate::edit_model::M1State>,
    mapping_profile: bool,
) -> Result<VerifiedTree> {
    let expected = entries
        .iter()
        .map(|entry| (entry.path.clone(), entry))
        .collect::<BTreeMap<_, _>>();
    let mut walk = namespace_walk::NamespaceWalk::new(reader, root)?;
    let mut seen = BTreeSet::new();
    let mut reachable_inodes = BTreeSet::new();
    let mut attributes = AttributeReadWork::default();
    let mut inode_classes = BTreeMap::new();
    let mut class_inodes = BTreeMap::new();
    let mut aliases = BTreeMap::<&str, u64>::new();
    for entry in entries {
        let class = match &entry.kind {
            EntryKind::File(_) => entry.path.as_str(),
            EntryKind::Hardlink(target) => target,
            _ => continue,
        };
        *aliases.entry(class).or_default() += 1;
    }
    let mut verified_bytes = 0;
    let mut file_roots = BTreeSet::new();
    let mut files = BTreeMap::new();
    let mut scratch = None;
    while let Some((path, resolved)) = walk.next()? {
        let _logical = LogicalPath::new(if path == "." { "" } else { &path })?;
        if !seen.insert(path.clone()) {
            return Err("duplicate persisted namespace path".into());
        }
        let entry = expected
            .get(&path)
            .ok_or("unexpected persisted namespace path")?;
        reachable_inodes.insert(resolved.serial);
        let inode = resolved.value;
        let metadata = read_portable(reader, inode.metadata_root, inode.kind, &mut attributes)?;
        let class = match &entry.kind {
            EntryKind::Hardlink(target) => target.as_str(),
            _ => path.as_str(),
        };
        let (mode, mtime) = if let Some(scope) = m1 {
            (
                scope
                    .directory_modes
                    .get(&path)
                    .or_else(|| scope.file_modes.get(class))
                    .copied(),
                scope.file_mtimes.get(class).copied(),
            )
        } else {
            (
                Some(entry.mode),
                Some((entry.mtime_seconds, entry.mtime_nanoseconds)),
            )
        };
        if mode.is_some_and(|mode| metadata.mode != mode)
            || mtime.is_some_and(|(seconds, nanos)| {
                metadata.mtime_seconds != seconds || metadata.mtime_nanoseconds != nanos
            })
        {
            return Err(format!("persisted portable metadata differs: {path}").into());
        }
        match &entry.kind {
            EntryKind::Directory => {
                if inode.kind != InodeKind::Directory {
                    return Err("persisted directory kind differs".into());
                }
                walk.queue_directory(path.clone(), resolved);
            }
            EntryKind::Symlink(target) => {
                if inode.kind != InodeKind::Symlink
                    || walk.tree.readlink_inode(resolved.serial)?.as_bytes() != target.as_bytes()
                {
                    return Err("persisted symlink kind/target differs".into());
                }
            }
            EntryKind::File(_) | EntryKind::Hardlink(_) => {
                file_roots.insert(inode.content_root);
                let (content, class) = match &entry.kind {
                    EntryKind::File(content) => (content, path.as_str()),
                    EntryKind::Hardlink(target) => match &expected[target].kind {
                        EntryKind::File(content) => (content, target.as_str()),
                        _ => return Err("frozen hardlink target kind".into()),
                    },
                    _ => unreachable!(),
                };
                if inode.kind != InodeKind::RegularFile
                    || inode.namespace_ref_count != aliases[class]
                {
                    return Err("persisted regular kind/link count differs".into());
                }
                if inode_classes
                    .insert(resolved.serial, class.to_owned())
                    .is_some_and(|old| old != class)
                    || class_inodes
                        .insert(class.to_owned(), resolved.serial)
                        .is_some_and(|old| old != resolved.serial)
                {
                    return Err("persisted alias classes differ".into());
                }
                files.insert(
                    path.clone(),
                    FileIdentity {
                        serial: resolved.serial,
                        content_root: inode.content_root,
                        references: inode.namespace_ref_count,
                    },
                );
                if membership_only {
                    continue;
                }
                let ranges = if let Some(scope) = m1 {
                    if matches!(content, Content::Digest { .. }) {
                        return Err(
                            "M1 proof requires independent source recipes, not custody digests"
                                .into(),
                        );
                    }
                    scope
                        .ranges
                        .get(&path)
                        .ok_or("M1 regular path lacks declared range scope")?
                        .clone()
                } else {
                    vec![(0, content.len())]
                };
                verified_bytes +=
                    Timing::disabled("independent.persisted.bytes", |timer| -> Result<u64> {
                        let view = FileView::open(reader, inode.content_root, timer.child("open"))?;
                        if view.logical_len() != content.len() {
                            return Err("persisted logical file length differs".into());
                        }
                        if mapping_profile {
                            verify_mapping(reader, &view)?;
                        }
                        let (wanted, observed) = scratch.get_or_insert_with(|| {
                            let wanted = vec![0; 1024 * 1024];
                            let observed = Vec::with_capacity(wanted.len());
                            (wanted, observed)
                        });
                        let mut hash = reference::Sha256::new();
                        let mut bytes = 0_u64;
                        for (start, length) in &ranges {
                            let end = start
                                .checked_add(*length)
                                .ok_or("persisted declared range overflow")?;
                            if end > content.len() {
                                return Err("persisted declared range exceeds logical file".into());
                            }
                            let mut offset = *start;
                            while offset < end {
                                let count = (end - offset).min(wanted.len() as u64) as usize;
                                observed.clear();
                                view.read_range(
                                    reader,
                                    offset..offset + count as u64,
                                    &mut *observed,
                                    timer,
                                )?;
                                if observed.len() != count {
                                    return Err("persisted read byte count differs".into());
                                }
                                match content {
                                    Content::Digest { .. } => hash.update(observed),
                                    _ => {
                                        if content.read_at(offset, &mut wanted[..count])? != count
                                            || observed.as_slice() != &wanted[..count]
                                        {
                                            return Err(format!(
                                                "persisted exact bytes differ: {path} at {offset}"
                                            )
                                            .into());
                                        }
                                    }
                                }
                                offset += count as u64;
                                bytes += count as u64;
                            }
                        }
                        if let Content::Digest { sha256, .. } = content {
                            if ranges != [(0, content.len())]
                                || crate::hex(&hash.finish()) != *sha256
                            {
                                return Err("persisted custody digest differs".into());
                            }
                        }
                        Ok(bytes)
                    })
                    .0?;
            }
        }
    }
    if seen.len() != expected.len() {
        return Err("persisted namespace path count differs".into());
    }
    crate::edit_oracle::require_complete_membership(reader, walk.tree.root(), &reachable_inodes)?;
    Ok(VerifiedTree {
        paths: seen.len() as u64,
        bytes: verified_bytes,
        file_roots,
        files,
    })
}

fn identity_bytes<const N: usize>(value: &str) -> Result<[u8; N]> {
    if value.len() != 2 * N
        || !value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("history identity must be canonical lowercase hex".into());
    }
    let mut bytes = [0; N];
    for (index, byte) in bytes.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&value[index * 2..index * 2 + 2], 16)?;
    }
    Ok(bytes)
}

/// Complete public mapping grammar, including the frozen boundary and empty form.
pub fn verify_mapping(reader: &dyn AuthenticatedObjects, view: &FileView) -> Result<()> {
    let state = match view.content() {
        FileContent::WholeFile { logical_len } => {
            if logical_len == 0 || logical_len >= 131_072 {
                return Err("current whole-file representation outside frozen boundary".into());
            }
            return Ok(());
        }
        FileContent::Chunked(state) => {
            if (state.logical_len > 0 && state.logical_len < 131_072)
                || state.profile_id != mapping::profile_id()
            {
                return Err(
                    "current chunked representation/profile outside frozen boundary".into(),
                );
            }
            state
        }
    };
    let mut pending = vec![(
        state.mapping_root,
        true,
        state.tree_level,
        state.logical_len,
        state.extent_count,
    )];
    let (mut total_bytes, mut total_extents) = (0_u64, 0_u64);
    while let Some((id, root_page, level, bytes, count)) = pending.pop() {
        let node = mapping::decode_node_with_context(&reader.read_canonical(id)?, root_page)?;
        if (node.level(), node.logical_len(), node.extent_count()) != (level, bytes, count) {
            return Err("current mapping parent/child totals differ".into());
        }
        match node {
            mapping::ExtentNode::Leaf { extents, .. } => {
                for extent in extents {
                    total_bytes = total_bytes
                        .checked_add(u64::from(extent.logical_length()))
                        .ok_or("current mapping byte total overflow")?;
                    total_extents = total_extents
                        .checked_add(1)
                        .ok_or("current mapping count overflow")?;
                }
            }
            mapping::ExtentNode::Branch { children, .. } => {
                let (mut previous_bytes, mut previous_count) = (0_u64, 0_u64);
                let mut next = Vec::with_capacity(children.len());
                for child in children {
                    next.push((
                        child.child_object_id,
                        false,
                        level
                            .checked_sub(1)
                            .ok_or("current mapping depth differs")?,
                        child
                            .cumulative_logical_end
                            .checked_sub(previous_bytes)
                            .ok_or("current mapping child byte summary differs")?,
                        child
                            .cumulative_extent_end
                            .checked_sub(previous_count)
                            .ok_or("current mapping child extent summary differs")?,
                    ));
                    previous_bytes = child.cumulative_logical_end;
                    previous_count = child.cumulative_extent_end;
                }
                pending.extend(next.into_iter().rev());
            }
        }
    }
    if (total_bytes, total_extents) != (state.logical_len, state.extent_count) {
        return Err("current complete mapping totals differ".into());
    }
    Ok(())
}

fn history_selection(case: &str) -> Result<(usize, BTreeSet<usize>)> {
    let (commits, steps) = if case == "small-file-delta-10x30-v1" {
        (30, (0..=30).collect())
    } else if case == "local-snapshot-create-25000-onebyte-v1" {
        (3, (0..=3).collect())
    } else if crate::edit_model::is_m1(case) {
        let plan = reference::v016_stages::mixed_case(case)?.ok_or("original M1 case required")?;
        (
            plan.k,
            if plan.exhaustive_verify_only() {
                (5..=plan.k).step_by(5).collect()
            } else {
                BTreeSet::from([plan.k])
            },
        )
    } else {
        let selected = reference::workspace_registry::resolve(case)?;
        match selected.family {
            "file_size_transition" => {
                let commits = reference::workspace_registry::steps(&selected);
                (commits, (0..=commits).collect())
            }
            "dedup_branch_history" => (
                selected.tier,
                reference::dedup_branch_history::verification_steps(&selected)
                    .into_iter()
                    .collect(),
            ),
            _ => return Err("complete original registered history case required".into()),
        }
    };
    Ok((commits, steps))
}

/// Case-specific parser guard; the public proof also checks original selections.
pub fn history_limit(case: &str) -> Result<usize> {
    Ok(history_selection(case)?.0)
}

fn file_identity(path: &Path) -> Result<(String, u64)> {
    let mut file = fs::File::open(path)?;
    let mut hash = reference::Sha256::new();
    let mut buffer = [0; 65_536];
    let mut length = 0_u64;
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
        length = length
            .checked_add(count as u64)
            .ok_or("provider byte length overflow")?;
    }
    Ok((crate::hex(&hash.finish()), length))
}

/// Canonical original helper observations; future cumulative domain keys allowed.
pub fn created_modes(case: &str, path: &Path) -> Result<BTreeMap<String, u32>> {
    let domain = crate::edit_model::m1_state(case, history_limit(case)?, None)?
        .required_created_directory_modes;
    let body = fs::read_to_string(path)?;
    if !body.is_empty() && !body.ends_with('\n') {
        return Err("M1 created-mode observations require canonical line endings".into());
    }
    let mut result = BTreeMap::new();
    for row in body.lines() {
        let fields = row.split('\t').collect::<Vec<_>>();
        if fields.len() != 2 || !domain.contains(fields[0]) {
            return Err("M1 created-mode path outside original cumulative domain".into());
        }
        let mode = u32::from_str_radix(fields[1], 8)?;
        if mode & !0o1777 != 0
            || format!("{mode:o}") != fields[1]
            || result.insert(fields[0].to_owned(), mode).is_some()
        {
            return Err("M1 created-mode duplicate/noncanonical/mode envelope differs".into());
        }
    }
    Ok(result)
}

pub fn verify_history(args: &Args, events: &mut Events) -> Result<()> {
    let case = args.case.as_deref().ok_or("--case required")?;
    let small = case == "small-file-delta-10x30-v1";
    let snapshot_case = case == "local-snapshot-create-25000-onebyte-v1";
    let legacy = small || snapshot_case;
    let m1 = crate::edit_model::is_m1(case);
    let alias = case == reference::file_size_transition::ALIAS_ROUNDTRIP;
    let (commits, original_selection) = history_selection(case)?;
    if args
        .history_step
        .is_some_and(|step| !original_selection.contains(&step))
    {
        return Err("selected history state outside original verification checkpoints".into());
    }
    let alias_custody = if alias {
        let body = fs::read_to_string(
            args.source
                .as_ref()
                .ok_or("alias proof requires measured --source-copy parent mtime custody")?,
        )?;
        Some((
            boundary_metadata::parse(case, &body)?,
            reference::sdk_edit_common::sha256_hex(body.as_bytes()),
        ))
    } else {
        None
    };
    let modes = if m1 {
        Some(created_modes(
            case,
            args.source
                .as_deref()
                .ok_or("M1 proof requires measured --source-copy created modes")?,
        )?)
    } else {
        if args.source.is_some() && !alias {
            return Err(
                "history source-copy observations are only accepted for original M1".into(),
            );
        }
        None
    };
    let body = fs::read_to_string(
        args.history_file
            .as_ref()
            .ok_or("--history-file required")?,
    )?;
    let rows = body.lines().collect::<Vec<_>>();
    if rows.len() != commits + 1 {
        return Err("original history requires initial and all declared roots".into());
    }
    let manifest = StoreManifest::decode(&fs::read(&args.manifest)?)?;
    if manifest.profile != layerfs_bridge::provision::StoreProfile::Disposable {
        return Err("history proof requires explicitly provisioned Disposable profile".into());
    }
    let sealed = args.sealed.as_ref().ok_or("--sealed required")?;
    let before = file_identity(sealed)?;
    let config =
        PersistenceConfig::sqlite(sealed).with_sqlite_profile(SqlitePersistenceProfile::Disposable);
    let begun = Instant::now();
    // This sole-owner typed proof copy is distinct from the immutable SQL census
    // input. Seal honestly reports its resulting bytes; no read-only claim.
    let handles = Handles::open_writable(config, &manifest.binding, manifest.cursor_key)?;
    let catalog = handles.history.catalog_id();
    if catalog != CatalogId::derive(&manifest.binding)?
        || handles.profile().persistence != SqlitePersistenceProfile::Disposable
        || !handles.profile().journal_mode.eq_ignore_ascii_case("wal")
        || handles.profile().synchronous != 0
    {
        return Err("public provider catalog/profile binding differs".into());
    }
    let incarnation = handles.history.incarnation();
    let branch = BranchId::from_bytes(manifest.branch)?;
    let stack = LayerStackId::from_bytes(manifest.stack)?;
    let snapshot = handles
        .history
        .branch_snapshot(branch)?
        .ok_or("persisted history Branch missing")?;
    let initial = ObjectId::from_bytes(&manifest.root)?;
    let base = handles
        .history
        .layer(snapshot.branch.base_layer)?
        .ok_or("history base Layer missing")?;
    let stack_record = handles
        .history
        .layer_stack(stack)?
        .ok_or("history LayerStack missing")?;
    if snapshot.base_root != initial
        || snapshot.branch.id != branch
        || snapshot.branch.stack != stack
        || base.stack != stack
        || base.root != initial
        || stack_record.id != stack
        || stack_record.scope != snapshot.scope
        || stack_record.profile != snapshot.profile
    {
        return Err("history initial root/manifest stack/branch/base binding differs".into());
    }
    let storage = Storage::new(handles.storage.clone())?;
    let reader = storage.reader()?;
    let (mut previous, mut final_root, mut selected_root) = (None, initial, initial);
    let (mut paths, mut verified_bytes, mut verified_roots) = (0_u64, 0_u64, 0_u64);
    let mut ids = BTreeSet::new();
    let mut roots = BTreeSet::new();
    let mut acknowledged = Vec::new();
    let mut observed = BTreeMap::new();
    let mut file_roots = BTreeSet::new();
    for (step, row) in rows.into_iter().enumerate() {
        let columns = row.split('\t').collect::<Vec<_>>();
        if columns.len() != 5
            || columns[0].parse::<usize>()? != step
            || (!legacy && columns[0] != step.to_string())
        {
            return Err("history transcript index/cardinality differs".into());
        }
        if !legacy
            && ((original_selection.contains(&step) && columns[4] == "-")
                || (!original_selection.contains(&step) && columns[4] != "-"))
        {
            return Err("history transcript selected manifest/omission differs".into());
        }
        let root = ObjectId::from_bytes(&identity_bytes::<32>(columns[3])?)?;
        if !roots.insert(root) && small {
            return Err("history state roots are not distinct".into());
        }
        if step == 0 {
            if columns[1] != "-" || columns[2] != "-" || root != initial {
                return Err("history initial acknowledgement differs".into());
            }
        } else {
            let id = CommitId::from_bytes(identity_bytes::<33>(columns[1])?)?;
            let parent = if columns[2] == "-" {
                None
            } else {
                Some(CommitId::from_bytes(identity_bytes::<33>(columns[2])?)?)
            };
            let record = handles
                .history
                .commit(id)?
                .ok_or("acknowledged historical Commit missing")?;
            if !ids.insert(id)
                || record.id != id
                || record.parent != previous
                || parent != previous
                || record.root != root
                || record.stack != stack
                || record.base_layer != snapshot.branch.base_layer
            {
                return Err(
                    "historical Commit root/ancestry/stack/base differs from acknowledgement"
                        .into(),
                );
            }
            previous = Some(id);
        }
        if !legacy {
            let tree = FilesystemRead::new(&reader, FilesystemRootId(root))?;
            if tree.root().scope().object() != snapshot.scope
                || tree.root().profile() != snapshot.profile
            {
                return Err("acknowledged history filesystem scope/profile differs".into());
            }
        }
        acknowledged.push(root);
        let selected = original_selection.contains(&step)
            && args.history_step.is_none_or(|chosen| chosen == step);
        if selected {
            let expected_body = fs::read_to_string(columns[4])?;
            let proof = if m1 {
                let materialization = crate::edit_model::m1_state(case, step, None)?;
                if crate::edit_model::m1_scope_tsv(&materialization)? != expected_body {
                    return Err("M1 selected scope differs from original independent state".into());
                }
                let scope = crate::edit_model::m1_state(case, step, modes.as_ref())?;
                verify_tree(&reader, root, &scope.entries, false, Some(&scope), true)?
            } else {
                let mut entries = reference::workspace_common::decode_manifest(&expected_body)?;
                if !legacy || snapshot_case {
                    let original = crate::edit_model::entries(case, step)?;
                    if reference::workspace_common::manifest(&original)? != expected_body {
                        return Err("selected manifest differs from original complete state".into());
                    }
                }
                if alias && step == boundary_metadata::STEP {
                    entries = boundary_metadata::entries(
                        case,
                        step,
                        alias_custody
                            .as_ref()
                            .ok_or("alias parent mtime custody missing")?
                            .0,
                    )?;
                }
                verify_tree(&reader, root, &entries, false, None, !legacy)?
            };
            if legacy
                && proof.paths
                    != if small {
                        11
                    } else if step == 0 {
                        1
                    } else {
                        25001
                    }
            {
                return Err("original retained state namespace cardinality differs".into());
            }
            paths += proof.paths;
            verified_bytes += proof.bytes;
            file_roots.extend(&proof.file_roots);
            observed.insert(step, proof.files);
            selected_root = root;
            verified_roots += 1;
            events.numeric_fields("history_root_verified", None,
                "original independent selected byte/metadata scope; current public authenticated structure/mapping and complete inode census; all acknowledgement ancestry remains bound",
                &[("root", columns[3].into()), ("commit_id", columns[1].into()), ("parent", columns[2].into())],
                &[("step", step as u64), ("paths", proof.paths), ("verified_bytes", proof.bytes)])?;
        }
        final_root = root;
    }
    if ids.len() != commits
        || previous != snapshot.branch.head_commit
        || final_root != snapshot.effective_root
    {
        return Err("complete history final head/root/cardinality differs".into());
    }
    if !legacy && !m1 {
        verify_reference_identities(case, &reader, &acknowledged, &observed, events)?;
    }
    if small {
        let dependencies = payload_dependencies(&handles, &file_roots)?;
        events.numeric_fields("history_payload_encoding", None,
            "bounded authenticated public pack reads; actual current WholeFile/PREFIX dependency records; complete byte proof already reconstructed these objects; retired schema10 encoding not asserted",
            &[("root", crate::hex(&selected_root.to_bytes()))],
            &[("payload_objects", file_roots.len() as u64), ("payload_dependency_records", dependencies)])?;
    }
    drop(reader);
    drop(storage);
    handles.seal()?;
    let after = file_identity(sealed)?;
    if let Some((_, digest)) = &alias_custody {
        events.fields("history_automatic_parent_mtime_verified", None,
            "independently qualified native alias automatic mtime; exact live-to-persisted nanosecond custody; all other independent fields unchanged",
            &[("parent_mtime_custody_sha256", digest.clone()),
              ("path", boundary_metadata::PATH.into()),
              ("step", boundary_metadata::STEP.to_string())])?;
    }
    events.numeric_fields("workspace_verified", Some(events.span(begun)),
        "original selected payload checkpoints plus all typed acknowledgements/parents/final head; independent bytes/metadata under the declared scope, public provider schema/source/binding validation and exhaustive inode census; separate typed proof copy",
        &[("status", "PASS".into()), ("root", crate::hex(&selected_root.to_bytes())),
          ("final_head_root", crate::hex(&final_root.to_bytes())),
          ("final_head_commit_id", previous.map(|id| crate::hex(id.as_slice())).unwrap_or_else(|| "-".into())),
          ("initial_root", crate::hex(initial.as_bytes())),
          ("provider_validation", "current-public-schema-source-binding-validated".into()),
          ("catalog_id", crate::hex(catalog.as_slice())),
          ("binding_sha256", reference::sdk_edit_common::sha256_hex(&manifest.binding)),
          ("stack_id", crate::hex(stack.as_slice())), ("branch_id", crate::hex(branch.as_slice())),
          ("base_layer_id", crate::hex(snapshot.branch.base_layer.as_slice())),
          ("acknowledged_transcript_sha256", reference::sdk_edit_common::sha256_hex(body.as_bytes())),
          ("parent_mtime_custody_sha256", alias_custody.as_ref().map(|(_, digest)| digest.clone()).unwrap_or_else(|| "-".into())),
          ("provider_store_sha256", before.0.clone()), ("provider_store_after_sha256", after.0.clone())],
        &[("roots", verified_roots), ("commits", commits as u64), ("paths", paths),
          ("verified_bytes", verified_bytes), ("catalog_incarnation", incarnation),
          ("provider_store_size", before.1), ("provider_store_after_size", after.1),
          ("provider_store_unchanged", u64::from(before == after))])?;
    Ok(())
}

fn identities(
    reader: &dyn AuthenticatedObjects,
    root: ObjectId,
    entries: &[Entry],
) -> Result<BTreeMap<String, FileIdentity>> {
    let mut tree = FilesystemRead::new(reader, FilesystemRootId(root))?;
    let mut result = BTreeMap::new();
    for entry in entries {
        if !matches!(entry.kind, EntryKind::File(_) | EntryKind::Hardlink(_)) {
            continue;
        }
        let resolved = tree.resolve(&LogicalPath::new(&entry.path)?)?;
        if resolved.value.kind != InodeKind::RegularFile {
            return Err("historical identity target is not regular".into());
        }
        result.insert(
            entry.path.clone(),
            FileIdentity {
                serial: resolved.serial,
                content_root: resolved.value.content_root,
                references: resolved.value.namespace_ref_count,
            },
        );
    }
    Ok(result)
}

fn verify_reference_identities(
    case: &str,
    reader: &dyn AuthenticatedObjects,
    roots: &[ObjectId],
    observed: &BTreeMap<usize, BTreeMap<String, FileIdentity>>,
    events: &mut Events,
) -> Result<()> {
    let selected = reference::workspace_registry::resolve(case)?;
    if selected.family == "file_size_transition" {
        if reference::file_size_transition::plan(case)?.alias {
            let last = roots.len() - 1;
            let before = identities(
                reader,
                roots[last - 1],
                &crate::edit_model::entries(case, last - 1)?,
            )?;
            let after = identities(
                reader,
                roots[last],
                &crate::edit_model::entries(case, last)?,
            )?;
            let target = reference::file_size_transition::TARGET;
            let alias = reference::file_size_transition::ALIAS;
            let prior = before[target];
            if before[alias] != prior
                || prior.references != 2
                || after[target].serial == after[alias].serial
                || after[target].references != 1
                || after[alias].references != 1
                || after[alias].serial != prior.serial
                || after[alias].content_root != prior.content_root
            {
                return Err(
                    "original boundary surviving alias inode/content identity differs".into(),
                );
            }
            events.numeric_fields("history_alias_identity", None,
                "current pre-replacement/final scoped inode serial and content-root retention; exact bytes/classes independently verified",
                &[("before_content_root", crate::hex(prior.content_root.as_bytes())),
                  ("alias_content_root", crate::hex(after[alias].content_root.as_bytes())),
                  ("target_content_root", crate::hex(after[target].content_root.as_bytes()))],
                &[("before_inode_serial", prior.serial), ("alias_inode_serial", after[alias].serial), ("target_inode_serial", after[target].serial)])?;
        }
        return Ok(());
    }
    let original = crate::edit_model::entries(case, 0)?;
    let initial = identities(reader, roots[0], &original)?;
    let mut recurring = BTreeMap::new();
    if selected.kind == "recurring" {
        recurring.insert(
            0,
            initial[&reference::dedup_workloads::shard_path(192)].content_root,
        );
    }
    let mut unchanged = 0_u64;
    for (step, files) in observed {
        let entries = crate::edit_model::entries(case, *step)?;
        let delta = reference::workspace_common::fast_delta_from_entries(
            &original,
            &entries,
            1,
            "dedup_branch_history",
        )?;
        for (path, actual) in files {
            if !delta.changed_paths.contains(path) {
                if initial
                    .get(path)
                    .is_none_or(|prior| prior.content_root != actual.content_root)
                {
                    return Err("original unchanged current content reference differs".into());
                }
                unchanged += 1;
            }
        }
        if selected.kind == "metadata"
            && files.iter().any(|(path, actual)| {
                initial
                    .get(path)
                    .is_none_or(|prior| prior.content_root != actual.content_root)
            })
        {
            return Err("original metadata history changed file content roots".into());
        }
        if selected.kind == "recurring" {
            let file = files[&reference::dedup_workloads::shard_path(192)].content_root;
            if recurring
                .insert(step % 2, file)
                .is_some_and(|prior| prior != file)
            {
                return Err("original recurring history changed A/B current content roots".into());
            }
        }
    }
    events.numeric_fields("history_reference_reuse", None,
        "original unchanged/metadata/A-B content-root identity checks in current format; no retired encoding or physical storage quota claim",
        &[("case", case.into())], &[("unchanged_file_root_observations", unchanged), ("recurring_classes", recurring.len() as u64)])?;
    Ok(())
}

fn payload_dependencies(handles: &Handles, files: &BTreeSet<ObjectId>) -> Result<u64> {
    use layerfs_storage::{
        encoding::{delta::record::stored_base, framed_record},
        pack::{group_view, parse_header, GroupCodec, PackLane},
    };
    let mut dependencies = 0;
    for id in files {
        let mut located = Vec::new();
        handles.storage.locate(&[*id], &mut located)?;
        if located.len() != 1 {
            return Err("historical payload locator absent/duplicated".into());
        }
        let location = located[0].location;
        let mut packs = Vec::new();
        handles
            .storage
            .read_packs(&[location.pack_id], &mut packs)?;
        if packs.len() != 1 {
            return Err("historical payload pack absent/duplicated".into());
        }
        let body = packs[0].body();
        let header = parse_header(body)?;
        let group = group_view(body, header, location.group_number)?;
        if !matches!(header.lane, PackLane::WholeFile | PackLane::Singleton)
            || group.codec != GroupCodec::Raw
        {
            return Err(
                "original small files did not produce current whole-file payload records".into(),
            );
        }
        let record = framed_record(&body[group.start..group.end], location.record_number)?;
        dependencies += u64::from(
            stored_base(
                header.lane,
                record,
                location.canonical_length,
                location.role,
            )?
            .is_some(),
        );
    }
    Ok(dependencies)
}

#[derive(Clone)]
pub struct TopologyBranch {
    pub role: String,
    pub id: BranchId,
    pub name: String,
    pub stack: LayerStackId,
    pub base: layerfs_history::LayerId,
    pub initial_parent: Option<CommitId>,
    pub initial_root: ObjectId,
    pub head: Option<CommitId>,
    pub root: ObjectId,
    pub source_role: String,
    pub source_local: usize,
}
#[derive(Clone)]
pub struct TopologyCommit {
    pub role: String,
    pub local: usize,
    pub id: CommitId,
    pub stack: LayerStackId,
    pub root: ObjectId,
    pub parent: Option<CommitId>,
    pub base: layerfs_history::LayerId,
    pub selected: String,
    pub modes: String,
}
pub struct TopologyTranscript {
    pub case: String,
    pub branches: BTreeMap<String, TopologyBranch>,
    pub commits: Vec<TopologyCommit>,
}
fn topology_optional(value: &str) -> Result<Option<CommitId>> {
    if value == "-" {
        Ok(None)
    } else {
        Ok(Some(CommitId::from_bytes(identity_bytes::<33>(value)?)?))
    }
}
fn topology_ordinal(value: &str) -> Result<usize> {
    let number = value.parse::<usize>()?;
    if number.to_string() != value {
        return Err("topology canonical ordinal required".into());
    }
    Ok(number)
}
/// Versioned role-local graph; scope files exist only at frozen payload checkpoints.
pub fn parse_topology(body: &str) -> Result<TopologyTranscript> {
    if !body.ends_with('\n') || body.contains('\r') {
        return Err("topology canonical LF required".into());
    }
    let mut lines = body.lines();
    let first = lines
        .next()
        .ok_or("topology header missing")?
        .split('\t')
        .collect::<Vec<_>>();
    if first.len() != 2 || first[0] != "topology-v1" {
        return Err("topology version/case differs".into());
    }
    let mut branches = BTreeMap::new();
    let mut ids = BTreeSet::new();
    let mut names = BTreeSet::new();
    let mut commits = Vec::new();
    let mut local = BTreeMap::<String, usize>::new();
    for line in lines {
        let columns = line.split('\t').collect::<Vec<_>>();
        match columns[0] {
            "branch" if columns.len() == 12 => {
                let role = columns[1];
                if role.is_empty()
                    || !role
                        .bytes()
                        .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
                {
                    return Err("topology unsafe role".into());
                }
                let branch = TopologyBranch {
                    role: role.into(),
                    id: BranchId::from_bytes(identity_bytes::<17>(columns[2])?)?,
                    name: layerfs_history::HistoryName::new(columns[3])?
                        .as_str()
                        .into(),
                    stack: LayerStackId::from_bytes(identity_bytes::<17>(columns[4])?)?,
                    base: layerfs_history::LayerId::from_bytes(identity_bytes::<33>(columns[5])?)?,
                    initial_parent: topology_optional(columns[6])?,
                    initial_root: ObjectId::from_bytes(&identity_bytes::<32>(columns[7])?)?,
                    head: topology_optional(columns[8])?,
                    root: ObjectId::from_bytes(&identity_bytes::<32>(columns[9])?)?,
                    source_role: columns[10].into(),
                    source_local: topology_ordinal(columns[11])?,
                };
                if !ids.insert(branch.id)
                    || !names.insert(branch.name.clone())
                    || branches.insert(role.into(), branch).is_some()
                {
                    return Err("topology duplicate role/Branch/name".into());
                }
            }
            "commit" if columns.len() == 10 => {
                let role = columns[1];
                let index = topology_ordinal(columns[2])?;
                let previous = local.entry(role.into()).or_default();
                if !branches.contains_key(role)
                    || index != *previous + 1
                    || columns[8].is_empty()
                    || columns[9].is_empty()
                {
                    return Err("topology role-local order/scope differs".into());
                }
                *previous = index;
                commits.push(TopologyCommit {
                    role: role.into(),
                    local: index,
                    id: CommitId::from_bytes(identity_bytes::<33>(columns[3])?)?,
                    stack: LayerStackId::from_bytes(identity_bytes::<17>(columns[4])?)?,
                    root: ObjectId::from_bytes(&identity_bytes::<32>(columns[5])?)?,
                    parent: topology_optional(columns[6])?,
                    base: layerfs_history::LayerId::from_bytes(identity_bytes::<33>(columns[7])?)?,
                    selected: columns[8].into(),
                    modes: columns[9].into(),
                });
            }
            _ => return Err("topology row grammar differs".into()),
        }
    }
    if branches.is_empty() || commits.is_empty() {
        return Err("topology full graph required".into());
    }
    Ok(TopologyTranscript {
        case: first[1].into(),
        branches,
        commits,
    })
}

fn topology_roles(case: &str) -> Result<Vec<&'static str>> {
    if crate::edit_model::context_roles(case).is_ok() {
        return crate::edit_model::context_roles(case);
    }
    if matches!(
        case,
        reference::dedup_branch_history::BOUNDARY_CYCLE_K100
            | reference::dedup_branch_history::NAMESPACE_INODE_K100
    ) {
        return Ok(vec!["main"]);
    }
    Err("original batch-five producer required".into())
}
fn topology_limit(case: &str, role: &str) -> Result<usize> {
    if role == "main" {
        return history_limit(case);
    }
    crate::edit_model::context_limit(case, role)
}
fn topology_selected(
    case: &str,
    access: Option<reference::historical_access::AccessCase>,
) -> Result<BTreeSet<(String, usize)>> {
    if let Some(selected) = access {
        return Ok(BTreeSet::from([(
            match selected.branch {
                reference::historical_access::ProducerBranch::Main => "main",
                reference::historical_access::ProducerBranch::Trunk => "trunk",
                reference::historical_access::ProducerBranch::B => "b",
            }
            .into(),
            selected.ordinal,
        )]));
    }
    let mut result = BTreeSet::new();
    for role in topology_roles(case)? {
        result.insert((role.into(), topology_limit(case, role)?));
    }
    if reference::v016_stages::compact_case(case)?.is_some() {
        result.insert(("trunk".into(), 5));
    }
    Ok(result)
}
fn topology_source(case: &str, role: &str) -> Result<(String, usize, Option<String>)> {
    if role == "main" {
        return Ok(("-".into(), 0, None));
    }
    if let Some(compact) = reference::v016_stages::compact_case(case)? {
        let selected = match role {
            "trunk" => reference::v016_stages::CompactRole::Trunk,
            "a" => reference::v016_stages::CompactRole::A,
            "b" => reference::v016_stages::CompactRole::B,
            "c" if compact.descendant => reference::v016_stages::CompactRole::C,
            _ => return Err("original compact role differs".into()),
        };
        return Ok((
            if role == "trunk" {
                "-"
            } else if role == "c" {
                "a"
            } else {
                "trunk"
            }
            .into(),
            if role == "trunk" { 0 } else { 5 },
            Some(reference::v016_stages::compact_branch_name(case, selected)),
        ));
    }
    let plan =
        reference::v016_stages::mixed_case(case)?.ok_or("original contextual M1 required")?;
    if plan.topology == reference::v016_stages::Topology::Branch {
        return Ok((
            if role == "trunk" { "-" } else { "trunk" }.into(),
            if role == "trunk" { 0 } else { 5 },
            Some(if role == "trunk" {
                format!("v016-{case}-0")
            } else {
                format!("{case}-child-{}", if role == "a" { 1 } else { 2 })
            }),
        ));
    }
    Ok((
        "-".into(),
        0,
        Some(format!("v016-{case}-{}", topology_ordinal(role)?)),
    ))
}
/// Root wires the existing offline driver; no Fork, mount or Store write is issued here.
pub fn verify_topology(args: &Args, events: &mut Events) -> Result<()> {
    topology_proof(args, events, false)
}
pub fn verify_access(args: &Args, events: &mut Events) -> Result<()> {
    topology_proof(args, events, true)
}
fn topology_proof(args: &Args, events: &mut Events, access_mode: bool) -> Result<()> {
    if args.source.is_some() || args.history_step.is_some() {
        return Err(
            "topology selected scope is transcript-bound, not a sequential override".into(),
        );
    }
    let case = args.case.as_deref().ok_or("--case required")?;
    let access = if access_mode {
        Some(
            reference::historical_access::access_case(case)?
                .ok_or("original six access case required")?,
        )
    } else {
        None
    };
    let producer = access.map(|selected| selected.producer).unwrap_or(case);
    let body = fs::read_to_string(
        args.history_file
            .as_ref()
            .ok_or("--history-file required")?,
    )?;
    let graph = parse_topology(&body)?;
    if graph.case != producer {
        return Err("topology exact original producer/case differs".into());
    }
    let manifest = StoreManifest::decode(&fs::read(&args.manifest)?)?;
    if manifest.profile != layerfs_bridge::provision::StoreProfile::Disposable {
        return Err("topology explicit Disposable required".into());
    }
    let sealed = args.sealed.as_ref().ok_or("--sealed required")?;
    let before = file_identity(sealed)?;
    let begun = Instant::now();
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(sealed).with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &manifest.binding,
        manifest.cursor_key,
    )?;
    let catalog = handles.history.catalog_id();
    if catalog != CatalogId::derive(&manifest.binding)?
        || handles.profile().persistence != SqlitePersistenceProfile::Disposable
        || !handles.profile().journal_mode.eq_ignore_ascii_case("wal")
        || handles.profile().synchronous != 0
    {
        return Err("topology public provider profile/catalog differs".into());
    }
    let incarnation = handles.history.incarnation();
    let stack = LayerStackId::from_bytes(manifest.stack)?;
    let manifest_branch = BranchId::from_bytes(manifest.branch)?;
    let original = handles
        .history
        .branch_snapshot(manifest_branch)?
        .ok_or("topology manifest Branch missing")?;
    let initial = ObjectId::from_bytes(&manifest.root)?;
    let layer = handles
        .history
        .layer(original.branch.base_layer)?
        .ok_or("topology initial Layer missing")?;
    let stack_record = handles
        .history
        .layer_stack(stack)?
        .ok_or("topology stack missing")?;
    if original.branch.stack != stack
        || original.base_root != initial
        || layer.stack != stack
        || layer.root != initial
        || layer.parent.is_some()
        || layer.source_branch.is_some()
        || layer.source_commit.is_some()
        || stack_record.head_layer != layer.id
        || stack_record.scope != original.scope
        || stack_record.profile != original.profile
    {
        return Err("topology manifest stack/base/profile/scope differs".into());
    }
    let roles = topology_roles(producer)?;
    let mut required = roles
        .iter()
        .map(|role| role.to_string())
        .collect::<BTreeSet<_>>();
    if !roles.contains(&"main") {
        required.insert("initial".into());
    }
    if access_mode {
        required.insert("access".into());
    }
    if graph.branches.keys().cloned().collect::<BTreeSet<_>>() != required {
        return Err("topology complete original role/Branch set differs".into());
    }
    let selected = topology_selected(producer, access)?;
    let mut by_role = BTreeMap::<String, Vec<&TopologyCommit>>::new();
    let mut union = BTreeMap::<
        CommitId,
        (
            LayerStackId,
            ObjectId,
            Option<CommitId>,
            layerfs_history::LayerId,
        ),
    >::new();
    for ack in &graph.commits {
        if !roles.iter().any(|role| *role == ack.role) || ack.stack != stack || ack.base != layer.id
        {
            return Err("topology acknowledgement role/stack/base differs".into());
        }
        let tuple = (ack.stack, ack.root, ack.parent, ack.base);
        if union.insert(ack.id, tuple).is_some_and(|old| old != tuple) {
            return Err("topology conflicting duplicate full Commit tuple".into());
        }
        let record = handles
            .history
            .commit(ack.id)?
            .ok_or("topology acknowledged Commit missing")?;
        if CommitId::derive(
            record.root,
            record.parent,
            record.base_layer,
            record.second_parent,
            &record.meta,
        ) != ack.id
            || (record.stack, record.root, record.parent, record.base_layer) != tuple
        {
            return Err("topology persisted five-field acknowledgement differs".into());
        }
        let chosen = selected.contains(&(ack.role.clone(), ack.local));
        if chosen == (ack.selected == "-") || (!chosen && ack.modes != "-") {
            return Err("topology frozen payload checkpoint/omission differs".into());
        }
        if chosen && (crate::edit_model::is_context_m1(producer) == (ack.modes == "-")) {
            return Err("topology selected contextual modes binding differs".into());
        }
        by_role.entry(ack.role.clone()).or_default().push(ack);
    }
    let collapse = reference::v016_stages::compact_case(producer)?.is_some();
    if !collapse && union.len() != graph.commits.len() {
        return Err(
            "original M1/single producer acknowledgements must have distinct Commit identities"
                .into(),
        );
    }
    let mut public_branches = BTreeSet::new();
    let mut cursor = None;
    loop {
        let page = handles
            .history
            .branches(stack, &layerfs_history::Page { limit: 128, cursor })?;
        for branch in page.records {
            if !public_branches.insert(branch.id) {
                return Err("topology duplicate public Branch page".into());
            }
        }
        cursor = page.continuation;
        if cursor.is_none() {
            break;
        }
    }
    if public_branches != graph.branches.values().map(|branch| branch.id).collect() {
        return Err("topology unfiltered public Branch set differs".into());
    }
    let storage = Storage::new(handles.storage.clone())?;
    let reader = storage.reader()?;
    let mut verified_roots = 0_u64;
    let mut paths = 0_u64;
    let mut bytes = 0_u64;
    let mut content_roots = BTreeMap::new();
    let mut selected_root = initial;
    for (role, branch) in &graph.branches {
        let (source, source_local, name) = if role == "initial" {
            ("-".into(), 0, None)
        } else if role == "access" {
            let selected = access.ok_or("unexpected access Branch")?;
            (
                match selected.branch {
                    reference::historical_access::ProducerBranch::Main => "main",
                    reference::historical_access::ProducerBranch::Trunk => "trunk",
                    reference::historical_access::ProducerBranch::B => "b",
                }
                .into(),
                selected.ordinal,
                Some(format!("access-{}-{case}", selected.ordinal)),
            )
        } else {
            topology_source(producer, role)?
        };
        if branch.role != *role
            || branch.source_role != source
            || branch.source_local != source_local
            || name.is_some_and(|name| name != branch.name)
            || branch.stack != stack
            || branch.base != layer.id
        {
            return Err("topology original fork/name/stack/base differs".into());
        }
        let (mut parent, mut root) = if source == "-" {
            (None, initial)
        } else {
            let source_ack = by_role
                .get(&source)
                .and_then(|rows| rows.get(source_local - 1))
                .ok_or("topology fork source ordinal missing")?;
            (Some(source_ack.id), source_ack.root)
        };
        if branch.initial_parent != parent || branch.initial_root != root {
            return Err("topology selected fork root/parent differs".into());
        }
        if (role == "initial" || role == "main") && branch.id != manifest_branch {
            return Err("topology original manifest Branch substituted".into());
        }
        let expected_count = if role == "initial" || role == "access" {
            0
        } else {
            topology_limit(producer, role)?
        };
        let acknowledgements = by_role.get(role).map(Vec::as_slice).unwrap_or(&[]);
        if acknowledgements.len() != expected_count {
            return Err("topology original role-local cardinality differs".into());
        }
        for ack in acknowledgements {
            if ack.parent != parent {
                return Err("topology exact local parent edge differs".into());
            }
            parent = Some(ack.id);
            root = ack.root;
            let tree = FilesystemRead::new(&reader, FilesystemRootId(root))?;
            if tree.root().scope().object() != original.scope
                || tree.root().profile() != original.profile
            {
                return Err("topology acknowledged root scope/profile differs".into());
            }
            if selected.contains(&(role.clone(), ack.local)) {
                let expected = if role == "main" {
                    reference::workspace_common::manifest(&crate::edit_model::entries(
                        producer, ack.local,
                    )?)?
                } else {
                    crate::edit_model::context_manifest(producer, role, ack.local)?
                };
                if fs::read_to_string(&ack.selected)? != expected {
                    return Err(
                        "topology selected scope differs from independent original recipe".into(),
                    );
                }
                let proof = if let Some(access) = access {
                    access_tree(&reader, root, access, events)?
                } else if crate::edit_model::is_context_m1(producer) {
                    let modes = crate::edit_model::parse_context_created_modes(
                        producer,
                        &fs::read_to_string(&ack.modes)?,
                    )?;
                    let state = crate::edit_model::context_m1_state(
                        producer,
                        role,
                        ack.local,
                        Some(&modes),
                    )?;
                    verify_tree(&reader, root, &state.entries, false, Some(&state), true)?
                } else {
                    verify_tree(
                        &reader,
                        root,
                        &crate::edit_model::context_entries(producer, role, ack.local)?,
                        false,
                        None,
                        true,
                    )?
                };
                verified_roots += 1;
                paths += proof.paths;
                bytes += proof.bytes;
                selected_root = root;
                if let Some(file) = proof.files.get("medium/m0.dat") {
                    content_roots.insert(role.clone(), file.content_root);
                }
                events.numeric_fields("topology_root_verified",None,"original selected semantic scope; complete current inode membership and typed mapping/profile; no all-state payload proof",
                    &[("role",role.clone()),("root",crate::hex(root.as_bytes())),("commit_id",crate::hex(ack.id.as_slice()))],
                    &[("local",ack.local as u64),("paths",proof.paths),("verified_bytes",proof.bytes)])?;
            }
        }
        let snapshot = handles
            .history
            .branch_snapshot(branch.id)?
            .ok_or("topology Branch missing")?;
        if parent != branch.head
            || root != branch.root
            || snapshot.branch.name.as_str() != branch.name
            || snapshot.branch.stack != stack
            || snapshot.branch.base_layer != layer.id
            || snapshot.branch.head_commit != parent
            || snapshot.effective_root != root
            || snapshot.scope != original.scope
            || snapshot.profile != original.profile
        {
            return Err("topology final head/root/name/base differs".into());
        }
        let mut expected_history = parent;
        let mut continuation = None;
        loop {
            let page = handles
                .history
                .commit_history(&layerfs_history::CommitHistoryRequest {
                    branch: branch.id,
                    start: parent,
                    cursor: continuation,
                    limit: 128,
                })?;
            for record in page.records {
                if Some(record.id) != expected_history
                    || union.get(&record.id)
                        != Some(&(record.stack, record.root, record.parent, record.base_layer))
                {
                    return Err("topology exact public ancestry membership differs".into());
                }
                expected_history = record.parent;
            }
            continuation = page.continuation;
            if continuation.is_none() {
                break;
            }
        }
        if expected_history.is_some() {
            return Err("topology public ancestry did not reach EOF".into());
        }
        events.fields("topology_branch_verified",None,"exact original published Branch binding and anchored public History to EOF; access Fork creates no Commit",
            &[("role",role.clone()),("branch_id",crate::hex(branch.id.as_slice())),("head",parent.map(|id|crate::hex(id.as_slice())).unwrap_or_else(||"-".into())),("root",crate::hex(root.as_bytes()))])?;
    }
    if !access_mode {
        if let Some(compact) = reference::v016_stages::compact_case(producer)? {
            let a = content_roots
                .get("a")
                .ok_or("compact selected A content identity missing")?;
            let b = content_roots
                .get("b")
                .ok_or("compact selected B content identity missing")?;
            if !compact.descendant && a != b
                || compact.descendant
                    && (a == b || content_roots.get("c").is_none_or(|c| c == a || c == b))
            {
                return Err(
                    "original compact medium file-content identity relation differs".into(),
                );
            }
        }
    }
    if verified_roots as usize != selected.len() {
        return Err("topology selected root count differs".into());
    }
    drop(reader);
    drop(storage);
    handles.seal()?;
    let after = file_identity(sealed)?;
    events.numeric_fields("workspace_verified",Some(events.span(begun)),"batch-five original selected roots; all typed role-local/fork edges, public Branch/History EOF and provider binding; independent bytes and complete inode census; SQL global tuple census remains separate",
        &[("status","PASS".into()),("case",case.into()),("topology_case",producer.into()),("root",crate::hex(selected_root.as_bytes())),
          ("final_head_root",crate::hex(original.effective_root.as_bytes())),("final_head_commit_id",original.branch.head_commit.map(|id|crate::hex(id.as_slice())).unwrap_or_else(||"-".into())),
          ("initial_root",crate::hex(initial.as_bytes())),("provider_validation","current-public-schema-source-binding-validated".into()),
          ("catalog_id",crate::hex(catalog.as_slice())),("binding_sha256",reference::sdk_edit_common::sha256_hex(&manifest.binding)),
          ("stack_id",crate::hex(stack.as_slice())),("branch_id",crate::hex(manifest_branch.as_slice())),("base_layer_id",crate::hex(layer.id.as_slice())),
          ("acknowledged_transcript_sha256",reference::sdk_edit_common::sha256_hex(body.as_bytes())),("provider_store_sha256",before.0.clone()),("provider_store_after_sha256",after.0.clone())],
        &[("roots",verified_roots),("paths",paths),("verified_bytes",bytes),("catalog_incarnation",incarnation),
          ("topology_acknowledgements",graph.commits.len() as u64),("topology_distinct_commits",union.len() as u64),("topology_branches",graph.branches.len() as u64),
          ("provider_store_size",before.1),("provider_store_after_size",after.1),("provider_store_unchanged",u64::from(before==after))])?;
    Ok(())
}
fn access_tree(
    reader: &dyn AuthenticatedObjects,
    root: ObjectId,
    access: reference::historical_access::AccessCase,
    events: &mut Events,
) -> Result<VerifiedTree> {
    let entries = reference::historical_access::declared_state(access, 1)?;
    // Membership does not add payload reads outside the original selected target.
    // Original access checks no portable metadata beyond inode/link observations.
    let scope = crate::edit_model::M1State {
        entries: entries.clone(),
        ranges: BTreeMap::new(),
        file_modes: BTreeMap::new(),
        file_mtimes: BTreeMap::new(),
        directory_modes: BTreeMap::new(),
        required_created_directory_modes: BTreeSet::new(),
    };
    let mut proof = verify_tree(reader, root, &entries, true, Some(&scope), false)?;
    let mut tree = FilesystemRead::new(reader, FilesystemRootId(root))?;
    let (targets, absent) = reference::historical_access::read_targets(access, 1)?;
    for target in targets {
        let inode = tree.resolve(&LogicalPath::new(&target.path)?)?;
        Timing::disabled("independent.access.bytes", |timer| -> Result<()> {
            let view = FileView::open(reader, inode.value.content_root, timer.child("open"))?;
            if view.logical_len() != target.len {
                return Err("access selected full-read length differs".into());
            }
            verify_mapping(reader, &view)?;
            let mut observed = Vec::new();
            view.read_range(reader, 0..target.len, &mut observed, timer)?;
            if observed != target.content {
                return Err("access independent full bytes differ".into());
            }
            Ok(())
        })
        .0?;
        proof.bytes += target.len;
        events.numeric_fields("access_expected_read",None,"independent frozen producer derivation, exact full bytes for comparison with both mounted original helper passes",
            &[("path",target.path), ("sha256",reference::sdk_edit_common::sha256_hex(&target.content)),("payload_hex",crate::hex(&target.content))],&[("bytes",target.len)])?;
    }
    for path in absent {
        match tree.resolve(&LogicalPath::new(&path)?) {
            Err(layerfs_content::ContentError::PathNotFound) => {}
            Ok(_) => return Err("access declared absent alias present".into()),
            Err(error) => return Err(error.into()),
        }
        events.fields(
            "access_expected_absent",
            None,
            "original alias ENOENT scope",
            &[("path", path)],
        )?;
    }
    Ok(proof)
}

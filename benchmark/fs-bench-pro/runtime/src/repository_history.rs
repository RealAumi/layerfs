//! Typed proof of the frozen pre-verifier repository Store and ACK mappings.
//! Git byte/type/mode equality belongs to the separate original mounted observer.
use crate::{args::Args, events::Events, reference, Result};
use layerfs_bridge::provision::{StoreManifest, StoreProfile};
use layerfs_content::{
    file::FileView,
    filesystem::{
        attributes::read::{read_portable, AttributeReadWork},
        FilesystemRead, FilesystemRootId, LogicalPath,
    },
    inode_leaf::InodeKind,
    object::ObjectId,
};
use layerfs_history::{
    BranchId, CatalogId, CommitHistoryRequest, CommitId, HistoryCatalog, LayerId, LayerStackId,
    Page,
};
use layerfs_persistence::{Handles, PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::Storage;
use layerfs_telemetry::timer::Timing;
use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    fs,
    io::{Read, Write},
    os::unix::fs::OpenOptionsExt,
    path::Path,
    time::Instant,
};

pub fn count(case: &str) -> Result<usize> {
    match case {
        "deepseek-full" => Ok(157),
        "deepseek-stride3" => Ok(53),
        "deepseek-stride10" => Ok(17),
        _ => Err("original repository case required".into()),
    }
}
fn bytes<const N: usize>(text: &str) -> Result<[u8; N]> {
    if text.len() != N * 2
        || !text
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err("exact lowercase typed identity required".into());
    }
    let mut value = [0; N];
    for (i, byte) in value.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&text[2 * i..2 * i + 2], 16)?;
    }
    Ok(value)
}
fn digest(path: &Path) -> Result<(String, u64)> {
    if !fs::symlink_metadata(path)?.is_file() {
        return Err("exact regular proof artifact required".into());
    }
    let mut input = fs::File::open(path)?;
    let mut hash = reference::Sha256::new();
    let mut total = 0;
    let mut buffer = [0; 65536];
    loop {
        let n = input.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
        total += n as u64;
    }
    Ok((crate::hex(&hash.finish()), total))
}
fn fresh(path: &Path, body: &[u8]) -> Result<()> {
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)?
        .write_all(body)?;
    Ok(())
}
fn string_value(body: &str, key: &str) -> Result<String> {
    let marker = format!("\"{key}\"");
    let mut matched = body.match_indices(&marker);
    let (position, _) = matched.next().ok_or("fork event field missing")?;
    if matched.next().is_some() {
        return Err("fork event duplicate field".into());
    }
    let after = body[position + marker.len()..].trim_start();
    let after = after
        .strip_prefix(':')
        .ok_or("fork event field colon")?
        .trim_start();
    let after = after.strip_prefix('"').ok_or("fork event string field")?;
    let end = after.find('"').ok_or("fork event string end")?;
    let value = &after[..end];
    if value.contains(['\\', '\n', '\r']) {
        return Err("fork typed event escape refused".into());
    }
    Ok(value.to_owned())
}

pub struct Ack {
    pub index: usize,
    pub id: Option<CommitId>,
    pub parent: Option<CommitId>,
    pub root: ObjectId,
    pub oracle: String,
}
pub fn acknowledgements(body: &str, expected: usize) -> Result<Vec<Ack>> {
    let rows = body.lines().collect::<Vec<_>>();
    if rows.len() != expected + 1 {
        return Err("repository exact initial/all-selected ACK count differs".into());
    }
    rows.iter()
        .enumerate()
        .map(|(index, row)| {
            let cols = row.split('\t').collect::<Vec<_>>();
            if cols.len() != 5 || cols[0] != index.to_string() {
                return Err("repository canonical five-column ACK grammar".into());
            }
            let id = if cols[1] == "-" {
                None
            } else {
                Some(CommitId::from_bytes(bytes(cols[1])?)?)
            };
            let parent = if cols[2] == "-" {
                None
            } else {
                Some(CommitId::from_bytes(bytes(cols[2])?)?)
            };
            if index == 0 && (id.is_some() || parent.is_some() || cols[4] != "-")
                || index > 0 && cols[4] == "-"
            {
                return Err("repository original selected oracle/initial sentinel differs".into());
            }
            Ok(Ack {
                index,
                id,
                parent,
                root: ObjectId::from_bytes(&bytes::<32>(cols[3])?)?,
                oracle: cols[4].into(),
            })
        })
        .collect()
}

fn structure(
    reader: &dyn layerfs_content::AuthenticatedObjects,
    root: ObjectId,
    scope: ObjectId,
    profile: ObjectId,
) -> Result<u64> {
    let mut tree = FilesystemRead::new(reader, FilesystemRootId(root))?;
    if tree.root().scope().object() != scope || tree.root().profile() != profile {
        return Err("repository actual root scope/profile differs".into());
    }
    let mut pending = VecDeque::from([String::new()]);
    let mut paths = BTreeSet::new();
    let mut serials = BTreeSet::new();
    let mut attributes = AttributeReadWork::default();
    while let Some(path) = pending.pop_front() {
        if !paths.insert(path.clone()) {
            return Err("repository duplicate canonical path".into());
        }
        let logical = LogicalPath::new(&path)?;
        let resolved = tree.resolve(&logical)?;
        serials.insert(resolved.serial);
        let inode = resolved.value;
        read_portable(reader, inode.metadata_root, inode.kind, &mut attributes)?;
        match inode.kind {
            InodeKind::Directory => {
                let mut after = None;
                loop {
                    let page = tree.list(&logical, after.as_ref(), 128, 16384)?;
                    for (name, _) in page.entries {
                        pending.push_back(if path.is_empty() {
                            name.as_str().into()
                        } else {
                            format!("{path}/{}", name.as_str())
                        });
                    }
                    if page.continuation == after && page.continuation.is_some() {
                        return Err("repository directory cursor did not advance".into());
                    }
                    after = page.continuation;
                    if after.is_none() {
                        break;
                    }
                }
            }
            InodeKind::Symlink => {
                tree.readlink(&logical)?;
            }
            InodeKind::RegularFile => {
                Timing::disabled("repository.typed.mapping", |timer| -> Result<()> {
                    let view = FileView::open(reader, inode.content_root, timer.child("open"))?;
                    crate::workspace_oracle::verify_mapping(reader, &view)
                })
                .0?;
            }
        }
    }
    crate::edit_oracle::require_complete_membership(reader, tree.root(), &serials)?;
    Ok(paths.len() as u64)
}

pub fn verify(args: &Args, events: &mut Events) -> Result<()> {
    if args.history_step.is_some() {
        return Err("repository proof requires every selected ACK".into());
    }
    let case = args.case.as_deref().ok_or("repository case required")?;
    let expected = count(case)?;
    let directory = args
        .source
        .as_ref()
        .ok_or("repository proof-input directory required")?;
    let full_path = args
        .history_file
        .as_ref()
        .ok_or("repository all-selected transcript required")?;
    let full = fs::read_to_string(full_path)?;
    let acks = acknowledgements(&full, expected)?;
    let census_path = directory.join("created.tsv");
    let census = fs::read_to_string(&census_path)?;
    let fork_body = fs::read_to_string(directory.join("fork.tsv"))?;
    let fork = fork_body
        .trim_end_matches('\n')
        .split('\t')
        .collect::<Vec<_>>();
    if fork.len() != 7 || fork[1] != "history" || fork[5] != "-" {
        return Err("repository exact Layer Fork descriptor required".into());
    }
    let fork_event = directory.join("fork-event.json");
    let event_body = fs::read_to_string(&fork_event)?;
    if digest(&fork_event)?.0 != fork[6] || string_value(&event_body, "event")? != "fork" {
        return Err("repository actual Fork event binding differs".into());
    }
    for (key, value) in [
        ("branch_id", fork[0]),
        ("name", fork[1]),
        ("stack", fork[2]),
        ("base_layer", fork[3]),
        ("root", fork[4]),
        ("head", fork[5]),
    ] {
        if string_value(&event_body, key)? != value {
            return Err("repository Fork event typed fields differ".into());
        }
    }
    let original_bytes = fs::read(&args.manifest)?;
    let original = StoreManifest::decode(&original_bytes)?;
    if original.profile != StoreProfile::Disposable {
        return Err("repository requires explicit Disposable".into());
    }
    let stack = LayerStackId::from_bytes(original.stack)?;
    let branch = BranchId::from_bytes(bytes(fork[0])?)?;
    let main = BranchId::from_bytes(original.branch)?;
    let initial = ObjectId::from_bytes(&original.root)?;
    let base = LayerId::derive(stack, None, initial);
    let mut derived = StoreManifest::decode(&original_bytes)?;
    derived.branch = branch.to_bytes();
    let derived_path = directory.join("derived.manifest");
    fresh(&derived_path, &derived.encode()?)?;
    let derivation_path = directory.join("manifest-derivation.json");
    let derivation=format!("{{\"schema\":\"fs-bench-pro-repository-manifest-derivation-v1\",\"status\":\"UNVERIFIED\",\"original_manifest_sha256\":\"{}\",\"derived_manifest_sha256\":\"{}\",\"fork_event_sha256\":\"{}\",\"all_selected_transcript_sha256\":\"{}\",\"created_transcript_sha256\":\"{}\",\"branch_id\":\"{}\",\"scope\":\"branch-only derivation; public validation required before promotion; no cursor or binding bytes\"}}\n",digest(&args.manifest)?.0,digest(&derived_path)?.0,fork[6],digest(full_path)?.0,digest(&census_path)?.0,fork[0]);
    fresh(&derivation_path, derivation.as_bytes())?;
    if branch == main
        || fork[2] != crate::hex(&original.stack)
        || fork[3] != crate::hex(base.as_slice())
        || fork[4] != crate::hex(&original.root)
        || acks[0].root != initial
    {
        return Err("repository authenticated genesis/Fork fields differ".into());
    }
    let sealed = args
        .sealed
        .as_ref()
        .ok_or("repository frozen typed Store required")?;
    let before = digest(sealed)?;
    let begun = Instant::now();
    let handles = Handles::open_writable(
        PersistenceConfig::sqlite(sealed).with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        &original.binding,
        original.cursor_key,
    )?;
    let catalog = handles.history.catalog_id();
    let incarnation = handles.history.incarnation();
    if catalog != CatalogId::derive(&original.binding)?
        || handles.profile().persistence != SqlitePersistenceProfile::Disposable
        || handles.profile().journal_mode.to_ascii_lowercase() != "wal"
        || handles.profile().synchronous != 0
    {
        return Err("repository current public provider binding/profile differs".into());
    }
    let main_snapshot = handles
        .history
        .branch_snapshot(main)?
        .ok_or("repository original Main missing")?;
    let snapshot = handles
        .history
        .branch_snapshot(branch)?
        .ok_or("repository actual Fork Branch missing")?;
    let layer = handles
        .history
        .layer(base)?
        .ok_or("repository genesis Layer missing")?;
    if main_snapshot.branch.head_commit.is_some()
        || main_snapshot.effective_root != initial
        || main_snapshot.branch.name.as_str() != "main"
        || main_snapshot.branch.stack != stack
        || main_snapshot.branch.base_layer != base
        || layer.root != initial
        || layer.stack != stack
        || snapshot.branch.name.as_str() != "history"
        || snapshot.branch.stack != stack
        || snapshot.branch.base_layer != base
        || snapshot.scope != main_snapshot.scope
        || snapshot.profile != main_snapshot.profile
    {
        return Err("repository original/fork public catalogue differs".into());
    }
    let mut branches = BTreeSet::new();
    let mut continuation = None;
    loop {
        let page = handles.history.branches(
            stack,
            &Page {
                limit: 128,
                cursor: continuation,
            },
        )?;
        for record in page.records {
            if !branches.insert(record.id) {
                return Err("repository duplicate Branch enumeration".into());
            }
        }
        continuation = page.continuation;
        if continuation.is_none() {
            break;
        }
    }
    if branches != BTreeSet::from([main, branch]) {
        return Err(
            "repository frozen Store must contain only originalMain and actualhistoryFork".into(),
        );
    }
    let storage = Storage::new(handles.storage.clone())?;
    let reader = storage.reader()?;
    if structure(&reader, initial, snapshot.scope, snapshot.profile)? != 1 {
        return Err("repository initial root is not empty".into());
    }
    let mut previous = None;
    let mut prior_parent = None;
    let mut prior_root = initial;
    let mut created = BTreeMap::new();
    let mut canonical_paths = 0;
    let mut wanted_census = format!("0\t-\t-\t{}\t-\n", crate::hex(initial.as_bytes()));
    for ack in acks.iter().skip(1) {
        digest(Path::new(&ack.oracle))?;
        if ack.id == previous {
            if case != "deepseek-full" || ack.root != prior_root || ack.parent != prior_parent {
                return Err(
                    "repository UpToDate did not retain prior actual Commit/root/parent".into(),
                );
            }
        } else {
            let id = ack.id.ok_or("repository changed ACK missing CommitID")?;
            let record = handles
                .history
                .commit(id)?
                .ok_or("repository acknowledged Commit missing")?;
            if record.parent != previous
                || ack.parent != previous
                || record.root != ack.root
                || record.stack != stack
                || record.base_layer != base
                || record.id
                    != CommitId::derive(
                        record.root,
                        record.parent,
                        record.base_layer,
                        record.second_parent,
                        &record.meta,
                    )
                || created.insert(id, record.clone()).is_some()
            {
                return Err("repository canonical Created tuple/parent differs".into());
            }
            wanted_census += &format!(
                "{}\t{}\t{}\t{}\t{}\n",
                created.len(),
                crate::hex(id.as_slice()),
                ack.parent
                    .map(|p| crate::hex(p.as_slice()))
                    .unwrap_or_else(|| "-".into()),
                crate::hex(ack.root.as_bytes()),
                ack.oracle
            );
            previous = Some(id);
            prior_parent = ack.parent;
            prior_root = ack.root;
        }
        canonical_paths += structure(&reader, ack.root, snapshot.scope, snapshot.profile)?;
        events.numeric_fields("repository_root_verified",None,"actual current authenticated structure/mapping and exhaustive inode membership; originalGit bytes separately proved through fresh FUSE",
            &[("root",crate::hex(ack.root.as_bytes())),("commit_id",ack.id.map(|id|crate::hex(id.as_slice())).unwrap_or_else(||"-".into())),("oracle_sha256",digest(Path::new(&ack.oracle))?.0)],&[("step",ack.index as u64)])?;
    }
    if census != wanted_census
        || created.is_empty()
        || snapshot.branch.head_commit != previous
        || snapshot.effective_root != prior_root
    {
        return Err(
            "repository Created-only census transcript or actual final head/root differs".into(),
        );
    }
    let mut expected_head = previous;
    let mut cursor = None;
    loop {
        let page = handles.history.commit_history(&CommitHistoryRequest {
            branch,
            start: previous,
            cursor,
            limit: 32,
        })?;
        for record in page.records {
            if Some(record.id) != expected_head || created.get(&record.id) != Some(&record) {
                return Err("repository actual public History differs from Created chain".into());
            }
            expected_head = record.parent;
        }
        cursor = page.continuation;
        if cursor.is_none() {
            break;
        }
    }
    if expected_head.is_some() {
        return Err("repository actual History did not reach EOF".into());
    }
    drop(reader);
    drop(storage);
    handles.seal()?;
    let after = digest(sealed)?;
    events.fields("repository_manifest_derived",None,"known public verification of exact original Init/Fork event and branch-only derived manifest; private bytes retained without exposure",
        &[("status","PASS".into()),("original_manifest_sha256",digest(&args.manifest)?.0),("derived_manifest",derived_path.to_string_lossy().into()),("derived_manifest_sha256",digest(&derived_path)?.0),("derivation_receipt",derivation_path.to_string_lossy().into()),("derivation_receipt_sha256",digest(&derivation_path)?.0),("fork_event_sha256",fork[6].into())])?;
    events.numeric_fields("workspace_verified",Some(events.span(begun)),"current public provider and canonical actual repository ACK structure; frozen two-branch performance Store; separate mounted fullGit oracle mandatory",
        &[("status","PASS".into()),("root",crate::hex(prior_root.as_bytes())),("initial_root",crate::hex(initial.as_bytes())),("final_head_root",crate::hex(prior_root.as_bytes())),("final_head_commit_id",previous.map(|id|crate::hex(id.as_slice())).unwrap_or_else(||"-".into())),("provider_validation","current-public-schema-source-binding-validated".into()),("catalog_id",crate::hex(catalog.as_slice())),("binding_sha256",reference::sdk_edit_common::sha256_hex(&original.binding)),("stack_id",crate::hex(stack.as_slice())),("branch_id",crate::hex(branch.as_slice())),("base_layer_id",crate::hex(base.as_slice())),("acknowledged_transcript_sha256",digest(&census_path)?.0),("repository_acknowledged_transcript_sha256",digest(full_path)?.0),("provider_store_sha256",before.0.clone()),("provider_store_after_sha256",after.0.clone())],
        &[("commits",created.len() as u64),("roots",expected as u64),("paths",canonical_paths),("verified_bytes",0),("catalog_incarnation",incarnation),("provider_store_size",before.1),("provider_store_after_size",after.1),("provider_store_unchanged",u64::from(before==after))])?;
    Ok(())
}

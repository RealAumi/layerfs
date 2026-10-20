//! One Store, ordinary local Save/history publication, no network inside its lane.
use crate::{
    config::{self, Config},
    wire::{self, error, Decode, Encode, Result},
};
use layerfs_bridge::{
    control::{Answer, ConflictReport, MergedCommit, Reply},
    duplex,
};
use layerfs_content::{
    filesystem::{FilesystemRead, FilesystemRootId, InodeScope},
    AuthenticatedObjects, FinalizedObject, ObjectId, ObjectRole,
};
use layerfs_history::{BranchId, CommitVia};
use layerfs_storage::{StorageError, StoragePolicy, WriteOutcome};
use layerfs_store_service::{
    store::{
        commit_merge::PendingMerge,
        publish::{CandidateInput, Publication, PublishedCandidate},
        BackendError, CommitOptions, CommitPhase, MergeReport, Store,
    },
    StoreService,
};
use layerfs_workspace::InodeSerials;
use std::{
    net::TcpListener,
    path::Path,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    time::Duration,
};
fn storage(e: StorageError) -> BackendError {
    BackendError {
        unknown: e.is_unknown_outcome(),
        detail: e.to_string(),
    }
}
pub fn serve(config: Config) -> Result<()> {
    let service = Arc::new(
        StoreService::open_direct(
            Path::new(config.get("store")?),
            &config::unhex(config.get("binding")?)?,
            config.key("cursor")?,
            Path::new(config.get("overlay")?),
        )
        .map_err(|e| error(format!("{e:?}")))?,
    );
    if service.store.policy() != StoragePolicy::frozen_default() {
        return Err(error("prototype requires frozen Store policy"));
    }
    let listener = TcpListener::bind(config.get("listen")?).map_err(error)?;
    let key = config.key("private_key")?;
    let peer = duplex::public_key(&config.key("token")?).map_err(error)?;
    let active = Arc::new(AtomicUsize::new(0));
    println!(
        "REMOTE_STORE_READY {}",
        listener.local_addr().map_err(error)?
    );
    for stream in listener.incoming() {
        let stream = stream.map_err(error)?;
        if active
            .fetch_update(Ordering::AcqRel, Ordering::Relaxed, |n| {
                (n < 16).then_some(n + 1)
            })
            .is_err()
        {
            continue;
        }
        let service = service.clone();
        let active = active.clone();
        std::thread::spawn(move || {
            let result: Result<()> = (|| {
                stream
                    .set_read_timeout(Some(Duration::from_secs(10)))
                    .map_err(error)?;
                stream
                    .set_write_timeout(Some(Duration::from_secs(10)))
                    .map_err(error)?;
                let settings = stream.try_clone().map_err(error)?;
                let mut connection = duplex::accept(stream, &key, peer).map_err(error)?;
                settings.set_read_timeout(None).map_err(error)?;
                let mut saved = WriteOutcome::default();
                let mut last = 0;
                loop {
                    let bytes = wire::receive(&mut connection)?;
                    let mut input = Decode(&bytes);
                    let id = input.number()?;
                    if id <= last {
                        return Err(error("request replay/order"));
                    }
                    last = id;
                    let opcode = input.byte()?;
                    let result = dispatch(&service.store, opcode, &mut input, &mut saved);
                    let mut answer = Encode::new();
                    answer.number(id);
                    match result {
                        Ok(value) => {
                            answer.byte(0);
                            answer.raw(&value.0);
                        }
                        Err(e) => {
                            answer.byte(if e.unknown { 2 } else { 1 });
                            answer.text(&e.detail.chars().take(4096).collect::<String>());
                        }
                    }
                    wire::send(&mut connection, &answer.0)?;
                }
            })();
            if let Err(e) = result {
                eprintln!("remote connection ended: {e}");
            }
            active.fetch_sub(1, Ordering::Release);
        });
    }
    Ok(())
}
fn dispatch(
    store: &Arc<Store>,
    opcode: u8,
    input: &mut Decode<'_>,
    saved: &mut WriteOutcome,
) -> Result<Encode> {
    let mut out = Encode::new();
    match opcode {
        wire::SNAPSHOT => {
            let branch = BranchId::from_bytes(input.array()?).map_err(error)?;
            finish(input)?;
            let value = store
                .history()
                .branch_snapshot(branch)
                .map_err(error)?
                .ok_or_else(|| error("missing branch"))?;
            out.number(store.policy().small_file_threshold_bytes());
            out.byte(store.policy().format_profile());
            out.blob(&layerfs_bridge::snapshot::encode(&value).map_err(error)?);
        }
        wire::OBJECTS | wire::LENGTHS | wire::LACKING => {
            let ids = wire::ids(input)?;
            finish(input)?;
            if opcode == wire::LACKING {
                for missing in store.lacking(&ids).map_err(storage)? {
                    out.byte(u8::from(missing));
                }
            } else {
                let ports = store.ports(ObjectId::for_bytes(b"remote-read"));
                out.number(ids.len() as u64);
                if opcode == wire::OBJECTS {
                    for bytes in ports.read_canonical_batch(&ids).map_err(error)? {
                        out.blob(&bytes);
                    }
                } else {
                    for n in ports.file_lengths(&ids).map_err(error)? {
                        out.number(n);
                    }
                }
            }
        }
        wire::RESERVE => {
            let scope = ObjectId::from_bytes(input.take(32)?).map_err(error)?;
            let count = input.number()?;
            finish(input)?;
            if count != 1024 {
                return Err(error("serial reservation window"));
            }
            let (start, n) = store
                .ports(scope)
                .reserve(count)
                .map_err(|e| BackendError {
                    detail: e.to_string(),
                    unknown: true,
                })?;
            out.number(start);
            out.number(n);
        }
        wire::UPLOAD => {
            let scope = ObjectId::from_bytes(input.take(32)?).map_err(error)?;
            let base = FilesystemRootId(ObjectId::from_bytes(input.take(32)?).map_err(error)?);
            let count = input.number()?;
            if count > 512 {
                return Err(error("upload window"));
            }
            let storage_handle = store.producer().map_err(storage)?;
            let save = storage_handle.begin_save().map_err(storage)?;
            let root = FilesystemRead::new(&save, base).map_err(error)?.root();
            if root.scope() != InodeScope::from_object(scope) {
                return Err(error("upload scope"));
            }
            let policy = store.policy().construction();
            let mut total = 0;
            for _ in 0..count {
                let id = ObjectId::from_bytes(input.take(32)?).map_err(error)?;
                let role = ObjectRole::from_code(input.byte()?).map_err(error)?;
                let bytes = input.blob(wire::MAX_OBJECT)?.to_vec();
                total += bytes.len();
                if count > 1 && total >= 4 * 1024 * 1024 {
                    return Err(error("upload byte window"));
                }
                let object =
                    layerfs_telemetry::timer::Timing::disabled("remote.admit", |scope_timer| {
                        FinalizedObject::admit(
                            id,
                            role,
                            bytes,
                            policy,
                            root.scope(),
                            scope_timer.child("object"),
                        )
                    })
                    .0
                    .map_err(error)?;
                layerfs_telemetry::timer::Timing::disabled("remote.context", |timing| {
                    object.validate_context(
                        &save,
                        policy,
                        root.scope(),
                        root.root_inode().serial(),
                        timing.child("object"),
                    )
                })
                .0
                .map_err(error)?;
                save.accept(object).map_err(storage)?;
            }
            finish(input)?;
            let result = save.finish().map_err(storage)?;
            saved.canonical_bytes += result.canonical_bytes;
            saved.stored_bytes += result.stored_bytes;
            saved.metadata_bytes += result.metadata_bytes;
        }
        wire::COMMIT => {
            let binding = layerfs_bridge::snapshot::decode(input.blob(8192)?).map_err(error)?;
            let root = FilesystemRootId(ObjectId::from_bytes(input.take(32)?).map_err(error)?);
            let message = input.text(4096)?;
            let count = input.number()?;
            if count > 4096 {
                return Err(error("conflict context window"));
            }
            let conflicts = (0..count)
                .map(|_| input.text(4096))
                .collect::<Result<Vec<_>>>()?;
            finish(input)?;
            let handle = store.producer().map_err(storage)?;
            let save = handle.begin_save().map_err(storage)?;
            let mut receipt = Publication::default();
            let result = layerfs_store_service::telemetry::timed("remote.publish", |timing| {
                store.publish_candidate(
                    &handle,
                    save,
                    &CandidateInput {
                        binding,
                        root,
                        options: CommitOptions {
                            force: false,
                            message: Some(message),
                        },
                        via: CommitVia::Workspace,
                        conflicts,
                    },
                    std::mem::take(saved),
                    &mut receipt,
                    |_, _| Ok(()),
                    timing,
                )
            });
            let value = result.map_err(|e| BackendError {
                unknown: e.uncertain() || receipt.published.is_some(),
                detail: format!("{e:?}"),
            })?;
            out = encode_publication(value, receipt)?;
        }
        _ => return Err(error("unknown Store operation")),
    }
    Ok(out)
}
fn finish(input: &mut Decode<'_>) -> Result<()> {
    if input.0.is_empty() {
        Ok(())
    } else {
        Err(error("trailing request fields"))
    }
}
fn encode_publication(value: PublishedCandidate, receipt: Publication) -> Result<Encode> {
    let mut out = Encode::new();
    out.blob(&layerfs_bridge::snapshot::encode(&value.binding).map_err(error)?);
    out.raw(value.root.0.as_bytes());
    let reply = match (receipt.published, value.merge) {
        (Some(outcome), None) => Reply::Committed(outcome),
        (Some(outcome), Some(m)) => Reply::MergeCommitted(Box::new(MergedCommit {
            outcome,
            from: m.from,
            head: m.head,
            lww: m.lww,
        })),
        (None, Some(m)) => Reply::Conflict(Box::new(ConflictReport {
            head: m.head,
            base: m.from,
            markers: false,
            conflicts: m.conflicts,
            lww: m.lww,
            written: m.written,
            truncated: m.written_truncated,
        })),
        _ => return Err(error("publication without outcome")),
    };
    out.blob(&Answer { id: 1, reply }.encode().map_err(error)?);
    let saved = receipt.saved.unwrap_or_default();
    out.number(saved.canonical_bytes);
    out.number(saved.stored_bytes);
    out.number(saved.metadata_bytes);
    Ok(out)
}
pub(crate) fn decode_publication(
    bytes: &[u8],
    ours: FilesystemRootId,
) -> Result<(PublishedCandidate, Publication)> {
    let mut input = Decode(bytes);
    let binding = layerfs_bridge::snapshot::decode(input.blob(8192)?).map_err(error)?;
    let root = FilesystemRootId(ObjectId::from_bytes(input.take(32)?).map_err(error)?);
    let answer = Answer::decode(input.blob(65519)?).map_err(error)?;
    let mut receipt = Publication {
        phase: CommitPhase::Publish,
        ..Publication::default()
    };
    let mut merge = None;
    let mut pending = None;
    match answer.reply {
        Reply::Committed(outcome) => receipt.published = Some(outcome),
        Reply::MergeCommitted(m) => {
            receipt.published = Some(m.outcome);
            merge = Some(MergeReport {
                from: m.from,
                head: m.head,
                lww: m.lww,
                conflicts: Vec::new(),
                written: Vec::new(),
                written_truncated: false,
                lane_paths: None,
            });
        }
        Reply::Conflict(m) => {
            pending = Some(PendingMerge {
                local_root: root.0,
                conflicted: m.conflicts.iter().map(|c| c.path.clone()).collect(),
            });
            merge = Some(MergeReport {
                from: m.base,
                head: m.head,
                lww: m.lww,
                conflicts: m.conflicts,
                written: m.written,
                written_truncated: m.truncated,
                lane_paths: None,
            });
        }
        _ => return Err(error("candidate reply kind")),
    }
    let saved = WriteOutcome {
        canonical_bytes: input.number()?,
        stored_bytes: input.number()?,
        metadata_bytes: input.number()?,
        ..WriteOutcome::default()
    };
    receipt.saved = Some(saved);
    input.finish()?;
    Ok((
        PublishedCandidate {
            binding,
            root,
            merge,
            pending,
            replaced: (root != ours).then_some((ours.0, root.0)),
        },
        receipt,
    ))
}

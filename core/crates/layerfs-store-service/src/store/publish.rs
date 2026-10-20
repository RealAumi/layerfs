//! Store-only candidate publication, shared by local and remote construction.
use super::{bind::checked_base, CommitError, CommitOptions, CommitPhase, MergeReport, Store};
use crate::telemetry::phase;
use layerfs_content::filesystem::FilesystemRootId;
use layerfs_history::{BranchSnapshot, CommitMeta, CommitOutcome, CommitRequest, CommitVia};
use layerfs_storage::{Save, Storage, WriteOutcome};
use layerfs_telemetry::timer::{Active, TimingScope};
use std::sync::Arc;

pub struct CandidateInput {
    pub binding: BranchSnapshot,
    pub root: FilesystemRootId,
    pub options: CommitOptions,
    pub via: CommitVia,
    pub conflicts: Vec<String>,
}
pub struct Publication {
    pub phase: CommitPhase,
    pub intent: Option<CommitRequest>,
    pub saved: Option<WriteOutcome>,
    pub published: Option<CommitOutcome>,
}
impl Default for Publication {
    fn default() -> Self {
        Self {
            phase: CommitPhase::Construct,
            intent: None,
            saved: None,
            published: None,
        }
    }
}
pub struct PublishedCandidate {
    pub binding: BranchSnapshot,
    pub root: FilesystemRootId,
    pub merge: Option<MergeReport>,
    pub pending: Option<super::commit_merge::PendingMerge>,
    pub replaced: Option<(layerfs_content::ObjectId, layerfs_content::ObjectId)>,
}
impl Store {
    /// Completes a local Save, merges and publishes without calling a remote provider.
    /// The local caller prepares its install before publication; a remote caller
    /// prepares after the reply and retains any known-publication/install failure.
    #[allow(clippy::too_many_arguments)]
    pub fn publish_candidate(
        self: &Arc<Self>,
        storage: &Storage,
        save: Save<'_>,
        input: &CandidateInput,
        incoming: WriteOutcome,
        receipt: &mut Publication,
        prepare: impl FnOnce(&BranchSnapshot, FilesystemRootId) -> Result<(), CommitError>,
        timing: &TimingScope<'_, Active>,
    ) -> Result<PublishedCandidate, CommitError> {
        let snapshot = &input.binding;
        let force = input.options.force;
        let options = &input.options;
        let via = input.via;
        let candidate = input.root;
        let mut merge = None;
        let mut replaced = None;
        let built: Result<_, CommitError> = (|| {
            // Two-stage merge (#355). The head is read and merged with
            // before the publication lane, so the merge's records and its
            // whole build stay outside it. In the lane the head is read
            // again: if it moved meanwhile, only what landed in between
            // is merged into the result, in memory, then published.
            let current = phase(timing, "head", || {
                if !input.conflicts.is_empty() {
                    let marked = crate::telemetry::timed("markers", |scope| {
                        layerfs_content::merge::paths_with_markers(
                            &save,
                            candidate,
                            &input.conflicts,
                            scope,
                        )
                    })
                    .map_err(CommitError::from)?;
                    if !marked.is_empty() {
                        return Err(CommitError::Markers(marked));
                    }
                }
                self.history
                    .branch_snapshot(snapshot.branch.id)
                    .map_err(CommitError::History)?
                    .ok_or(CommitError::Context("bound Branch is absent"))
            })?;
            let moved = current.branch.head_commit != snapshot.branch.head_commit
                || current.branch.base_layer != snapshot.branch.base_layer;
            let root = if moved && !force {
                let (root, report) = phase(timing, "merge", || {
                    self.merge_candidate(&save, snapshot, &current, candidate)
                })?;
                merge = Some(report);
                root
            } else {
                candidate
            };
            // Everything that grows with the Commit runs before the lane:
            // the Save's finish, the logical count and the binding hints.
            let node = current
                .branch
                .head_commit
                .map(layerfs_history::NodeId::Commit)
                .unwrap_or(layerfs_history::NodeId::Layer(current.branch.base_layer));
            let known = phase(timing, "logical.known", || {
                self.logical_size(node).map_err(CommitError::History)
            })?;
            receipt.phase = CommitPhase::Finish;
            let saved = phase(timing, "finish", || {
                save.finish().map_err(CommitError::Storage)
            })?;
            self.note_save(&saved);
            let mut saved = saved;
            saved.canonical_bytes += incoming.canonical_bytes;
            saved.stored_bytes += incoming.stored_bytes;
            saved.metadata_bytes += incoming.metadata_bytes;
            receipt.saved = Some(saved);
            // Count only after finish has proved the root's references
            // closed, so a missing dependency stays a Storage refusal.
            let logical = phase(timing, "logical.count", || {
                logical_after(storage, current.effective_root, root, known)
            })?;
            phase(timing, "bindings", || {
                let reader = storage.reader().map_err(CommitError::Storage)?;
                super::hints::record_new_bindings(
                    &reader,
                    &*self.history,
                    Some(FilesystemRootId(current.effective_root)),
                    root,
                )
            })?;
            let lane = phase(timing, "lane", || {
                self.history.publish_lane().map_err(CommitError::History)
            })?;
            let conflicted = merge
                .as_ref()
                .is_some_and(|report: &MergeReport| !report.conflicts.is_empty());
            let (current, root, moved, logical) = if force || conflicted {
                (current, root, moved, logical)
            } else {
                let now = phase(timing, "head.lane", || {
                    self.history
                        .branch_snapshot(snapshot.branch.id)
                        .map_err(CommitError::History)?
                        .ok_or(CommitError::Context("bound Branch is absent"))
                })?;
                if now.branch.head_commit == current.branch.head_commit
                    && now.branch.base_layer == current.branch.base_layer
                {
                    (current, root, moved, logical)
                } else {
                    // The in-lane step has its own Save; its count and
                    // hints cover only what it changed in the result.
                    let step_save = storage.begin_save().map_err(CommitError::Storage)?;
                    let (stepped, step) = phase(timing, "merge.lane", || {
                        self.merge_in_lane(&step_save, &current, &now, root, candidate)
                    })?;
                    let step_saved = phase(timing, "finish.lane", || {
                        step_save.finish().map_err(CommitError::Storage)
                    })?;
                    self.note_save(&step_saved);
                    if let Some(saved) = receipt.saved.as_mut() {
                        saved.canonical_bytes += step_saved.canonical_bytes;
                        saved.stored_bytes += step_saved.stored_bytes;
                        saved.metadata_bytes += step_saved.metadata_bytes;
                    }
                    let logical = phase(timing, "logical.lane", || {
                        logical_after(storage, root.0, stepped, logical)
                    })?;
                    phase(timing, "bindings.lane", || {
                        let reader = storage.reader().map_err(CommitError::Storage)?;
                        super::hints::record_new_bindings(
                            &reader,
                            &*self.history,
                            Some(root),
                            stepped,
                        )
                    })?;
                    merge = Some(match merge.take() {
                        Some(first) => MergeReport {
                            from: first.from,
                            lww: first.lww.into_iter().chain(step.lww).collect(),
                            ..step
                        },
                        None => step,
                    });
                    (now, stepped, true, logical)
                }
            };
            Ok((root, candidate, current, moved, logical, lane))
        })();
        let (candidate, ours, current, moved, logical, lane) = built?;
        if candidate != ours {
            replaced = Some((ours.0, candidate.0));
        }
        let conflicted = merge
            .as_ref()
            .is_some_and(|report: &MergeReport| !report.conflicts.is_empty());
        // A merge is published against the head it merged with; a forced
        // or unmoved Commit against the head the Workspace bound.
        let target = if merge.is_some() { &current } else { snapshot };
        if !conflicted {
            receipt.intent = Some(CommitRequest {
                branch: snapshot.branch.id,
                expected_head: target.branch.head_commit,
                expected_base: target.branch.base_layer,
                expected_root: target.effective_root,
                candidate_root: candidate.0,
                profile: snapshot.profile,
                scope: snapshot.scope,
                second_parent: None,
                meta: CommitMeta {
                    message: Some(
                        options
                            .message
                            .clone()
                            .unwrap_or_else(|| "Commit Workspace changes".into()),
                    ),
                    statistics: {
                        let saved = receipt
                            .saved
                            .as_ref()
                            .ok_or(CommitError::Context("finished Save"))?;
                        layerfs_history::CommitStatistics {
                            logical,
                            new_canonical: saved.canonical_bytes,
                            new_stored: saved.stored_bytes,
                            new_metadata: saved.metadata_bytes,
                        }
                    },
                    merged_from: merge.as_ref().map(|_| {
                        snapshot
                            .branch
                            .head_commit
                            .map(layerfs_history::NodeId::Commit)
                            .unwrap_or(layerfs_history::NodeId::Layer(snapshot.branch.base_layer))
                    }),
                    lww: merge
                        .as_ref()
                        .map_or_else(Vec::new, |report| report.lww.clone()),
                    ..CommitMeta::new(via)
                },
                force: force && moved,
            });
        }
        receipt.phase = CommitPhase::Validate;
        let mut next = target.clone();
        next.effective_root = candidate.0;
        phase(timing, "validate", || {
            let ports = self.ports(snapshot.scope);
            let client = ports.client();
            let original = checked_base(client.clone(), snapshot).map_err(CommitError::from)?;
            let checked = checked_base(client, &next).map_err(CommitError::from)?;
            if original.root().root_inode() != checked.root().root_inode() {
                return Err(CommitError::Context(
                    "candidate changes root inode identity",
                ));
            }
            prepare(&next, candidate)
        })?;
        let pending = if conflicted {
            // Nothing is published: the history binding follows the head
            // merged with, and the merge stays the local base.
            next = current.clone();
            Some(super::commit_merge::PendingMerge {
                local_root: candidate.0,
                conflicted: merge
                    .as_ref()
                    .map(|report| report.conflicts.iter().map(|c| c.path.clone()).collect())
                    .unwrap_or_default(),
            })
        } else {
            receipt.phase = CommitPhase::Publish;
            let intent = receipt.intent.as_ref().expect("checked intent");
            let outcome = phase(timing, "publish", || {
                self.history
                    .commit_branch(intent)
                    .map_err(CommitError::History)
            })?;
            let (head, root) = match &outcome {
                CommitOutcome::Committed { record, .. } => (Some(record.id), record.root),
                CommitOutcome::UpToDate { head, root } => (*head, *root),
            };
            drop(lane);
            receipt.published = Some(outcome);
            if root != candidate.0 {
                return Err(CommitError::Context(
                    "publication differs from saved candidate",
                ));
            }
            next.branch.head_commit = head;
            next.head_root = head.map(|_| root);
            None
        };
        Ok(PublishedCandidate {
            binding: next,
            root: candidate,
            merge,
            pending,
            replaced,
        })
    }
}
/// Logical size of `after`, from `before`'s known size and the change
/// between them. File lengths come from the Store catalogue a window at
/// a time (`Reader::file_lengths`), never from reading file payloads; a
/// Storage refusal keeps its original error.
fn logical_after(
    storage: &layerfs_storage::Storage,
    before: layerfs_content::ObjectId,
    after: FilesystemRootId,
    known: u64,
) -> Result<u64, CommitError> {
    let reader = storage.reader().map_err(CommitError::Storage)?;
    let mut refused = None;
    let counted = layerfs_content::filesystem::statistics::logical_size_after_with(
        &reader,
        FilesystemRootId(before),
        after,
        known,
        &mut |roots| {
            reader.file_lengths(roots).map_err(|error| {
                refused = Some(error);
                layerfs_content::ContentError::OutputRejected
            })
        },
    );
    match (counted, refused) {
        (Ok(size), _) => Ok(size),
        (Err(_), Some(error)) => Err(CommitError::Storage(error)),
        (Err(error), None) => Err(CommitError::Content {
            error,
            provider: None,
        }),
    }
}

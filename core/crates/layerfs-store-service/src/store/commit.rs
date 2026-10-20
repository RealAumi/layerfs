//! One synchronous Content/Save/history producer and exact paired local install.
use super::{
    BoundWorkspace, CommitError, CommitFailure, CommitOptions, CommitPhase, CommitSuccess,
};
use crate::telemetry::phase;
use layerfs_content::filesystem::FilesystemRootId;
use layerfs_history::{BranchSnapshot, CommitOutcome, CommitVia};
use layerfs_overlay::Capture;
use layerfs_storage::Save;
use layerfs_telemetry::timer::{Active, TimingScope};
use layerfs_workspace::WorkspaceError;
use std::sync::atomic::Ordering;

/// Admission belongs to exactly one invocation. It stays held unless that
/// invocation establishes a safe disposition, including its captured releases.
/// Unwinding or an unknown result conservatively retains admission.
pub(super) struct CommitAdmission<'a> {
    workspace: &'a BoundWorkspace,
    pub(super) released: bool,
}
impl Drop for CommitAdmission<'_> {
    fn drop(&mut self) {
        if self.released {
            self.workspace.committing.store(false, Ordering::Release);
        }
    }
}

impl BoundWorkspace {
    /// Captures once and drives one caller-owned Content producer over that
    /// exact context. The producer must represent the capture faithfully; live
    /// namespace normalization is a separate constructor, not an implicit Init.
    /// No owner or Workspace mutex spans construction or provider I/O. On definite
    /// nonpublication one local resolution preserves the accepted view; unknown
    /// and known-publication/install failure retain original custody.
    pub fn commit(
        &self,
        construct: impl FnOnce(
            &Save<'_>,
            Capture,
            &BranchSnapshot,
        ) -> Result<FilesystemRootId, CommitError>,
    ) -> Result<CommitSuccess, Box<CommitFailure>> {
        let mut admission = self.admit_commit()?;
        let result = crate::telemetry::timed("commit", |timing| {
            self.commit_admitted(
                construct,
                || (),
                &CommitOptions::default(),
                CommitVia::Workspace,
                timing,
            )
        });
        admission.released = match &result {
            Ok(_) => true,
            Err(failure) => failure.locally_settled,
        };
        result
    }
    pub(super) fn admit_commit(&self) -> Result<CommitAdmission<'_>, Box<CommitFailure>> {
        self.committing
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| {
                Box::new(CommitFailure::new(
                    CommitError::InFlight,
                    self.identity,
                    self.route(),
                ))
            })?;
        Ok(CommitAdmission {
            workspace: self,
            released: false,
        })
    }
    /// The admitted invocation owns the flag through any wrapper's releases.
    /// `published` runs once, only after History answered this publication
    /// with the saved root; a failed, unknown or conflicted publication, and
    /// every earlier failure, never runs it.
    ///
    /// When the Branch head moved since the Workspace bound, the candidate is
    /// merged into the head in the same Save unless `force`. A clean merge is
    /// published against that head and installed as the new base. A conflict
    /// publishes nothing: the merge, with marker blocks, is installed as the
    /// Workspace's local base and its history binding moves to the head.
    /// Each phase is a child of `timing`; untraced, it records nothing.
    pub(super) fn commit_admitted(
        &self,
        construct: impl FnOnce(
            &Save<'_>,
            Capture,
            &BranchSnapshot,
        ) -> Result<FilesystemRootId, CommitError>,
        published: impl FnOnce(),
        options: &CommitOptions,
        via: CommitVia,
        timing: &TimingScope<'_, Active>,
    ) -> Result<CommitSuccess, Box<CommitFailure>> {
        let mut retained = CommitFailure::new(
            CommitError::Context("incomplete Commit"),
            self.identity,
            self.route(),
        );
        let mut producer = None;
        let mut merge = None;
        let mut replaced = None;
        let result = (|| {
            let store = self.store.local().ok_or(CommitError::Context(
                "local Save callback on remote Workspace",
            ))?;
            let snapshot = self.snapshot().map_err(CommitError::Workspace)?;
            retained.binding = Some(snapshot.clone());
            let local = self.local_root(&snapshot)?;
            let original_base = self.workspace.base().map_err(CommitError::Workspace)?;
            // Nothing above the installed floor and the head where the
            // Workspace bound it: UpToDate with no capture, Save, lane or
            // install (#352 c04 records why the answer stays exact).
            let state = phase(timing, "uptodate.state", || {
                self.job(|job_client: &crate::OwnerClient, job_route| job_client.state(job_route))
                    .map_err(CommitError::Owner)
            })?;
            if state.dirty_inodes == 0
                && state.dirty_directory_entries == 0
                && state.captured.is_none()
                && state.consolidating.is_none()
                && state.base_root == local.to_bytes()
                && self
                    .pending_conflicts()
                    .map_err(CommitError::Workspace)?
                    .is_none()
            {
                let current = phase(timing, "uptodate.head", || {
                    store
                        .history
                        .branch_snapshot(snapshot.branch.id)
                        .map_err(CommitError::History)?
                        .ok_or(CommitError::Context("bound Branch is absent"))
                })?;
                if current.branch.head_commit == snapshot.branch.head_commit
                    && current.branch.base_layer == snapshot.branch.base_layer
                {
                    retained.published = Some(CommitOutcome::UpToDate {
                        head: current.branch.head_commit,
                        root: current.effective_root,
                    });
                    retained.saved = Some(Default::default());
                    retained.storage = Some(Default::default());
                    return Ok(());
                }
            }
            retained.phase = CommitPhase::Capture;
            let capture = phase(timing, "capture", || {
                self.job(|job_client: &crate::OwnerClient, job_route| job_client.capture(job_route))
                    .map_err(CommitError::Owner)
            })?;
            retained.capture = Some(capture);
            if capture.base_root != local.to_bytes() || original_base.identity().0 != local {
                return Err(CommitError::Context(
                    "capture differs from bound history root",
                ));
            }
            retained.phase = CommitPhase::Begin;
            let (storage, before) = phase(timing, "producer", || {
                self.producer.take(&store).map_err(CommitError::Storage)
            })?;
            let mut publication = super::publish::Publication::default();
            let built = (|| {
                let save = phase(timing, "begin", || {
                    storage.begin_save().map_err(CommitError::Storage)
                })?;
                retained.phase = CommitPhase::Construct;
                let candidate =
                    match phase(timing, "construct", || construct(&save, capture, &snapshot)) {
                        Ok(root) => root,
                        Err(original) => {
                            return Err(match save.take_failure() {
                                Some(storage) => CommitError::Construction {
                                    original: Box::new(original),
                                    storage,
                                },
                                None => original,
                            })
                        }
                    };
                store.publish_candidate(
                    &storage,
                    save,
                    &super::publish::CandidateInput {
                        binding: snapshot.clone(),
                        root: candidate,
                        options: options.clone(),
                        via,
                        conflicts: self
                            .pending_conflicts()
                            .map_err(CommitError::Workspace)?
                            .unwrap_or_default(),
                    },
                    Default::default(),
                    &mut publication,
                    |_, candidate| {
                        let client = store.ports(snapshot.scope).client();
                        retained.prepared = Some(
                            self.workspace
                                .scoped(client)
                                .map_err(CommitError::Workspace)?
                                .prepare_base_install(capture, candidate)
                                .map_err(CommitError::Workspace)?,
                        );
                        Ok(())
                    },
                    timing,
                )
            })();
            retained.storage = Some(super::producer::since(storage.diagnostics(), before));
            retained.phase = publication.phase;
            retained.intent = publication.intent;
            retained.saved = publication.saved;
            retained.published = publication.published;
            let result = built?;
            replaced = result.replaced;
            merge = result.merge;
            let next = result.binding;
            let pending = result.pending;
            if retained.published.is_some() {
                published();
            }
            producer = Some(storage);
            retained.phase = CommitPhase::Install;
            let prepared = retained.prepared.take().expect("prepared install");
            phase(timing, "install", || {
                self.job(|job_client: &crate::OwnerClient, route| {
                    job_client.install_prepared(route, self.workspace.clone(), prepared)
                })
                .map_err(CommitError::Owner)
            })?;
            *self
                .snapshot
                .lock()
                .map_err(|_| CommitError::Workspace(WorkspaceError::BindingPoisoned))? = next;
            *self
                .pending
                .lock()
                .map_err(|_| CommitError::Workspace(WorkspaceError::BindingPoisoned))? = pending;
            Ok(())
        })();
        if let Err(error) = result {
            retained.error = error;
            return Err(self.settle_failure(retained));
        }
        if let Some(storage) = producer {
            self.producer.keep(storage);
        }
        Ok(CommitSuccess {
            history: retained.published,
            merge,
            saved: retained.saved.expect("known Save"),
            storage: retained.storage.expect("producer observations"),
            capture: retained.capture,
            namespace: None,
            replaced,
        })
    }
}

//! Captured local construction and known remote publication/install boundaries.
use super::{
    backend::RemoteContext, publish::CandidateInput, BoundWorkspace, CapturedConstruction,
    CommitError, CommitFailure, CommitOptions, CommitPhase, CommitSuccess, RemoteBuild,
};
use layerfs_content::filesystem::FilesystemRootId;
use layerfs_content::{ContentError, ContentResult, FinalizedConsumer, FinalizedObject};
use layerfs_history::CommitVia;
use std::sync::Arc;

struct Sink<'a>(&'a dyn RemoteBuild);
impl FinalizedConsumer for Sink<'_> {
    fn accept(&mut self, object: FinalizedObject) -> ContentResult<()> {
        self.0
            .accept(object)
            .map_err(|_| ContentError::OutputRejected)
    }
}
impl BoundWorkspace {
    pub(super) fn commit_remote(
        &self,
        remote: &Arc<RemoteContext>,
        options: &CommitOptions,
        via: CommitVia,
    ) -> Result<CommitSuccess, Box<CommitFailure>> {
        let mut admission = self.admit_commit()?;
        let mut retained = CommitFailure::new(
            CommitError::Context("incomplete remote Commit"),
            self.identity,
            self.route(),
        );
        let mut held = CapturedConstruction::default();
        let mut build = None;
        let mut outcome = None;
        let result = (|| {
            let binding = self.snapshot().map_err(CommitError::Workspace)?;
            retained.binding = Some(binding.clone());
            let local = self.local_root(&binding)?;
            retained.phase = CommitPhase::Capture;
            let capture = self
                .job(|owner, route| owner.capture(route))
                .map_err(CommitError::Owner)?;
            retained.capture = Some(capture);
            if capture.base_root != local.to_bytes() {
                return Err(CommitError::Context("remote capture base"));
            }
            build = Some(remote.source.build().map_err(CommitError::Remote)?);
            let objects = build.as_ref().expect("created build");
            retained.phase = CommitPhase::Construct;
            let root = self
                .construct_captured(
                    objects.reader(),
                    &mut Sink(objects.as_ref()),
                    capture,
                    &mut held,
                    None,
                )
                .map_err(|cause| objects.failure().map(CommitError::Remote).unwrap_or(cause))?;
            let remote_failure =
                |cause: ContentError| objects.failure().map_or(cause.into(), CommitError::Remote);
            // With ignored names kept local, `root` is the whole local tree and
            // the candidate its projection onto the published side.
            let candidate = if remote.ignore {
                let published = FilesystemRootId(self.published_root(&binding)?);
                self.ignore_state()?
                    .project(
                        objects.reader(),
                        &mut Sink(objects.as_ref()),
                        self.workspace.hints(),
                        [published, FilesystemRootId(local), root],
                    )
                    .map_err(remote_failure)?
            } else {
                root
            };
            retained.phase = CommitPhase::Publish;
            let (published, receipt) = objects
                .publish(&CandidateInput {
                    binding: binding.clone(),
                    root: candidate,
                    options: options.clone(),
                    via,
                    conflicts: self
                        .pending_conflicts()
                        .map_err(CommitError::Workspace)?
                        .unwrap_or_default(),
                })
                .map_err(CommitError::Remote)?;
            if remote.ignore && receipt.published.is_some() {
                self.ignore_state()?.published();
            }
            retained.saved = receipt.saved;
            retained.published = receipt.published;
            retained.intent = receipt.intent;
            retained.phase = CommitPhase::Install;
            let installed = if remote.ignore {
                self.ignore_state()?
                    .rebase(
                        objects.reader(),
                        &mut Sink(objects.as_ref()),
                        self.workspace.hints(),
                        [candidate, published.root, root],
                    )
                    .map_err(remote_failure)?
            } else {
                published.root
            };
            let client = self.store.ports(binding.scope).client();
            let mut checked = published.binding.clone();
            checked.effective_root = installed.0;
            let base =
                super::bind::checked_base(client.clone(), &checked).map_err(CommitError::from)?;
            if base.root().root_inode()
                != self
                    .workspace
                    .base()
                    .map_err(CommitError::Workspace)?
                    .root()
                    .root_inode()
            {
                return Err(CommitError::Context("remote root inode changed"));
            }
            let prepared = self
                .workspace
                .scoped(client)
                .map_err(CommitError::Workspace)?
                .prepare_base_install(capture, installed)
                .map_err(CommitError::Workspace)?;
            self.job(|owner, route| {
                owner.install_prepared(route, self.workspace.clone(), prepared)
            })
            .map_err(CommitError::Owner)?;
            *self
                .snapshot
                .lock()
                .map_err(|_| CommitError::Context("binding poisoned"))? = published.binding;
            *self
                .pending
                .lock()
                .map_err(|_| CommitError::Context("pending merge poisoned"))? = published.pending;
            self.ignore_state()?.base =
                (installed != published.root).then_some(super::ignore::LocalBase {
                    local: installed.0,
                    published: published.root.0,
                });
            outcome = Some((published.merge, published.replaced));
            Ok(())
        })();
        if let Err(error) = result {
            retained.error = error;
            let mut failed = self.settle_failure(retained);
            if failed.locally_settled {
                self.release_captured(&mut held);
            }
            admission.released = failed.locally_settled && !held.retained();
            failed.namespace = Some(held);
            failed.remote = build;
            return Err(failed);
        }
        self.release_captured(&mut held);
        admission.released = !held.retained();
        let (merge, replaced) = outcome.expect("known outcome");
        Ok(CommitSuccess {
            history: retained.published,
            merge,
            saved: retained.saved.unwrap_or_default(),
            storage: Default::default(),
            capture: retained.capture,
            namespace: Some(held),
            replaced,
        })
    }
}

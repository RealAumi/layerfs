//! Workspace-facing boundary. Physical Store providers never cross it.
use super::ignore::{IgnoreState, LocalBase, RestorePoint};
use super::publish::{CandidateInput, Publication, PublishedCandidate};
use super::{BindRequest, BindSuccess, BoundWorkspace, PortError, Recognizer, Store, StorePorts};
use layerfs_content::{AuthenticatedObjects, FinalizedObject, ObjectId};
use layerfs_history::{BranchId, BranchSnapshot, WorkspaceId};
use layerfs_storage::StoragePolicy;
use layerfs_workspace::{CanonicalCache, CanonicalClient, Workspace};
use std::sync::{atomic::AtomicU64, Arc, Mutex};

#[derive(Clone, Debug)]
pub struct BackendError {
    pub detail: String,
    pub unknown: bool,
}
impl std::fmt::Display for BackendError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.detail)
    }
}
impl std::error::Error for BackendError {}

/// One construction's indexed objects; an unknown result retains this owner.
pub trait RemoteBuild: Send + Sync + std::fmt::Debug {
    fn reader(&self) -> &dyn AuthenticatedObjects;
    fn failure(&self) -> Option<BackendError>;
    fn accept(&self, object: FinalizedObject) -> Result<(), BackendError>;
    fn publish(
        &self,
        input: &CandidateInput,
    ) -> Result<(PublishedCandidate, Publication), BackendError>;
}
/// Canonical/semantic operations only, with one attempted call and exact failure.
pub trait RemoteStore: Send + Sync {
    fn restore(
        &self,
        _head: &BranchSnapshot,
        _key: &str,
    ) -> Result<Option<RestorePoint>, BackendError> {
        Ok(None)
    }
    fn save_restore(&self, _key: &str, _point: &RestorePoint) -> Result<(), BackendError> {
        Err(BackendError {
            detail: "restore unsupported".into(),
            unknown: false,
        })
    }
    fn policy(&self) -> StoragePolicy;
    fn snapshot(&self, branch: BranchId) -> Result<BranchSnapshot, BackendError>;
    fn objects(&self, ids: &[ObjectId]) -> Result<Vec<Vec<u8>>, BackendError>;
    fn lengths(&self, ids: &[ObjectId]) -> Result<Vec<u64>, BackendError>;
    fn reserve(&self, scope: ObjectId, count: u64) -> Result<(u64, u64), BackendError>;
    fn build(&self) -> Result<Box<dyn RemoteBuild>, BackendError>;
}
pub struct RemoteContext {
    pub source: Arc<dyn RemoteStore>,
    pub(super) cache: Arc<CanonicalCache>,
    pub(super) resident: Arc<CanonicalClient>,
    pub(super) recognizer: Recognizer,
    pub(super) low_water: AtomicU64,
    /// Commits keep Git-ignored names local (see `super::ignore`).
    pub(super) ignore: bool,
}
#[derive(Clone)]
pub enum WorkspaceBackend {
    Local(Arc<Store>),
    Remote(Arc<RemoteContext>),
}
impl From<Arc<Store>> for WorkspaceBackend {
    fn from(store: Arc<Store>) -> Self {
        Self::Local(store)
    }
}
impl WorkspaceBackend {
    /// `ignore`: Commits keep Git-ignored names local (see `super::ignore`).
    pub fn remote(source: Arc<dyn RemoteStore>, cache_bytes: usize, ignore: bool) -> Self {
        let cache = Arc::new(CanonicalCache::new(cache_bytes));
        Self::Remote(Arc::new(RemoteContext {
            source,
            resident: Arc::new(CanonicalClient::resident(cache.clone())),
            cache,
            recognizer: Recognizer::new(),
            low_water: AtomicU64::new(0),
            ignore,
        }))
    }
    pub fn local(&self) -> Option<Arc<Store>> {
        match self {
            Self::Local(s) => Some(s.clone()),
            Self::Remote(_) => None,
        }
    }
    pub fn policy(&self) -> StoragePolicy {
        match self {
            Self::Local(s) => s.policy(),
            Self::Remote(s) => s.source.policy(),
        }
    }
    pub fn ports(&self, scope: ObjectId) -> Arc<StorePorts> {
        match self {
            Self::Local(s) => s.ports(scope),
            Self::Remote(s) => StorePorts::remote(s.clone(), scope),
        }
    }
    pub fn ports_for(&self, scope: ObjectId, workspace: WorkspaceId) -> Arc<StorePorts> {
        match self {
            Self::Local(s) => s.ports_for(scope, workspace),
            Self::Remote(s) => StorePorts::remote(s.clone(), scope),
        }
    }
    pub fn bind(
        &self,
        owner: crate::OwnerClient,
        request: BindRequest,
    ) -> Result<BindSuccess, super::BindRefusal> {
        self.bind_restore(owner, request, None)
    }
    /// Opt-in remote restore; the caller owns single-writer discipline for a key.
    pub fn bind_restore(
        &self,
        owner: crate::OwnerClient,
        request: BindRequest,
        restore_key: Option<String>,
    ) -> Result<BindSuccess, super::BindRefusal> {
        if let Self::Local(store) = self {
            return store.bind(owner, request);
        }
        let Self::Remote(remote) = self else {
            unreachable!()
        };
        let mut phase = super::BindPhase::Snapshot;
        let mut snapshot = None;
        let result = (|| {
            let mut binding = remote
                .source
                .snapshot(request.branch)
                .map_err(|e| super::BindError::Read(Arc::new(PortError::Remote(e))))?;
            let mut ignore = IgnoreState::default();
            let restore_key = restore_key.filter(|_| remote.ignore);
            if let Some(key) = &restore_key {
                if let Some(point) = remote
                    .source
                    .restore(&binding, key)
                    .map_err(|e| super::BindError::Read(Arc::new(PortError::Remote(e))))?
                {
                    binding = point.binding;
                    ignore.base = Some(LocalBase {
                        local: point.local,
                        published: point.published,
                    });
                    ignore.pending = point.seeds;
                }
            }
            snapshot = Some(binding.clone());
            let mut local = binding.clone();
            if let Some(base) = ignore.base {
                local.effective_root = base.local;
            }
            phase = super::BindPhase::Root;
            let ports = self.ports_for(binding.scope, request.workspace);
            let base = super::bind::checked_base(ports.client(), &local).map_err(|error| {
                super::BindError::Content {
                    error,
                    provider: ports.failure().ok().flatten(),
                }
            })?;
            phase = super::BindPhase::Open;
            let route = owner
                .open(
                    None,
                    request.workspace.to_bytes(),
                    local.effective_root.to_bytes(),
                )
                .map_err(super::BindError::Owner)?;
            let owner = owner
                .workspace_client(route)
                .map_err(super::BindError::Owner)?;
            Ok(BindSuccess {
                workspace: BoundWorkspace {
                    store: self.clone(),
                    owner,
                    snapshot: Mutex::new(binding),
                    identity: request.workspace,
                    workspace: Arc::new(Workspace::bind(route, base)),
                    committing: Default::default(),
                    producer: Default::default(),
                    pending: Mutex::new(None),
                    ignore: Mutex::new(ignore),
                    restore_key,
                },
            })
        })();
        result.map_err(|error| super::BindRefusal {
            phase,
            request,
            snapshot,
            error,
        })
    }
}

impl Store {
    /// Bounded canonical presence check; physical locators remain inside the Store.
    pub fn lacking(&self, ids: &[ObjectId]) -> layerfs_storage::StorageResult<Vec<bool>> {
        if ids.len() > 4096 {
            return Err(layerfs_storage::StorageError::Integrity("presence window"));
        }
        let mut unique = ids.to_vec();
        unique.sort_unstable();
        unique.dedup();
        let mut located = Vec::new();
        self.writer.locate(&unique, &mut located)?;
        let present: std::collections::BTreeSet<_> =
            located.iter().map(|row| row.location.object_id).collect();
        Ok(ids.iter().map(|id| !present.contains(id)).collect())
    }
}

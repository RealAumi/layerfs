//! One operation's original failures over batched public Store demands.
use super::{read_handle::ReadSession, ReadAdmissionError, Store};
use layerfs_content::{AuthenticatedObjects, ContentError, ContentResult, ObjectId};
use layerfs_history::{HistoryError, ReserveRequest, WorkspaceId};
use layerfs_storage::StorageError;
use layerfs_workspace::{
    CanonicalClient, FileLengths, InodeSerials, Workspace, WorkspaceError, WorkspaceResult,
};
use std::{
    fmt,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};

/// Original provider failure, retained independently from shared cache state.
#[derive(Debug)]
pub enum PortError {
    Storage(StorageError),
    History(HistoryError),
    Poisoned,
    ConcurrentDemand,
    ReadAdmission(ReadAdmissionError),
    Remote(super::BackendError),
}
impl fmt::Display for PortError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Store port: {self:?}")
    }
}
impl std::error::Error for PortError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Storage(e) => Some(e),
            Self::History(e) => Some(e),
            Self::ReadAdmission(e) => Some(e),
            Self::Remote(e) => Some(e),
            Self::Poisoned | Self::ConcurrentDemand => None,
        }
    }
}
/// Fresh demand custody for one operation, never stored in the immutable cache.
pub struct StorePorts {
    source: Source,
    scope: ObjectId,
    failure: Mutex<Option<Arc<PortError>>>,
    attempting: AtomicBool,
}
impl Store {
    pub fn ports(self: &Arc<Self>, scope: ObjectId) -> Arc<StorePorts> {
        self.ports_in(scope, None)
    }
    pub fn ports_for(self: &Arc<Self>, scope: ObjectId, workspace: WorkspaceId) -> Arc<StorePorts> {
        self.ports_in(scope, Some(workspace))
    }
    fn ports_in(
        self: &Arc<Self>,
        scope: ObjectId,
        workspace: Option<WorkspaceId>,
    ) -> Arc<StorePorts> {
        Arc::new(StorePorts {
            source: Source::Local(self.clone(), self.reader(workspace)),
            scope,
            failure: Mutex::new(None),
            attempting: AtomicBool::new(false),
        })
    }
}
#[derive(Clone)]
enum Source {
    Local(Arc<Store>, Result<Arc<ReadSession>, ReadAdmissionError>),
    Remote(Arc<super::backend::RemoteContext>),
}
impl StorePorts {
    pub(super) fn remote(
        context: Arc<super::backend::RemoteContext>,
        scope: ObjectId,
    ) -> Arc<Self> {
        Arc::new(Self {
            source: Source::Remote(context),
            scope,
            failure: Mutex::new(None),
            attempting: AtomicBool::new(false),
        })
    }
    fn cache(&self) -> Arc<layerfs_workspace::CanonicalCache> {
        match &self.source {
            Source::Local(s, _) => s.cache.clone(),
            Source::Remote(s) => s.cache.clone(),
        }
    }
    pub fn resident(&self) -> Arc<CanonicalClient> {
        match &self.source {
            Source::Local(s, _) => s.resident.clone(),
            Source::Remote(s) => s.resident.clone(),
        }
    }
    /// The daemon's write-recognizer slots.
    pub fn recognizer(&self) -> &super::Recognizer {
        match &self.source {
            Source::Local(s, _) => &s.recognizer,
            Source::Remote(s) => &s.recognizer,
        }
    }
    /// Fresh demand custody over the same scope and opened reader. A failure in
    /// it stays there and never becomes this operation's.
    pub fn fresh(&self) -> Arc<Self> {
        Arc::new(Self {
            source: self.source.clone(),
            scope: self.scope,
            failure: Mutex::new(None),
            attempting: AtomicBool::new(false),
        })
    }
    pub fn client(self: &Arc<Self>) -> Arc<CanonicalClient> {
        Arc::new(CanonicalClient::with_cache(
            self.clone(),
            Some(self.clone()),
            self.cache(),
        ))
    }
    /// The first exact failure; poison is itself an explicit refusal.
    pub fn failure(&self) -> Result<Option<Arc<PortError>>, PortError> {
        self.failure
            .lock()
            .map(|first| first.clone())
            .map_err(|_| PortError::Poisoned)
    }
    fn attempt<T>(
        &self,
        call: impl FnOnce() -> Result<T, Arc<PortError>>,
    ) -> Result<T, Arc<PortError>> {
        self.attempting
            .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
            .map_err(|_| Arc::new(PortError::ConcurrentDemand))?;
        let _attempt = Attempt(&self.attempting);
        if let Some(error) = self.failure().map_err(Arc::new)? {
            return Err(error);
        }
        call().inspect_err(|error| {
            // Retain this original failure even if an earlier observer poisoned
            // the mutex. Subsequent access still reports the poison explicitly.
            let mut first = self
                .failure
                .lock()
                .unwrap_or_else(|poison| poison.into_inner());
            *first = Some(error.clone());
        })
    }
    /// One unused serial for a create. An early refill below the Store's
    /// low-water is made in a custody scope of its own: its failure is
    /// returned beside the serial and never becomes this operation's.
    pub fn take_serial(
        &self,
        workspace: &Workspace,
    ) -> WorkspaceResult<(u64, Option<WorkspaceError>)> {
        let low_water = match &self.source {
            Source::Local(s, _) => s.serial_low_water.load(Ordering::Relaxed),
            Source::Remote(s) => s.low_water.load(Ordering::Relaxed),
        };
        workspace.next_serial_with_low_water(self, &EarlyRefill(self), low_water)
    }
    fn reader(&self) -> Result<&Arc<ReadSession>, Arc<PortError>> {
        let Source::Local(store, reader) = &self.source else {
            return Err(Arc::new(PortError::Remote(super::BackendError {
                detail: "remote has no SQL reader".into(),
                unknown: false,
            })));
        };
        store
            .readers
            .admit()
            .map_err(|e| Arc::new(PortError::ReadAdmission(e)))?;
        reader
            .as_ref()
            .map_err(|e| Arc::new(PortError::ReadAdmission(*e)))
    }
    /// Bounded grouped metadata demand, with original cardinality/order.
    pub fn file_lengths(&self, ids: &[ObjectId]) -> Result<Vec<u64>, Arc<PortError>> {
        self.attempt(|| match &self.source {
            Source::Local(_, _) => self.reader()?.file_lengths(ids),
            Source::Remote(s) => s
                .source
                .lengths(ids)
                .map_err(|e| Arc::new(PortError::Remote(e))),
        })
    }
}
impl StorePorts {
    /// One object demand through caches the caller keeps across its demands,
    /// under this operation's custody (#352 F-035).
    pub fn objects_with(
        &self,
        cache: &mut layerfs_storage::ReadCache,
        ids: &[ObjectId],
    ) -> Result<Vec<Vec<u8>>, Arc<PortError>> {
        self.attempt(|| match &self.source {
            Source::Local(_, _) => self.reader()?.objects_with(cache, ids),
            Source::Remote(s) => s
                .source
                .objects(ids)
                .map_err(|e| Arc::new(PortError::Remote(e))),
        })
    }
}
impl AuthenticatedObjects for StorePorts {
    fn read_canonical_batch(&self, ids: &[ObjectId]) -> ContentResult<Vec<Vec<u8>>> {
        self.attempt(|| match &self.source {
            Source::Local(_, _) => self.reader()?.objects(ids),
            Source::Remote(s) => s
                .source
                .objects(ids)
                .map_err(|e| Arc::new(PortError::Remote(e))),
        })
        .map_err(|error| match error.as_ref() {
            PortError::Storage(StorageError::ObjectMissing(_)) => ContentError::MissingObject,
            PortError::Storage(StorageError::Content(error)) => error.clone(),
            _ => ContentError::ProviderFailure {
                what: "Store object demand",
            },
        })
    }
}
impl FileLengths for StorePorts {
    fn file_length(&self, id: ObjectId) -> WorkspaceResult<u64> {
        let values = self
            .file_lengths(&[id])
            .map_err(|e| WorkspaceError::Service(Box::new(e)))?;
        if values.len() != 1 {
            return Err(ContentError::BatchCardinality {
                requested: 1,
                returned: values.len(),
            }
            .into());
        }
        Ok(values[0])
    }
    fn file_lengths(&self, ids: &[ObjectId]) -> WorkspaceResult<Vec<u64>> {
        let values = StorePorts::file_lengths(self, ids)
            .map_err(|e| WorkspaceError::Service(Box::new(e)))?;
        if values.len() != ids.len() {
            return Err(ContentError::BatchCardinality {
                requested: ids.len(),
                returned: values.len(),
            }
            .into());
        }
        Ok(values)
    }
}
impl InodeSerials for StorePorts {
    fn reserve(&self, count: u64) -> WorkspaceResult<(u64, u64)> {
        self.reserve_block(count, count)
    }
}
/// Serials one catalog reservation takes for the Store's pool (#352 F-025
/// fix 4): an SDK file call the pool can serve opens no writer transaction.
const POOL_BLOCK: u64 = 4096;
impl StorePorts {
    /// `count` serials of this scope for an SDK file call: from the Store's
    /// pool when it holds them (memory only), else one catalog reservation of
    /// `POOL_BLOCK`, whose rest becomes the pool. Mounted Workspaces keep
    /// their own windows ([`InodeSerials::reserve`]). One attempt; serials
    /// stay consumed whether used or not, as every reservation's do.
    pub fn reserve_pooled(&self, count: u64) -> WorkspaceResult<(u64, u64)> {
        if let Source::Local(store, _) = &self.source {
            if let Some(range) = store.pooled_serials(self.scope, count) {
                return Ok(range);
            }
        }
        self.reserve_block(count, count.max(POOL_BLOCK))
    }
    /// One catalog reservation of `block` serials; the first `count` are the
    /// answer and any rest becomes the Store's pool for this scope.
    fn reserve_block(&self, count: u64, block: u64) -> WorkspaceResult<(u64, u64)> {
        self.attempt(|| {
            let store = match &self.source {
                Source::Remote(s) => {
                    return s
                        .source
                        .reserve(self.scope, count)
                        .map_err(|e| Arc::new(PortError::Remote(e)))
                }
                Source::Local(s, _) => s,
            };
            store.counts.serials.fetch_add(1, Ordering::Relaxed);
            let range = store
                .history
                .reserve_inodes(&ReserveRequest {
                    scope: self.scope,
                    count: block,
                })
                .map_err(|error| Arc::new(PortError::History(error)))?;
            if range.scope != self.scope || range.count != block {
                return Err(Arc::new(PortError::History(HistoryError::Integrity(
                    "inode reservation identity",
                ))));
            }
            let end = range
                .end()
                .map_err(|error| Arc::new(PortError::History(error)))?;
            if block > count {
                store.pool_serials(self.scope, range.start + count, end);
            }
            Ok((range.start, count))
        })
        .map_err(|e| WorkspaceError::Service(Box::new(e)))
    }
}
/// Fresh ports over the same scope, created only when the attempt is made.
struct EarlyRefill<'a>(&'a StorePorts);
impl InodeSerials for EarlyRefill<'_> {
    fn reserve(&self, count: u64) -> WorkspaceResult<(u64, u64)> {
        let ports = self.0;
        ports.fresh().reserve(count)
    }
}

struct Attempt<'a>(&'a AtomicBool);
impl Drop for Attempt<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}

//! Two persistent channels, no reconnection/replay, and exact request counters.
use crate::{
    cache::Cache,
    config::Config,
    wire::{self, error, Decode, Encode, Result},
};
use layerfs_bridge::duplex::{self, Connection};
use layerfs_content::{
    AuthenticatedObjects, ContentError, ContentResult, FinalizedObject, ObjectId,
};
use layerfs_history::{BranchId, BranchSnapshot};
use layerfs_storage::StoragePolicy;
use layerfs_store_service::store::{
    backend::{BackendError, RemoteBuild, RemoteStore},
    publish::{CandidateInput, Publication, PublishedCandidate},
};
use std::{
    net::TcpStream,
    path::Path,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
struct Channel {
    connection: Option<Connection>,
    next: u64,
}
pub(crate) struct Shared {
    read: Mutex<Channel>,
    write: Mutex<Channel>,
    pub(crate) cache: Cache,
    pub(crate) metadata: Mutex<()>,
    calls: AtomicU64,
    uploaded_objects: AtomicU64,
    uploaded_bytes: AtomicU64,
}
pub struct Client(pub(crate) Arc<Shared>);
impl Client {
    pub fn connect(config: &Config) -> Result<Arc<Self>> {
        let connect = || {
            let address = config.get("server")?.parse().map_err(error)?;
            let stream =
                TcpStream::connect_timeout(&address, Duration::from_secs(5)).map_err(error)?;
            stream
                .set_read_timeout(Some(Duration::from_secs(10)))
                .map_err(error)?;
            stream
                .set_write_timeout(Some(Duration::from_secs(10)))
                .map_err(error)?;
            let connection =
                duplex::initiate(stream, &config.key("token")?, config.key("server_key")?)
                    .map_err(error)?;
            Ok(Channel {
                connection: Some(connection),
                next: 1,
            })
        };
        Ok(Arc::new(Self(Arc::new(Shared {
            read: Mutex::new(connect()?),
            write: Mutex::new(connect()?),
            cache: Cache::open(Path::new(config.get("cache")?))?,
            metadata: Mutex::new(()),
            calls: AtomicU64::new(0),
            uploaded_objects: AtomicU64::new(0),
            uploaded_bytes: AtomicU64::new(0),
        }))))
    }
    pub fn round_trips(&self) -> u64 {
        self.0.calls.load(Ordering::Relaxed)
    }
    /// Canonical payload admitted by acknowledged Upload calls; excludes framing.
    pub fn uploaded(&self) -> (u64, u64) {
        (
            self.0.uploaded_objects.load(Ordering::Relaxed),
            self.0.uploaded_bytes.load(Ordering::Relaxed),
        )
    }
    pub(crate) fn call(&self, write: bool, opcode: u8, body: Encode) -> Result<Vec<u8>> {
        let channel = if write { &self.0.write } else { &self.0.read };
        self.exchange(&mut *channel.lock().map_err(error)?, opcode, body)
    }
    fn exchange(&self, channel: &mut Channel, opcode: u8, body: Encode) -> Result<Vec<u8>> {
        let connection = channel.connection.as_mut().ok_or_else(|| BackendError {
            detail: "channel quarantined; no replay".into(),
            unknown: true,
        })?;
        let id = channel.next;
        channel.next += 1;
        let mut request = Encode::new();
        request.number(id);
        request.byte(opcode);
        request.raw(&body.0);
        self.0.calls.fetch_add(1, Ordering::Relaxed);
        let received = (|| {
            wire::send(connection, &request.0)?;
            wire::receive(connection)
        })();
        let bytes = match received {
            Ok(b) => b,
            Err(mut e) => {
                channel.connection = None;
                e.unknown = wire::mutates(opcode);
                return Err(e);
            }
        };
        let parsed = (|| -> Result<Result<Vec<u8>>> {
            let mut input = Decode(&bytes);
            if input.number()? != id {
                return Err(error("reply correlation"));
            }
            match input.byte()? {
                0 => Ok(Ok(input.0.to_vec())),
                status @ (1 | 2) => {
                    let detail = input.text(8192)?;
                    input.finish()?;
                    Ok(Err(BackendError {
                        detail,
                        unknown: status == 2,
                    }))
                }
                _ => Err(error("reply status")),
            }
        })();
        match parsed {
            Ok(answer) => answer,
            Err(mut failure) => {
                channel.connection = None;
                failure.unknown = wire::mutates(opcode);
                Err(failure)
            }
        }
    }
}
impl RemoteStore for Client {
    fn policy(&self) -> StoragePolicy {
        StoragePolicy::frozen_default()
    }
    fn snapshot(&self, branch: BranchId) -> Result<BranchSnapshot> {
        let mut out = Encode::new();
        out.raw(&branch.to_bytes());
        let bytes = self.call(false, wire::SNAPSHOT, out)?;
        let mut input = Decode(&bytes);
        if input.number()? != self.policy().small_file_threshold_bytes()
            || input.byte()? != self.policy().format_profile()
        {
            return Err(error("unsupported Store policy"));
        }
        let snapshot = layerfs_bridge::snapshot::decode(input.blob(8192)?).map_err(error)?;
        input.finish()?;
        self.warm_metadata(snapshot.effective_root)?;
        Ok(snapshot)
    }
    fn objects(&self, ids: &[ObjectId]) -> Result<Vec<Vec<u8>>> {
        if ids.len() > wire::IDS {
            return Err(error("ID window"));
        }
        let mut values = Vec::new();
        let mut missing = Vec::new();
        let mut positions = Vec::new();
        for (i, id) in ids.iter().enumerate() {
            let value = self.0.cache.get(*id)?;
            if value.is_none() {
                missing.push(*id);
                positions.push(i);
            }
            values.push(value);
        }
        if !missing.is_empty() {
            let mut out = Encode::new();
            wire::put_ids(&mut out, &missing);
            let bytes = self.call(false, wire::OBJECTS, out)?;
            let mut input = Decode(&bytes);
            if input.number()? != missing.len() as u64 {
                return Err(error("object cardinality"));
            }
            for (id, i) in missing.into_iter().zip(positions) {
                let body = input.blob(wire::MAX_OBJECT)?.to_vec();
                self.0.cache.put(id, &body)?;
                values[i] = Some(body);
            }
            input.finish()?;
        }
        let mut total = 0;
        values
            .into_iter()
            .map(|v| {
                let v = v.ok_or_else(|| error("missing result"))?;
                total += v.len();
                if total > 32 * 1024 * 1024 {
                    return Err(error("canonical batch bytes"));
                }
                Ok(v)
            })
            .collect()
    }
    fn lengths(&self, ids: &[ObjectId]) -> Result<Vec<u64>> {
        if ids.len() > wire::IDS {
            return Err(error("length window"));
        }
        let mut values = Vec::new();
        let mut missing = Vec::new();
        let mut positions = Vec::new();
        for (i, id) in ids.iter().enumerate() {
            let value = self.0.cache.length(*id)?;
            if value.is_none() {
                missing.push(*id);
                positions.push(i);
            }
            values.push(value);
        }
        if !missing.is_empty() {
            let mut out = Encode::new();
            wire::put_ids(&mut out, &missing);
            let bytes = self.call(false, wire::LENGTHS, out)?;
            let mut input = Decode(&bytes);
            if input.number()? != missing.len() as u64 {
                return Err(error("length cardinality"));
            }
            for (id, i) in missing.into_iter().zip(positions) {
                let n = input.number()?;
                self.0.cache.keep_length(id, n)?;
                values[i] = Some(n);
            }
            input.finish()?;
        }
        values
            .into_iter()
            .map(|v| v.ok_or_else(|| error("length result")))
            .collect()
    }
    fn reserve(&self, scope: ObjectId, count: u64) -> Result<(u64, u64)> {
        let mut out = Encode::new();
        out.raw(scope.as_bytes());
        out.number(count);
        let bytes = self.call(false, wire::RESERVE, out)?;
        let mut input = Decode(&bytes);
        let result = (input.number()?, input.number()?);
        input.finish()?;
        Ok(result)
    }
    fn build(&self) -> Result<Box<dyn RemoteBuild>> {
        Ok(Box::new(Build {
            client: Self(self.0.clone()),
            attempt: self.0.cache.attempt()?,
            failure: Mutex::new(None),
        }))
    }
}
struct Build {
    client: Client,
    attempt: i64,
    failure: Mutex<Option<BackendError>>,
}
impl std::fmt::Debug for Build {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("RemoteBuild")
            .field("attempt", &self.attempt)
            .finish()
    }
}
impl AuthenticatedObjects for Build {
    fn read_canonical_batch(&self, ids: &[ObjectId]) -> ContentResult<Vec<Vec<u8>>> {
        self.client.objects(ids).map_err(|e| {
            *self.failure.lock().unwrap_or_else(|e| e.into_inner()) = Some(e);
            ContentError::ProviderFailure {
                what: "remote construction read",
            }
        })
    }
}
impl RemoteBuild for Build {
    fn reader(&self) -> &dyn AuthenticatedObjects {
        self
    }
    fn failure(&self) -> Option<BackendError> {
        self.failure
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }
    fn accept(&self, object: FinalizedObject) -> Result<()> {
        self.client
            .0
            .cache
            .accept(self.attempt, object)
            .inspect_err(|e| {
                *self.failure.lock().unwrap_or_else(|e| e.into_inner()) = Some(e.clone());
            })
    }
    fn publish(&self, candidate: &CandidateInput) -> Result<(PublishedCandidate, Publication)> {
        let mut channel = self.client.0.write.lock().map_err(error)?;
        let result = (|| {
            let mut after = 0;
            loop {
                let rows = self.client.0.cache.page(self.attempt, after)?;
                if rows.is_empty() {
                    break;
                }
                after = rows.last().expect("nonempty").sequence;
                let mut out = Encode::new();
                wire::put_ids(&mut out, &rows.iter().map(|r| r.id).collect::<Vec<_>>());
                let missing = self.client.exchange(&mut channel, wire::LACKING, out)?;
                if missing.len() != rows.len() {
                    return Err(error("missing bitmap cardinality"));
                }
                let mut out = Encode::new();
                out.raw(candidate.binding.scope.as_bytes());
                out.raw(candidate.binding.effective_root.as_bytes());
                out.number(missing.iter().filter(|&&m| m == 1).count() as u64);
                let mut uploaded = (0, 0);
                for (row, present) in rows.iter().zip(missing) {
                    match present {
                        0 => (),
                        1 => {
                            uploaded.0 += 1;
                            uploaded.1 += row.bytes.len() as u64;
                            out.raw(row.id.as_bytes());
                            out.byte(row.role.code());
                            out.blob(&row.bytes);
                        }
                        _ => return Err(error("missing bitmap")),
                    }
                }
                self.client.exchange(&mut channel, wire::UPLOAD, out)?;
                self.client
                    .0
                    .uploaded_objects
                    .fetch_add(uploaded.0, Ordering::Relaxed);
                self.client
                    .0
                    .uploaded_bytes
                    .fetch_add(uploaded.1, Ordering::Relaxed);
            }
            let mut out = Encode::new();
            out.blob(&layerfs_bridge::snapshot::encode(&candidate.binding).map_err(error)?);
            out.raw(candidate.root.0.as_bytes());
            out.text(
                candidate
                    .options
                    .message
                    .as_deref()
                    .unwrap_or("Remote Workspace Commit"),
            );
            out.number(candidate.conflicts.len() as u64);
            for path in &candidate.conflicts {
                out.text(path);
            }
            if candidate.options.force {
                return Err(error("remote force unsupported"));
            }
            let bytes = self.client.exchange(&mut channel, wire::COMMIT, out)?;
            super::server::decode_publication(&bytes, candidate.root).map_err(|mut error| {
                error.unknown = true;
                error
            })
        })();
        if result.is_err() {
            channel.connection = None;
        }
        result
    }
}

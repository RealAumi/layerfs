//! Two channels that reopen after a lost connection, and exact request counters.
//!
//! A lost connection is dropped and the next request opens a new one. Every
//! request except Commit is sent once more on the new connection: reads and
//! presence checks change nothing, uploaded objects are content-addressed and
//! reused, and a serial range whose answer was lost just stays consumed. A
//! Commit is never resent; its lost answer stays unknown.
//!
//! A connection can also die without failing: after a machine is paused and
//! resumed, or once a proxy drops it while idle, a request goes out and no
//! answer ever comes. So a request on a quiet channel first sends a probe
//! that waits only briefly, and the request itself goes out on a new
//! connection when the probe gets no answer.
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
    net::{SocketAddr, TcpStream},
    path::Path,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
/// A request on a channel quiet for longer than this is preceded by a probe.
const PROBE_AFTER: Duration = Duration::from_secs(1);
/// How long a probe waits. A live Store answers an empty presence check at
/// once; a connection silent this long is treated as cut.
const PROBE_WAIT: Duration = Duration::from_secs(2);
/// How long every other send or receive waits.
const WAIT: Duration = Duration::from_secs(10);
struct Dial {
    address: SocketAddr,
    token: [u8; 32],
    server_key: [u8; 32],
}
impl Dial {
    fn open(&self) -> Result<Link> {
        let stream =
            TcpStream::connect_timeout(&self.address, Duration::from_secs(5)).map_err(error)?;
        stream.set_read_timeout(Some(WAIT)).map_err(error)?;
        stream.set_write_timeout(Some(WAIT)).map_err(error)?;
        let socket = stream.try_clone().map_err(error)?;
        Ok(Link {
            connection: duplex::initiate(stream, &self.token, self.server_key).map_err(error)?,
            socket,
        })
    }
}
struct Link {
    connection: Connection,
    /// The same socket, to change how long a receive waits.
    socket: TcpStream,
}
struct Channel {
    connection: Option<Link>,
    next: u64,
    /// When this channel last received an answer.
    answered: Instant,
}
/// Why one attempt failed: `Lost` dropped the connection before an answer.
enum Failure {
    Lost(BackendError),
    Answered(BackendError),
}
impl Failure {
    fn error(self) -> BackendError {
        match self {
            Self::Lost(e) | Self::Answered(e) => e,
        }
    }
}
pub(crate) struct Shared {
    dial: Dial,
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
        let dial = Dial {
            address: config.get("server")?.parse().map_err(error)?,
            token: config.key("token")?,
            server_key: config.key("server_key")?,
        };
        let channel = || {
            Ok(Channel {
                connection: Some(dial.open()?),
                next: 1,
                answered: Instant::now(),
            })
        };
        Ok(Arc::new(Self(Arc::new(Shared {
            read: Mutex::new(channel()?),
            write: Mutex::new(channel()?),
            dial,
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
        if channel.answered.elapsed() > PROBE_AFTER {
            self.probe(channel);
        }
        match self.attempt(channel, opcode, &body) {
            Err(Failure::Lost(first)) if opcode != wire::COMMIT => {
                self.attempt(channel, opcode, &body).map_err(|failure| {
                    let mut e = failure.error();
                    e.unknown |= first.unknown;
                    e
                })
            }
            result => result.map_err(Failure::error),
        }
    }
    /// An empty presence check, which changes nothing, waiting at most
    /// `PROBE_WAIT`. A connection that does not answer is dropped, so the
    /// request that follows opens a new one.
    fn probe(&self, channel: &mut Channel) {
        let Some(link) = &channel.connection else {
            return;
        };
        if link.socket.set_read_timeout(Some(PROBE_WAIT)).is_ok() {
            let mut body = Encode::new();
            wire::put_ids(&mut body, &[]);
            // A probe that got no answer has already dropped its connection.
            let _ = self.attempt(channel, wire::LACKING, &body);
        }
        if let Some(link) = &channel.connection {
            if link.socket.set_read_timeout(Some(WAIT)).is_err() {
                channel.connection = None;
            }
        }
    }
    fn attempt(
        &self,
        channel: &mut Channel,
        opcode: u8,
        body: &Encode,
    ) -> std::result::Result<Vec<u8>, Failure> {
        if channel.connection.is_none() {
            channel.connection = Some(self.0.dial.open().map_err(Failure::Lost)?);
        }
        let connection = &mut channel
            .connection
            .as_mut()
            .expect("opened connection")
            .connection;
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
                return Err(Failure::Lost(e));
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
            Ok(answer) => {
                channel.answered = Instant::now();
                answer.map_err(Failure::Answered)
            }
            Err(mut failure) => {
                channel.connection = None;
                failure.unknown = wire::mutates(opcode);
                Err(Failure::Answered(failure))
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
#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::hex;
    use std::{
        fs,
        net::TcpListener,
        os::unix::fs::PermissionsExt,
        path::PathBuf,
        sync::atomic::AtomicUsize,
        thread::{self, JoinHandle},
    };
    type Script = Box<dyn FnOnce(Connection) + Send>;
    /// A Store stand-in: the nth accepted connection runs the nth script. The
    /// client opens read then write; later connections are reopened channels.
    fn fake(scripts: Vec<Script>) -> (Arc<Client>, JoinHandle<TcpListener>, PathBuf) {
        static RUN: AtomicUsize = AtomicUsize::new(0);
        let server = duplex::generate_keypair().unwrap();
        let token = duplex::generate_keypair().unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let directory = std::env::temp_dir().join(format!(
            "remote-reopen-{}-{}",
            std::process::id(),
            RUN.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&directory).unwrap();
        let path = directory.join("config");
        fs::write(
            &path,
            format!(
                "server={address}\nserver_key={}\ntoken={}\ncache={}\n",
                hex(&server.public),
                hex(&token.private),
                directory.join("cache.sqlite").display()
            ),
        )
        .unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        let worker = thread::spawn(move || {
            listener.set_nonblocking(true).unwrap();
            let running: Vec<_> = scripts
                .into_iter()
                .map(|script| {
                    let until = Instant::now() + Duration::from_secs(10);
                    let stream = loop {
                        match listener.accept() {
                            Ok((stream, _)) => break stream,
                            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                                assert!(Instant::now() < until, "accept deadline");
                                thread::sleep(Duration::from_millis(5));
                            }
                            Err(e) => panic!("accept: {e}"),
                        }
                    };
                    stream.set_nonblocking(false).unwrap();
                    stream
                        .set_read_timeout(Some(Duration::from_secs(3)))
                        .unwrap();
                    let connection = duplex::accept(stream, &server.private, token.public).unwrap();
                    thread::spawn(move || script(connection))
                })
                .collect();
            for script in running {
                script.join().unwrap();
            }
            listener
        });
        let client = Client::connect(&Config::read(&path).unwrap()).unwrap();
        (client, worker, directory)
    }
    /// Receives one request with this opcode; answers it when `reply` is set.
    fn serve(connection: &mut Connection, opcode: u8, reply: Option<Encode>) {
        let request = wire::receive(connection).unwrap();
        let mut input = Decode(&request);
        let id = input.number().unwrap();
        assert_eq!(input.byte().unwrap(), opcode);
        if let Some(body) = reply {
            let mut answer = Encode::new();
            answer.number(id);
            answer.byte(0);
            answer.raw(&body.0);
            wire::send(connection, &answer.0).unwrap();
        }
    }
    fn idle(_: Connection) {}
    #[test]
    fn a_lost_read_is_resent_on_a_new_connection() {
        let (client, worker, directory) = fake(vec![
            Box::new(|mut read| serve(&mut read, wire::LENGTHS, None)),
            Box::new(idle),
            Box::new(|mut read| {
                let mut lengths = Encode::new();
                lengths.number(1);
                lengths.number(7);
                serve(&mut read, wire::LENGTHS, Some(lengths));
            }),
        ]);
        assert_eq!(client.lengths(&[ObjectId::for_bytes(b"a")]).unwrap(), [7]);
        assert_eq!(client.round_trips(), 2);
        worker.join().unwrap();
        fs::remove_dir_all(directory).unwrap();
    }
    #[test]
    fn a_lost_commit_is_not_resent() {
        let (client, worker, directory) = fake(vec![
            Box::new(idle),
            Box::new(|mut write| serve(&mut write, wire::COMMIT, None)),
        ]);
        let error = client.call(true, wire::COMMIT, Encode::new()).unwrap_err();
        assert!(error.unknown, "{error}");
        assert_eq!(client.round_trips(), 1);
        let listener = worker.join().unwrap();
        assert_eq!(
            listener.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock,
            "no new connection for a lost Commit"
        );
        fs::remove_dir_all(directory).unwrap();
    }
    #[test]
    fn an_idle_commit_first_replaces_a_cut_connection() {
        let (client, worker, directory) = fake(vec![
            Box::new(idle),
            Box::new(idle),
            Box::new(|mut write| serve(&mut write, wire::COMMIT, Some(Encode::new()))),
        ]);
        thread::sleep(PROBE_AFTER + Duration::from_millis(100));
        assert!(client
            .call(true, wire::COMMIT, Encode::new())
            .unwrap()
            .is_empty());
        assert_eq!(client.round_trips(), 2, "lost probe, Commit");
        worker.join().unwrap();
        fs::remove_dir_all(directory).unwrap();
    }
    #[test]
    fn a_silent_connection_is_replaced_after_the_probe_wait() {
        let (client, worker, directory) = fake(vec![
            // Takes the probe and never answers, like a resumed machine's connection.
            Box::new(|mut read| {
                let _ = wire::receive(&mut read).unwrap();
                thread::sleep(PROBE_WAIT + Duration::from_secs(1));
            }),
            Box::new(idle),
            Box::new(|mut read| {
                let mut lengths = Encode::new();
                lengths.number(1);
                lengths.number(7);
                serve(&mut read, wire::LENGTHS, Some(lengths));
            }),
        ]);
        thread::sleep(PROBE_AFTER + Duration::from_millis(100));
        let started = Instant::now();
        assert_eq!(client.lengths(&[ObjectId::for_bytes(b"a")]).unwrap(), [7]);
        let waited = started.elapsed();
        assert!(waited >= PROBE_WAIT && waited < WAIT, "{waited:?}");
        assert_eq!(client.round_trips(), 2, "silent probe, read");
        worker.join().unwrap();
        fs::remove_dir_all(directory).unwrap();
    }
}

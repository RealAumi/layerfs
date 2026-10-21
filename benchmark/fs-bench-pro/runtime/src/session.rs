use crate::{args::Args, events::Events, runtime, Result};
use layerfs_api::{internal::Control, MountedWorkspace, ProjectApi};
use layerfs_bridge::{
    control::{Reply, Request},
    provision::StoreManifest,
};
use layerfs_history::{
    BranchId, CommitHistoryRequest, CommitId, CommitOutcome, ForkRequest, ForkSource, HistoryName,
    LayerId, LayerStackId, WorkspaceId,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{self, BufRead},
    path::Path,
    sync::{Arc, Condvar, Mutex},
    time::Instant,
};

pub(crate) struct Mounted {
    pub(crate) mounted: MountedWorkspace,
    pub(crate) channel: usize,
    pub(crate) label: String,
}

fn channel_control<'a>(
    primary: &'a mut Control,
    extras: &'a mut [Control],
    index: usize,
) -> Result<&'a mut Control> {
    if index == 0 {
        Ok(primary)
    } else {
        extras
            .get_mut(index - 1)
            .ok_or_else(|| "unknown original channel".into())
    }
}

fn valid_label(label: &str) -> Result<()> {
    if label.is_empty()
        || !label
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
    {
        return Err("protocol label must be nonempty ASCII alphanumeric/underscore/hyphen".into());
    }
    Ok(())
}

fn identity_bytes<const N: usize>(body: &str) -> Result<[u8; N]> {
    if body.len() != N * 2
        || !body
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
    {
        return Err("canonical lowercase typed identity required".into());
    }
    let mut bytes = [0; N];
    for (index, byte) in bytes.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&body[index * 2..index * 2 + 2], 16)?;
    }
    Ok(bytes)
}

fn single_row(body: &str) -> Result<Vec<&str>> {
    if body.contains('\r') {
        return Err("canonical protocol body requires LF".into());
    }
    let mut lines = body.lines();
    let first = lines.next().ok_or("protocol body row missing")?;
    if lines.next().is_some() {
        return Err("single protocol body row required".into());
    }
    Ok(first.split('\t').collect())
}

pub(crate) fn branch_selector(
    selector: &str,
    branches: &BTreeMap<String, BranchId>,
) -> Result<BranchId> {
    if let Some(identity) = selector.strip_prefix('@') {
        Ok(BranchId::from_bytes(identity_bytes(identity)?)?)
    } else {
        branches
            .get(selector)
            .copied()
            .ok_or_else(|| "unknown source branch label".into())
    }
}

pub(crate) fn parse_fork(
    body: &str,
    stack: LayerStackId,
    base: LayerId,
    branches: &BTreeMap<String, BranchId>,
) -> Result<ForkRequest> {
    let fields = single_row(body)?;
    let (branch, name, source) = match fields.as_slice() {
        ["layer", branch, name] => (
            BranchId::from_bytes(identity_bytes(branch)?)?,
            HistoryName::new(name)?,
            ForkSource::Layer(base),
        ),
        ["commit", branch, name, source, commit] => (
            BranchId::from_bytes(identity_bytes(branch)?)?,
            HistoryName::new(name)?,
            ForkSource::Commit {
                branch: branch_selector(source, branches)?,
                commit: CommitId::from_bytes(identity_bytes(commit)?)?,
            },
        ),
        _ => return Err("fork layer/commit original row grammar required".into()),
    };
    if branches.values().any(|known| *known == branch) {
        return Err("reused branch authority identity".into());
    }
    Ok(ForkRequest {
        stack,
        branch,
        name,
        source,
    })
}

pub(crate) fn parse_history(body: &str, branch: BranchId) -> Result<CommitHistoryRequest> {
    let fields = single_row(body)?;
    let [start, cursor, limit] = fields.as_slice() else {
        return Err("history start/cursor/limit row required".into());
    };
    let start = if *start == "-" {
        None
    } else {
        Some(CommitId::from_bytes(identity_bytes(start)?)?)
    };
    let cursor = if *cursor == "-" {
        None
    } else {
        if cursor.len() != layerfs_history::records::MAXIMUM_CURSOR_BYTES * 2 {
            return Err("original fixed cursor width required".into());
        }
        Some(identity_bytes::<{ layerfs_history::records::MAXIMUM_CURSOR_BYTES }>(cursor)?.to_vec())
    };
    let limit = limit.parse::<u16>()?;
    if limit == 0 || limit > layerfs_bridge::control::HISTORY_WINDOW {
        return Err("existing native History processing window1..32 required".into());
    }
    let request = CommitHistoryRequest {
        branch,
        start,
        cursor,
        limit,
    };
    layerfs_history::Page {
        cursor: request.cursor.clone(),
        limit: request.limit,
    }
    .check()?;
    Ok(request)
}

fn reference_sha(bytes: &[u8]) -> String {
    crate::reference::sdk_edit_common::sha256_hex(bytes)
}

pub(crate) struct Worker {
    role: String,
    key: String,
    channel: usize,
    directory: String,
    token: layerfs_bridge::control::WorkspaceToken,
    steps: Vec<(usize, String)>,
}
pub(crate) struct Round {
    pub(crate) case: String,
    pub(crate) workers: Vec<Worker>,
}

pub(crate) fn admit_round(
    body: &str,
    mounts: &BTreeMap<String, Mounted>,
    progress: &BTreeMap<(String, String), usize>,
) -> Result<Round> {
    let mut lines = body.lines();
    let header = lines
        .next()
        .ok_or("round header missing")?
        .split('\t')
        .collect::<Vec<_>>();
    let ["context-round-v1", case] = header.as_slice() else {
        return Err("original context round header required".into());
    };
    let roles = crate::edit_model::context_roles(case)?;
    let mut workers = Vec::<Worker>::new();
    for row in lines {
        let fields = row.split('\t').collect::<Vec<_>>();
        let [role, key, local, script] = fields.as_slice() else {
            return Err("round role/key/local/body row required".into());
        };
        let local = local.parse::<usize>()?;
        if !roles.contains(role)
            || local == 0
            || local > crate::edit_model::context_limit(case, role)?
            || fields[2] != local.to_string()
        {
            return Err("round original role/local schedule differs".into());
        }
        let mounted = selected(mounts, key)?;
        if mounted.label != *role {
            return Err("round role differs from mounted branch label".into());
        }
        let body = runtime::body(Path::new(script))?;
        let selected = if let Some(index) = workers.iter().position(|worker| worker.role == *role) {
            index
        } else {
            if workers.len() == 4
                || workers
                    .iter()
                    .any(|worker| worker.channel == mounted.channel || worker.key == *key)
            {
                return Err(
                    "round requires distinct mounted keys and at most four original channels"
                        .into(),
                );
            }
            workers.push(Worker {
                role: (*role).into(),
                key: (*key).into(),
                channel: mounted.channel,
                directory: mounted.mounted.ready.directory.clone(),
                token: mounted.mounted.bound.token,
                steps: Vec::new(),
            });
            workers.len() - 1
        };
        let worker = &mut workers[selected];
        let previous = worker
            .steps
            .last()
            .map(|(local, _)| *local)
            .unwrap_or_else(|| {
                progress
                    .get(&((*case).into(), (*role).into()))
                    .copied()
                    .unwrap_or(0)
            });
        if worker.key != *key || local != previous + 1 {
            return Err("round original per-role contiguous progress differs".into());
        }
        worker.steps.push((local, body));
    }
    if workers.is_empty() {
        return Err("round has no original workers".into());
    }
    Ok(Round {
        case: (*case).into(),
        workers,
    })
}

/// One common initial barrier. An original spawn failure wakes admitted peers;
/// it cannot leave them waiting for a worker that was never created.
pub(crate) struct Gate {
    state: Mutex<(usize, bool, bool)>,
    ready: Condvar,
    total: usize,
}
impl Gate {
    pub(crate) fn new(total: usize) -> Self {
        Self {
            state: Mutex::new((0, false, false)),
            ready: Condvar::new(),
            total,
        }
    }
    pub(crate) fn arrive(&self) -> std::result::Result<(), String> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| "round barrier lock poisoned")?;
        state.0 += 1;
        self.ready.notify_all();
        while !state.1 && !state.2 {
            state = self
                .ready
                .wait(state)
                .map_err(|_| "round barrier lock poisoned")?;
        }
        if state.2 {
            Err("round spawn failed; original peers released without operation".into())
        } else {
            Ok(())
        }
    }
    pub(crate) fn release(&self, abort: bool) -> std::result::Result<(), String> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| "round barrier lock poisoned")?;
        if abort {
            state.2 = true;
        } else {
            while state.0 < self.total && !state.2 {
                state = self
                    .ready
                    .wait(state)
                    .map_err(|_| "round barrier lock poisoned")?;
            }
            state.1 = true;
        }
        self.ready.notify_all();
        Ok(())
    }
}

fn commit_ack(
    control: &mut Control,
    scope: &[u8; 32],
    token: layerfs_bridge::control::WorkspaceToken,
    key: &str,
    events: &mut Events,
    created: bool,
) -> Result<()> {
    let before = control.channel_work();
    let begun = Instant::now();
    let outcome = layerfs_api::internal::with_observations(control, scope).commit(token)?;
    let span = events.span(begun);
    let after = control.channel_work();
    let (kind, root) = match &outcome {
        CommitOutcome::Committed { record, .. } => ("Committed", record.root),
        CommitOutcome::UpToDate { root, .. } => ("UpToDate", *root),
    };
    let mut fields = vec![
        ("key", key.into()),
        ("commit_kind", kind.into()),
        ("root", crate::hex(&root.to_bytes())),
    ];
    if let CommitOutcome::Committed { record, .. } = &outcome {
        fields.extend([
            ("commit_id", crate::hex(&record.id.to_bytes())),
            (
                "parent",
                record
                    .parent
                    .map(|id| crate::hex(&id.to_bytes()))
                    .unwrap_or_else(|| "-".into()),
            ),
            ("base_layer", crate::hex(&record.base_layer.to_bytes())),
            ("stack", crate::hex(&record.stack.to_bytes())),
        ]);
    }
    events.numeric_fields(
        "commit",
        Some(span),
        &format!("key={key} original_outcome={outcome:?}"),
        &fields,
        &[
            ("control_send_records_before", before.0.records),
            ("control_send_records_after", after.0.records),
            ("control_receive_records_before", before.1.records),
            ("control_receive_records_after", after.1.records),
        ],
    )?;
    if created && kind != "Committed" {
        return Err("original contextual changed stage requires Committed".into());
    }
    Ok(())
}

fn execute_round(
    args: &Args,
    sandbox: &layerfs_sandbox::backend::docker::Sandbox,
    primary: &mut Control,
    extras: &mut [Control],
    scopes: &[[u8; 32]],
    label: &str,
    plan: Round,
    progress: &mut BTreeMap<(String, String), usize>,
    events: &mut Events,
) -> Result<()> {
    let gate = Arc::new(Gate::new(plan.workers.len()));
    let mut channels = std::iter::once(primary)
        .chain(extras.iter_mut())
        .enumerate()
        .collect::<BTreeMap<_, _>>();
    if plan.workers.iter().any(|worker| {
        !channels.contains_key(&worker.channel) || scopes.get(worker.channel).is_none()
    }) {
        return Err("round original channel/scope missing before barrier".into());
    }
    let begun = Instant::now();
    let outputs = std::thread::scope(
        |scope| -> std::result::Result<Vec<(String, usize)>, String> {
            let mut handles = Vec::new();
            let mut spawn_error = None;
            for worker in plan.workers {
                let control = channels
                    .remove(&worker.channel)
                    .ok_or("round original channel missing")?;
                let gate = gate.clone();
                let observation = scopes[worker.channel];
                let sink = events.contextual(&[
                    ("role", worker.role.clone()),
                    ("channel", worker.channel.to_string()),
                    ("scope", crate::hex(&observation)),
                    ("round", label.into()),
                ]);
                let task = std::thread::Builder::new()
                    .name(format!("fsb-{}", worker.role))
                    .spawn_scoped(
                        scope,
                        move || -> std::result::Result<(String, usize), String> {
                            gate.arrive()?;
                            let mut last = 0;
                            for (local, body) in worker.steps {
                                let mut step_events = sink.contextual(&[
                                    ("local_step", local.to_string()),
                                    ("key", worker.key.clone()),
                                ]);
                                let work = control.channel_work();
                                runtime::concurrent_command(
                                    sandbox,
                                    layerfs_sandbox::CommandIdentity {
                                        uid: args.uid,
                                        gid: args.gid,
                                    },
                                    &body,
                                    &worker.directory,
                                    &args.environment,
                                    (work.0.records, work.1.records),
                                    &mut step_events,
                                )
                                .map_err(|error| error.to_string())?;
                                commit_ack(
                                    control,
                                    &observation,
                                    worker.token,
                                    &worker.key,
                                    &mut step_events,
                                    true,
                                )
                                .map_err(|error| error.to_string())?;
                                last = local;
                            }
                            Ok((worker.role, last))
                        },
                    );
                match task {
                    Ok(handle) => handles.push(handle),
                    Err(error) => {
                        spawn_error = Some(error.to_string());
                        break;
                    }
                }
            }
            gate.release(spawn_error.is_some())?;
            let mut outputs = Vec::new();
            let mut failure = spawn_error;
            for handle in handles {
                match handle.join() {
                    Ok(Ok(value)) => outputs.push(value),
                    Ok(Err(error)) => {
                        failure.get_or_insert(error);
                    }
                    Err(_) => {
                        failure.get_or_insert("original round worker panicked".into());
                    }
                }
            }
            if let Some(failure) = failure {
                Err(failure)
            } else {
                Ok(outputs)
            }
        },
    )
    .map_err(|error| format!("original concurrent round failure {error}"))?;
    for (role, local) in &outputs {
        progress.insert((plan.case.clone(), role.clone()), *local);
    }
    events.numeric_fields(
        "round_finished",
        Some(events.span(begun)),
        "original segment completed after every independent worker command/Commit acknowledgement",
        &[("round", label.into()), ("case", plan.case)],
        &[("workers", outputs.len() as u64)],
    )?;
    Ok(())
}

fn workspace(key: &str) -> Result<WorkspaceId> {
    if key.len() != 64 || !key.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("workspace key must be 64 hex digits".into());
    }
    let mut id = [0; 32];
    for (index, byte) in id.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&key[index * 2..index * 2 + 2], 16)?;
    }
    Ok(WorkspaceId::from_authority(id)?)
}
fn selected<'a>(mounts: &'a BTreeMap<String, Mounted>, key: &str) -> Result<&'a Mounted> {
    mounts
        .get(key)
        .ok_or_else(|| format!("unknown mounted key {key}").into())
}

/// Keeps daemon caches, Store sessions and one overlay alive across explicit calls.
pub fn serve(args: &Args, events: &mut Events) -> Result<()> {
    let manifest = StoreManifest::decode(&fs::read(&args.manifest)?)?;
    let stack = LayerStackId::from_bytes(manifest.stack)?;
    let initial_root = layerfs_content::ObjectId::from_bytes(&manifest.root)?;
    let base_layer = LayerId::derive(stack, None, initial_root);
    if args.case.is_some() {
        events.fields(
            "history_initial_root",
            None,
            "exact initial sealed Store manifest root; no additional control call",
            &[
                ("root", crate::hex(&manifest.root)),
                ("branch_id", crate::hex(&manifest.branch)),
                ("stack", crate::hex(&manifest.stack)),
                ("base_layer", crate::hex(&base_layer.to_bytes())),
                ("head", "-".into()),
                ("name", "main".into()),
            ],
        )?;
    }
    let branch = BranchId::from_bytes(manifest.branch)?;
    let (mut owner, mut keys) = runtime::start_with_keys(args, Some(manifest), events)?;
    let mut branches = BTreeMap::from([("main".to_owned(), branch)]);
    let mut extras = Vec::<Control>::new();
    let mut scopes = vec![args.observation_scope];
    let mut progress = BTreeMap::<(String, String), usize>::new();
    let mut mounts = BTreeMap::new();
    let mut closed = BTreeMap::new();
    let mut used_keys = BTreeSet::new();
    let origin = layerfs_api::internal::control(&mut owner)
        .channel_work()
        .0
        .records;
    if origin != 1 {
        return Err(
            "serve fresh Control must have exactly one Hello and no installation sends".into(),
        );
    }
    events.numeric_fields(
        "control_origin",
        None,
        "fresh serve Control; records equal successful call IDs on this channel",
        &[("channel", "0".into()), ("scope", crate::hex(&scopes[0]))],
        &[
            ("control_send_records", origin),
            (
                "control_receive_records",
                layerfs_api::internal::control(&mut owner)
                    .channel_work()
                    .1
                    .records,
            ),
        ],
    )?;
    events.value("protocol_ready", "mount KEY | mount-branch KEY LABEL | fork LABEL BODY_FILE | history LABEL BODY_FILE | round LABEL BODY_FILE | command KEY BODY_FILE | commit KEY | snapshot KEY | unmount KEY | cleanup KEY | observe | stop; fields separated by tabs")?;
    for line in io::stdin().lock().lines() {
        let line = line?;
        let fields: Vec<&str> = line.splitn(3, '\t').collect();
        let operation = fields[0];
        let key = fields.get(1).copied().unwrap_or("");
        match operation {
            "fork" => {
                valid_label(key)?;
                if branches.contains_key(key) {
                    return Err("reused branch label".into());
                }
                let request = parse_fork(
                    &fs::read_to_string(fields.get(2).ok_or("fork body file required")?)?,
                    stack,
                    base_layer,
                    &branches,
                )?;
                let before = layerfs_api::internal::control(&mut owner).channel_work();
                let begun = Instant::now();
                let snapshot = ProjectApi::new().fork(&mut owner, request)?;
                let span = events.span(begun);
                let after = layerfs_api::internal::control(&mut owner).channel_work();
                events.numeric_fields(
                    "fork",
                    Some(span),
                    "original public ProjectApi::fork acknowledgement",
                    &[
                        ("label", key.into()),
                        ("branch_id", crate::hex(&snapshot.branch.id.to_bytes())),
                        ("name", snapshot.branch.name.as_str().into()),
                        (
                            "base_layer",
                            crate::hex(&snapshot.branch.base_layer.to_bytes()),
                        ),
                        (
                            "head",
                            snapshot
                                .branch
                                .head_commit
                                .map(|id| crate::hex(&id.to_bytes()))
                                .unwrap_or_else(|| "-".into()),
                        ),
                        ("root", crate::hex(&snapshot.effective_root.to_bytes())),
                        ("stack", crate::hex(&snapshot.branch.stack.to_bytes())),
                        ("base_root", crate::hex(&snapshot.base_root.to_bytes())),
                        ("channel", "0".into()),
                        ("scope", crate::hex(&scopes[0])),
                    ],
                    &[
                        ("control_send_records_before", before.0.records),
                        ("control_send_records_after", after.0.records),
                        ("control_receive_records_before", before.1.records),
                        ("control_receive_records_after", after.1.records),
                    ],
                )?;
                branches.insert(key.into(), snapshot.branch.id);
            }
            "history" => {
                let branch = branch_selector(key, &branches)?;
                let request = parse_history(
                    &fs::read_to_string(fields.get(2).ok_or("history body file required")?)?,
                    branch,
                )?;
                let before = layerfs_api::internal::control(&mut owner).channel_work();
                let begun = Instant::now();
                let page = ProjectApi::new().commits(&mut owner, request)?;
                let span = events.span(begun);
                let after = layerfs_api::internal::control(&mut owner).channel_work();
                for record in &page.records {
                    events.fields(
                        "history_record",
                        None,
                        "original public SDK typed record",
                        &[
                            ("label", key.into()),
                            ("branch_id", crate::hex(&branch.to_bytes())),
                            ("commit_id", crate::hex(&record.id.to_bytes())),
                            ("root", crate::hex(&record.root.to_bytes())),
                            (
                                "parent",
                                record
                                    .parent
                                    .map(|id| crate::hex(&id.to_bytes()))
                                    .unwrap_or_else(|| "-".into()),
                            ),
                            ("base_layer", crate::hex(&record.base_layer.to_bytes())),
                            ("stack", crate::hex(&record.stack.to_bytes())),
                            ("channel", "0".into()),
                            ("scope", crate::hex(&scopes[0])),
                        ],
                    )?;
                }
                let mut cursor_fields = vec![("cursor_path", "-".into())];
                let cursor_bytes = page.continuation.as_ref().map_or(0, Vec::len);
                if let Some(cursor) = page.continuation {
                    use std::io::Write;
                    let (path, mut file) = events.output("history_cursor", "bin")?;
                    file.write_all(&cursor)?;
                    file.flush()?;
                    cursor_fields = vec![
                        ("cursor_path", path.display().to_string()),
                        ("cursor_sha256", reference_sha(&cursor)),
                    ];
                }
                cursor_fields.extend([
                    ("label", key.into()),
                    ("branch_id", crate::hex(&branch.to_bytes())),
                    ("channel", "0".into()),
                    ("scope", crate::hex(&scopes[0])),
                ]);
                events.numeric_fields("history_finished",Some(span),"one original bounded public SDK History page; cursor bytes remain in private artifact",&cursor_fields,&[("records",page.records.len() as u64),("cursor_bytes",cursor_bytes as u64),("control_send_records_before",before.0.records),("control_send_records_after",after.0.records),("control_receive_records_before",before.1.records),("control_receive_records_after",after.1.records)])?;
            }
            "round" => {
                valid_label(key)?;
                let plan = admit_round(
                    &fs::read_to_string(fields.get(2).ok_or("round body file required")?)?,
                    &mounts,
                    &progress,
                )?;
                let (runtime, control) = layerfs_api::internal::parts(&mut owner);
                execute_round(
                    args,
                    runtime,
                    control,
                    &mut extras,
                    &scopes,
                    key,
                    plan,
                    &mut progress,
                    events,
                )?;
            }
            "mount" | "mount-branch" => {
                let label = if operation == "mount-branch" {
                    fields
                        .get(2)
                        .copied()
                        .ok_or("mount-branch label required")?
                } else {
                    "main"
                };
                let branch = *branches.get(label).ok_or("unknown branch label")?;
                let channel = if operation == "mount" {
                    0
                } else {
                    (0..4)
                        .find(|index| {
                            !mounts
                                .values()
                                .any(|entry: &Mounted| entry.channel == *index)
                                && !closed.values().any(
                                    |entry: &(layerfs_bridge::control::WorkspaceToken, usize)| {
                                        entry.1 == *index
                                    },
                                )
                        })
                        .ok_or("four active channel ceiling")?
                };
                if channel > extras.len() {
                    let scope = layerfs_bridge::duplex::generate_keypair()?.public;
                    if scope == [0; 32] || scopes.contains(&scope) {
                        return Err("fresh independent extra scope required".into());
                    }
                    events.fields(
                        "control_open_attempt",
                        None,
                        "one original authenticated extra channel",
                        &[
                            ("channel", channel.to_string()),
                            ("scope", crate::hex(&scope)),
                        ],
                    )?;
                    let control = runtime::extra_control(&mut owner, &mut keys)?;
                    let (send, receive) = control.channel_work();
                    if send.records != 1 || receive.records != 1 {
                        return Err("extra Control origin must be exactly one Hello".into());
                    }
                    extras.push(control);
                    scopes.push(scope);
                    events.numeric_fields(
                        "control_origin",
                        None,
                        "fresh extra Control; same authority and daemon incarnation",
                        &[
                            ("channel", channel.to_string()),
                            ("scope", crate::hex(&scope)),
                        ],
                        &[
                            ("control_send_records", send.records),
                            ("control_receive_records", receive.records),
                        ],
                    )?;
                }
                let control = channel_control(
                    layerfs_api::internal::control(&mut owner),
                    &mut extras,
                    channel,
                )?;
                if used_keys.contains(&key.to_ascii_lowercase()) {
                    return Err("reused Workspace authority key; fresh incarnation required".into());
                }
                let id = workspace(key)?;
                let before = control.channel_work().0.records;
                let receive_before = control.channel_work().1.records;
                let begun = Instant::now();
                let mounted = layerfs_api::internal::with_observations(control, &scopes[channel])
                    .mount(id, branch)
                    .map_err(|failure| format!("mount original failure {failure:?}"))?;
                let elapsed = events.span(begun);
                let after = control.channel_work().0.records;
                let receive_after = control.channel_work().1.records;
                events.numeric_fields(
                    "mount",
                    Some(elapsed),
                    &format!("bound={:?} ready={:?}", mounted.bound, mounted.ready),
                    &[
                        ("key", key.into()),
                        ("directory", mounted.ready.directory.clone()),
                        (
                            "workspace_incarnation",
                            crate::hex(&mounted.bound.token.workspace.to_bytes()),
                        ),
                        ("branch_label", label.into()),
                        ("branch_id", crate::hex(&branch.to_bytes())),
                        (
                            "head",
                            mounted
                                .bound
                                .binding
                                .branch
                                .head_commit
                                .map(|id| crate::hex(&id.to_bytes()))
                                .unwrap_or_else(|| "-".into()),
                        ),
                        (
                            "root",
                            crate::hex(&mounted.bound.binding.effective_root.to_bytes()),
                        ),
                        (
                            "base_layer",
                            crate::hex(&mounted.bound.binding.branch.base_layer.to_bytes()),
                        ),
                        (
                            "stack",
                            crate::hex(&mounted.bound.binding.branch.stack.to_bytes()),
                        ),
                        ("channel", channel.to_string()),
                        ("scope", crate::hex(&scopes[channel])),
                    ],
                    &[
                        (
                            "workspace_namespace",
                            u64::try_from(mounted.bound.token.namespace)?,
                        ),
                        ("control_send_records_before", before),
                        ("control_send_records_after", after),
                        ("control_receive_records_before", receive_before),
                        ("control_receive_records_after", receive_after),
                    ],
                )?;
                used_keys.insert(key.to_ascii_lowercase());
                mounts.insert(
                    key.into(),
                    Mounted {
                        mounted,
                        channel,
                        label: label.into(),
                    },
                );
            }
            "command" | "verify" => {
                let directory = if let Some(native) = key.strip_prefix("native:") {
                    if !native.starts_with('/') {
                        return Err("native directory must be absolute".into());
                    }
                    native.to_owned()
                } else {
                    selected(&mounts, key)?.mounted.ready.directory.clone()
                };
                let path = Path::new(fields.get(2).ok_or("command body file required")?);
                let body = runtime::body(path)?;
                let channel = if key.starts_with("native:") {
                    0
                } else {
                    selected(&mounts, key)?.channel
                };
                let work = channel_control(
                    layerfs_api::internal::control(&mut owner),
                    &mut extras,
                    channel,
                )?
                .channel_work();
                let mut command_events = events
                    .contextual(&[
                        ("key", key.into()),
                        ("channel", channel.to_string()),
                        ("scope", crate::hex(&scopes[channel])),
                    ])
                    .contextual_numbers(&[
                        ("control_send_records_before", work.0.records),
                        ("control_send_records_after", work.0.records),
                        ("control_receive_records_before", work.1.records),
                        ("control_receive_records_after", work.1.records),
                    ]);
                runtime::command(
                    &owner,
                    &body,
                    if key.starts_with("native:") {
                        runtime::Directory::Host(
                            &directory,
                            layerfs_sandbox::CommandIdentity {
                                uid: args.uid,
                                gid: args.gid,
                            },
                        )
                    } else {
                        runtime::Directory::Mounted(&selected(&mounts, key)?.mounted)
                    },
                    operation,
                    false,
                    &args.environment,
                    &mut command_events,
                )?;
            }
            "commit" => {
                let channel = selected(&mounts, key)?.channel;
                let control = channel_control(
                    layerfs_api::internal::control(&mut owner),
                    &mut extras,
                    channel,
                )?;
                let token = selected(&mounts, key)?.mounted.bound.token;
                let before = control.channel_work().0.records;
                let receive_before = control.channel_work().1.records;
                let begun = Instant::now();
                let outcome = layerfs_api::internal::with_observations(control, &scopes[channel])
                    .commit(token)?;
                let elapsed = events.span(begun);
                let after = control.channel_work().0.records;
                let receive_after = control.channel_work().1.records;
                let commit_kind = match &outcome {
                    CommitOutcome::Committed { record: _, .. } => "Committed",
                    CommitOutcome::UpToDate { .. } => "UpToDate",
                };
                let root = match &outcome {
                    CommitOutcome::Committed { record, .. } => record.root,
                    CommitOutcome::UpToDate { root, .. } => *root,
                };
                let mut fields = vec![
                    ("key", key.into()),
                    ("channel", channel.to_string()),
                    ("scope", crate::hex(&scopes[channel])),
                    ("commit_kind", commit_kind.into()),
                    ("root", crate::hex(&root.to_bytes())),
                ];
                if let CommitOutcome::Committed { record, .. } = &outcome {
                    fields.extend([
                        ("commit_id", crate::hex(&record.id.to_bytes())),
                        (
                            "parent",
                            record
                                .parent
                                .map(|id| crate::hex(&id.to_bytes()))
                                .unwrap_or_else(|| "-".into()),
                        ),
                        ("base_layer", crate::hex(&record.base_layer.to_bytes())),
                        ("stack", crate::hex(&record.stack.to_bytes())),
                    ]);
                }
                events.numeric_fields(
                    "commit",
                    Some(elapsed),
                    &format!("key={key} original_outcome={outcome:?}"),
                    &fields,
                    &[
                        ("control_send_records_before", before),
                        ("control_send_records_after", after),
                        ("control_receive_records_before", receive_before),
                        ("control_receive_records_after", receive_after),
                    ],
                )?;
            }
            "snapshot" => {
                let channel = selected(&mounts, key)?.channel;
                let control = channel_control(
                    layerfs_api::internal::control(&mut owner),
                    &mut extras,
                    channel,
                )?;
                let token = selected(&mounts, key)?.mounted.bound.token;
                let before = control.channel_work().0.records;
                let receive_before = control.channel_work().1.records;
                let observed = layerfs_api::internal::with_observations(control, &scopes[channel])
                    .status(token)?;
                let after = control.channel_work().0.records;
                let receive_after = control.channel_work().1.records;
                let mut numbers = vec![
                    ("control_send_records_before", before),
                    ("control_send_records_after", after),
                    ("control_receive_records_before", receive_before),
                    ("control_receive_records_after", receive_after),
                    (
                        "status_state_attribution_available",
                        u64::from(observed.local.is_some()),
                    ),
                ];
                if observed.local.is_some() {
                    numbers.push(("status_state_lifecycle_jobs", 1));
                }
                events.numeric_fields(
                    "workspace_status",
                    None,
                    &format!("key={key} observed={observed:?}"),
                    &[
                        ("key", key.into()),
                        ("channel", channel.to_string()),
                        ("scope", crate::hex(&scopes[channel])),
                    ],
                    &numbers,
                )?;
                runtime::snapshot(&owner, &args.socket, events)?;
            }
            "observe" => runtime::snapshot(&owner, &args.socket, events)?,
            "unmount" => {
                let channel = selected(&mounts, key)?.channel;
                let control = channel_control(
                    layerfs_api::internal::control(&mut owner),
                    &mut extras,
                    channel,
                )?;
                let token = selected(&mounts, key)?.mounted.bound.token;
                let before = control.channel_work().0.records;
                let receive_before = control.channel_work().1.records;
                let begun = Instant::now();
                layerfs_api::internal::with_observations(control, &scopes[channel])
                    .unmount(token, false)?;
                let elapsed = events.span(begun);
                let after = control.channel_work().0.records;
                let receive_after = control.channel_work().1.records;
                events.numeric_fields("unmount", Some(elapsed), &format!("key={key} token={token:?}; logical_terminal=true; physical_cleanup requires its own original observation"), &[("key",key.into()),("workspace_incarnation",crate::hex(&token.workspace.to_bytes())),("channel",channel.to_string()),("scope",crate::hex(&scopes[channel]))], &[("workspace_namespace",u64::try_from(token.namespace)?),("control_send_records_before",before),("control_send_records_after",after),("control_receive_records_before",receive_before),("control_receive_records_after",receive_after)])?;
                mounts.remove(key);
                closed.insert(key.to_owned(), (token, channel));
            }
            "cleanup" => {
                let (token, channel) = *closed
                    .get(key)
                    .ok_or("unknown original closed Workspace key")?;
                let control = channel_control(
                    layerfs_api::internal::control(&mut owner),
                    &mut extras,
                    channel,
                )?;
                let before = control.channel_work().0.records;
                let receive_before = control.channel_work().1.records;
                let begun = Instant::now();
                let state = layerfs_api::internal::with_observations(control, &scopes[channel])
                    .cleanup(token)?;
                let span = events.span(begun);
                let after = control.channel_work().0.records;
                let receive_after = control.channel_work().1.records;
                events.numeric_fields(
                    "cleanup",
                    Some(span),
                    "original read-only cleanup observation; no replay or maintenance invocation",
                    &[
                        ("key", key.into()),
                        ("state", format!("{state:?}")),
                        (
                            "workspace_incarnation",
                            crate::hex(&token.workspace.to_bytes()),
                        ),
                        ("channel", channel.to_string()),
                        ("scope", crate::hex(&scopes[channel])),
                    ],
                    &[
                        ("workspace_namespace", u64::try_from(token.namespace)?),
                        ("control_send_records_before", before),
                        ("control_send_records_after", after),
                        ("control_receive_records_before", receive_before),
                        ("control_receive_records_after", receive_after),
                    ],
                )?;
                if matches!(state, layerfs_bridge::control::CleanupObservation::Gone) {
                    closed.remove(key);
                }
            }
            "stop" => {
                if !mounts.is_empty() || !closed.is_empty() {
                    return Err("explicit unmount and known Gone required before stop".into());
                }
                for channel in 0..=extras.len() {
                    let control = channel_control(
                        layerfs_api::internal::control(&mut owner),
                        &mut extras,
                        channel,
                    )?;
                    let before = control.channel_work();
                    let begun = Instant::now();
                    if control.call(Request::EndSession)? != Reply::SessionEnded {
                        return Err("unexpected original EndSession acknowledgement".into());
                    }
                    let after = control.channel_work();
                    events.numeric_fields(
                        "control_ended",
                        Some(events.span(begun)),
                        "original EndSession acknowledged and native socket fence completed",
                        &[
                            ("channel", channel.to_string()),
                            ("scope", crate::hex(&scopes[channel])),
                        ],
                        &[
                            ("control_send_records_before", before.0.records),
                            ("control_send_records_after", after.0.records),
                            ("control_receive_records_before", before.1.records),
                            ("control_receive_records_after", after.1.records),
                        ],
                    )?;
                }
                // Independent closed-Store and overlay readback still need this
                // exact stopped container. The receipt owner deletes it after
                // harvesting; do not destroy that evidence with whole-owner close.
                owner
                    .runtime
                    .stop(1)
                    .map_err(|error| format!("explicit container stop {error:?}"))?;
                events.value("container_stopped", &owner.runtime.identity().to_string())?;
                return Ok(());
            }
            _ => return Err(format!("unknown protocol command {operation}").into()),
        }
    }
    Err("stdin ended without explicit stop; container and original custody retained".into())
}

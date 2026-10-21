//! Synthetic protocol admission and receipt concurrency; no mounted case.
#[allow(dead_code)]
#[path = "../../engine/recipes/dedup_input.rs"]
mod dedup_input;
#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
pub(crate) mod namespace;
pub(crate) mod project {
    pub(crate) use crate::namespace;
}
pub(crate) use namespace::reference;
pub(crate) type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[allow(dead_code)]
#[path = "../src/args.rs"]
mod args;
#[allow(dead_code)]
#[path = "../../engine/recipes/edit_model.rs"]
mod edit_model;
#[allow(dead_code)]
#[path = "../src/edit_oracle.rs"]
mod edit_oracle;
#[allow(dead_code)]
#[path = "../src/events.rs"]
mod events;
#[allow(dead_code)]
#[path = "../src/runtime.rs"]
mod runtime;
#[allow(dead_code)]
#[path = "../src/session.rs"]
mod session;
#[allow(dead_code)]
#[path = "../src/workspace_oracle.rs"]
mod workspace_oracle;

use layerfs_api::{BoundWorkspace, MountedWorkspace};
use layerfs_bridge::control::{MountReceipt, ReadyMount, WorkspaceToken};
use layerfs_content::ObjectId;
use layerfs_history::{
    BranchId, BranchRecord, BranchSnapshot, CommitId, ForkSource, HistoryName, LayerId,
    LayerStackId, WorkspaceId,
};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    sync::{mpsc, Arc},
    time::Duration,
};

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
fn home(label: &str) -> PathBuf {
    let root = std::env::var("LAYERFS_SESSION_PROTOCOL_OUTPUT")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            std::env::temp_dir().join(format!("fsb-session-protocol-{}", std::process::id()))
        });
    fs::create_dir_all(&root).unwrap();
    let path = root.join(label);
    fs::create_dir(&path).unwrap();
    path
}
fn identities() -> (LayerStackId, LayerId, ObjectId) {
    let stack = LayerStackId::from_authority([31; 16]);
    let root = ObjectId::for_bytes(b"synthetic-admission-root");
    (stack, LayerId::derive(stack, None, root), root)
}
fn mounted(role: &str, channel: usize) -> (String, session::Mounted) {
    let (stack, base, root) = identities();
    let branch = BranchId::from_authority([channel as u8 + 1; 16]);
    let key = hex(&[channel as u8 + 1; 32]);
    let token = WorkspaceToken {
        workspace: WorkspaceId::from_authority([channel as u8 + 1; 32]).unwrap(),
        namespace: channel as i64 + 1,
    };
    let snapshot = BranchSnapshot {
        branch: BranchRecord {
            id: branch,
            stack,
            name: HistoryName::new(role).unwrap(),
            base_layer: base,
            head_commit: None,
        },
        head_root: None,
        base_root: root,
        effective_root: root,
        scope: root,
        profile: root,
    };
    let receipt = MountReceipt {
        mount: 1,
        root: 1,
        mount_id: 1,
        device_major: 0,
        device_minor: 1,
        abi_major: 7,
        abi_minor: 31,
        offered: 0,
        selected: 0,
        max_write: 65536,
        max_readahead: 0,
        max_background: 16,
        congestion_threshold: 12,
        page_size: 4096,
        loops: 1,
        abort_bound: true,
    };
    (
        key,
        session::Mounted {
            mounted: MountedWorkspace {
                bound: BoundWorkspace {
                    token,
                    binding: snapshot,
                },
                ready: ReadyMount {
                    token,
                    directory: "/synthetic-not-mounted".into(),
                    receipt,
                },
            },
            channel,
            label: role.into(),
        },
    )
}

#[test]
fn protocol_public_fork_request_preserves_typed_source_and_refuses_invalid_authority() {
    let (stack, base, root) = identities();
    let parent = BranchId::from_authority([41; 16]);
    let child = BranchId::from_authority([42; 16]);
    let branches = BTreeMap::from([("main".into(), parent)]);
    let commit = CommitId::derive(
        root,
        None,
        base,
        None,
        &layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
    );
    let request = session::parse_fork(
        &format!("layer\t{}\ttrunk\n", hex(&child.to_bytes())),
        stack,
        base,
        &branches,
    )
    .unwrap();
    assert_eq!(request.source, ForkSource::Layer(base));
    assert_eq!(request.branch, child);
    let request = session::parse_fork(
        &format!(
            "commit\t{}\tchild\tmain\t{}\n",
            hex(&child.to_bytes()),
            hex(&commit.to_bytes())
        ),
        stack,
        base,
        &branches,
    )
    .unwrap();
    assert_eq!(
        request.source,
        ForkSource::Commit {
            branch: parent,
            commit
        }
    );
    let direct = format!("@{}", hex(&parent.to_bytes()));
    assert_eq!(
        session::branch_selector(&direct, &BTreeMap::new()).unwrap(),
        parent
    );
    assert_eq!(session::branch_selector("main", &branches).unwrap(), parent);
    assert!(session::branch_selector(&hex(&parent.to_bytes()), &branches).is_err());
    for invalid in [
        "unknown".into(),
        "@".into(),
        format!("@{}", "ff".repeat(17)),
        format!(
            "@{}",
            hex(&BranchId::from_authority([0xab; 16]).to_bytes()).to_uppercase()
        ),
    ] {
        assert!(session::branch_selector(&invalid, &branches).is_err());
    }
    let request = session::parse_fork(
        &format!(
            "commit\t{}\tchild\t{direct}\t{}\n",
            hex(&child.to_bytes()),
            hex(&commit.to_bytes())
        ),
        stack,
        base,
        &BTreeMap::new(),
    )
    .unwrap();
    assert_eq!(
        request.source,
        ForkSource::Commit {
            branch: parent,
            commit
        }
    );
    assert!(session::parse_fork(
        &format!("layer\t{}\treused", hex(&parent.to_bytes())),
        stack,
        base,
        &branches
    )
    .is_err());
    for body in [
        format!("layer\t{}\tBadName", hex(&child.to_bytes())),
        format!("layer\t{}\ttrunk", "ff".repeat(17)),
        format!(
            "commit\t{}\tchild\tunknown\t{}",
            hex(&child.to_bytes()),
            hex(&commit.to_bytes())
        ),
        format!("layer\t{}\ttrunk\nextra", hex(&child.to_bytes())),
    ] {
        assert!(session::parse_fork(&body, stack, base, &branches).is_err());
    }
}

#[test]
fn protocol_history_is_anchored_and_keeps_original_cursor_and_page_bounds() {
    let (_, base, root) = identities();
    let branch = BranchId::from_authority([11; 16]);
    let commit = CommitId::derive(
        root,
        None,
        base,
        None,
        &layerfs_history::CommitMeta::new(layerfs_history::CommitVia::Workspace),
    );
    let request =
        session::parse_history(&format!("{}\t-\t32", hex(&commit.to_bytes())), branch).unwrap();
    assert_eq!(request.start, Some(commit));
    assert_eq!(request.limit, 32);
    assert_eq!(request.branch, branch);
    let request = session::parse_history(&format!("-\t{}\t1", "a1".repeat(160)), branch).unwrap();
    assert_eq!(request.cursor.unwrap(), vec![0xa1; 160]);
    for body in [
        "-\t-\t0".into(),
        "-\t-\t33".into(),
        "-\t-\t65536".into(),
        "-\t00\t1".into(),
        format!("-\t{}\t1", "A1".repeat(160)),
        "-\t-\t1\n-\t-\t1".into(),
    ] {
        assert!(session::parse_history(&body, branch).is_err());
    }
}

#[test]
fn protocol_round_admits_all_bodies_and_exact_contiguous_role_segments_before_work() {
    let home = home("round-admission");
    let body = home.join("stage.sh");
    fs::write(&body, "true\n").unwrap();
    let case = "v016-workspace-mixed-100mb-5000-k10-v1";
    let mut mounts = BTreeMap::new();
    let (mut key0, entry) = mounted("0", 0);
    mounts.insert(key0.clone(), entry);
    let (key1, entry) = mounted("1", 1);
    mounts.insert(key1.clone(), entry);
    let rows=format!("context-round-v1\t{case}\n0\t{key0}\t1\t{}\n1\t{key1}\t1\t{}\n0\t{key0}\t2\t{}\n1\t{key1}\t2\t{}\n",body.display(),body.display(),body.display(),body.display());
    let plan = session::admit_round(&rows, &mounts, &BTreeMap::new()).unwrap();
    assert_eq!(plan.case, case);
    assert_eq!(plan.workers.len(), 2);
    assert!(
        session::admit_round(&rows.replace("\t2\t", "\t3\t"), &mounts, &BTreeMap::new()).is_err()
    );
    assert!(session::admit_round(
        &rows.replace(body.to_str().unwrap(), "/missing-unadmitted-body"),
        &mounts,
        &BTreeMap::new()
    )
    .is_err());
    assert!(session::admit_round(&rows.replace(&key1, &key0), &mounts, &BTreeMap::new()).is_err());
    let progress = BTreeMap::from([
        ((case.into(), "0".into()), 5),
        ((case.into(), "1".into()), 5),
    ]);
    let continuation = format!(
        "context-round-v1\t{case}\n0\t{key0}\t6\t{}\n1\t{key1}\t6\t{}\n",
        body.display(),
        body.display()
    );
    assert!(session::admit_round(&continuation, &mounts, &progress).is_ok());
    assert!(session::admit_round(&rows, &mounts, &progress).is_err());
    let four = "v016-workspace-four-100mb-5000-k100-v1";
    let mut rows = format!("context-round-v1\t{four}\n");
    for index in 0..4 {
        let (key, entry) = mounted(&index.to_string(), index);
        mounts.insert(key.clone(), entry);
        rows += &format!("{index}\t{key}\t1\t{}\n", body.display());
        if index == 0 {
            key0 = key;
        }
    }
    assert_eq!(
        session::admit_round(&rows, &mounts, &BTreeMap::new())
            .unwrap()
            .workers
            .len(),
        4
    );
    assert!(session::admit_round(
        &format!("{rows}4\t{key0}\t1\t{}\n", body.display()),
        &mounts,
        &BTreeMap::new()
    )
    .is_err());
}

#[test]
fn protocol_single_barrier_releases_every_worker_and_abort_never_waits_for_absent_worker() {
    for abort in [false, true] {
        let total = 4;
        let gate = Arc::new(session::Gate::new(total));
        let (tx, rx) = mpsc::channel();
        let mut handles = Vec::new();
        for _ in 0..if abort { 3 } else { 4 } {
            let gate = gate.clone();
            let tx = tx.clone();
            handles.push(std::thread::spawn(move || {
                tx.send(gate.arrive().is_ok()).unwrap();
            }));
        }
        gate.release(abort).unwrap();
        for _ in &handles {
            assert_eq!(rx.recv_timeout(Duration::from_secs(2)).unwrap(), !abort);
        }
        for handle in handles {
            handle.join().unwrap();
        }
    }
}

#[test]
fn protocol_parallel_events_have_unique_private_artifacts_atomic_sequence_and_shared_clock() {
    let home = home("parallel-events");
    let path = home.join("events.jsonl");
    let events = events::Events::new(&path).unwrap();
    let mut handles = Vec::new();
    let mut sinks = Vec::new();
    for role in 0..4 {
        let mut sink =
            events.contextual(&[("role", role.to_string()), ("channel", role.to_string())]);
        handles.push(std::thread::spawn(move || {
            let (path, _) = sink.output("command", "stdout").unwrap();
            for local in 1..=4 {
                let begin = std::time::Instant::now();
                sink.numeric_fields(
                    "command",
                    Some(sink.span(begin)),
                    "synthetic admission only",
                    &[],
                    &[("local_step", local)],
                )
                .unwrap();
            }
            path
        }));
    }
    for handle in handles {
        sinks.push(handle.join().unwrap());
    }
    sinks.sort();
    sinks.dedup();
    assert_eq!(sinks.len(), 4);
    use std::os::unix::fs::PermissionsExt;
    for path in sinks {
        assert_eq!(
            fs::metadata(path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
    let body = fs::read_to_string(path).unwrap();
    let rows = body.lines().collect::<Vec<_>>();
    assert_eq!(rows.len(), 16);
    for (index, row) in rows.iter().enumerate() {
        assert!(row.contains(&format!("\"sequence\":{},", index + 1)));
        assert!(row.contains("\"clock_id\":\"monotonic\""));
        assert!(row.contains("\"role\":"));
        assert!(row.ends_with('}'));
    }
}

//! Single automatic parent-mtime custody for the unchanged native alias helper.
use crate::{edit_model, reference};
use reference::workspace_common::{Entry, EntryKind};

pub const SCHEMA: &str = "original-boundary-parent-mtime-v1";
pub const PATH: &str = "data";
pub const STEP: usize = 5;
pub const NATIVE_PRECISION_NS: i128 = 1_000_000_000;
pub const MAX_OPERATION_NS: i128 = 60_000_000_000;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Timestamp {
    pub seconds: i64,
    pub nanoseconds: u32,
}

impl Timestamp {
    fn total(self) -> i128 {
        i128::from(self.seconds) * 1_000_000_000 + i128::from(self.nanoseconds)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Custody {
    pub initial: Timestamp,
    pub started: Timestamp,
    pub finished: Timestamp,
    pub observed: Timestamp,
}

impl Custody {
    pub fn encode(self) -> String {
        let mut body = format!(
            "{SCHEMA}\ncase\t{}\nstep\t{STEP}\npath\t{PATH}\n",
            reference::file_size_transition::ALIAS_ROUNDTRIP
        );
        for (name, time) in [
            ("initial", self.initial),
            ("started", self.started),
            ("finished", self.finished),
            ("observed", self.observed),
        ] {
            body.push_str(&format!("{name}\t{}\t{}\n", time.seconds, time.nanoseconds));
        }
        body
    }
}

/// Canonical fixed-domain custody; no arbitrary metadata override is accepted.
pub fn parse(case: &str, body: &str) -> reference::Result<Custody> {
    if case != reference::file_size_transition::ALIAS_ROUNDTRIP {
        return Err("automatic parent mtime requires the original alias case".into());
    }
    let rows = body.lines().collect::<Vec<_>>();
    if rows.len() != 8
        || rows[0] != SCHEMA
        || rows[1] != format!("case\t{case}")
        || rows[2] != format!("step\t{STEP}")
        || rows[3] != format!("path\t{PATH}")
    {
        return Err("automatic parent mtime case/path/step/header differs".into());
    }
    let timestamp = |row: &str, name: &str| -> reference::Result<Timestamp> {
        let fields = row.split('\t').collect::<Vec<_>>();
        if fields.len() != 3 || fields[0] != name {
            return Err("automatic parent mtime timestamp row differs".into());
        }
        let seconds = fields[1].parse::<i64>()?;
        let nanoseconds = fields[2].parse::<u32>()?;
        if seconds < 0 || nanoseconds >= 1_000_000_000 {
            return Err("automatic parent mtime timestamp outside native domain".into());
        }
        Ok(Timestamp {
            seconds,
            nanoseconds,
        })
    };
    let custody = Custody {
        initial: timestamp(rows[4], "initial")?,
        started: timestamp(rows[5], "started")?,
        finished: timestamp(rows[6], "finished")?,
        observed: timestamp(rows[7], "observed")?,
    };
    let declared = Timestamp {
        seconds: reference::file_size_transition::DECLARED_MTIME_SECONDS,
        nanoseconds: 0,
    };
    // Native inode clocks may round below the userspace start observation.
    // Only this automatic field receives the declared one-second allowance;
    // publication and fresh-mount comparison keep its exact nanoseconds.
    if custody.encode() != body
        || custody.initial != declared
        || custody.observed == declared
        || custody.finished.total() < custody.started.total()
        || custody.finished.total() - custody.started.total() > MAX_OPERATION_NS
        || custody.observed.total() < custody.started.total() - NATIVE_PRECISION_NS
        || custody.observed.total() > custody.finished.total()
    {
        return Err("automatic parent mtime canonical custody/clock envelope differs".into());
    }
    Ok(custody)
}

/// First construct the independent complete model, then bind only one field.
pub fn entries(case: &str, step: usize, custody: Custody) -> reference::Result<Vec<Entry>> {
    if case != reference::file_size_transition::ALIAS_ROUNDTRIP || step != STEP {
        return Err("automatic parent mtime substitution is only alias state5".into());
    }
    let mut entries = edit_model::entries(case, step)?;
    let parent = entries
        .iter_mut()
        .find(|entry| entry.path == PATH)
        .ok_or("original alias parent absent")?;
    if !matches!(parent.kind, EntryKind::Directory)
        || parent.mtime_seconds != custody.initial.seconds
        || parent.mtime_nanoseconds != custody.initial.nanoseconds
    {
        return Err("original alias parent descriptor differs".into());
    }
    parent.mtime_seconds = custody.observed.seconds;
    parent.mtime_nanoseconds = custody.observed.nanoseconds;
    Ok(entries)
}

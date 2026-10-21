use crate::Result;
use std::fmt::Write as FmtWrite;
use std::{
    fs::{File, OpenOptions},
    io::{self, Write},
    os::unix::fs::OpenOptionsExt,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::Instant,
};

/// Append-only newline JSON. Debug records are opaque diagnostics, never parsed as outcomes.
pub struct Events {
    shared: Arc<Mutex<Records>>,
    pub origin: Instant,
    pub directory: PathBuf,
    context: Vec<(&'static str, String)>,
    numeric_context: Vec<(&'static str, u64)>,
}
struct Records {
    file: File,
    sequence: u64,
    outputs: u64,
}
#[derive(Clone, Copy)]
pub struct Span {
    pub start_ns: u128,
    pub end_ns: u128,
    pub duration_ns: u128,
}
pub fn quoted(value: &str) -> String {
    let mut out = String::from("\"");
    for character in value.chars() {
        match character {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => out.push_str(&format!("\\u{:04x}", u32::from(c))),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}
impl Events {
    pub fn new(path: &Path) -> Result<Self> {
        path.parent().ok_or("receipt parent")?;
        let directory = path.with_extension("artifacts");
        std::fs::create_dir(&directory)?;
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(path)?;
        Ok(Self {
            shared: Arc::new(Mutex::new(Records {
                file,
                sequence: 0,
                outputs: 0,
            })),
            origin: Instant::now(),
            directory,
            context: Vec::new(),
            numeric_context: Vec::new(),
        })
    }
    /// Workers share only atomic receipt publication, never an operation lock.
    pub fn contextual(&self, fields: &[(&'static str, String)]) -> Self {
        let mut context = self.context.clone();
        context.extend_from_slice(fields);
        Self {
            shared: self.shared.clone(),
            origin: self.origin,
            directory: self.directory.clone(),
            context,
            numeric_context: self.numeric_context.clone(),
        }
    }
    pub fn contextual_numbers(&self, numbers: &[(&'static str, u64)]) -> Self {
        let mut copy = self.contextual(&[]);
        copy.numeric_context.extend_from_slice(numbers);
        copy
    }
    pub fn value(&mut self, event: &str, value: &str) -> Result<()> {
        self.phase(event, None, value)
    }
    pub fn span(&self, start: Instant) -> Span {
        let end = Instant::now();
        Span {
            start_ns: start.duration_since(self.origin).as_nanos(),
            end_ns: end.duration_since(self.origin).as_nanos(),
            duration_ns: end.duration_since(start).as_nanos(),
        }
    }
    pub fn phase(&mut self, event: &str, elapsed: Option<Span>, value: &str) -> Result<()> {
        self.fields(event, elapsed, value, &[])
    }
    pub fn fields(
        &mut self,
        event: &str,
        elapsed: Option<Span>,
        value: &str,
        fields: &[(&str, String)],
    ) -> Result<()> {
        self.numeric_fields(event, elapsed, value, fields, &[])
    }
    pub fn numeric_fields(
        &mut self,
        event: &str,
        elapsed: Option<Span>,
        value: &str,
        fields: &[(&str, String)],
        numbers: &[(&str, u64)],
    ) -> Result<()> {
        let mut records = self
            .shared
            .lock()
            .map_err(|_| "event publication lock poisoned")?;
        records.sequence += 1;
        let numbers = self
            .numeric_context
            .iter()
            .chain(numbers.iter())
            .copied()
            .collect::<Vec<_>>();
        let span = elapsed.map(|span|format!("{{\"clock_id\":\"monotonic\",\"start_ns\":{},\"end_ns\":{},\"duration_ns\":{}}}", span.start_ns,span.end_ns,span.duration_ns)).unwrap_or_else(||"null".into());
        for (key, value) in &self.context {
            if fields
                .iter()
                .any(|(name, actual)| name == key && actual != value)
                || numbers.iter().any(|(name, _)| name == key)
            {
                return Err("event context differs from original typed field".into());
            }
        }
        let mut fields = self
            .context
            .iter()
            .filter(|(key, _)| !fields.iter().any(|(name, _)| name == key))
            .chain(fields.iter())
            .map(|(key, value)| format!("{}:{}", quoted(key), quoted(value)))
            .collect::<Vec<_>>()
            .join(",");
        for (key, value) in &numbers {
            if !fields.is_empty() {
                fields.push(',');
            }
            write!(&mut fields, "{}:{value}", quoted(key))?;
        }
        let record = format!("{{\"schema\":\"r7-runtime-events-v1\",\"sequence\":{},\"at_ns\":{},\"event\":{},\"elapsed_ns\":{},\"span\":{},\"value\":{},\"fields\":{{{fields}}}}}\n", records.sequence, self.origin.elapsed().as_nanos(), quoted(event), elapsed.map(|v|v.duration_ns.to_string()).unwrap_or_else(||"null".into()), span, quoted(value));
        records.file.write_all(record.as_bytes())?;
        records.file.flush()?;
        let mut stdout = io::stdout().lock();
        stdout.write_all(record.as_bytes())?;
        stdout.flush()?;
        Ok(())
    }
    pub fn output(&mut self, label: &str, stream: &str) -> Result<(PathBuf, File)> {
        let mut records = self
            .shared
            .lock()
            .map_err(|_| "event output lock poisoned")?;
        records.outputs += 1;
        let path = self.directory.join(format!(
            "{:06}-{:06}-{label}.{stream}",
            records.sequence + 1,
            records.outputs
        ));
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)?;
        Ok((path, file))
    }
}

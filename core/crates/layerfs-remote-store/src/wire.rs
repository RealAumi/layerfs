//! Bounded fragmented messages over the existing authenticated record channel.
use layerfs_bridge::duplex::Connection;
use layerfs_store_service::store::BackendError;
use std::fmt::Display;
pub type Result<T> = std::result::Result<T, BackendError>;
pub const MAX_MESSAGE: usize = 34 * 1024 * 1024;
pub const MAX_OBJECT: usize = 16 * 1024 * 1024;
pub const IDS: usize = 4096;
pub const SNAPSHOT: u8 = 1;
pub const OBJECTS: u8 = 2;
pub const LENGTHS: u8 = 3;
pub const RESERVE: u8 = 4;
pub const LACKING: u8 = 5;
pub const UPLOAD: u8 = 6;
pub const COMMIT: u8 = 7;
pub const METADATA: u8 = 8;
pub fn mutates(opcode: u8) -> bool {
    matches!(opcode, RESERVE | UPLOAD | COMMIT)
}
pub fn error(e: impl Display) -> BackendError {
    BackendError {
        detail: e.to_string(),
        unknown: false,
    }
}
pub fn send(c: &mut Connection, bytes: &[u8]) -> Result<()> {
    if bytes.len() > MAX_MESSAGE {
        return Err(error("message window"));
    }
    let mut header = b"LFRS\x01".to_vec();
    header.extend_from_slice(&(bytes.len() as u32).to_be_bytes());
    c.send.send(&header).map_err(error)?;
    for (index, chunk) in bytes.chunks(60_000).enumerate() {
        let mut frame = Vec::with_capacity(chunk.len() + 4);
        frame.extend_from_slice(&((index * 60_000) as u32).to_be_bytes());
        frame.extend_from_slice(chunk);
        c.send.send(&frame).map_err(error)?;
    }
    Ok(())
}
pub fn receive(c: &mut Connection) -> Result<Vec<u8>> {
    let head = c.receive.receive().map_err(error)?;
    if head.len() != 9 || &head[..5] != b"LFRS\x01" {
        return Err(error("Store wire version/header"));
    }
    let size = u32::from_be_bytes(head[5..].try_into().map_err(error)?) as usize;
    if size > MAX_MESSAGE {
        return Err(error("message window"));
    }
    let mut out = Vec::with_capacity(size);
    while out.len() < size {
        let frame = c.receive.receive().map_err(error)?;
        if frame.len() < 5 || frame.len() > 60_004 {
            return Err(error("fragment size"));
        }
        let offset = u32::from_be_bytes(frame[..4].try_into().map_err(error)?) as usize;
        if offset != out.len() || frame.len() - 4 > size - out.len() {
            return Err(error("fragment offset"));
        }
        out.extend_from_slice(&frame[4..]);
    }
    Ok(out)
}
pub struct Encode(pub Vec<u8>);
impl Encode {
    pub fn new() -> Self {
        Self(Vec::new())
    }
    pub fn byte(&mut self, v: u8) {
        self.0.push(v);
    }
    pub fn number(&mut self, v: u64) {
        self.0.extend_from_slice(&v.to_be_bytes());
    }
    pub fn raw(&mut self, v: &[u8]) {
        self.0.extend_from_slice(v);
    }
    pub fn blob(&mut self, v: &[u8]) {
        self.number(v.len() as u64);
        self.raw(v);
    }
    pub fn text(&mut self, v: &str) {
        self.blob(v.as_bytes());
    }
}
impl Default for Encode {
    fn default() -> Self {
        Self::new()
    }
}
pub struct Decode<'a>(pub &'a [u8]);
impl<'a> Decode<'a> {
    pub fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        if n > self.0.len() {
            return Err(error("truncated field"));
        }
        let (value, rest) = self.0.split_at(n);
        self.0 = rest;
        Ok(value)
    }
    pub fn byte(&mut self) -> Result<u8> {
        Ok(self.take(1)?[0])
    }
    pub fn number(&mut self) -> Result<u64> {
        Ok(u64::from_be_bytes(self.take(8)?.try_into().map_err(error)?))
    }
    pub fn array<const N: usize>(&mut self) -> Result<[u8; N]> {
        self.take(N)?.try_into().map_err(error)
    }
    pub fn blob(&mut self, max: usize) -> Result<&'a [u8]> {
        let n = usize::try_from(self.number()?).map_err(error)?;
        if n > max {
            return Err(error("field window"));
        }
        self.take(n)
    }
    pub fn text(&mut self, max: usize) -> Result<String> {
        String::from_utf8(self.blob(max)?.to_vec()).map_err(error)
    }
    pub fn finish(self) -> Result<()> {
        if self.0.is_empty() {
            Ok(())
        } else {
            Err(error("trailing fields"))
        }
    }
}
pub fn ids(input: &mut Decode<'_>) -> Result<Vec<layerfs_content::ObjectId>> {
    let n = input.number()?;
    if n > IDS as u64 {
        return Err(error("ID window"));
    }
    (0..n)
        .map(|_| layerfs_content::ObjectId::from_bytes(input.take(32)?).map_err(error))
        .collect()
}
pub fn put_ids(out: &mut Encode, ids: &[layerfs_content::ObjectId]) {
    out.number(ids.len() as u64);
    for id in ids {
        out.raw(id.as_bytes());
    }
}

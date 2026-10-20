//! The paths Git tracks, from the bytes of `.git/index`. A tracked path is
//! never treated as ignored, whatever the patterns say.
use std::collections::BTreeSet;

#[derive(Debug, Default)]
pub struct Tracked(BTreeSet<String>);

impl Tracked {
    /// Whether Git tracks `path`, or any path below it.
    pub fn covers(&self, path: &str) -> bool {
        if self.0.contains(path) {
            return true;
        }
        let below = format!("{path}/");
        self.0
            .range(below.clone()..)
            .next()
            .is_some_and(|next| next.starts_with(&below))
    }
    pub fn len(&self) -> usize {
        self.0.len()
    }
    /// Paths tracked here and not in `before`.
    pub fn added(&self, before: &Self) -> Vec<String> {
        self.0.difference(&before.0).cloned().collect()
    }
}

/// Index versions 2–4 with SHA-1 names. `None` for anything else, including
/// a split index, whose entries live partly in another file.
pub fn parse(bytes: &[u8]) -> Option<Tracked> {
    const ENTRY: usize = 62;
    if bytes.len() < 12 || &bytes[..4] != b"DIRC" {
        return None;
    }
    let version = u32::from_be_bytes(bytes[4..8].try_into().ok()?);
    let count = u32::from_be_bytes(bytes[8..12].try_into().ok()?);
    if !(2..=4).contains(&version) {
        return None;
    }
    let mut paths = BTreeSet::new();
    let mut at = 12;
    let mut previous: Vec<u8> = Vec::new();
    for _ in 0..count {
        let start = at;
        let flags = u16::from_be_bytes(bytes.get(at + 60..at + ENTRY)?.try_into().ok()?);
        at += ENTRY;
        if flags & 0x4000 != 0 {
            if version < 3 {
                return None;
            }
            at += 2;
        }
        let path = if version == 4 {
            let (strip, used) = varint(bytes.get(at..)?)?;
            at += used;
            let end = at + bytes.get(at..)?.iter().position(|b| *b == 0)?;
            let keep = previous.len().checked_sub(usize::try_from(strip).ok()?)?;
            let mut path = previous[..keep].to_vec();
            path.extend_from_slice(&bytes[at..end]);
            at = end + 1;
            path
        } else {
            let end = at + bytes.get(at..)?.iter().position(|b| *b == 0)?;
            let path = bytes[at..end].to_vec();
            // NUL padding to a multiple of eight bytes, at least one.
            at = start + (end - start + 8) / 8 * 8;
            path
        };
        paths.insert(String::from_utf8_lossy(&path).into_owned());
        previous = path;
    }
    // Extensions follow until the trailing checksum; a split index's
    // "link" means entries we did not read.
    while bytes.len() >= at + 8 + 20 {
        let signature = &bytes[at..at + 4];
        let size = u32::from_be_bytes(bytes[at + 4..at + 8].try_into().ok()?) as usize;
        if signature == b"link" {
            return None;
        }
        at = at.checked_add(8 + size)?;
    }
    Some(Tracked(paths))
}

/// Git's offset varint: each continuation adds one before shifting.
fn varint(bytes: &[u8]) -> Option<(u64, usize)> {
    let mut used = 0;
    let mut c = *bytes.first()?;
    let mut value = u64::from(c & 0x7f);
    while c & 0x80 != 0 {
        used += 1;
        c = *bytes.get(used)?;
        value = value.checked_add(1)?.checked_shl(7)? | u64::from(c & 0x7f);
    }
    Some((value, used + 1))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(path: &str, version: u32, strip: Option<u8>) -> Vec<u8> {
        let mut entry = vec![0u8; 60];
        entry.extend_from_slice(&(path.len().min(0xfff) as u16).to_be_bytes());
        match strip {
            Some(strip) => {
                entry.push(strip);
                entry.extend_from_slice(path.as_bytes());
                entry.push(0);
            }
            None => {
                entry.extend_from_slice(path.as_bytes());
                let padded = (entry.len() + 8) / 8 * 8;
                entry.resize(padded, 0);
            }
        }
        let _ = version;
        entry
    }

    fn index(version: u32, entries: &[Vec<u8>], extension: Option<&[u8; 4]>) -> Vec<u8> {
        let mut bytes = b"DIRC".to_vec();
        bytes.extend_from_slice(&version.to_be_bytes());
        bytes.extend_from_slice(&(entries.len() as u32).to_be_bytes());
        for entry in entries {
            bytes.extend_from_slice(entry);
        }
        if let Some(signature) = extension {
            bytes.extend_from_slice(signature);
            bytes.extend_from_slice(&4u32.to_be_bytes());
            bytes.extend_from_slice(&[0; 4]);
        }
        bytes.extend_from_slice(&[0; 20]);
        bytes
    }

    #[test]
    fn version_two_and_four_paths_and_prefixes() {
        let two = index(
            2,
            &[
                entry("build/keep.txt", 2, None),
                entry("src/A.java", 2, None),
            ],
            Some(b"TREE"),
        );
        let tracked = parse(&two).expect("v2");
        assert!(tracked.covers("src/A.java"));
        assert!(
            tracked.covers("build"),
            "a directory holding a tracked file"
        );
        assert!(!tracked.covers("build/out.txt"));
        assert!(!tracked.covers("sr"));
        let four = index(
            4,
            &[entry("src/A.java", 4, Some(0)), entry("B.java", 4, Some(6))],
            None,
        );
        let tracked = parse(&four).expect("v4");
        assert!(tracked.covers("src/A.java"));
        assert!(tracked.covers("src/B.java"));
        assert_eq!(tracked.len(), 2);
    }

    #[test]
    fn a_split_index_is_not_read() {
        assert!(parse(&index(2, &[entry("a", 2, None)], Some(b"link"))).is_none());
        assert!(parse(b"nope").is_none());
    }
}

//! Private prototype configuration; no credentials in command arguments.
use crate::wire::{error, Result};
use std::{collections::BTreeMap, fs, os::unix::fs::MetadataExt, path::Path};
pub struct Config(BTreeMap<String, String>);
impl Config {
    pub fn read(path: &Path) -> Result<Self> {
        let m = fs::symlink_metadata(path).map_err(error)?;
        if !m.is_file()
            || m.mode() & 0o077 != 0
            || m.uid() != nix::unistd::Uid::effective().as_raw()
            || m.len() > 8192
        {
            return Err(error("config ownership/mode/size"));
        }
        let text = fs::read_to_string(path).map_err(error)?;
        let mut values = BTreeMap::new();
        for line in text.lines().filter(|l| !l.is_empty()) {
            let (key, value) = line.split_once('=').ok_or_else(|| error("config field"))?;
            if values.insert(key.to_owned(), value.to_owned()).is_some() {
                return Err(error("duplicate config field"));
            }
        }
        Ok(Self(values))
    }
    pub fn get(&self, key: &str) -> Result<&str> {
        self.0
            .get(key)
            .map(String::as_str)
            .ok_or_else(|| error(format!("missing {key}")))
    }
    pub fn key(&self, key: &str) -> Result<[u8; 32]> {
        unhex(self.get(key)?)?
            .try_into()
            .map_err(|_| error("key width"))
    }
    pub fn number(&self, key: &str) -> Result<u32> {
        self.get(key)?.parse().map_err(error)
    }
}
pub fn hex(bytes: &[u8]) -> String {
    const HEX: &[u8] = b"0123456789abcdef";
    bytes
        .iter()
        .flat_map(|b| {
            [
                HEX[(b >> 4) as usize] as char,
                HEX[(b & 15) as usize] as char,
            ]
        })
        .collect()
}
pub fn unhex(text: &str) -> Result<Vec<u8>> {
    if text.len() % 2 != 0 || !text.is_ascii() {
        return Err(error("hex width"));
    }
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).map_err(error))
        .collect()
}

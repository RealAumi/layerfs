//! Bounded metadata waves over an immutable root. File payload stays demand-read.
use crate::{
    client::Client,
    wire::{self, error, Decode, Encode, Result},
};
use layerfs_content::{
    filesystem::{
        directory::{decode_directory_page, DirectoryPage},
        inode::{decode_inode_page, InodePage},
        FilesystemRoot,
    },
    inode_leaf::InodeKind,
    AuthenticatedObjects, ObjectId,
};
use layerfs_store_service::store::Store;

pub const ROOT: u8 = 1;
pub const INODES: u8 = 2;
pub const DIRECTORY: u8 = 3;
pub const WINDOW: usize = 256;
pub type Demand = (u8, ObjectId);
/// Decode with the existing canonical grammars; regular-file roots are lengths
/// only. Attribute trees and symlink targets retain their ordinary demand path.
pub fn expand(kind: u8, bytes: &[u8]) -> Result<(Vec<Demand>, Vec<ObjectId>)> {
    if bytes.len() > 8192 {
        return Err(error("metadata page size"));
    }
    let mut children = Vec::new();
    let mut files = Vec::new();
    match kind {
        ROOT => children.push((
            INODES,
            FilesystemRoot::decode(bytes).map_err(error)?.inode_table(),
        )),
        INODES => match decode_inode_page(bytes).map_err(error)? {
            InodePage::Branch { children: rows, .. } => {
                children.extend(rows.into_iter().map(|(_, id)| (INODES, id)))
            }
            InodePage::Leaf { entries } => {
                for (_, value) in entries {
                    match value.kind {
                        InodeKind::Directory => children.push((DIRECTORY, value.content_root)),
                        InodeKind::RegularFile => files.push(value.content_root),
                        InodeKind::Symlink => (),
                    }
                }
            }
        },
        DIRECTORY => {
            if let DirectoryPage::Branch { children: rows, .. } =
                decode_directory_page(bytes).map_err(error)?
            {
                children.extend(rows.into_iter().map(|(_, id)| (DIRECTORY, id)));
            }
        }
        _ => return Err(error("metadata kind")),
    }
    Ok((children, files))
}
pub(crate) fn serve(store: &std::sync::Arc<Store>, input: &mut Decode<'_>) -> Result<Encode> {
    let count = input.number()? as usize;
    if count == 0 || count > WINDOW {
        return Err(error("metadata window"));
    }
    let mut demands = Vec::with_capacity(count);
    for _ in 0..count {
        let kind = input.byte()?;
        if !(ROOT..=DIRECTORY).contains(&kind) {
            return Err(error("metadata kind"));
        }
        demands.push((kind, ObjectId::from_bytes(input.take(32)?).map_err(error)?));
    }
    if !input.0.is_empty() {
        return Err(error("metadata trailing fields"));
    }
    let ports = store.ports(ObjectId::for_bytes(b"remote-metadata"));
    let ids: Vec<_> = demands.iter().map(|(_, id)| *id).collect();
    let bodies = ports.read_canonical_batch(&ids).map_err(error)?;
    let mut out = Encode::new();
    out.number(count as u64);
    let mut files = Vec::new();
    for ((kind, _), body) in demands.iter().zip(bodies) {
        files.extend(expand(*kind, &body)?.1);
        out.blob(&body);
    }
    out.number(files.len() as u64);
    for page in files.chunks(wire::IDS) {
        for length in ports.file_lengths(page).map_err(error)? {
            out.number(length);
        }
    }
    if std::env::var_os("LAYERFS_REMOTE_TRACE_READS").is_some() {
        eprintln!("STORE_METADATA objects={count} lengths={}", files.len());
    }
    Ok(out)
}
impl Client {
    pub(crate) fn warm_metadata(&self, root: ObjectId) -> Result<()> {
        // One temporary disk frontier per client, not one tree-sized resident list.
        let _owner = self.0.metadata.lock().map_err(error)?;
        if !self.0.cache.metadata_start(root)? {
            return Ok(());
        }
        loop {
            let page = self.0.cache.metadata_page()?;
            if page.is_empty() {
                break;
            }
            let mut missing = Vec::new();
            let mut children = Vec::new();
            let mut cached_files = Vec::new();
            for &(kind, id) in &page {
                if let Some(body) = self.0.cache.get(id)? {
                    let (next, files) = expand(kind, &body)?;
                    children.extend(next);
                    cached_files.extend(files);
                } else {
                    missing.push((kind, id));
                }
            }
            for files in cached_files.chunks(wire::IDS) {
                layerfs_store_service::store::RemoteStore::lengths(self, files)?;
            }
            if !missing.is_empty() {
                let mut request = Encode::new();
                request.number(missing.len() as u64);
                for (kind, id) in &missing {
                    request.byte(*kind);
                    request.raw(id.as_bytes());
                }
                let reply = self.call(false, wire::METADATA, request)?;
                let mut input = Decode(&reply);
                if input.number()? != missing.len() as u64 {
                    return Err(error("metadata cardinality"));
                }
                let mut files = Vec::new();
                for (kind, id) in &missing {
                    let body = input.blob(8192)?;
                    self.0.cache.put(*id, body)?;
                    let (next, roots) = expand(*kind, body)?;
                    children.extend(next);
                    files.extend(roots);
                }
                if input.number()? != files.len() as u64 {
                    return Err(error("metadata lengths cardinality"));
                }
                for id in files {
                    self.0.cache.keep_length(id, input.number()?)?;
                }
                input.finish()?;
            }
            self.0.cache.metadata_advance(&page, &children)?;
        }
        self.0.cache.metadata_complete(root)
    }
}

//! Immutable-root traversal with bounded child acquisition and point validation.
use crate::Result;
use layerfs_content::{
    filesystem::{
        directory::lookup, read::Resolved, DirectoryRoot, FilesystemRead, FilesystemRootId,
        PathName,
    },
    inode_leaf::InodeValue,
    AuthenticatedObjects, ObjectId,
};
use std::{collections::VecDeque, vec::IntoIter};

struct Directory {
    path: String,
    inode: Resolved,
    after: Option<PathName>,
}

struct Page {
    parent: String,
    names: IntoIter<(PathName, u64)>,
    values: IntoIter<Option<InodeValue>>,
}

pub(super) struct NamespaceWalk<'a> {
    pub(super) tree: FilesystemRead<'a>,
    reader: &'a dyn AuthenticatedObjects,
    root: Option<Resolved>,
    directories: VecDeque<Directory>,
    active: Option<Directory>,
    page: Option<Page>,
}

impl<'a> NamespaceWalk<'a> {
    pub(super) fn new(reader: &'a dyn AuthenticatedObjects, root: ObjectId) -> Result<Self> {
        let mut tree = FilesystemRead::new(reader, FilesystemRootId(root))?;
        let root = Some(tree.resolve_inode(tree.root().root_inode().serial())?);
        Ok(Self {
            tree,
            reader,
            root,
            directories: VecDeque::new(),
            active: None,
            page: None,
        })
    }

    pub(super) fn queue_directory(&mut self, path: String, inode: Resolved) {
        self.directories.push_back(Directory {
            path,
            inode,
            after: None,
        });
    }

    pub(super) fn next(&mut self) -> Result<Option<(String, Resolved)>> {
        if let Some(root) = self.root.take() {
            return Ok(Some((".".to_owned(), root)));
        }
        loop {
            if let Some(page) = self.page.as_mut() {
                if let Some((name, serial)) = page.names.next() {
                    let value = page
                        .values
                        .next()
                        .ok_or("persisted inode batch cardinality differs")?
                        .ok_or("persisted directory serial missing from inode table")?;
                    let path = if page.parent == "." {
                        name.as_str().to_owned()
                    } else {
                        format!("{}/{}", page.parent, name.as_str())
                    };
                    return Ok(Some((path, Resolved { serial, value })));
                }
                if page.values.next().is_some() {
                    return Err("persisted inode batch cardinality differs".into());
                }
                self.page = None;
            }
            let Some(mut directory) = self.active.take().or_else(|| self.directories.pop_front())
            else {
                return Ok(None);
            };
            let page = self.tree.list_inode(
                directory.inode.serial,
                directory.after.as_ref(),
                128,
                16384,
            )?;
            for (name, serial) in &page.entries {
                if lookup(
                    self.reader,
                    DirectoryRoot(directory.inode.value.content_root),
                    name,
                )? != Some(*serial)
                {
                    return Err("persisted directory point/list binding differs".into());
                }
            }
            let serials = page
                .entries
                .iter()
                .map(|(_, serial)| *serial)
                .collect::<Vec<_>>();
            let values = self.tree.lookup_inodes(&serials)?;
            if values.len() != page.entries.len() {
                return Err("persisted inode batch cardinality differs".into());
            }
            self.page = Some(Page {
                parent: directory.path.clone(),
                names: page.entries.into_iter(),
                values: values.into_iter(),
            });
            directory.after = page.continuation;
            if directory.after.is_some() {
                self.active = Some(directory);
            }
        }
    }
}

//! Replays the changes between two roots onto a third, name by name.
//!
//! The changed inodes of `from → to` come from the inode-table difference, and
//! the changed names from the directories among them, so the work follows the
//! change, not the tree. A change is applied only where `onto` still agrees
//! with `from` (otherwise `onto`'s own change wins) and where [`Keep`] says
//! so. A kept name that binds an inode `onto` lacks brings that inode, and the
//! kept part of its subtree, from `to`.
//!
//! A kept name that binds an inode `onto` holds elsewhere adopts it. A
//! directory has one name, so an adopted directory loses the name `onto` gave
//! it, as does an adopted file whose old name this replay saw left out. When
//! `to` may keep, below inodes both roots hold, what `onto` never got (names
//! left out until a rule or the index flipped them), adopted inodes and the
//! places [`Keep::flipped`] names are reconciled: their kept names and values
//! are made `to`'s.
use layerfs_content::compare::{
    binding_changes, inode_changes, list_directory, locate, same_value, DifferenceWork, TreeTable,
};
use layerfs_content::filesystem::{FilesystemResources, FilesystemRootId, PathName};
use layerfs_content::inode_leaf::{InodeKind, InodeValue};
use layerfs_content::{
    update_filesystem, AuthenticatedObjects, ContentError, ContentResult, DirectoryUpdate,
    FilesystemInput, FilesystemObjects, FinalizedConsumer, InodeUpdate,
};
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// Directories a walk may list to find where `onto` binds an adopted one.
const WALK: usize = 1 << 20;

/// Which changes a replay carries.
pub trait Keep {
    /// `parent` binds `name` to `child` in the replayed tree.
    fn learn(&mut self, parent: u64, name: &PathName, child: u64);
    /// Whether the change of `name` in directory `parent` is carried;
    /// `directory` is the kind of what the name binds, after or before.
    fn binding(&mut self, parent: u64, name: &PathName, directory: bool) -> ContentResult<bool>;
    /// Whether the new value of a file that keeps its names is carried.
    fn value(&mut self, serial: u64) -> ContentResult<bool>;
    /// A file of `to` whose value changed, carried or not.
    fn changed(&mut self, _serial: u64) -> ContentResult<()> {
        Ok(())
    }
    /// Whether `to` may keep, below inodes both roots hold, names and values
    /// `onto` lacks: adopted inodes are then reconciled.
    fn diverges(&self) -> bool {
        false
    }
    /// Places whose classification the changes flipped, asked once after the
    /// changes are planned; only when [`Self::diverges`].
    fn flipped(&mut self) -> ContentResult<Vec<Seed>> {
        Ok(Vec::new())
    }
}

/// A place of `to` whose kept names `onto` must come to equal.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Seed {
    /// A path, relative to the root, that `to` keeps.
    Path(String),
    /// A directory both roots hold.
    Directory(u64),
}

/// Carries every change.
pub struct All;
impl Keep for All {
    fn learn(&mut self, _: u64, _: &PathName, _: u64) {}
    fn binding(&mut self, _: u64, _: &PathName, _: bool) -> ContentResult<bool> {
        Ok(true)
    }
    fn value(&mut self, _: u64) -> ContentResult<bool> {
        Ok(true)
    }
}

/// One replay's result and what it carried.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Replayed {
    pub root: FilesystemRootId,
    /// Names bound or unbound, including those of brought subtrees.
    pub bindings: u64,
    /// Values carried for inodes `onto` has.
    pub values: u64,
    /// Inodes brought from `to`.
    pub brought: u64,
    /// Changes left out by [`Keep`] or because `onto` changed them too.
    pub skipped: u64,
}

fn directory(value: Option<&InodeValue>) -> bool {
    value.is_some_and(|value| value.kind == InodeKind::Directory)
}

/// The update one replay plans, and the trees it reads.
struct Replay<'a> {
    reader: &'a dyn AuthenticatedObjects,
    after: TreeTable,
    target: TreeTable,
    keep: &'a mut dyn Keep,
    work: DifferenceWork,
    directories: BTreeMap<u64, BTreeMap<PathName, Option<u64>>>,
    values: BTreeMap<u64, InodeValue>,
    fresh: BTreeSet<u64>,
    /// Inodes `onto` holds that a planned name binds anew.
    adopted: Vec<u64>,
    bindings: u64,
    carried: u64,
    skipped: u64,
}

/// `onto` plus the kept changes of `from → to`. Objects of the result go to
/// `consumer`; `reader` reads all three roots and what `consumer` accepted.
pub fn replay(
    reader: &dyn AuthenticatedObjects,
    consumer: &mut dyn FinalizedConsumer,
    [from, to, onto]: [FilesystemRootId; 3],
    keep: &mut dyn Keep,
) -> ContentResult<Replayed> {
    let unchanged = Replayed {
        root: onto,
        bindings: 0,
        values: 0,
        brought: 0,
        skipped: 0,
    };
    if from == to {
        return Ok(unchanged);
    }
    let before = TreeTable::open(reader, from)?;
    let mut replay = Replay {
        reader,
        after: TreeTable::open(reader, to)?,
        target: TreeTable::open(reader, onto)?,
        keep,
        work: DifferenceWork::default(),
        directories: BTreeMap::new(),
        values: BTreeMap::new(),
        fresh: BTreeSet::new(),
        adopted: Vec::new(),
        bindings: 0,
        carried: 0,
        skipped: 0,
    };
    let scope = replay.target.root.scope();
    if before.root.scope() != scope || replay.after.root.scope() != scope {
        return Err(ContentError::InvalidRecord("replay scope"));
    }
    let mut changed = Vec::new();
    inode_changes(
        reader,
        &before,
        &replay.after,
        &mut replay.work,
        |serial, was, now| {
            changed.push((serial, was.copied(), now.copied()));
            Ok(())
        },
    )?;
    let mut names = Vec::new();
    for (parent, was, now) in &changed {
        let Some(now) = now.filter(|now| now.kind == InodeKind::Directory) else {
            continue;
        };
        // Names in a directory `onto` lacks are never carried by name, so
        // a new ignored tree costs no listing.
        if !replay.is_directory(*parent)? {
            continue;
        }
        let listed = was
            .filter(|was| was.kind == InodeKind::Directory)
            .map(|was| was.content_root);
        if listed == Some(now.content_root) {
            continue;
        }
        binding_changes(
            reader,
            listed,
            Some(now.content_root),
            &mut replay.work,
            |name, old, new| {
                names.push((*parent, name.clone(), old, new));
                Ok(())
            },
        )?;
    }
    // Where `from` bound each inode a name change unbound.
    let mut olds: HashMap<u64, Vec<(u64, PathName)>> = HashMap::new();
    for (parent, name, old, new) in &names {
        if let Some(child) = new {
            replay.keep.learn(*parent, name, *child);
        }
        if let Some(old) = old {
            olds.entry(*old).or_default().push((*parent, name.clone()));
        }
    }
    for (parent, name, old, new) in names {
        // A brought directory's listing is complete already; a directory
        // `onto` lacks is either brought by its own name or not carried.
        if replay.fresh.contains(&parent) || !replay.is_directory(parent)? {
            continue;
        }
        let kind = match new {
            Some(child) => replay.after.value(reader, child)?,
            None => old
                .map(|old| before.value(reader, old))
                .transpose()?
                .flatten(),
        };
        if !replay
            .keep
            .binding(parent, &name, directory(kind.as_ref()))?
            || replay.target.lookup(reader, parent, &name)? != old
        {
            replay.skipped += 1;
            continue;
        }
        replay.place(parent, name, new)?;
    }
    for (serial, was, now) in &changed {
        let (Some(was), Some(now)) = (was, now) else {
            continue;
        };
        if now.kind != InodeKind::Directory {
            replay.keep.changed(*serial)?;
        }
        if replay.fresh.contains(serial) {
            continue;
        }
        let Some(current) = replay.target.value(reader, *serial)? else {
            continue;
        };
        if now.kind == InodeKind::Directory {
            // A directory's own attributes travel with its carried names only,
            // so names left out never make an unchanged-looking change.
            if replay.directories.contains_key(serial) && now.metadata_root != was.metadata_root {
                replay.values.insert(*serial, *now);
                replay.carried += 1;
            }
            continue;
        }
        if !same_value(&current, was) || !replay.keep.value(*serial)? {
            replay.skipped += 1;
            continue;
        }
        replay.values.insert(*serial, *now);
        replay.carried += 1;
    }
    if replay.keep.diverges() {
        let mut queue = Vec::new();
        for seed in replay.keep.flipped()? {
            match seed {
                Seed::Directory(serial) => queue.push(serial),
                Seed::Path(path) => replay.impose(&path, &mut queue)?,
            }
        }
        replay.reconcile(queue)?;
    }
    replay.detach(&olds)?;
    replay.finish(consumer, onto, unchanged)
}

impl Replay<'_> {
    fn is_directory(&self, serial: u64) -> ContentResult<bool> {
        Ok(directory(self.target.value(self.reader, serial)?.as_ref()))
    }

    fn bind(&mut self, parent: u64, name: PathName, child: Option<u64>) {
        self.directories
            .entry(parent)
            .or_default()
            .insert(name, child);
        self.bindings += 1;
    }

    /// The planned binding of `name` in `parent`, else `onto`'s.
    fn bound(&self, parent: u64, name: &PathName) -> ContentResult<Option<u64>> {
        match self
            .directories
            .get(&parent)
            .and_then(|names| names.get(name))
        {
            Some(planned) => Ok(*planned),
            None => self.target.lookup(self.reader, parent, name),
        }
    }

    /// Binds `child` and brings or adopts it.
    fn place(&mut self, parent: u64, name: PathName, child: Option<u64>) -> ContentResult<()> {
        self.bind(parent, name, child);
        if let Some(child) = child {
            if self.target.value(self.reader, child)?.is_none() {
                self.bring(child)?;
            } else {
                self.adopted.push(child);
            }
        }
        Ok(())
    }

    /// Brings `serial` and the kept part of its subtree from `to`. Inodes
    /// `onto` already has are adopted, not brought again.
    fn bring(&mut self, serial: u64) -> ContentResult<()> {
        let mut stack = vec![serial];
        while let Some(serial) = stack.pop() {
            if !self.fresh.insert(serial) {
                continue;
            }
            let value = self
                .after
                .value(self.reader, serial)?
                .ok_or(ContentError::InvalidRecord("replayed inode"))?;
            self.values.insert(serial, value);
            if value.kind != InodeKind::Directory {
                continue;
            }
            // Every brought directory gets a listing, an empty one included.
            self.directories.entry(serial).or_default();
            let mut children = Vec::new();
            list_directory(self.reader, value.content_root, |name, child| {
                children.push((name.clone(), child));
                Ok(true)
            })?;
            let serials: Vec<u64> = children.iter().map(|(_, child)| *child).collect();
            let values = self.after.values(self.reader, &serials)?;
            for ((name, child), value) in children.into_iter().zip(values) {
                self.keep.learn(serial, &name, child);
                if !self
                    .keep
                    .binding(serial, &name, directory(value.as_ref()))?
                {
                    self.skipped += 1;
                    continue;
                }
                self.bind(serial, name, Some(child));
                if self.target.value(self.reader, child)?.is_none() {
                    stack.push(child);
                } else {
                    self.adopted.push(child);
                }
            }
        }
        Ok(())
    }

    /// Makes `onto` reach `path` as `to` does: places the first name that
    /// differs, or queues the path's inode when every name already agrees.
    fn impose(&mut self, path: &str, queue: &mut Vec<u64>) -> ContentResult<()> {
        let mut parent = self.target.root_serial();
        let mut parts = path.split('/').filter(|part| !part.is_empty()).peekable();
        while let Some(part) = parts.next() {
            let name = PathName::new(part)?;
            let Some(child) = self.after.lookup(self.reader, parent, &name)? else {
                return Ok(());
            };
            self.keep.learn(parent, &name, child);
            if self.fresh.contains(&child) {
                return Ok(());
            }
            let bound = self.bound(parent, &name)?;
            if bound == Some(child) && parts.peek().is_some() {
                parent = child;
                continue;
            }
            let kind = self.after.value(self.reader, child)?;
            if !self.keep.binding(parent, &name, directory(kind.as_ref()))? {
                return Ok(());
            }
            if bound == Some(child) {
                queue.push(child);
            } else {
                self.place(parent, name, Some(child))?;
            }
            return Ok(());
        }
        Ok(())
    }

    /// Makes the kept names and values below each queued or adopted inode
    /// `to`'s. Names `to` does not keep stay as `onto` has them.
    fn reconcile(&mut self, mut queue: Vec<u64>) -> ContentResult<()> {
        let (mut seen, mut cursor) = (BTreeSet::new(), 0);
        loop {
            let serial = match queue.pop() {
                Some(serial) => serial,
                None if cursor < self.adopted.len() => {
                    cursor += 1;
                    self.adopted[cursor - 1]
                }
                None => return Ok(()),
            };
            if self.fresh.contains(&serial) || !seen.insert(serial) {
                continue;
            }
            let (Some(now), Some(current)) = (
                self.after.value(self.reader, serial)?,
                self.target.value(self.reader, serial)?,
            ) else {
                continue;
            };
            if now.kind != InodeKind::Directory || current.kind != InodeKind::Directory {
                if now.kind == current.kind
                    && !same_value(&current, &now)
                    && !self.values.contains_key(&serial)
                {
                    self.values.insert(serial, now);
                    self.carried += 1;
                }
                continue;
            }
            let mut differ = BTreeMap::new();
            if current.content_root != now.content_root {
                binding_changes(
                    self.reader,
                    Some(current.content_root),
                    Some(now.content_root),
                    &mut self.work,
                    |name, old, _| {
                        differ.insert(name.clone(), old);
                        Ok(())
                    },
                )?;
            }
            let mut children = Vec::new();
            list_directory(self.reader, now.content_root, |name, child| {
                children.push((name.clone(), child));
                Ok(true)
            })?;
            let serials: Vec<u64> = children.iter().map(|(_, child)| *child).collect();
            let values = self.after.values(self.reader, &serials)?;
            for ((name, child), value) in children.into_iter().zip(values) {
                self.keep.learn(serial, &name, child);
                let differs = differ.remove(&name).is_some();
                if !self
                    .keep
                    .binding(serial, &name, directory(value.as_ref()))?
                {
                    continue;
                }
                if differs {
                    self.place(serial, name, Some(child))?;
                } else {
                    queue.push(child);
                }
            }
            // Names only `onto` binds.
            for (name, old) in differ {
                let kind = old
                    .map(|old| self.target.value(self.reader, old))
                    .transpose()?
                    .flatten();
                if self.keep.binding(serial, &name, directory(kind.as_ref()))? {
                    self.bind(serial, name, None);
                }
            }
        }
    }

    /// Unbinds adopted inodes where `onto` still binds them: at the old
    /// names this replay saw, and for a directory whose old name it did not
    /// see, wherever a walk of `onto` finds it.
    fn detach(&mut self, olds: &HashMap<u64, Vec<(u64, PathName)>>) -> ContentResult<()> {
        for child in self.adopted.clone() {
            if self.fresh.contains(&child) {
                continue;
            }
            let seen = olds.get(&child).cloned().unwrap_or_default();
            let unseen = seen.is_empty() && self.is_directory(child)?;
            for (parent, name) in seen {
                if self.bound(parent, &name)? == Some(child) {
                    self.bind(parent, name, None);
                }
            }
            if !unseen {
                continue;
            }
            let wanted = BTreeSet::from([child]);
            let found = locate(self.reader, &self.target, &wanted, WALK)?;
            let Some(path) = found.get(&child) else {
                return Err(ContentError::InvalidRecord("adopted directory not found"));
            };
            let mut parent = self.target.root_serial();
            let mut parts = path.trim_start_matches('/').split('/').peekable();
            while let Some(part) = parts.next() {
                let name = PathName::new(part)?;
                if parts.peek().is_none() {
                    if self.bound(parent, &name)? == Some(child) {
                        self.bind(parent, name, None);
                    }
                    break;
                }
                match self.target.lookup(self.reader, parent, &name)? {
                    Some(next) => parent = next,
                    None => break,
                }
            }
        }
        Ok(())
    }

    fn finish(
        self,
        consumer: &mut dyn FinalizedConsumer,
        onto: FilesystemRootId,
        unchanged: Replayed,
    ) -> ContentResult<Replayed> {
        if self.directories.is_empty() && self.values.is_empty() {
            return Ok(Replayed {
                skipped: self.skipped,
                ..unchanged
            });
        }
        let directories: Vec<DirectoryUpdate> = self
            .directories
            .into_iter()
            .map(|(parent, changes)| DirectoryUpdate {
                parent,
                changes: changes.into_iter().collect(),
            })
            .collect();
        let inodes: Vec<InodeUpdate> = self
            .values
            .into_iter()
            .map(|(serial, value)| InodeUpdate { serial, value })
            .collect();
        let fresh: Vec<u64> = self.fresh.iter().copied().collect();
        let input = FilesystemInput {
            base: Some(onto),
            scope: self.target.root.scope(),
            root_serial: self.target.root_serial(),
            directories: &directories,
            inodes: &inodes,
            new_inodes: &fresh,
            resources: FilesystemResources::default(),
        };
        let mut objects = FilesystemObjects::new_with_accepted(self.reader, consumer, self.reader);
        let built = update_filesystem(&mut objects, &input, None)?;
        Ok(Replayed {
            root: built.root,
            bindings: self.bindings,
            values: self.carried,
            brought: fresh.len() as u64,
            skipped: self.skipped,
        })
    }
}

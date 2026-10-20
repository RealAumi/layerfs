//! Which names of one tree Git ignores, decided directory by directory from
//! the root: `.git/info/exclude`, every `.gitignore` on the way, and the
//! index's tracked paths, all read from that same tree. `.git` itself is
//! never ignored. A name that cannot be placed in the tree is kept, so an
//! unknown never withholds a change.
//!
//! Names left out stay out of the published root, so a change of the rules
//! or of the index can make kept what the published root never got: newly
//! tracked paths and directories whose rules changed are handed back to the
//! replay to reconcile.
use super::index::Tracked;
use super::replay::{Keep, Seed};
use super::rules::{Rules, Stack};
use layerfs_content::compare::{list_directory, BindingHints, TreeTable};
use layerfs_content::filesystem::PathName;
use layerfs_content::inode_leaf::InodeKind;
use layerfs_content::{read_all_bounded, AuthenticatedObjects, ContentResult, ObjectId};
use layerfs_telemetry::timer::Timing;
use std::collections::{BTreeSet, HashMap, VecDeque};
use std::rc::Rc;
use std::sync::Arc;

/// Rule files larger than this are read as empty.
const RULE_BYTES: u64 = 1 << 20;
/// Directories the single fallback placement walk may list.
const WALK: usize = 1 << 20;
/// Bindings one climb follows before it falls back to the walk.
const DEPTH: usize = 4096;

struct Dir {
    path: String,
    /// Excluded by the patterns, tracked paths below it or not.
    ignored: bool,
    /// `.git` or below: never ignored, never read for rules.
    git: bool,
    rules: Stack,
}

/// [`Keep`] for one Commit's local tree: carries what Git does not ignore.
pub struct Ignore<'r> {
    reader: &'r dyn AuthenticatedObjects,
    tree: TreeTable,
    hints: &'r dyn BindingHints,
    tracked: Arc<Tracked>,
    dirs: HashMap<u64, Option<Rc<Dir>>>,
    /// Bindings this replay saw, by child.
    pub learned: HashMap<u64, Vec<(u64, PathName)>>,
    /// Decisions kept because the name could not be placed.
    pub unplaced: u64,
    /// Names left out as ignored.
    pub ignored: u64,
    /// Paths the index tracks now but did not before.
    newly: Vec<String>,
    /// Directories whose rules changed; the root for `.git/info/exclude`.
    rules: BTreeSet<u64>,
    walked: bool,
    pub seeds: Vec<Seed>,
}

fn join(path: &str, name: &PathName) -> String {
    if path.is_empty() {
        name.as_str().to_owned()
    } else {
        format!("{path}/{}", name.as_str())
    }
}

impl<'r> Ignore<'r> {
    pub fn new(
        reader: &'r dyn AuthenticatedObjects,
        tree: TreeTable,
        hints: &'r dyn BindingHints,
        tracked: Arc<Tracked>,
        newly: Vec<String>,
    ) -> Self {
        Self {
            reader,
            tree,
            hints,
            tracked,
            dirs: HashMap::new(),
            learned: HashMap::new(),
            unplaced: 0,
            ignored: 0,
            newly,
            rules: BTreeSet::new(),
            walked: false,
            seeds: Vec::new(),
        }
    }

    /// Raw directory identities survive until the next projection's tree is known.
    pub(super) fn take_flips(&mut self) -> Vec<Seed> {
        let mut seeds: Vec<Seed> = std::mem::take(&mut self.newly)
            .into_iter()
            .map(Seed::Path)
            .collect();
        seeds.append(&mut self.seeds);
        seeds.extend(
            std::mem::take(&mut self.rules)
                .into_iter()
                .map(Seed::Directory),
        );
        seeds
    }

    /// Notes `name` in `parent` if it is a rule file.
    fn note(&mut self, parent: u64, name: &PathName) -> ContentResult<()> {
        match name.as_str() {
            ".gitignore" => {
                self.rules.insert(parent);
            }
            "exclude" if Some(parent) == self.info()? => {
                self.rules.insert(self.tree.root_serial());
            }
            _ => {}
        }
        Ok(())
    }

    /// The serial of `.git/info`, if the tree has one.
    fn info(&self) -> ContentResult<Option<u64>> {
        let root = self.tree.root_serial();
        let Some(git) = self
            .tree
            .lookup(self.reader, root, &PathName::new(".git")?)?
        else {
            return Ok(None);
        };
        self.tree.lookup(self.reader, git, &PathName::new("info")?)
    }

    /// Whether the patterns exclude `name` in `parent`, as Git decides for a
    /// path it does not track: below an excluded directory, everything is.
    fn excluded(&self, parent: &Dir, name: &PathName, directory: bool) -> bool {
        if parent.git || (parent.path.is_empty() && name.as_str() == ".git") {
            return false;
        }
        parent.ignored || parent.rules.ignored(&join(&parent.path, name), directory)
    }

    /// Whether `name` in `parent` is ignored: excluded and not tracked.
    fn ignores(&self, parent: &Dir, name: &PathName, directory: bool) -> bool {
        self.excluded(parent, name, directory) && !self.tracked.covers(&join(&parent.path, name))
    }

    /// The bytes of a regular file `name` in directory `serial`, if any.
    fn file(&self, serial: u64, name: &str) -> ContentResult<Option<Vec<u8>>> {
        let Some(child) = self
            .tree
            .lookup(self.reader, serial, &PathName::new(name)?)?
        else {
            return Ok(None);
        };
        match self.tree.value(self.reader, child)? {
            Some(value) if value.kind == InodeKind::RegularFile => {
                read_file(self.reader, value.content_root, RULE_BYTES)
            }
            _ => Ok(None),
        }
    }

    fn root(&self) -> ContentResult<Rc<Dir>> {
        let root = self.tree.root_serial();
        let mut rules = Stack::default();
        let git = self
            .tree
            .lookup(self.reader, root, &PathName::new(".git")?)?;
        if let Some(info) = git
            .map(|git| self.tree.lookup(self.reader, git, &PathName::new("info")?))
            .transpose()?
            .flatten()
        {
            if let Some(text) = self.file(info, "exclude")? {
                rules = rules.with(Rules::parse("", &text));
            }
        }
        if let Some(text) = self.file(root, ".gitignore")? {
            rules = rules.with(Rules::parse("", &text));
        }
        Ok(Rc::new(Dir {
            path: String::new(),
            ignored: false,
            git: false,
            rules,
        }))
    }

    fn descend(&self, parent: &Dir, name: &PathName, serial: u64) -> ContentResult<Rc<Dir>> {
        let path = join(&parent.path, name);
        let git = parent.git || (parent.path.is_empty() && name.as_str() == ".git");
        let ignored = self.excluded(parent, name, true);
        let rules = if ignored || git {
            Stack::default()
        } else {
            match self.file(serial, ".gitignore")? {
                Some(text) => parent.rules.with(Rules::parse(&path, &text)),
                None => parent.rules.clone(),
            }
        };
        Ok(Rc::new(Dir {
            path,
            ignored,
            git,
            rules,
        }))
    }

    /// The checked bindings of `serial`: learned this replay, then hinted.
    fn bindings(&self, serial: u64) -> ContentResult<Vec<(u64, PathName)>> {
        if self.walked {
            return Ok(self.learned.get(&serial).cloned().unwrap_or_default());
        }
        let mut seen = BTreeSet::new();
        let mut checked = Vec::new();
        let learned = self.learned.get(&serial).cloned().unwrap_or_default();
        for (parent, name) in learned.into_iter().chain(self.hints.bindings_of(serial)?) {
            if seen.insert((parent, name.clone()))
                && self.tree.lookup(self.reader, parent, &name)? == Some(serial)
            {
                checked.push((parent, name));
            }
        }
        Ok(checked)
    }

    /// The directory `serial`, climbed from its bindings to a known
    /// directory, else placed by a walk from the root.
    fn dir(&mut self, serial: u64) -> ContentResult<Option<Rc<Dir>>> {
        let mut chain = Vec::new();
        let mut current = serial;
        let top = loop {
            if let Some(known) = self.dirs.get(&current) {
                break known.clone();
            }
            if current == self.tree.root_serial() {
                let root = self.root()?;
                self.dirs.insert(current, Some(root.clone()));
                break Some(root);
            }
            match self.bindings(current)?.into_iter().next() {
                Some((parent, name)) if chain.len() < DEPTH => {
                    chain.push((current, name));
                    current = parent;
                }
                _ => break None,
            }
        };
        let Some(mut dir) = top else {
            return self.walk_to(serial);
        };
        for (serial, name) in chain.into_iter().rev() {
            dir = self.descend(&dir, &name, serial)?;
            self.dirs.insert(serial, Some(dir.clone()));
        }
        Ok(Some(dir))
    }

    /// At most one complete, bounded placement walk per projection. Every
    /// alias is recorded, including names not touched by this Commit.
    fn walk(&mut self) -> ContentResult<()> {
        if self.walked {
            return Ok(());
        }
        let mut queue = VecDeque::from([self.tree.root_serial()]);
        self.learned.clear();
        for _ in 0..WALK {
            let Some(parent) = queue.pop_front() else {
                break;
            };
            let value = self.tree.value(self.reader, parent)?.expect("directory");
            let mut children = Vec::new();
            list_directory(self.reader, value.content_root, |name, child| {
                children.push((name.clone(), child));
                Ok(true)
            })?;
            let serials: Vec<_> = children.iter().map(|(_, child)| *child).collect();
            let values = self.tree.values(self.reader, &serials)?;
            for ((name, child), value) in children.into_iter().zip(values) {
                self.learn(parent, &name, child);
                if value.is_some_and(|v| v.kind == InodeKind::Directory) {
                    queue.push_back(child);
                }
            }
        }
        self.walked = true;
        Ok(())
    }

    fn complete_bindings(
        &mut self,
        serial: u64,
        count: u64,
    ) -> ContentResult<Vec<(u64, PathName)>> {
        let bindings = self.bindings(serial)?;
        if bindings.len() as u64 >= count {
            return Ok(bindings);
        }
        self.walk()?;
        self.bindings(serial)
    }

    fn walk_to(&mut self, serial: u64) -> ContentResult<Option<Rc<Dir>>> {
        self.walk()?;
        let mut chain = Vec::new();
        let mut current = serial;
        let mut dir = loop {
            if let Some(Some(dir)) = self.dirs.get(&current) {
                break dir.clone();
            }
            if current == self.tree.root_serial() {
                break self.root()?;
            }
            let Some((parent, name)) = self.bindings(current)?.into_iter().next() else {
                return Ok(None);
            };
            if chain.len() == WALK {
                return Ok(None);
            }
            chain.push((current, name));
            current = parent;
        };
        for (child, name) in chain.into_iter().rev() {
            dir = self.descend(&dir, &name, child)?;
            self.dirs.insert(child, Some(dir.clone()));
        }
        self.dirs.insert(serial, Some(dir.clone()));
        Ok(Some(dir))
    }
}

impl Keep for Ignore<'_> {
    fn learn(&mut self, parent: u64, name: &PathName, child: u64) {
        let known = self.learned.entry(child).or_default();
        if !known.iter().any(|(p, n)| *p == parent && n == name) {
            known.push((parent, name.clone()));
        }
    }

    fn binding(&mut self, parent: u64, name: &PathName, directory: bool) -> ContentResult<bool> {
        self.note(parent, name)?;
        let Some(dir) = self.dir(parent)? else {
            self.unplaced += 1;
            return Ok(true);
        };
        let ignored = self.ignores(&dir, name, directory);
        self.ignored += u64::from(ignored);
        Ok(!ignored)
    }

    /// Carried when any name of the file is kept, or when some name of it
    /// cannot be placed.
    fn value(&mut self, serial: u64) -> ContentResult<bool> {
        let Some(value) = self.tree.value(self.reader, serial)? else {
            return Ok(true);
        };
        let mut named = 0u64;
        for (parent, name) in self.complete_bindings(serial, value.namespace_ref_count.max(1))? {
            named += 1;
            self.note(parent, &name)?;
            let Some(dir) = self.dir(parent)? else {
                self.unplaced += 1;
                return Ok(true);
            };
            if !self.ignores(&dir, &name, false) {
                return Ok(true);
            }
        }
        if named < value.namespace_ref_count.max(1) {
            self.unplaced += 1;
            return Ok(true);
        }
        self.ignored += 1;
        Ok(false)
    }

    /// Notes a changed rule file by the names it was seen under; a change
    /// to an ignored one counts too, as Git reads it all the same.
    fn changed(&mut self, serial: u64) -> ContentResult<()> {
        let count = self
            .tree
            .value(self.reader, serial)?
            .map_or(0, |v| v.namespace_ref_count);
        for (parent, name) in self.complete_bindings(serial, count)? {
            self.note(parent, &name)?;
        }
        Ok(())
    }

    fn diverges(&self) -> bool {
        true
    }

    fn flipped(&mut self) -> ContentResult<Vec<Seed>> {
        let mut seeds = self.take_flips();
        for seed in &mut seeds {
            if let Seed::Directory(serial) = seed {
                if *serial != self.tree.root_serial() {
                    if let Some(dir) = self.dir(*serial)? {
                        *seed = Seed::Path(dir.path.clone());
                    }
                }
            }
        }
        Ok(seeds)
    }
}

/// The content root of `.git/index` in `tree`, if it is a regular file.
pub fn index_root(
    reader: &dyn AuthenticatedObjects,
    tree: &TreeTable,
) -> ContentResult<Option<ObjectId>> {
    file_root(reader, tree, &[".git", "index"])
}

pub(super) fn file_root(
    reader: &dyn AuthenticatedObjects,
    tree: &TreeTable,
    path: &[&str],
) -> ContentResult<Option<ObjectId>> {
    let mut serial = tree.root_serial();
    for name in path {
        let Some(child) = tree.lookup(reader, serial, &PathName::new(name)?)? else {
            return Ok(None);
        };
        serial = child;
    }
    Ok(tree
        .value(reader, serial)?
        .filter(|v| v.kind == InodeKind::RegularFile)
        .map(|v| v.content_root))
}

/// A whole file's bytes, or `None` when it is longer than `maximum`.
pub fn read_file(
    reader: &dyn AuthenticatedObjects,
    root: ObjectId,
    maximum: u64,
) -> ContentResult<Option<Vec<u8>>> {
    let mut bytes = Vec::new();
    let read = Timing::disabled("ignore.read", |scope| {
        read_all_bounded(reader, root, maximum, &mut bytes, scope.child("file"))
    })
    .0;
    match read {
        Ok(_) => Ok(Some(bytes)),
        Err(layerfs_content::ContentError::BoundedCapacityExceeded { .. }) => Ok(None),
        Err(error) => Err(error),
    }
}

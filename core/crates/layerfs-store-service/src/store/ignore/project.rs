//! One remote Commit with Git-ignored names kept local: the root it publishes
//! and the local base it installs.
use super::classify::{file_root, index_root, read_file, Ignore};
use super::index::{self, Tracked};
use super::replay::{replay, All, Keep, Seed};
use layerfs_content::compare::TreeTable;
use layerfs_content::filesystem::{FilesystemRootId, PathName};
use layerfs_content::{AuthenticatedObjects, ContentResult, FinalizedConsumer, ObjectId};
use layerfs_workspace::PathHints;
use std::sync::Arc;

/// `.git/index` files larger than this are not read.
const INDEX_BYTES: u64 = 256 << 20;

/// A local base that is not the published root: the Workspace's tree, and the
/// published root it projects onto (pending flips reconcile on the next Commit).
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct LocalBase {
    pub local: ObjectId,
    pub published: ObjectId,
}

/// What one Commit's projection did.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct Projection {
    /// Names and file values carried to the published root.
    pub carried: u64,
    /// Names and file values left out as ignored.
    pub ignored: u64,
    /// Changes left out because the published root changed them too.
    pub conflicting: u64,
    /// Decisions kept because the name could not be placed.
    pub unplaced: u64,
    /// Paths the index tracks.
    pub tracked: usize,
    /// The index could not be read; only patterns determine what is kept.
    pub unreadable_index: bool,
}

/// Last installed local view and the original history binding for its next merge.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RestorePoint {
    pub binding: layerfs_history::BranchSnapshot,
    pub local: ObjectId,
    pub published: ObjectId,
    pub seeds: Vec<Seed>,
}

/// Per-Workspace state: local base, pending flips, and the last two indexes read.
#[derive(Debug, Default)]
pub struct IgnoreState {
    pub base: Option<LocalBase>,
    index: Vec<(ObjectId, Arc<Tracked>)>,
    pub last: Option<Projection>,
    pub pending: Vec<Seed>,
}

impl IgnoreState {
    /// Tracked paths of `tree`'s index: none when it has no index, `None`
    /// when an index is there but cannot be read.
    fn tracked(
        &mut self,
        reader: &dyn AuthenticatedObjects,
        tree: &TreeTable,
    ) -> ContentResult<Option<Arc<Tracked>>> {
        let Some(root) = index_root(reader, tree)? else {
            return Ok(Some(Arc::default()));
        };
        if let Some((_, tracked)) = self.index.iter().find(|(known, _)| *known == root) {
            return Ok(Some(tracked.clone()));
        }
        let Some(tracked) = read_file(reader, root, INDEX_BYTES)?
            .as_deref()
            .and_then(index::parse)
        else {
            return Ok(None);
        };
        let tracked = Arc::new(tracked);
        self.index.insert(0, (root, tracked.clone()));
        self.index.truncate(2);
        Ok(Some(tracked))
    }

    /// The root to publish for `built`, the tree constructed on `local`, whose
    /// kept names equal those of `published`: `published` plus the changes
    /// of `local → built` that Git does not ignore. Objects go to `consumer`.
    pub fn project(
        &mut self,
        reader: &dyn AuthenticatedObjects,
        consumer: &mut dyn FinalizedConsumer,
        hints: &PathHints,
        [published, local, built]: [FilesystemRootId; 3],
    ) -> ContentResult<FilesystemRootId> {
        let tree = TreeTable::open(reader, built)?;
        let tracked = self.tracked(reader, &tree)?;
        let unreadable_index = tracked.is_none();
        let tracked = tracked.unwrap_or_default();
        let before = self
            .tracked(reader, &TreeTable::open(reader, local)?)?
            .unwrap_or_default();
        let newly = tracked.added(&before);
        let mut keep = Ignore::new(reader, tree, hints, tracked.clone(), newly);
        keep.seeds = self.pending.clone();
        let replayed = replay(reader, consumer, [local, built, published], &mut keep)?;
        for (child, bindings) in &keep.learned {
            for (parent, name) in bindings {
                hints.record(*child, *parent, name);
            }
        }
        self.last = Some(Projection {
            carried: replayed.bindings + replayed.values,
            ignored: keep.ignored,
            conflicting: replayed.skipped.saturating_sub(keep.ignored),
            unplaced: keep.unplaced,
            tracked: tracked.len(),
            unreadable_index,
        });
        // Nothing left out of a tree with no local-only names: the built tree
        // is the published one, and no local base forms.
        if replayed.skipped == 0 && local == published && self.pending.is_empty() {
            return Ok(built);
        }
        Ok(replayed.root)
    }

    /// A known publication acknowledges the pending seeds consumed by project.
    /// Failed or uncertain publication must never call this method.
    pub fn published(&mut self) {
        self.pending.clear();
    }

    /// Rebase after publication, remembering server rule/index flips for the
    /// next projection. Until then the local kept view may be ahead of Q.
    pub fn rebase(
        &mut self,
        reader: &dyn AuthenticatedObjects,
        consumer: &mut dyn FinalizedConsumer,
        hints: &PathHints,
        [candidate, published, built]: [FilesystemRootId; 3],
    ) -> ContentResult<FilesystemRootId> {
        if candidate == published {
            return Ok(built);
        }
        let before = TreeTable::open(reader, candidate)?;
        let after = TreeTable::open(reader, published)?;
        let tracked = self.tracked(reader, &after)?.unwrap_or_default();
        let previous = self.tracked(reader, &before)?.unwrap_or_default();
        let newly = tracked.added(&previous);
        let mut keep = ServerChanges(Ignore::new(reader, after, hints, tracked, newly));
        let exclude = &[".git", "info", "exclude"];
        if file_root(reader, &before, exclude)? != file_root(reader, &after, exclude)? {
            keep.0.seeds.push(Seed::Directory(after.root_serial()));
        }
        let result = replay(reader, consumer, [candidate, published, built], &mut keep)?.root;
        self.pending.extend(keep.0.take_flips());
        Ok(result)
    }
}

/// The next local base: `built` plus what publication added to `candidate`
/// (a merge with a moved head), with `built`'s own names kept where both
/// changed. Work follows the publication's change, not the local names.
pub fn rebase(
    reader: &dyn AuthenticatedObjects,
    consumer: &mut dyn FinalizedConsumer,
    [candidate, published, built]: [FilesystemRootId; 3],
) -> ContentResult<FilesystemRootId> {
    if published == candidate {
        return Ok(built);
    }
    Ok(replay(reader, consumer, [candidate, published, built], &mut All)?.root)
}

/// Classify only to observe flips; carry all server changes in this replay.
struct ServerChanges<'a>(Ignore<'a>);
impl Keep for ServerChanges<'_> {
    fn learn(&mut self, parent: u64, name: &PathName, child: u64) {
        self.0.learn(parent, name, child);
    }
    fn binding(&mut self, parent: u64, name: &PathName, directory: bool) -> ContentResult<bool> {
        self.0.binding(parent, name, directory)?;
        Ok(true)
    }
    fn changed(&mut self, serial: u64) -> ContentResult<()> {
        self.0.changed(serial)
    }
    fn value(&mut self, _: u64) -> ContentResult<bool> {
        Ok(true)
    }
    fn preserve_local(&self) -> bool {
        true
    }
    fn retained(&mut self, serial: u64) {
        self.0.seeds.push(Seed::Directory(serial));
    }
}

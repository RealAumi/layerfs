//! One remote Commit with Git-ignored names kept local: the root it publishes
//! and the local base it installs.
use super::classify::{index_root, read_file, Ignore};
use super::index::{self, Tracked};
use super::replay::{replay, All};
use layerfs_content::compare::TreeTable;
use layerfs_content::filesystem::FilesystemRootId;
use layerfs_content::{AuthenticatedObjects, ContentResult, FinalizedConsumer, ObjectId};
use layerfs_workspace::PathHints;
use std::sync::Arc;

/// `.git/index` files larger than this are not read.
const INDEX_BYTES: u64 = 256 << 20;

/// A local base that is not the published root: the Workspace's tree, and the
/// published root its kept names equal.
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
    /// The index could not be read, so nothing was left out.
    pub unreadable_index: bool,
}

/// Per-Workspace state: the local base, and the last two indexes read.
#[derive(Debug, Default)]
pub struct IgnoreState {
    pub base: Option<LocalBase>,
    index: Vec<(ObjectId, Arc<Tracked>)>,
    pub last: Option<Projection>,
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
        let Some(tracked) = self.tracked(reader, &tree)? else {
            // Never withhold a change on a guess: publish the whole tree.
            self.last = Some(Projection {
                unreadable_index: true,
                ..Projection::default()
            });
            return Ok(built);
        };
        // A previous index that could not be read published its whole tree,
        // so nothing it tracked can have been left out.
        let newly = match self.tracked(reader, &TreeTable::open(reader, local)?)? {
            Some(before) => tracked.added(&before),
            None => Vec::new(),
        };
        let mut keep = Ignore::new(reader, tree, hints, tracked.clone(), newly);
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
            unreadable_index: false,
        });
        // Nothing left out of a tree with no local-only names: the built tree
        // is the published one, and no local base forms.
        if replayed.skipped == 0 && local == published {
            return Ok(built);
        }
        Ok(replayed.root)
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

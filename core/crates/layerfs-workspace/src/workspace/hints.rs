//! Name bindings this Workspace has seen: every inode the kernel looked up and
//! every binding a Commit added, as path hints for Commit-time path rules.
//! A hint is advisory: readers check it against the tree they name.
use layerfs_content::{compare::BindingHints, filesystem::PathName, ContentResult};
use std::{collections::HashMap, sync::Mutex};

/// Bindings kept per inode; the oldest goes first past it.
const PER_INODE: usize = 8;

#[derive(Debug, Default)]
pub struct PathHints(Mutex<HashMap<u64, Vec<(u64, PathName)>>>);

impl PathHints {
    /// Records that `parent` binds `name` to `child`.
    pub fn record(&self, child: u64, parent: u64, name: &PathName) {
        let mut hints = self.0.lock().unwrap_or_else(|e| e.into_inner());
        let known = hints.entry(child).or_default();
        if known.iter().any(|(p, n)| *p == parent && n == name) {
            return;
        }
        if known.len() == PER_INODE {
            known.remove(0);
        }
        known.push((parent, name.clone()));
    }
    /// Inodes with at least one recorded binding.
    pub fn len(&self) -> usize {
        self.0.lock().unwrap_or_else(|e| e.into_inner()).len()
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

impl BindingHints for PathHints {
    fn bindings_of(&self, child: u64) -> ContentResult<Vec<(u64, PathName)>> {
        Ok(self
            .0
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .get(&child)
            .cloned()
            .unwrap_or_default())
    }
}

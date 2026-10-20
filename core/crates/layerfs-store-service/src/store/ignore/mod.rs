//! Git-ignored names stay local (mp2 fork). A remote Workspace's Commit builds
//! its whole local tree as before, then publishes a projection of it: the
//! published root plus the changes Git does not ignore. The Workspace keeps
//! the whole tree as its local base; ignored objects never leave the sandbox.
//! See docs/mp2/ignore.md.
mod classify;
mod index;
mod project;
mod replay;
mod rules;
#[cfg(test)]
mod tests;

pub use project::{rebase, IgnoreState, LocalBase, Projection};
pub use replay::{replay, All, Keep, Replayed, Seed};

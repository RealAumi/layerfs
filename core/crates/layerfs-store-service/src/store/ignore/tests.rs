//! The remote Commit round trip at the content level: a warm base, local
//! Commits projected to published roots, and the local base installed after
//! each publication, with or without a moved head.
use super::classify::read_file;
use super::project::{rebase, IgnoreState, LocalBase};
use layerfs_content::compare::{subtree, TreeTable};
use layerfs_content::filesystem::attributes::portable::PortableMetadata;
use layerfs_content::filesystem::{
    build_filesystem, scope_for_seed, FilesystemResources, FilesystemRootId, PathName,
};
use layerfs_content::inode_leaf::{InodeKind, InodeMetadata, InodeValue};
use layerfs_content::{
    construct_bytes, update_filesystem, AuthenticatedObjects, ConstructionPolicy, ContentError,
    ContentResult, DirectoryUpdate, FilesystemInput, FilesystemObjects, FinalizedConsumer,
    FinalizedObject, InodeUpdate, ObjectId,
};
use layerfs_telemetry::timer::Timing;
use layerfs_workspace::PathHints;
use std::cell::{Cell, RefCell};
use std::collections::{BTreeMap, BTreeSet};

const ROOT: u64 = 1;

#[derive(Default)]
struct Mem {
    objects: RefCell<BTreeMap<ObjectId, Vec<u8>>>,
    next: Cell<u64>,
}

impl AuthenticatedObjects for Mem {
    fn read_canonical_batch(&self, ids: &[ObjectId]) -> ContentResult<Vec<Vec<u8>>> {
        let objects = self.objects.borrow();
        ids.iter()
            .map(|id| objects.get(id).cloned().ok_or(ContentError::MissingObject))
            .collect()
    }
}

struct Sink<'m>(&'m Mem);

impl FinalizedConsumer for Sink<'_> {
    fn accept(&mut self, object: FinalizedObject) -> ContentResult<()> {
        let parts = object.into_parts();
        self.0
            .objects
            .borrow_mut()
            .insert(parts.id, parts.canonical);
        Ok(())
    }
}

enum Op<'a> {
    Write(&'a str, &'a [u8]),
    Remove(&'a str),
    Move(&'a str, &'a str),
}
use Op::{Move, Remove, Write};

fn name(part: &str) -> PathName {
    PathName::new(part).expect("name")
}

fn metadata(mode: u32) -> InodeMetadata {
    InodeMetadata::Inline(PortableMetadata {
        mode,
        mtime_seconds: 1_700_000_000,
        mtime_nanoseconds: 0,
    })
}

fn directory() -> InodeValue {
    InodeValue {
        kind: InodeKind::Directory,
        namespace_ref_count: 0,
        content_root: ObjectId::for_bytes(b"ignore-tests/unused"),
        metadata_root: metadata(0o755),
    }
}

/// One set of edits to a root, planned path by path.
struct Edit<'m> {
    mem: &'m Mem,
    tree: Option<TreeTable>,
    directories: BTreeMap<u64, BTreeMap<PathName, Option<u64>>>,
    values: BTreeMap<u64, InodeValue>,
    fresh: BTreeSet<u64>,
}

impl Edit<'_> {
    fn lookup(&self, parent: u64, part: &PathName) -> Option<u64> {
        if let Some(planned) = self
            .directories
            .get(&parent)
            .and_then(|names| names.get(part))
        {
            return *planned;
        }
        if self.fresh.contains(&parent) {
            return None;
        }
        self.tree
            .as_ref()?
            .lookup(self.mem, parent, part)
            .expect("lookup")
    }

    fn bind(&mut self, parent: u64, part: PathName, child: Option<u64>) {
        self.directories
            .entry(parent)
            .or_default()
            .insert(part, child);
    }

    fn create(&mut self, value: InodeValue) -> u64 {
        let serial = self.mem.next.get().max(ROOT) + 1;
        self.mem.next.set(serial);
        self.fresh.insert(serial);
        self.values.insert(serial, value);
        if value.kind == InodeKind::Directory {
            self.directories.entry(serial).or_default();
        }
        serial
    }

    /// The parent of `path`, its directories created as needed.
    fn parent(&mut self, path: &str) -> (u64, PathName) {
        let mut parts = path.split('/').collect::<Vec<_>>();
        let last = name(parts.pop().expect("path"));
        let mut current = ROOT;
        for part in parts {
            let part = name(part);
            current = match self.lookup(current, &part) {
                Some(child) => child,
                None => {
                    let child = self.create(directory());
                    self.bind(current, part, Some(child));
                    child
                }
            };
        }
        (current, last)
    }

    fn apply(&mut self, op: &Op<'_>) {
        match *op {
            Write(path, bytes) => {
                let policy = ConstructionPolicy::frozen_default();
                let content_root = Timing::disabled("ignore.tests", |scope| {
                    construct_bytes(
                        policy,
                        &policy.capacities(),
                        bytes,
                        &mut Sink(self.mem),
                        scope.child("construct"),
                    )
                })
                .0
                .expect("construct")
                .root;
                let value = InodeValue {
                    kind: InodeKind::RegularFile,
                    namespace_ref_count: 0,
                    content_root,
                    metadata_root: metadata(0o644),
                };
                let (parent, part) = self.parent(path);
                match self.lookup(parent, &part) {
                    Some(serial) => {
                        self.values.insert(serial, value);
                    }
                    None => {
                        let serial = self.create(value);
                        self.bind(parent, part, Some(serial));
                    }
                }
            }
            Remove(path) => {
                let (parent, part) = self.parent(path);
                self.bind(parent, part, None);
            }
            Move(from, to) => {
                let (parent, part) = self.parent(from);
                let serial = self.lookup(parent, &part).expect("moved name");
                self.bind(parent, part, None);
                let (parent, part) = self.parent(to);
                self.bind(parent, part, Some(serial));
            }
        }
    }
}

impl Mem {
    fn edit(&self, base: Option<FilesystemRootId>, ops: &[Op<'_>]) -> FilesystemRootId {
        let mut edit = Edit {
            mem: self,
            tree: base.map(|base| TreeTable::open(self, base).expect("open")),
            directories: BTreeMap::new(),
            values: BTreeMap::new(),
            fresh: BTreeSet::new(),
        };
        if base.is_none() {
            edit.fresh.insert(ROOT);
            edit.values.insert(ROOT, directory());
            edit.directories.entry(ROOT).or_default();
        }
        for op in ops {
            edit.apply(op);
        }
        let directories: Vec<DirectoryUpdate> = edit
            .directories
            .into_iter()
            .map(|(parent, changes)| DirectoryUpdate {
                parent,
                changes: changes.into_iter().collect(),
            })
            .collect();
        let inodes: Vec<InodeUpdate> = edit
            .values
            .into_iter()
            .map(|(serial, value)| InodeUpdate { serial, value })
            .collect();
        let fresh: Vec<u64> = edit.fresh.into_iter().collect();
        let input = FilesystemInput {
            base,
            scope: scope_for_seed([0x16; 32]),
            root_serial: ROOT,
            directories: &directories,
            inodes: &inodes,
            new_inodes: &fresh,
            resources: FilesystemResources::default(),
        };
        let mut sink = Sink(self);
        let mut objects = FilesystemObjects::new_with_accepted(self, &mut sink, self);
        let built = match base {
            None => build_filesystem(&mut objects, &input, None),
            Some(_) => update_filesystem(&mut objects, &input, None),
        };
        built.expect("tree").root
    }

    /// Every path of a root: files with their text, directories as `path/`.
    fn files(&self, root: FilesystemRootId) -> BTreeMap<String, String> {
        let tree = TreeTable::open(self, root).expect("open");
        let mut entries = Vec::new();
        subtree(self, &tree, "/", ROOT, usize::MAX, &mut entries).expect("walk");
        entries
            .into_iter()
            .map(|(path, _, value)| {
                let path = path.trim_start_matches('/');
                match value.kind {
                    InodeKind::Directory => (format!("{path}/"), String::new()),
                    _ => {
                        let bytes = read_file(self, value.content_root, 1 << 20)
                            .expect("read")
                            .expect("bounded");
                        (
                            path.to_owned(),
                            String::from_utf8_lossy(&bytes).into_owned(),
                        )
                    }
                }
            })
            .collect()
    }
}

/// A version 2 index tracking `paths`.
fn index(paths: &[&str]) -> Vec<u8> {
    let mut paths = paths.to_vec();
    paths.sort_unstable();
    let mut bytes = b"DIRC".to_vec();
    bytes.extend_from_slice(&2u32.to_be_bytes());
    bytes.extend_from_slice(&(paths.len() as u32).to_be_bytes());
    for path in paths {
        let mut entry = vec![0u8; 60];
        entry.extend_from_slice(&(path.len() as u16).to_be_bytes());
        entry.extend_from_slice(path.as_bytes());
        entry.resize((entry.len() + 8) / 8 * 8, 0);
        bytes.extend_from_slice(&entry);
    }
    bytes.extend_from_slice(&[0; 20]);
    bytes
}

const TRACKED: &[&str] = &[".gitignore", "build/keep.txt", "src/A.java"];

/// A warm base built with ignore off: ignored outputs included.
fn warm(mem: &Mem) -> FilesystemRootId {
    let index = index(TRACKED);
    mem.edit(
        None,
        &[
            Write(
                ".gitignore",
                b"target/\nnode_modules/\nbuild/\nout/\n*.log\n",
            ),
            Write(".git/HEAD", b"ref: refs/heads/main\n"),
            Write(".git/index", &index),
            Write("src/A.java", b"v1"),
            Write("build/keep.txt", b"keep v1"),
            Write("target/old.class", b"old"),
            Write("node_modules/x/index.js", b"x"),
        ],
    )
}

/// One Workspace's remote Commits, as `remote_commit` runs them.
struct Workspace<'m> {
    mem: &'m Mem,
    state: IgnoreState,
    hints: PathHints,
    published: FilesystemRootId,
}

impl<'m> Workspace<'m> {
    fn new(mem: &'m Mem) -> Self {
        Self {
            mem,
            state: IgnoreState::default(),
            hints: PathHints::default(),
            published: warm(mem),
        }
    }

    fn local(&self) -> FilesystemRootId {
        self.state
            .base
            .map_or(self.published, |base| FilesystemRootId(base.local))
    }

    /// Commits `ops`; the head moves by `server` before publication lands.
    /// Returns the published root.
    fn commit(&mut self, ops: &[Op<'_>], server: &[Op<'_>]) -> FilesystemRootId {
        let local = self.local();
        let built = self.mem.edit(Some(local), ops);
        let candidate = self
            .state
            .project(
                self.mem,
                &mut Sink(self.mem),
                &self.hints,
                [self.published, local, built],
            )
            .expect("project");
        let published = if server.is_empty() {
            candidate
        } else {
            self.mem.edit(Some(candidate), server)
        };
        let installed =
            rebase(self.mem, &mut Sink(self.mem), [candidate, published, built]).expect("rebase");
        self.state.base = (installed != published).then_some(LocalBase {
            local: installed.0,
            published: published.0,
        });
        self.published = published;
        published
    }
}

fn has(files: &BTreeMap<String, String>, path: &str, text: &str) -> bool {
    files.get(path).map(String::as_str) == Some(text)
}

#[test]
fn ignored_changes_stay_local() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    let published = workspace.commit(
        &[
            Write("src/A.java", b"v2"),
            Write("notes.txt", b"untracked, not ignored"),
            Write("target/new.class", b"new"),
            Write("target/old.class", b"rebuilt"),
            Write("app.log", b"log"),
            Write("node_modules/y/index.js", b"y"),
        ],
        &[],
    );
    let out = mem.files(published);
    assert!(has(&out, "src/A.java", "v2"));
    assert!(has(&out, "notes.txt", "untracked, not ignored"));
    assert!(
        has(&out, "target/old.class", "old"),
        "warm-base output kept as published"
    );
    assert!(!out.contains_key("target/new.class"));
    assert!(!out.contains_key("app.log"));
    assert!(!out.contains_key("node_modules/y/"));
    let local = mem.files(workspace.local());
    assert!(has(&local, "target/new.class", "new"));
    assert!(has(&local, "target/old.class", "rebuilt"));
    assert!(has(&local, "app.log", "log"));
    assert!(has(&local, "node_modules/y/index.js", "y"));
    let last = workspace.state.last.expect("projection");
    assert!(last.ignored >= 4, "{last:?}");
    assert_eq!(last.unplaced, 0, "{last:?}");
}

#[test]
fn cleans_stay_local() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    workspace.commit(&[Write("target/new.class", b"new")], &[]);
    // `mvn clean`, `rm -rf node_modules`, `git clean -fdX`.
    let published = workspace.commit(
        &[
            Remove("target"),
            Remove("node_modules"),
            Write("src/A.java", b"v2"),
        ],
        &[],
    );
    let out = mem.files(published);
    assert!(has(&out, "target/old.class", "old"));
    assert!(has(&out, "node_modules/x/index.js", "x"));
    assert!(has(&out, "src/A.java", "v2"));
    let local = mem.files(workspace.local());
    assert!(!local.contains_key("target/"));
    assert!(!local.contains_key("node_modules/"));
    // The next build writes the outputs again, still locally only.
    let published = workspace.commit(&[Write("target/old.class", b"rebuilt")], &[]);
    assert!(has(&mem.files(published), "target/old.class", "old"));
    assert!(has(
        &mem.files(workspace.local()),
        "target/old.class",
        "rebuilt"
    ));
}

#[test]
fn tracked_files_in_ignored_directories() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    let published = workspace.commit(
        &[
            Write("build/keep.txt", b"keep v2"),
            Write("build/tmp.o", b"obj"),
        ],
        &[],
    );
    let out = mem.files(published);
    assert!(has(&out, "build/keep.txt", "keep v2"));
    assert!(!out.contains_key("build/tmp.o"));
}

#[test]
fn moves_out_of_ignored_directories_carry_local_content() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    // Changed while ignored, then moved where it is kept: the published
    // root must get the local bytes, not the warm base's.
    workspace.commit(&[Write("node_modules/x/index.js", b"x patched")], &[]);
    let published = workspace.commit(&[Move("node_modules/x", "vendor/x")], &[]);
    let out = mem.files(published);
    assert!(has(&out, "vendor/x/index.js", "x patched"));
    assert!(
        !out.contains_key("node_modules/x/"),
        "a directory has one name"
    );
    let published = workspace.commit(&[Move("target/old.class", "src/Old.class")], &[]);
    let out = mem.files(published);
    assert!(has(&out, "src/Old.class", "old"));
    assert!(
        !out.contains_key("target/old.class"),
        "a move is no hard link"
    );
    workspace.commit(&[Write("out/gen/a.txt", b"generated")], &[]);
    let published = workspace.commit(&[Move("out/gen", "src/gen")], &[]);
    assert!(has(&mem.files(published), "src/gen/a.txt", "generated"));
}

#[test]
fn newly_tracked_paths_are_published() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    let published = workspace.commit(
        &[
            Write("out/gen.txt", b"gen"),
            Write("out/other.txt", b"other"),
        ],
        &[],
    );
    assert!(!mem.files(published).contains_key("out/"));
    // `git add -f out/gen.txt`: only the index changes.
    let mut paths = TRACKED.to_vec();
    paths.push("out/gen.txt");
    let index = index(&paths);
    let published = workspace.commit(&[Write(".git/index", &index)], &[]);
    let out = mem.files(published);
    assert!(has(&out, "out/gen.txt", "gen"));
    assert!(!out.contains_key("out/other.txt"));
    // A warm-base file changed while ignored, then force-added.
    workspace.commit(&[Write("target/old.class", b"rebuilt")], &[]);
    paths.push("target/old.class");
    let index = self::index(&paths);
    let published = workspace.commit(&[Write(".git/index", &index)], &[]);
    assert!(has(&mem.files(published), "target/old.class", "rebuilt"));
}

#[test]
fn rule_changes_publish_what_they_unignore() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    workspace.commit(
        &[
            Write("target/new.class", b"new"),
            Write("target/old.class", b"rebuilt"),
            Write("app.log", b"log"),
        ],
        &[],
    );
    let published = workspace.commit(
        &[Write(".gitignore", b"node_modules/\nbuild/\nout/\n*.log\n")],
        &[],
    );
    let out = mem.files(published);
    assert!(has(&out, "target/new.class", "new"));
    assert!(has(&out, "target/old.class", "rebuilt"));
    assert!(!out.contains_key("app.log"));
    // A nested rule file un-ignoring one name.
    workspace.commit(
        &[
            Write("logs/keep.log", b"kept"),
            Write("logs/drop.log", b"dropped"),
        ],
        &[],
    );
    let published = workspace.commit(&[Write("logs/.gitignore", b"!keep.log\n")], &[]);
    let out = mem.files(published);
    assert!(has(&out, "logs/keep.log", "kept"));
    assert!(!out.contains_key("logs/drop.log"));
}

#[test]
fn moved_heads_rebase_the_local_base() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    let published = workspace.commit(
        &[
            Write("target/new.class", b"new"),
            Write("src/A.java", b"v2"),
        ],
        &[
            Write("docs/README.md", b"server"),
            Write("target/old.class", b"server build"),
        ],
    );
    let out = mem.files(published);
    assert!(has(&out, "docs/README.md", "server"));
    assert!(!out.contains_key("target/new.class"));
    let local = mem.files(workspace.local());
    assert!(
        has(&local, "docs/README.md", "server"),
        "the head's change reaches the local base"
    );
    assert!(has(&local, "src/A.java", "v2"));
    assert!(
        has(&local, "target/new.class", "new"),
        "local outputs survive the rebase"
    );
    assert!(has(&local, "target/old.class", "server build"));
    // The next Commit projects onto the moved head.
    let published = workspace.commit(&[Write("docs/README.md", b"local")], &[]);
    let out = mem.files(published);
    assert!(has(&out, "docs/README.md", "local"));
    assert!(has(&out, "src/A.java", "v2"));
}

#[test]
fn trees_without_ignored_changes_publish_as_built() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    let local = workspace.local();
    let published = workspace.commit(&[Write("src/A.java", b"v2")], &[]);
    assert_ne!(published, local);
    assert_eq!(workspace.state.base, None, "no local base forms");
    assert!(has(&mem.files(published), "src/A.java", "v2"));
}

#[test]
fn directories_moved_while_ignored_leave_their_old_name_when_kept() {
    let mem = Mem::default();
    let mut workspace = Workspace::new(&mem);
    // Both names ignored: the published root keeps the old one.
    let published = workspace.commit(&[Move("node_modules/x", "out/x")], &[]);
    assert!(mem.files(published).contains_key("node_modules/x/"));
    let mut paths = TRACKED.to_vec();
    paths.push("out/x/index.js");
    let index = index(&paths);
    let published = workspace.commit(&[Write(".git/index", &index)], &[]);
    let out = mem.files(published);
    assert!(has(&out, "out/x/index.js", "x"));
    assert!(!out.contains_key("node_modules/x/"));
}

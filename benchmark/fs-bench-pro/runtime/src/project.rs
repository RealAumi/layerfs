//! Current public SDK Init and an independent, separate-process read proof.
use crate::{args::Args, events::Events, Result};
use layerfs_api::{InitRequest, ProjectApi};
use layerfs_bridge::{duplex, provision::StoreManifest};
use layerfs_content::{
    file::FileView,
    filesystem::{
        attributes::read::{read_portable, AttributeReadWork},
        FilesystemRead, FilesystemRootId, LogicalPath,
    },
    inode_leaf::InodeKind,
};
use layerfs_history::{BranchId, HistoryCatalog, HistoryCatalogConfig, HistoryName, LayerStackId};
use layerfs_persistence::{Handles, PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::{Storage, StoragePolicy};
use layerfs_telemetry::timer::Timing;
use std::{
    fs,
    io::Write,
    os::unix::{
        fs::{MetadataExt, OpenOptionsExt},
        io::AsRawFd,
    },
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

#[allow(dead_code)]
#[path = "../../engine/recipes/namespace.rs"]
pub(crate) mod namespace;

/// Only the frozen native-import registries admit this complete count plan.
/// Namespace Init retains its existing independent sampled plan below.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ImportCounts {
    pub family: &'static str,
    pub entries: u64,
    pub files: u64,
    pub directories: u64,
    pub logical_bytes: u64,
}

pub fn import_counts(case: &str) -> Result<Option<ImportCounts>> {
    use namespace::reference::{store_footprint as footprint, workspace_common::EntryKind};
    if let Ok(control) = footprint::control(case) {
        let (files, directories, logical_bytes) = if control.kind == footprint::Kind::LargeObject {
            let files = if control.infra_tier == 100_000 {
                100
            } else {
                control.infra_tier.min(100)
            };
            let size = if control.infra_tier == 100_000 {
                5_000_000
            } else {
                1_000_000
            };
            (files, 2, files * size)
        } else {
            // These are the actual source generator's namespace geometries,
            // never invented labels attached to a large-object fixture.
            let id = match control.infra_tier {
                100 => "namespace-100-compact-v3",
                10_000 => "namespace-10000",
                100_000 => "namespace-100000",
                _ => return Err("original Store footprint geometry absent".into()),
            };
            let plan = namespace::reference::namespace_plan(id)?;
            (
                plan.scenario.regular_files,
                plan.scenario.data_directories + 1,
                plan.scenario.logical_bytes,
            )
        };
        if files != control.regular_files || logical_bytes != control.logical_bytes {
            return Err("original Store footprint control differs from native geometry".into());
        }
        return Ok(Some(ImportCounts {
            family: footprint::FAMILY_ID,
            entries: files + directories,
            files,
            directories,
            logical_bytes,
        }));
    }
    let Ok(selected) = namespace::reference::workspace_registry::resolve(case) else {
        return Ok(None);
    };
    if !matches!(selected.family, "dedup_cross_file" | "dedup_cdc_locality") {
        return Ok(None);
    }
    let entries = crate::edit_model::entries(case, 0)?;
    let logical_bytes = namespace::reference::workspace_common::validate_entries(&entries)?;
    let files = entries
        .iter()
        .filter(|entry| matches!(entry.kind, EntryKind::File(_)))
        .count() as u64;
    let directories = entries
        .iter()
        .filter(|entry| matches!(entry.kind, EntryKind::Directory))
        .count() as u64;
    if files + directories != entries.len() as u64
        || entries
            .iter()
            .filter(|entry| entry.path == "." && matches!(entry.kind, EntryKind::Directory))
            .count()
            != 1
    {
        return Err("original dedup import requires exact regular/directory/root entries".into());
    }
    Ok(Some(ImportCounts {
        family: selected.family,
        entries: entries.len() as u64,
        files,
        directories,
        logical_bytes,
    }))
}

/// Validate the actual Init acknowledgement; it is not inferred from native
/// fixture counts or a guessed successful close.
pub fn validate_import_ack(plan: ImportCounts, project: &layerfs_api::SealedProject) -> Result<()> {
    use layerfs_bridge::provision::{ProviderKind, StoreProfile};
    let initialized = &project.initialized;
    let branch = &project.branch;
    if plan.files.checked_add(plan.directories) != Some(plan.entries)
        || initialized.entries != plan.entries
        || initialized.namespace_work.entries as u64 != plan.entries
        || initialized.namespace_work.jobs as u64 != plan.files
        || initialized.namespace_work.unique_files as u64 != plan.files
        || initialized.namespace_work.regular_aliases != 0
        || branch.effective_root != initialized.root
        || branch.base_root != initialized.root
        || branch.head_root.is_some()
        || branch.branch.head_commit.is_some()
        || branch.branch.stack != initialized.stack.id
        || branch.branch.base_layer != initialized.stack.head_layer
        || branch.scope != initialized.stack.scope
        || branch.profile != layerfs_content::filesystem::profile_id()
        || initialized.stack.profile != branch.profile
        || project.manifest.root != initialized.root.to_bytes()
        || project.manifest.branch != branch.branch.id.to_bytes()
        || project.manifest.stack != initialized.stack.id.to_bytes()
        || project.manifest.provider != ProviderKind::Sqlite
        || project.manifest.profile != StoreProfile::Disposable
        || project.store.profile != SqlitePersistenceProfile::Disposable
        || project.manifest.bytes != project.store.bytes
    {
        return Err(
            "original import Init counts/typed Branch/root/head/profile acknowledgement differs"
                .into(),
        );
    }
    Ok(())
}

pub fn initialize(args: &Args, events: &mut Events) -> Result<()> {
    initialize_sealed(args, events).map(|_| ())
}

/// The exact public closed result stays alive across the host-controlled hold.
pub fn initialize_sealed(args: &Args, events: &mut Events) -> Result<layerfs_api::SealedProject> {
    let source = args
        .source
        .as_ref()
        .ok_or("--source-copy required")?
        .canonicalize()?;
    let sealed = args.sealed.as_ref().ok_or("--sealed required")?;
    let case = args.case.as_deref().ok_or("--case required")?;
    let generic = import_counts(case)?;
    let (entries, files) = if let Some(plan) = generic {
        (plan.entries, plan.files)
    } else {
        let plan = namespace::reference::namespace_plan(case)?;
        (
            plan.scenario.regular_files + plan.scenario.data_directories + 1,
            plan.scenario.regular_files,
        )
    };
    let stack_key = duplex::generate_keypair()?.public;
    let branch_key = duplex::generate_keypair()?.public;
    let mut stack = [0; 16];
    let mut branch = [0; 16];
    stack.copy_from_slice(&stack_key[..16]);
    branch.copy_from_slice(&branch_key[..16]);
    let request = InitRequest {
        source,
        store: PersistenceConfig::sqlite(sealed)
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        locator: "/layerfs-store/global/store.sqlite".into(),
        policy: StoragePolicy::frozen_default(),
        catalog: HistoryCatalogConfig {
            binding_key: b"fs-bench-pro-init".to_vec(),
            cursor_key: duplex::generate_keypair()?.private,
            incarnation: 1,
        },
        stack: LayerStackId::from_authority(stack),
        stack_name: HistoryName::new("project")?,
        branch: BranchId::from_authority(branch),
        branch_name: HistoryName::new("main")?,
        scope_seed: duplex::generate_keypair()?.public,
        deadline: Instant::now() + Duration::from_secs(args.init_seconds),
    };
    let begun = Instant::now();
    let project = Timing::disabled("fs-bench-pro.init", |timer| {
        ProjectApi::new().init(request, timer)
    })
    .0?;
    let elapsed = events.span(begun);
    if project.initialized.entries != entries
        || project.initialized.namespace_work.unique_files as u64 != files
        || project.branch.effective_root != project.initialized.root
    {
        return Err("original acknowledged Init counts/Branch root differ from frozen plan".into());
    }
    if let Some(plan) = generic {
        validate_import_ack(plan, &project)?;
    }
    let metadata = project.store.path.metadata()?;
    let mut manifest = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&args.manifest)?;
    let encoded_manifest = project.manifest.encode()?;
    manifest.write_all(&encoded_manifest)?;
    let mut fields = vec![
        ("case", case.into()),
        ("root", crate::hex(&project.manifest.root)),
        ("stack", crate::hex(&project.manifest.stack)),
        ("host_sqlite", project.manifest.host_sqlite.clone()),
    ];
    if args.mode == "init-install" {
        fields.extend([
            ("branch", crate::hex(&project.manifest.branch)),
            ("profile", "Disposable/WAL/OFF".into()),
            ("manifest_path", args.manifest.display().to_string()),
            (
                "manifest_sha256",
                namespace::reference::sdk_edit_common::sha256_hex(&encoded_manifest),
            ),
        ]);
    }
    events.numeric_fields(
        "project_init",
        Some(elapsed),
        "public Init acknowledged; sole Store consumed by seal; no daemon/mount",
        &fields,
        &[
            ("entries", project.initialized.entries),
            ("files", files),
            ("logical_bytes", metadata.len()),
            ("allocated_bytes", metadata.blocks() * 512),
        ],
    )?;
    Ok(project)
}

#[repr(C)]
struct PollFd {
    fd: std::os::raw::c_int,
    events: i16,
    revents: i16,
}
#[cfg(target_os = "macos")]
type PollCount = std::os::raw::c_uint;
#[cfg(not(target_os = "macos"))]
type PollCount = std::os::raw::c_ulong;
extern "C" {
    fn poll(
        fds: *mut PollFd,
        count: PollCount,
        timeout: std::os::raw::c_int,
    ) -> std::os::raw::c_int;
    fn read(fd: std::os::raw::c_int, buffer: *mut u8, count: usize) -> isize;
}

/// One bounded command frame. EOF, EINTR and invalid bytes are final refusals;
/// no reader thread, background wait, retry or second installation is created.
pub fn wait_install<R: AsRawFd>(input: &mut R, stop: Instant) -> Result<()> {
    let mut received = [0; 8];
    for byte in &mut received {
        let remaining = stop
            .checked_duration_since(Instant::now())
            .ok_or("install input deadline")?;
        let timeout = remaining.as_millis().min(120_000) as i32;
        if timeout == 0 {
            return Err("install input deadline".into());
        }
        let mut selected = PollFd {
            fd: input.as_raw_fd(),
            events: 1,
            revents: 0,
        };
        // Unix poll layout/constants are identical on the qualified macOS/Linux
        // targets. Only this owned input descriptor is observed, without mutation.
        let ready = unsafe { poll(&mut selected, 1, timeout) };
        if ready < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        if ready == 0 {
            return Err("install input deadline".into());
        }
        if selected.revents & (8 | 32) != 0 || selected.revents & (1 | 16) == 0 {
            return Err("install input descriptor unavailable".into());
        }
        // Unbuffered descriptor read avoids Stdin's internal BufReader retaining
        // bytes invisibly from the next poll. Readiness precedes every one-byte read.
        let received = unsafe { read(input.as_raw_fd(), byte, 1) };
        if received < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        if received != 1 {
            return Err("install input EOF".into());
        }
    }
    if &received != b"install\n" {
        return Err("exact install command required".into());
    }
    Ok(())
}

fn output_identity(path: &Path) -> Result<PathBuf> {
    if path.exists() || fs::symlink_metadata(path).is_ok() {
        return Err("fresh installed manifest output required".into());
    }
    Ok(path
        .parent()
        .ok_or("installed manifest parent")?
        .canonicalize()?
        .join(path.file_name().ok_or("installed manifest name")?))
}

pub fn install_output(args: &Args) -> Result<PathBuf> {
    let path = args
        .installed_manifest
        .as_ref()
        .ok_or("--installed-manifest required")?;
    let output = output_identity(path)?;
    let host = args
        .manifest
        .parent()
        .ok_or("host manifest parent")?
        .canonicalize()?
        .join(args.manifest.file_name().ok_or("host manifest name")?);
    let sealed = args.sealed.as_ref().ok_or("--sealed required")?;
    let sealed = sealed
        .parent()
        .ok_or("sealed Store parent")?
        .canonicalize()?
        .join(sealed.file_name().ok_or("sealed Store name")?);
    if output == host || output == sealed {
        return Err("installed manifest must be distinct from host manifest and Store".into());
    }
    Ok(output)
}

pub fn install_ready(project: &layerfs_api::SealedProject) -> Result<()> {
    use layerfs_bridge::provision::StoreProfile;
    if project.manifest.profile != StoreProfile::Disposable
        || project.store.profile != SqlitePersistenceProfile::Disposable
    {
        return Err("installation requires explicit Disposable actual project".into());
    }
    if project.manifest.daemon_sqlite.is_some() {
        return Err("already installed project refused".into());
    }
    project.manifest.check()?;
    Ok(())
}

pub fn initialize_install_with<R: AsRawFd>(
    args: &Args,
    events: &mut Events,
    input: &mut R,
    installer: impl FnOnce(&Args, &layerfs_api::SealedProject, &Path, &mut Events) -> Result<()>,
) -> Result<()> {
    let output = install_output(args)?;
    let project = initialize_sealed(args, events)?;
    install_ready(&project)?;
    events.value("project_install_waiting", "actual public SealedProject retained; host sends one install command; no open Store or installation yet")?;
    wait_install(
        input,
        Instant::now() + Duration::from_secs(args.init_seconds.min(120)),
    )?;
    installer(args, &project, &output, events)
}

pub fn initialize_install(args: &Args, events: &mut Events) -> Result<()> {
    initialize_install_with(
        args,
        events,
        &mut std::io::stdin(),
        crate::fixture::install_sealed,
    )
}

pub fn verify(args: &Args, events: &mut Events) -> Result<()> {
    let case = args.case.as_deref().ok_or("--case required")?;
    if let Some(plan) = import_counts(case)? {
        if matches!(plan.family, "dedup_cross_file" | "dedup_cdc_locality") {
            // This offline full typed proof complements the original fresh FUSE
            // native verifier owned by the controller; it never substitutes for it.
            return crate::workspace_oracle::verify_import(args, events).map_err(Into::into);
        }
        return Err(
            "Store-footprint initial/final proof requires its separately scoped runtime route"
                .into(),
        );
    }
    let manifest = StoreManifest::decode(&fs::read(&args.manifest)?)?;
    let plan =
        namespace::reference::namespace_plan(args.case.as_deref().ok_or("--case required")?)?;
    let config = PersistenceConfig::sqlite(args.sealed.as_ref().ok_or("--sealed required")?)
        .with_sqlite_profile(SqlitePersistenceProfile::Disposable);
    let begun = Instant::now();
    let handles = Handles::open_writable(config, &manifest.binding, manifest.cursor_key)?;
    let branch = handles
        .history
        .branch_snapshot(BranchId::from_bytes(manifest.branch)?)?
        .ok_or("missing first Branch")?;
    if branch.effective_root.to_bytes() != manifest.root || branch.branch.head_commit.is_some() {
        return Err("persisted first Branch root/head differs".into());
    }
    let storage = Storage::new(handles.storage.clone())?;
    let reader = storage.reader()?;
    let mut tree = FilesystemRead::new(&reader, FilesystemRootId(branch.effective_root))?;
    let mut work = AttributeReadWork::default();
    let check = |path: &str,
                 kind,
                 mode,
                 tree: &mut FilesystemRead<'_>,
                 work: &mut AttributeReadWork|
     -> Result<_> {
        let inode = tree.resolve(&LogicalPath::new(path)?)?.value;
        let attributes = read_portable(&reader, inode.metadata_root, inode.kind, work)?;
        if inode.kind != kind
            || attributes.mode != mode
            || attributes.mtime_seconds != namespace::reference::NAMESPACE_MTIME_SECONDS
            || attributes.mtime_nanoseconds != namespace::reference::NAMESPACE_MTIME_NANOSECONDS
        {
            return Err(format!("independent metadata mismatch at {path}").into());
        }
        Ok(inode)
    };
    check("", InodeKind::Directory, 0o750, &mut tree, &mut work)?;
    let indices = namespace::samples(&plan);
    let mut verified_bytes = 0;
    for index in &indices {
        let planned = &plan.files[*index];
        let parent = planned
            .relative_path
            .rsplit_once('/')
            .ok_or("frozen parent")?
            .0;
        check(parent, InodeKind::Directory, 0o750, &mut tree, &mut work)?;
        let inode = check(
            &planned.relative_path,
            InodeKind::RegularFile,
            0o640,
            &mut tree,
            &mut work,
        )?;
        let mut expected = vec![0; planned.size.min(65536) as usize];
        namespace::reference::NamespaceContentStream::new(plan.scenario, planned)
            .fill(&mut expected);
        let observed = Timing::disabled("independent.init.bytes", |timer| -> Result<_> {
            let view = FileView::open(&reader, inode.content_root, timer.child("open"))?;
            if view.logical_len() != planned.size {
                return Err("independent file length mismatch".into());
            }
            let mut actual = Vec::with_capacity(expected.len());
            view.read_range(&reader, 0..expected.len() as u64, &mut actual, timer)?;
            Ok(actual)
        })
        .0?;
        if observed != expected {
            return Err(format!("independent bytes mismatch at {}", planned.relative_path).into());
        }
        verified_bytes += observed.len() as u64;
    }
    drop(tree);
    drop(reader);
    drop(storage);
    handles.seal()?;
    events.numeric_fields("project_verified", Some(events.span(begun)), "original import counts plus reopen root/first Branch and exact original sampled modes/mtime/size/prefix bytes; unselected paths/payload bytes omitted", &[("status", "PASS".into())], &[("sampled_files", indices.len() as u64), ("verified_bytes", verified_bytes)])?;
    Ok(())
}

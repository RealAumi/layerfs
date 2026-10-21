use crate::{args::Args, events::Events, runtime, Result};
use layerfs_api::{InitRequest, ProjectApi};
use layerfs_bridge::{
    control::{Reply, Request},
    duplex,
};
use layerfs_history::{BranchId, HistoryCatalogConfig, HistoryName, LayerStackId};
use layerfs_persistence::{PersistenceConfig, SqlitePersistenceProfile};
use layerfs_storage::StoragePolicy;
use layerfs_telemetry::timer::Timing;
use std::{
    fs::OpenOptions,
    io::Write,
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::Path,
    time::{Duration, Instant},
};

/// Host Init from an independently prepared copy, once; SDK installation once.
pub fn provision(args: &Args, events: &mut Events) -> Result<()> {
    let source = args
        .source
        .as_ref()
        .ok_or("--source-copy required")?
        .canonicalize()?;
    if source.starts_with("/Users/yifanxu/Ephemeral-AI-Lab/deepseek-harness") {
        return Err(
            "protected fixture checkout cannot be used: prepare an independent copy".into(),
        );
    }
    let sealed = args.sealed.as_ref().ok_or("--sealed required")?;
    let metadata = source.metadata()?;
    if (metadata.uid(), metadata.gid()) != (args.uid, args.gid) {
        return Err("command identity must equal preserved source-copy owner".into());
    }
    let stack_key = duplex::generate_keypair()?.public;
    let branch_key = duplex::generate_keypair()?.public;
    let cursor_key = duplex::generate_keypair()?.private;
    let scope_seed = duplex::generate_keypair()?.public;
    let mut stack = [0; 16];
    stack.copy_from_slice(&stack_key[..16]);
    let mut branch = [0; 16];
    branch.copy_from_slice(&branch_key[..16]);
    let request = InitRequest {
        source,
        store: PersistenceConfig::sqlite(sealed)
            .with_sqlite_profile(SqlitePersistenceProfile::Disposable),
        locator: "/layerfs-store/global/store.sqlite".into(),
        policy: StoragePolicy::frozen_default(),
        catalog: HistoryCatalogConfig {
            binding_key: b"r7-exploratory-runtime".to_vec(),
            cursor_key,
            incarnation: 1,
        },
        stack: LayerStackId::from_authority(stack),
        stack_name: HistoryName::new("project")?,
        branch: BranchId::from_authority(branch),
        branch_name: HistoryName::new("main")?,
        scope_seed,
        deadline: Instant::now() + Duration::from_secs(args.init_seconds),
    };
    let begun = Instant::now();
    let project = Timing::disabled("r7.setup.init", |timer| {
        ProjectApi::new().init(request, timer)
    })
    .0?;
    let elapsed = events.span(begun);
    let sealed_stat = project.store.path.metadata()?;
    events.phase("host_init_setup", Some(elapsed), &format!("sealed={} logical_bytes={} allocated_bytes={} entries={} sqlite={} root={:?} diagnostics={:?} namespace_work={:?}", project.store.path.display(), sealed_stat.len(), sealed_stat.blocks()*512, project.initialized.entries, project.store.sqlite_version, project.initialized.root, project.initialized.diagnostics, project.initialized.namespace_work))?;
    install_sealed(args, &project, &args.manifest, events)
}

/// One public installation of the actual closed Init result, followed by the
/// original setup snapshot, EndSession and known container Stop.
pub fn install_sealed(
    args: &Args,
    project: &layerfs_api::SealedProject,
    manifest_path: &Path,
    events: &mut Events,
) -> Result<()> {
    crate::project::install_ready(project)?;
    let begun = Instant::now();
    let mut owner = runtime::start(args, project, events)?;
    let installed = owner
        .installed
        .take()
        .ok_or("original create installation acknowledgement missing")?;
    let elapsed = events.span(begun);
    events.phase(
        "install_setup",
        Some(elapsed),
        &format!(
            "work={:?} host_sqlite={} daemon_sqlite={:?}",
            installed.work, installed.manifest.host_sqlite, installed.manifest.daemon_sqlite
        ),
    )?;
    let mut manifest = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(manifest_path)?;
    let encoded_manifest = installed.manifest.encode()?;
    manifest.write_all(&encoded_manifest)?;
    events.value("installed_manifest", &manifest_path.display().to_string())?;
    if args.mode == "init-install" {
        let source_metadata = project.store.path.metadata()?;
        events.numeric_fields(
            "project_install", Some(elapsed),
            "actual public SealedProject installed once; manifest now carries acknowledged daemon SQLite",
            &[
                ("installed_manifest", manifest_path.display().to_string()),
                ("daemon_sqlite", installed.manifest.daemon_sqlite.clone().ok_or("actual installed daemon SQLite missing")?),
                ("host_sqlite", installed.manifest.host_sqlite.clone()),
                ("container", owner.runtime.identity().to_string()),
                ("root", crate::hex(&installed.manifest.root)),
                ("stack", crate::hex(&installed.manifest.stack)),
                ("branch", crate::hex(&installed.manifest.branch)),
                ("profile", "Disposable/WAL/OFF".into()),
                ("installed_manifest_sha256", crate::reference::sdk_edit_common::sha256_hex(&encoded_manifest)),
                ("host_manifest_sha256", crate::reference::sdk_edit_common::sha256_hex(&project.manifest.encode()?)),
                ("allocated_bytes_scope", "actual host sealed main file; installed destination allocation not returned by public SDK".into()),
            ],
            &[("logical_bytes", installed.manifest.bytes), ("allocated_bytes", source_metadata.blocks()*512)],
        )?;
    }
    runtime::snapshot(&owner, &args.socket, events)?;
    if layerfs_api::internal::control(&mut owner).call(Request::EndSession)? != Reply::SessionEnded
    {
        return Err("unexpected original EndSession acknowledgement".into());
    }
    let container = owner.runtime.identity().to_string();
    runtime::close(owner, &args.socket)?;
    events.value("setup_container_stopped", &container)?;
    // The acknowledged close deletes this setup container. Shared volume,
    // source copy and sealed master remain retained as the prepared input.
    Ok(())
}

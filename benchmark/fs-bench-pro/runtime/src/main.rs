//! SDK-driven host provisioning and persistent real-daemon benchmark control.
mod args;
#[allow(dead_code)]
#[path = "../../engine/recipes/dedup_input.rs"]
mod dedup_input;
#[path = "../../engine/recipes/edit_model.rs"]
mod edit_model;
mod edit_oracle;
mod events;
mod fixture;
mod project;
mod repository_history;
mod runtime;
mod session;
mod store_footprint;
mod workspace_oracle;

use args::Args;
use events::Events;
use project::namespace::reference;
use std::error::Error;

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut text = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        text.push(DIGITS[usize::from(byte >> 4)] as char);
        text.push(DIGITS[usize::from(byte & 15)] as char);
    }
    text
}

fn main() -> Result<()> {
    let args = Args::parse()?;
    let mut events = Events::new(&args.receipt)?;
    let scope = hex(&args.observation_scope);
    events.fields(
        "observation_scope",
        None,
        "fresh public per-channel scope; no daemon retained preference",
        &[("scope", scope)],
    )?;
    events.value("selection", &format!("mode={} image={} uid={} gid={} construction_workers=1 admission_eligible=false exploratory=true", args.mode, args.image, args.uid, args.gid))?;
    let result = match args.mode.as_str() {
        "provision" => fixture::provision(&args, &mut events),
        "serve" => session::serve(&args, &mut events),
        "init" => project::initialize(&args, &mut events),
        "init-install" => project::initialize_install(&args, &mut events),
        "verify-init" => project::verify(&args, &mut events),
        "verify-footprint" => store_footprint::verify(&args, &mut events),
        "verify-repository" => repository_history::verify(&args, &mut events),
        "verify-reuse-initial" => {
            workspace_oracle::verify_reuse_initial(&args, &mut events).map_err(Into::into)
        }
        "verify-workspace" | "verify-membership" => workspace_oracle::verify(&args, &mut events),
        "verify-history" => workspace_oracle::verify_history(&args, &mut events),
        "verify-topology" => workspace_oracle::verify_topology(&args, &mut events),
        "verify-access" => workspace_oracle::verify_access(&args, &mut events),
        _ => Err("mode must be provision or serve".into()),
    };
    match result {
        Ok(()) => events.value("finished", "known successful harness completion"),
        Err(error) => {
            events.value(
                "failed",
                &format!("original_failure={error}; no replay or automatic teardown"),
            )?;
            Err(error)
        }
    }
}

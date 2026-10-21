//! Export one genuine public Store for the independent canonical census regression.
#[allow(dead_code)]
#[path = "../../engine/recipes/dedup_input.rs"]
mod dedup_input;
#[path = "batch4_oracle.rs"]
mod support;
pub(crate) use support::{
    args, edit_model, edit_oracle, events, hex, namespace, project, reference, workspace_oracle,
    Result,
};

#[test]
fn batch4_census_canonical_fixture() {
    let output = std::env::var_os("LAYERFS_BATCH4_CENSUS_FIXTURE")
        .expect("explicit fresh native fixture output required");
    support::export_census_fixture(std::path::Path::new(&output));
}

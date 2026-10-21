//! Original historical fork inheritance, role-bound modes and compact edits.
#[allow(dead_code)]
#[path = "../../engine/recipes/edit_model.rs"]
mod edit_model;
#[allow(dead_code)]
#[path = "../../workload/main.rs"]
mod reference;
#[path = "../../engine/recipes/sdk_edit_model.rs"]
mod sdk_edit_model;

use edit_model::{context_entries, context_m1_state, ContextCreatedModes};
use reference::workspace_common::{Content, Entry, EntryKind};
use sdk_edit_model::context_sdk_step;
use std::{fs, path::Path, process::Command};

const BRANCH: &str = "v016-branch-mixed-100mb-5000-k10-v1";
const MULTI: &str = "v016-workspace-mixed-100mb-5000-k10-v1";
const SEQUENTIAL: &str = "v016-mixed-development-100mb-5000-k10-v1";
const CONVERGENT: &str = "v016-branch-convergent-content-v1";
const DESCENDANT: &str = "v016-branch-fork-descendant-v1";

fn content<'a>(entries: &'a [Entry], path: &str) -> &'a Content {
    let entry = entries.iter().find(|entry| entry.path == path).unwrap();
    match &entry.kind {
        EntryKind::File(content) => content,
        _ => panic!("regular file required"),
    }
}

fn fixture() -> reference::v016_common::LoadFixture {
    reference::v016_common::load_fixture(&reference::v016_common::L100, 1).unwrap()
}

#[test]
fn context_child_zero_inherits_exact_trunk_five_not_genesis_or_trunk_ten() {
    let child = context_m1_state(BRANCH, "a", 0, None).unwrap();
    let inherited = context_m1_state(BRANCH, "trunk", 5, None).unwrap();
    assert_eq!(
        edit_model::m1_scope_tsv(&child).unwrap(),
        edit_model::m1_scope_tsv(&inherited).unwrap()
    );
    assert_ne!(
        edit_model::m1_scope_tsv(&child).unwrap(),
        edit_model::m1_scope_tsv(&context_m1_state(BRANCH, "trunk", 10, None).unwrap()).unwrap()
    );
    let fixture = fixture();
    assert_eq!(
        content(&child.entries, &fixture.roles.edit.sdk_insert).len(),
        1_048_832
    );
    assert_eq!(
        content(&child.entries, &fixture.roles.edit.sdk_delete).len(),
        1_048_320
    );
    let first = content(&child.entries, &fixture.roles.refresh_pool[3])
        .digest()
        .unwrap();
    assert_ne!(
        first,
        content(&fixture.entries, &fixture.roles.refresh_pool[3])
            .digest()
            .unwrap()
    );
    assert_eq!(
        child.file_mtimes[&fixture.roles.link_targets[4]],
        (1_700_000_010, 123_456_789)
    );
}

#[test]
fn context_role_cycles_tags_sdk_order_and_original_selective_ranges_are_exact() {
    let fixture = fixture();
    for (role, tag) in [("a", 1), ("b", 2)] {
        let state = context_m1_state(BRANCH, role, 4, None).unwrap();
        assert_eq!(
            state.file_mtimes[&fixture.roles.link_targets[0]],
            (1_700_000_020 + tag, 123_456_789)
        );
        let members = context_sdk_step(BRANCH, role, 2).unwrap();
        assert_eq!(members[0].edit.path, fixture.roles.edit.sdk_insert);
        assert_eq!(members[1].edit.path, fixture.roles.edit.sdk_delete);
        assert_eq!(
            (
                members[0].before_len,
                members[0].after_len,
                members[0].edit.delete_len
            ),
            (1_048_832, 1_048_576, 256)
        );
        assert_eq!(
            (
                members[1].before_len,
                members[1].after_len,
                members[1].edit.replacement.len()
            ),
            (1_048_320, 1_048_576, 256)
        );
        let old = sdk_edit_model::sdk_step(SEQUENTIAL, 7).unwrap();
        assert_eq!(members[1].edit.replacement, old[1].edit.replacement);
        let second = context_m1_state(BRANCH, role, 2, None).unwrap();
        assert_eq!(
            second.ranges[&fixture.roles.witnesses.boundary_exact],
            Vec::<(u64, u64)>::new()
        );
        assert_eq!(
            second.ranges[&fixture.roles.edit.anchor_overwrite],
            vec![(4_194_304, 4096), (0, 4096)]
        );
    }
    let main = context_m1_state(MULTI, "0", 4, None).unwrap();
    assert_eq!(
        edit_model::m1_scope_tsv(&main).unwrap(),
        edit_model::m1_scope_tsv(&edit_model::m1_state(SEQUENTIAL, 4, None).unwrap()).unwrap()
    );
    let peer = context_m1_state(MULTI, "1", 4, None).unwrap();
    assert_eq!(
        peer.file_mtimes[&fixture.roles.link_targets[0]],
        (1_700_000_011, 123_456_789)
    );
    assert_ne!(
        content(&main.entries, &fixture.roles.refresh_pool[3])
            .digest()
            .unwrap(),
        content(&peer.entries, &fixture.roles.refresh_pool[3])
            .digest()
            .unwrap()
    );
    assert_eq!(
        content(&main.entries, &fixture.roles.refresh_pool[0])
            .digest()
            .unwrap(),
        content(&peer.entries, &fixture.roles.refresh_pool[0])
            .digest()
            .unwrap()
    );
}

#[test]
fn context_created_modes_keep_inherited_trunk_and_own_child_custody_separate() {
    let fixture = fixture();
    let mut maps = ContextCreatedModes::new();
    for (role, mode) in [("trunk", 0o701), ("a", 0o753)] {
        let state = context_m1_state(
            BRANCH,
            role,
            edit_model::context_limit(BRANCH, role).unwrap(),
            None,
        )
        .unwrap();
        maps.insert(
            role.to_owned(),
            state
                .required_created_directory_modes
                .into_iter()
                .map(|path| (path, mode))
                .collect(),
        );
    }
    let initial = context_m1_state(BRANCH, "a", 0, Some(&maps)).unwrap();
    assert_eq!(initial.directory_modes[&fixture.roles.deletion_root], 0o701);
    let own = context_m1_state(BRANCH, "a", 5, Some(&maps)).unwrap();
    assert_eq!(own.directory_modes[&fixture.roles.deletion_root], 0o753);
    let removed = maps.remove("trunk").unwrap();
    assert!(context_m1_state(BRANCH, "a", 5, Some(&maps)).is_err());
    maps.insert("trunk".into(), removed);
    maps.get_mut("a")
        .unwrap()
        .remove(&fixture.roles.deletion_root);
    assert!(context_m1_state(BRANCH, "a", 5, Some(&maps)).is_err());
    let mut body = String::from("original-context-created-modes-v1\nrole\tpath\tmode\n");
    for (role, rows) in &maps {
        for (path, mode) in rows {
            body.push_str(&format!("{role}\t{path}\t{mode:o}\n"));
        }
    }
    assert_eq!(
        edit_model::parse_context_created_modes(BRANCH, &body).unwrap(),
        maps
    );
    for row in [
        "a\t../x\t750",
        "c\tscratch00\t750",
        "a\tundeclared\t750",
        "a\tscratch00\t4000",
    ] {
        assert!(
            edit_model::parse_context_created_modes(BRANCH, &format!("{body}{row}\n")).is_err()
        );
    }
    let row = body.lines().nth(2).unwrap();
    assert!(edit_model::parse_context_created_modes(BRANCH, &format!("{body}{row}\n")).is_err());
}

#[test]
fn context_compact_fork_content_equations_and_duplicate_identity_semantics() {
    let target = "medium/m0.dat";
    for id in [CONVERGENT, DESCENDANT] {
        let a0 = context_entries(id, "a", 0).unwrap();
        let t5 = context_entries(id, "trunk", 5).unwrap();
        assert_eq!(
            content(&a0, target).digest().unwrap(),
            content(&t5, target).digest().unwrap()
        );
        let a = context_entries(id, "a", 10).unwrap();
        let b = context_entries(id, "b", 10).unwrap();
        let a_digest = content(&a, target).digest().unwrap();
        let b_digest = content(&b, target).digest().unwrap();
        if id == CONVERGENT {
            assert_eq!(a_digest, b_digest);
        } else {
            assert_ne!(a_digest, b_digest);
            let c = context_entries(id, "c", 10).unwrap();
            let digest = content(&c, target).digest().unwrap();
            assert_ne!(digest, a_digest);
            assert_ne!(digest, b_digest);
            assert_eq!(
                content(&context_entries(id, "c", 0).unwrap(), target)
                    .digest()
                    .unwrap(),
                content(&context_entries(id, "a", 5).unwrap(), target)
                    .digest()
                    .unwrap()
            );
        }
        let member = context_sdk_step(id, "a", 1).unwrap().remove(0);
        assert_eq!(
            (
                member.edit.start,
                member.edit.delete_len,
                member.edit.replacement.len()
            ),
            (4096, 256, 256)
        );
        assert_eq!((member.before_len, member.after_len), (65536, 65536));
    }
    for (id, role, step) in [
        (CONVERGENT, "c", 1),
        (BRANCH, "trunk", 11),
        (MULTI, "2", 1),
        (MULTI, "00", 1),
        (BRANCH, "a", 11),
    ] {
        assert!(context_entries(id, role, step).is_err());
    }
    assert!(context_sdk_step(BRANCH, "a", 1).is_err());
    assert!(context_sdk_step(CONVERGENT, "a", 0).is_err());
    assert_eq!(
        edit_model::context_roles("v016-workspace-four-100mb-5000-k100-v1").unwrap(),
        ["0", "1", "2", "3"]
    );
    assert_eq!(
        edit_model::context_limit("v016-workspace-four-100mb-5000-k100-v1", "3").unwrap(),
        100
    );
}

fn invoke(binary: &str, root: &Path, args: &[&str]) -> std::process::Output {
    Command::new(binary)
        .args(args)
        .current_dir(root)
        .output()
        .unwrap()
}

#[test]
fn context_native_compact_writer_seal_role_payload_and_complete_oracle() {
    let writer = std::env::var("LAYERFS_CONTEXT_EDIT_WRITER").unwrap();
    let recipe = std::env::var("LAYERFS_CONTEXT_RECIPE").unwrap();
    let root = Path::new(&std::env::var("LAYERFS_CONTEXT_TEST_OUTPUT").unwrap()).to_path_buf();
    fs::create_dir(&root).unwrap();
    let native = root.join("native");
    let payloads = root.join("payloads");
    let generated = invoke(
        &recipe,
        &root,
        &[
            "materialize-context",
            DESCENDANT,
            "c",
            "0",
            native.to_str().unwrap(),
        ],
    );
    assert!(
        generated.status.success(),
        "{}",
        String::from_utf8_lossy(&generated.stderr)
    );
    let prepared = invoke(
        &writer,
        &root,
        &[
            "prepare-context-step",
            DESCENDANT,
            "c",
            "1",
            payloads.to_str().unwrap(),
        ],
    );
    assert!(
        prepared.status.success(),
        "{}",
        String::from_utf8_lossy(&prepared.stderr)
    );
    let descriptor = payloads.join("descriptor.tsv");
    let body = fs::read(&descriptor).unwrap();
    let sha = reference::sdk_edit_common::sha256_hex(&body);
    let target = native.join("medium/m0.dat");
    let before = fs::read(&target).unwrap();
    let wrong = invoke(
        &writer,
        &native,
        &[
            "apply-context-step-prepared",
            DESCENDANT,
            "b",
            "1",
            descriptor.to_str().unwrap(),
            &sha,
            "1",
        ],
    );
    assert!(!wrong.status.success());
    assert_eq!(fs::read(&target).unwrap(), before);
    let tampered = payloads.join("member-1.bin");
    let mut value = fs::read(&tampered).unwrap();
    value[0] ^= 1;
    fs::write(&tampered, &value).unwrap();
    let wrong = invoke(
        &writer,
        &native,
        &[
            "apply-context-step-prepared",
            DESCENDANT,
            "c",
            "1",
            descriptor.to_str().unwrap(),
            &sha,
            "1",
        ],
    );
    assert!(!wrong.status.success());
    assert_eq!(fs::read(&target).unwrap(), before);
    value[0] ^= 1;
    fs::write(&tampered, &value).unwrap();
    let applied = invoke(
        &writer,
        &native,
        &[
            "apply-context-step-prepared",
            DESCENDANT,
            "c",
            "1",
            descriptor.to_str().unwrap(),
            &sha,
            "1",
        ],
    );
    assert!(
        applied.status.success(),
        "{}",
        String::from_utf8_lossy(&applied.stderr)
    );
    let verified = invoke(
        &recipe,
        &root,
        &[
            "verify-context",
            DESCENDANT,
            "c",
            "1",
            native.to_str().unwrap(),
            "-",
        ],
    );
    assert!(
        verified.status.success(),
        "{}",
        String::from_utf8_lossy(&verified.stderr)
    );
    let duplicate = invoke(
        &recipe,
        &root,
        &[
            "materialize-context",
            DESCENDANT,
            "c",
            "0",
            native.to_str().unwrap(),
        ],
    );
    assert!(!duplicate.status.success());
    // Native controls and every refusal are retained even on assertion failure.
}

#[test]
fn context_native_m1_prepared_pair_preserves_inherited_lengths_and_exact_bytes() {
    use reference::workspace_common as common;
    let writer = std::env::var("LAYERFS_CONTEXT_EDIT_WRITER").unwrap();
    let folder = Path::new(&std::env::var("LAYERFS_CONTEXT_TEST_OUTPUT").unwrap())
        .with_extension("m1-members");
    fs::create_dir(&folder).unwrap();
    // External writer controls retain only the two declared target files.
    // This is not a resized benchmark fixture or a measured Workspace case.
    let members = context_sdk_step(BRANCH, "a", 2).unwrap();
    for selected in &members {
        let target = folder.join(&selected.edit.path);
        fs::create_dir_all(target.parent().unwrap()).unwrap();
        content(
            &context_entries(BRANCH, "a", 1).unwrap(),
            &selected.edit.path,
        )
        .write_to(&mut fs::File::create(&target).unwrap())
        .unwrap();
        common::set_metadata(&target, &selected.metadata).unwrap();
    }
    let payloads = folder.join("payloads");
    let prepared = invoke(
        &writer,
        &folder,
        &[
            "prepare-context-step",
            BRANCH,
            "a",
            "2",
            payloads.to_str().unwrap(),
        ],
    );
    assert!(
        prepared.status.success(),
        "{}",
        String::from_utf8_lossy(&prepared.stderr)
    );
    let descriptor = payloads.join("descriptor.tsv");
    let sha = reference::sdk_edit_common::sha256_hex(&fs::read(&descriptor).unwrap());
    for member in ["1", "2"] {
        let applied = invoke(
            &writer,
            &folder,
            &[
                "apply-context-step-prepared",
                BRANCH,
                "a",
                "2",
                descriptor.to_str().unwrap(),
                &sha,
                member,
            ],
        );
        assert!(
            applied.status.success(),
            "{}",
            String::from_utf8_lossy(&applied.stderr)
        );
    }
    let after = context_entries(BRANCH, "a", 2).unwrap();
    for selected in members {
        let target = folder.join(&selected.edit.path);
        let actual = fs::read(&target).unwrap();
        assert_eq!(actual.len() as u64, selected.after_len);
        assert_eq!(
            reference::sdk_edit_common::sha256_hex(&actual),
            content(&after, &selected.edit.path).digest().unwrap()
        );
    }
}

#[test]
fn context_legacy_prepared_header_and_two_ordered_members_remain_compatible() {
    use reference::workspace_common as common;
    let writer = std::env::var("LAYERFS_CONTEXT_EDIT_WRITER").unwrap();
    let folder = Path::new(&std::env::var("LAYERFS_CONTEXT_TEST_OUTPUT").unwrap())
        .with_extension("legacy-members");
    fs::create_dir(&folder).unwrap();
    let members = sdk_edit_model::sdk_step(SEQUENTIAL, 7).unwrap();
    let before = edit_model::entries(SEQUENTIAL, 6).unwrap();
    for selected in &members {
        let target = folder.join(&selected.edit.path);
        fs::create_dir_all(target.parent().unwrap()).unwrap();
        content(&before, &selected.edit.path)
            .write_to(&mut fs::File::create(&target).unwrap())
            .unwrap();
        common::set_metadata(&target, &selected.metadata).unwrap();
    }
    let payloads = folder.join("payloads");
    let prepared = invoke(
        &writer,
        &folder,
        &[
            "prepare-sdk-step",
            SEQUENTIAL,
            "7",
            payloads.to_str().unwrap(),
        ],
    );
    assert!(
        prepared.status.success(),
        "{}",
        String::from_utf8_lossy(&prepared.stderr)
    );
    let descriptor = payloads.join("descriptor.tsv");
    let body = fs::read_to_string(&descriptor).unwrap();
    assert!(body.starts_with(&format!(
        "original-sdk-step-payloads-v1\ncase\t{SEQUENTIAL}\nstep\t7\nmembers\t2\n"
    )));
    assert!(!body.contains("\nrole\t"));
    let digest = reference::sdk_edit_common::sha256_hex(body.as_bytes());
    for member in ["1", "2"] {
        let applied = invoke(
            &writer,
            &folder,
            &[
                "apply-sdk-step-prepared",
                SEQUENTIAL,
                "7",
                descriptor.to_str().unwrap(),
                &digest,
                member,
            ],
        );
        assert!(
            applied.status.success(),
            "{}",
            String::from_utf8_lossy(&applied.stderr)
        );
    }
    let after = edit_model::entries(SEQUENTIAL, 7).unwrap();
    for selected in &members {
        assert_eq!(
            reference::sdk_edit_common::sha256_hex(
                &fs::read(folder.join(&selected.edit.path)).unwrap()
            ),
            content(&after, &selected.edit.path).digest().unwrap()
        );
    }
}

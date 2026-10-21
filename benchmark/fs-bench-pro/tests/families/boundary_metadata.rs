//! External, product-free validation of the sole automatic timestamp domain.
#[allow(dead_code)]
#[path = "../../engine/recipes/boundary_metadata.rs"]
mod boundary_metadata;
#[allow(dead_code)]
#[path = "../../engine/recipes/edit_model.rs"]
mod edit_model;
#[allow(dead_code)]
#[path = "../../workload/main.rs"]
mod reference;

use boundary_metadata::{Custody, Timestamp};
use reference::file_size_transition::ALIAS_ROUNDTRIP;

fn valid() -> Custody {
    Custody {
        initial: Timestamp {
            seconds: 1_700_000_000,
            nanoseconds: 0,
        },
        started: Timestamp {
            seconds: 1_800_000_000,
            nanoseconds: 500_000_000,
        },
        finished: Timestamp {
            seconds: 1_800_000_001,
            nanoseconds: 0,
        },
        observed: Timestamp {
            seconds: 1_800_000_000,
            nanoseconds: 750_000_001,
        },
    }
}

#[test]
fn exact_independent_complete_model_changes_only_parent_timestamp() {
    let custody = boundary_metadata::parse(ALIAS_ROUNDTRIP, &valid().encode()).unwrap();
    let expected = edit_model::entries(ALIAS_ROUNDTRIP, 5).unwrap();
    let changed = boundary_metadata::entries(ALIAS_ROUNDTRIP, 5, custody).unwrap();
    let mut normalized = changed.clone();
    let parent = normalized
        .iter_mut()
        .find(|entry| entry.path == "data")
        .unwrap();
    assert_eq!(
        (parent.mtime_seconds, parent.mtime_nanoseconds),
        (custody.observed.seconds, custody.observed.nanoseconds)
    );
    parent.mtime_seconds = custody.initial.seconds;
    parent.mtime_nanoseconds = custody.initial.nanoseconds;
    assert_eq!(
        reference::workspace_common::manifest(&normalized).unwrap(),
        reference::workspace_common::manifest(&expected).unwrap()
    );
    assert_eq!(changed.len(), expected.len());
}

#[test]
fn malformed_extra_duplicate_or_wrong_domain_custody_is_refused() {
    let original = valid().encode();
    for body in [
        original.replace("path\tdata", "path\tdata/target.bin"),
        original.replace("step\t5", "step\t4"),
        original.replace(
            "case\tv016-boundary-alias-roundtrip-v1",
            "case\tv016-boundary-roundtrip-v1",
        ),
        original.replace("initial\t1700000000\t0", "initial\t1700000000\t1"),
        original.replace(
            "observed\t1800000000\t750000001",
            "observed\t1800000000\t1000000000",
        ),
        original.replace("observed\t1800000000", "observed\t01800000000"),
        format!("{original}observed\t1800000000\t750000001\n"),
        format!("{original}\n"),
        original.trim_end().to_owned(),
        original.replace('\n', "\r\n"),
    ] {
        assert!(
            boundary_metadata::parse(ALIAS_ROUNDTRIP, &body).is_err(),
            "{body}"
        );
    }
    assert!(boundary_metadata::parse("v016-boundary-roundtrip-v1", &original).is_err());
    for step in [0, 1, 2, 3, 4, 6] {
        assert!(boundary_metadata::entries(ALIAS_ROUNDTRIP, step, valid()).is_err());
    }
}

#[test]
fn timestamp_envelope_and_exact_native_precision_edges_are_enforced() {
    let sample = valid();
    let mut coarse = sample;
    coarse.observed = Timestamp {
        seconds: 1_799_999_999,
        nanoseconds: 500_000_000,
    };
    assert!(boundary_metadata::parse(ALIAS_ROUNDTRIP, &coarse.encode()).is_ok());
    coarse.observed.nanoseconds -= 1;
    assert!(boundary_metadata::parse(ALIAS_ROUNDTRIP, &coarse.encode()).is_err());
    let mut late = sample;
    late.observed = late.finished;
    assert!(boundary_metadata::parse(ALIAS_ROUNDTRIP, &late.encode()).is_ok());
    late.observed.nanoseconds += 1;
    assert!(boundary_metadata::parse(ALIAS_ROUNDTRIP, &late.encode()).is_err());
    let mut reverse = sample;
    reverse.finished = Timestamp {
        seconds: sample.started.seconds - 1,
        nanoseconds: 0,
    };
    assert!(boundary_metadata::parse(ALIAS_ROUNDTRIP, &reverse.encode()).is_err());
    let mut too_long = sample;
    too_long.finished = Timestamp {
        seconds: sample.started.seconds + 60,
        nanoseconds: sample.started.nanoseconds + 1,
    };
    assert!(boundary_metadata::parse(ALIAS_ROUNDTRIP, &too_long.encode()).is_err());
    let mut unchanged = sample;
    unchanged.observed = unchanged.initial;
    assert!(boundary_metadata::parse(ALIAS_ROUNDTRIP, &unchanged.encode()).is_err());
}

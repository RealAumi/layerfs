//! Independent original CDC scanner vectors and native source-only guards.
#[allow(dead_code)]
#[path = "../../engine/recipes/dedup_input.rs"]
mod dedup_input;
#[allow(dead_code)]
#[path = "../../workload/main.rs"]
mod reference;

use std::{
    fs,
    io::{self, Read},
    os::unix::fs::PermissionsExt,
    path::PathBuf,
};

const ORIGINAL: &str = include_str!("../../src/dedup_verify.rs");
const HELPER: &str = include_str!("../../engine/recipes/dedup_input.rs");

fn scanner_body(source: &str) -> &str {
    let begin = source.find("fn scan(").unwrap();
    let body = source[begin..].find("{\n").unwrap() + begin;
    let end = source[body..].find("\n}\n").unwrap() + body + 3;
    &source[body..end]
}

fn gear(source: &str) -> &str {
    let begin = source.find("const GEAR: [u64; 256] = [").unwrap();
    let end = source[begin..].find("\n];").unwrap() + begin + 3;
    &source[begin..end]
}

struct Fixture(PathBuf);
impl Fixture {
    fn new(label: &str) -> Self {
        let root = std::env::temp_dir().join(format!(
            "layerfs-dedup-input-{label}-{}",
            std::process::id()
        ));
        assert!(
            !root.exists(),
            "fresh test fixture required: {}",
            root.display()
        );
        Self(root)
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if std::thread::panicking() {
            eprintln!("RETAINED_FAILED_DEDUP_INPUT_FIXTURE={}", self.0.display());
        } else if self.0.exists() {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
}

#[test]
fn frozen_scanner_body_and_every_gear_value_match_original_source() {
    assert_eq!(scanner_body(HELPER), scanner_body(ORIGINAL));
    assert_eq!(gear(HELPER), gear(ORIGINAL));
    assert_eq!(gear(HELPER).matches("0x").count(), 256);
    assert_eq!(
        (
            dedup_input::MINIMUM_CHUNK_BYTES,
            dedup_input::TARGET_CHUNK_BYTES,
            dedup_input::MAXIMUM_CHUNK_BYTES
        ),
        (8192, 16384, 32768)
    );
    for forbidden in [
        "FastCdc::",
        "LayerStackStore",
        "Handles::",
        "ProjectApi",
        "layerfs_content::",
    ] {
        assert!(
            !HELPER.contains(forbidden),
            "source helper includes product work: {forbidden}"
        );
    }
}

#[test]
fn independent_frozen_vector_fragments_boundaries_and_callback_errors() {
    let mut state = 0x9e37_79b9_7f4a_7c15u64;
    let data: Vec<_> = (0..100000)
        .map(|_| {
            state ^= state.wrapping_shl(7);
            state ^= state.wrapping_shr(9);
            state ^= state.wrapping_shl(8);
            state as u8
        })
        .collect();
    let chunks = dedup_input::transcript(&data[..]).unwrap();
    assert_eq!(
        chunks.iter().map(|c| c.len).collect::<Vec<_>>(),
        [16396, 17093, 16413, 20273, 19016, 10809]
    );
    struct Fragment<'a>(&'a [u8]);
    impl Read for Fragment<'_> {
        fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
            let n = output.len().min(self.0.len()).min(3);
            output[..n].copy_from_slice(&self.0[..n]);
            self.0 = &self.0[n..];
            Ok(n)
        }
    }
    assert_eq!(chunks, dedup_input::transcript(Fragment(&data)).unwrap());
    for len in [0, 1, 8191, 8192, 16384, 32768, 32769] {
        let chunks = dedup_input::transcript(&data[..len]).unwrap();
        assert_eq!(chunks.iter().map(|c| c.len).sum::<u64>(), len as u64);
        assert!(chunks.iter().all(|c| c.len > 0 && c.len <= 32768));
        if len == 0 {
            assert!(chunks.is_empty());
        }
        if len == 32769 {
            assert!(chunks.len() >= 2);
        }
        for chunk in chunks {
            let start = chunk.logical_start as usize;
            assert_eq!(
                chunk.raw_sha256,
                reference::sdk_edit_common::sha256_hex(&data[start..start + chunk.len as usize])
            );
        }
    }
    let mut calls = 0;
    let result = dedup_input::scan(&data[..], |_| {
        calls += 1;
        Err("exact source callback failure".into())
    });
    assert_eq!(calls, 1);
    assert_eq!(
        result.unwrap_err().to_string(),
        "exact source callback failure"
    );
}

#[test]
fn all_boundary_source_paths_and_short_changed_identity_are_required() {
    let case = "dedup-cdc-boundaries-proof";
    let expected = dedup_input::expected(case, 0).unwrap();
    assert_eq!(expected.len(), 60);
    assert_eq!(
        expected.values().flatten().map(|c| c.len).sum::<u64>(),
        884745
    );
    assert_eq!(expected.values().filter(|c| c.is_empty()).count(), 6);
    let mut bad = expected.clone();
    bad.remove("boundary/s3/n32769/changed.dat");
    assert!(dedup_input::validate_contract(case, 0, &bad).is_err());
    let mut bad = expected.clone();
    bad.insert(
        "boundary/s3/n8192/changed.dat".into(),
        expected["boundary/s3/n8192/a.dat"].clone(),
    );
    assert!(dedup_input::validate_contract(case, 0, &bad)
        .unwrap_err()
        .to_string()
        .contains("sole chunk"));
    let mut bad = expected.clone();
    bad.get_mut("boundary/s1/n1/a.dat").unwrap()[0].logical_start = 1;
    assert!(dedup_input::validate_contract(case, 0, &bad).is_err());
}

#[test]
fn cross_file_internal_duplicates_disjoint_bases_and_mixed_pairs_stay_strict() {
    for case in [
        "dedup-cross-file-anchor-1",
        "dedup-cross-file-identical-100",
        "dedup-cross-file-unique-100",
        "dedup-cross-file-mixed-100",
    ] {
        let expected = dedup_input::expected(case, 0).unwrap();
        assert!(dedup_input::validate_contract(case, 0, &expected).is_ok());
    }
    let case = "dedup-cross-file-unique-100";
    let expected = dedup_input::expected(case, 0).unwrap();
    let mut bad = expected.clone();
    bad.insert(
        "files/f0001.dat".into(),
        expected["files/f0000.dat"].clone(),
    );
    assert!(dedup_input::validate_contract(case, 0, &bad)
        .unwrap_err()
        .to_string()
        .contains("distinct cross-file bases"));
    let case = "dedup-cross-file-mixed-100";
    let mut bad = dedup_input::expected(case, 0).unwrap();
    bad.get_mut("files/f0001.dat").unwrap()[0].raw_sha256 = "f".repeat(64);
    assert!(dedup_input::validate_contract(case, 0, &bad)
        .unwrap_err()
        .to_string()
        .contains("mixed exact pair"));
    let mut bad = dedup_input::expected("dedup-cross-file-anchor-1", 0).unwrap();
    let chunks = bad.get_mut("files/f0000.dat").unwrap();
    let identity = chunks[0].raw_sha256.clone();
    // Valid full length and positive bounded chunks isolate the duplicate guard.
    *chunks = (0..32)
        .map(|n| dedup_input::Chunk {
            logical_start: n * 32768,
            len: 32768,
            raw_sha256: identity.clone(),
        })
        .collect();
    assert!(
        dedup_input::validate_contract("dedup-cross-file-anchor-1", 0, &bad)
            .unwrap_err()
            .to_string()
            .contains("anchor internal duplicate")
    );
}

#[test]
fn workspace_exact_local_unique_and_frozen_cdc_diagnostics_are_preserved() {
    for profile in ["exact", "local", "unique"] {
        let case = format!("dedup-workspace-{profile}-100");
        for step in 0..=1 {
            assert!(dedup_input::expected(&case, step).is_ok());
        }
    }
    let case = "dedup-workspace-unique-100";
    let mut bad = dedup_input::expected(case, 1).unwrap();
    bad.insert("added/a0000.dat".into(), bad["base/b0000.dat"].clone());
    assert!(dedup_input::validate_contract(case, 1, &bad)
        .unwrap_err()
        .to_string()
        .contains("intersect base"));
    let case = "dedup-workspace-exact-100";
    let mut bad = dedup_input::expected(case, 1).unwrap();
    bad.get_mut("added/a0000.dat").unwrap()[0].raw_sha256 = "f".repeat(64);
    assert!(dedup_input::validate_contract(case, 1, &bad)
        .unwrap_err()
        .to_string()
        .contains("new regular payload"));
    for profile in ["overwrite", "insert", "delete", "common-body", "scattered"] {
        let case = format!("dedup-cdc-{profile}-1");
        let expected = dedup_input::expected(&case, 0).unwrap();
        let receipt = dedup_input::validate_contract(&case, 0, &expected).unwrap();
        for field in [
            "shared_chunk_count",
            "shared_logical_bytes",
            "prefix_chunk_count",
            "prefix_bytes",
            "suffix_chunk_count",
            "suffix_bytes",
            "suffix_base_position",
            "suffix_variant_position",
        ] {
            assert!(receipt.contains_key(&format!("variant_0000_{field}")));
        }
        if matches!(profile, "insert" | "delete") {
            for field in [
                "base_resynchronization_distance_bytes",
                "variant_resynchronization_distance_bytes",
            ] {
                assert!(receipt.contains_key(&format!("variant_0000_{field}")));
            }
        }
        assert!(receipt["sharing_metrics_scope"].contains("no numeric sharing threshold"));
    }
    assert!(dedup_input::expected("namespace-100-compact-v3", 0).is_err());
    assert!(dedup_input::expected(case, 2).is_err());
}

#[test]
fn native_qualification_reads_all_source_bytes_and_metadata_without_store() {
    for (index, case) in [
        "dedup-cdc-boundaries-proof",
        "dedup-cross-file-anchor-1",
        "dedup-workspace-exact-100",
    ]
    .iter()
    .enumerate()
    {
        let fixture = Fixture::new(&index.to_string());
        let rows = dedup_input::entries(case, 0).unwrap();
        reference::workspace_common::create_fixture(&fixture.0, &rows).unwrap();
        let qualification = dedup_input::qualify_native(case, 0, &fixture.0).unwrap();
        assert_eq!(qualification.transcript_sha256.len(), 64);
        assert_eq!(
            qualification.files as usize,
            qualification.transcripts.len()
        );
        assert!(qualification.receipt["scope"].contains("no Store operation"));
        let path = qualification.transcripts.keys().next_back().unwrap();
        let file = fixture.0.join(path);
        let mut bytes = fs::read(&file).unwrap();
        assert!(!bytes.is_empty());
        let last = bytes.len() - 1;
        bytes[last] ^= 1;
        fs::write(&file, &bytes).unwrap();
        let declared = rows.iter().find(|row| row.path == *path).unwrap();
        reference::workspace_common::set_metadata(&file, declared).unwrap();
        assert!(dedup_input::qualify_native(case, 0, &fixture.0).is_err());
        bytes[last] ^= 1;
        fs::write(&file, bytes).unwrap();
        reference::workspace_common::set_metadata(&file, declared).unwrap();
        fs::set_permissions(&file, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(dedup_input::qualify_native(case, 0, &fixture.0).is_err());
        assert!(!fixture.0.join("store.sqlite").exists());
    }
}

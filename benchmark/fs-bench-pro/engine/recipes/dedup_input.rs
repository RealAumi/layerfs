//! Independent original batch-six source CDC and import/reuse qualification.
//! The scanner and GEAR values below are transcribed unchanged from frozen
//! benchmark/fs-bench-pro/src/dedup_verify.rs at d296981ace76fe751bebf00dee52818fe18a3eef.
//! Legacy object framing is deliberately absent: identity here is raw SHA-256.
//! Product constructors, FastCdc, Store and History are never called.
use crate::reference;
use reference::workspace_common::{Entry, EntryKind, Receipt};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{self, Read},
    path::Path,
};

pub const MINIMUM_CHUNK_BYTES: u64 = 8192;
pub const TARGET_CHUNK_BYTES: u64 = 16384;
pub const MAXIMUM_CHUNK_BYTES: u64 = 32768;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Chunk {
    pub logical_start: u64,
    pub len: u64,
    pub raw_sha256: String,
}

#[derive(Debug)]
pub struct Qualification {
    pub files: u64,
    pub logical_bytes: u64,
    pub transcript_sha256: String,
    pub receipt: Receipt,
    pub transcripts: BTreeMap<String, Vec<Chunk>>,
}

pub fn transcript(input: impl Read) -> reference::Result<Vec<Chunk>> {
    let mut result = Vec::new();
    let mut logical_start = 0;
    scan(input, |raw| {
        let len = raw.len() as u64;
        result.push(Chunk {
            logical_start,
            len,
            raw_sha256: reference::sdk_edit_common::sha256_hex(raw),
        });
        logical_start = logical_start
            .checked_add(len)
            .ok_or("source length overflow")?;
        Ok(())
    })?;
    Ok(result)
}

fn selection(id: &str, step: usize) -> reference::Result<reference::workspace_common::Case> {
    let case = reference::workspace_registry::resolve(id)?;
    if !matches!(
        case.family,
        "dedup_cdc_locality" | "dedup_cross_file" | "dedup_workspace_reuse"
    ) || step > 1
    {
        return Err("original batch-six source case and step0/1 required".into());
    }
    Ok(case)
}

pub fn entries(id: &str, step: usize) -> reference::Result<Vec<Entry>> {
    reference::workspace_registry::expected(&selection(id, step)?, 1, step)
}

pub fn expected(id: &str, step: usize) -> reference::Result<BTreeMap<String, Vec<Chunk>>> {
    let mut files = BTreeMap::new();
    for entry in entries(id, step)? {
        if let EntryKind::File(content) = entry.kind {
            files.insert(entry.path, transcript(content.reader())?);
        }
    }
    validate_contract(id, step, &files)?;
    Ok(files)
}

fn unique(chunks: &[Chunk]) -> reference::Result<BTreeMap<String, u64>> {
    let mut payloads = BTreeMap::new();
    let mut position = 0;
    for chunk in chunks {
        if chunk.logical_start != position
            || chunk.len == 0
            || chunk.len > MAXIMUM_CHUNK_BYTES
            || chunk.raw_sha256.len() != 64
            || !chunk
                .raw_sha256
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        {
            return Err("invalid independent source transcript geometry/digest".into());
        }
        position = position
            .checked_add(chunk.len)
            .ok_or("source transcript overflow")?;
        if payloads
            .insert(chunk.raw_sha256.clone(), chunk.len)
            .is_some_and(|old| old != chunk.len)
        {
            return Err("one raw payload identity has conflicting lengths".into());
        }
    }
    Ok(payloads)
}

fn union<'a>(
    files: impl IntoIterator<Item = &'a Vec<Chunk>>,
) -> reference::Result<BTreeMap<String, u64>> {
    let mut payloads = BTreeMap::new();
    for chunks in files {
        for (id, len) in unique(chunks)? {
            if payloads.insert(id, len).is_some_and(|old| old != len) {
                return Err("raw payload length mismatch across files".into());
            }
        }
    }
    Ok(payloads)
}

fn same_payload(a: &Chunk, b: &Chunk) -> bool {
    a.len == b.len && a.raw_sha256 == b.raw_sha256
}

fn boundary_contract(
    files: &BTreeMap<String, Vec<Chunk>>,
    receipt: &mut Receipt,
) -> reference::Result<()> {
    if files.len() != 60 {
        return Err("CDC boundary input cardinality".into());
    }
    for seed in 1..=3 {
        for len in [0, 1, 8191, 8192, 16384, 32768, 32769] {
            let path = format!("boundary/s{seed}/n{len}");
            let a = &files[&format!("{path}/a.dat")];
            let b = &files[&format!("{path}/b.dat")];
            if a != b
                || a.iter().map(|c| c.len).sum::<u64>() != len
                || len == 0 && !a.is_empty()
                || len == 32769 && a.len() < 2
            {
                return Err("CDC boundary shape or equal pair differs".into());
            }
            if len > 0 && len <= 8192 {
                let changed = &files[&format!("{path}/changed.dat")];
                if a.len() != 1 || changed.iter().any(|c| c.raw_sha256 == a[0].raw_sha256) {
                    return Err("CDC short mutation retained sole chunk".into());
                }
            }
        }
        receipt.insert(format!("seed_{seed}_boundary_status"), "pass".into());
    }
    receipt.insert("boundary_file_count".into(), "60".into());
    receipt.insert("boundary_seed_count".into(), "3".into());
    Ok(())
}

fn cross_contract(
    case: &reference::workspace_common::Case,
    files: &BTreeMap<String, Vec<Chunk>>,
    receipt: &mut Receipt,
) -> reference::Result<()> {
    let anchor = &files["files/f0000.dat"];
    if unique(anchor)?.len() != anchor.len() {
        return Err("unintended anchor internal duplicate chunk".into());
    }
    if case.kind == "identical" && files.values().any(|chunks| chunks != anchor) {
        return Err("identical file transcripts differ".into());
    }
    let mut bases = BTreeMap::new();
    for (path, chunks) in files {
        let ordinal = path
            .strip_prefix("files/f")
            .and_then(|s| s.strip_suffix(".dat"))
            .ok_or("cross-file source path")?
            .parse::<usize>()?;
        let base = match case.kind {
            "anchor" | "identical" => 0,
            "unique" => ordinal,
            "mixed" => 3 * (ordinal / 4) + (ordinal % 4).saturating_sub(1),
            _ => return Err("cross-file source profile".into()),
        };
        if bases.insert(base, chunks).is_some_and(|old| old != chunks) {
            return Err("mixed exact pair differs".into());
        }
    }
    let mut distinct = BTreeSet::new();
    for chunks in bases.values() {
        for chunk in *chunks {
            if !distinct.insert(&chunk.raw_sha256) {
                return Err("unintended duplicate chunk in distinct cross-file bases".into());
            }
        }
    }
    receipt.insert(
        "distinct_complete_file_count".into(),
        bases.len().to_string(),
    );
    Ok(())
}

fn cdc_contract(
    case: &reference::workspace_common::Case,
    files: &BTreeMap<String, Vec<Chunk>>,
    receipt: &mut Receipt,
) -> reference::Result<()> {
    let base = &files["reference.dat"];
    let base_ids = unique(base)?;
    for i in 0..case.tier {
        let variant = &files[&format!("variants/v{i:04}.dat")];
        let shared: BTreeSet<_> = variant
            .iter()
            .filter(|c| base_ids.contains_key(&c.raw_sha256))
            .map(|c| &c.raw_sha256)
            .collect();
        let prefix_count = base
            .iter()
            .zip(variant)
            .take_while(|(a, b)| same_payload(a, b))
            .count();
        let suffix_count = base
            .iter()
            .rev()
            .zip(variant.iter().rev())
            .take_while(|(a, b)| same_payload(a, b))
            .count();
        let base_position =
            (suffix_count > 0).then(|| base[base.len() - suffix_count].logical_start);
        let variant_position =
            (suffix_count > 0).then(|| variant[variant.len() - suffix_count].logical_start);
        let prefix = format!("variant_{i:04}_");
        for (key, value) in [
            ("shared_chunk_count", shared.len() as u64),
            (
                "shared_logical_bytes",
                variant
                    .iter()
                    .filter(|c| base_ids.contains_key(&c.raw_sha256))
                    .map(|c| c.len)
                    .sum(),
            ),
            ("prefix_chunk_count", prefix_count as u64),
            (
                "prefix_bytes",
                variant[..prefix_count].iter().map(|c| c.len).sum(),
            ),
            ("suffix_chunk_count", suffix_count as u64),
            (
                "suffix_bytes",
                variant[variant.len() - suffix_count..]
                    .iter()
                    .map(|c| c.len)
                    .sum(),
            ),
        ] {
            receipt.insert(format!("{prefix}{key}"), value.to_string());
        }
        for (label, position) in [
            ("suffix_base_position", base_position),
            ("suffix_variant_position", variant_position),
        ] {
            receipt.insert(
                format!("{prefix}{label}"),
                position.map_or("not-found".into(), |n| n.to_string()),
            );
        }
        if matches!(case.kind, "insert" | "delete") {
            let at = reference::dedup_workloads::offset(case.family, case.kind, 1, i)?;
            for (label, position, end) in [
                (
                    "base_resynchronization_distance_bytes",
                    base_position,
                    at + if case.kind == "delete" { 4096 } else { 0 },
                ),
                (
                    "variant_resynchronization_distance_bytes",
                    variant_position,
                    at + if case.kind == "insert" { 4096 } else { 0 },
                ),
            ] {
                let distance = position
                    .map(|n| {
                        n.checked_sub(end)
                            .ok_or("suffix resumes before edit boundary")
                    })
                    .transpose()?;
                receipt.insert(
                    format!("{prefix}{label}"),
                    distance.map_or("not-found".into(), |n| n.to_string()),
                );
            }
        }
        if case.kind == "common-body" {
            let middle: BTreeSet<_> = base
                .iter()
                .filter(|c| c.logical_start >= 131072 && c.logical_start + c.len <= 917504)
                .map(|c| &c.raw_sha256)
                .collect();
            let coverage: u64 = variant
                .iter()
                .filter(|c| middle.contains(&c.raw_sha256))
                .map(|c| {
                    (c.logical_start + c.len)
                        .min(917504)
                        .saturating_sub(c.logical_start.max(131072))
                })
                .sum();
            receipt.insert(
                format!("{prefix}shared_middle_logical_bytes"),
                coverage.to_string(),
            );
        }
    }
    let mut digests = BTreeSet::new();
    for entry in reference::dedup_cdc_locality::fixture(case, 1)? {
        if let EntryKind::File(content) = entry.kind {
            if !digests.insert(content.digest()?) {
                return Err("duplicate CDC reference/variant fixture".into());
            }
        }
    }
    Ok(())
}

fn reuse_contract(
    case: &reference::workspace_common::Case,
    step: usize,
    files: &BTreeMap<String, Vec<Chunk>>,
    receipt: &mut Receipt,
) -> reference::Result<()> {
    let base_count = reference::dedup_workspace_reuse::base_file_count(case)?;
    let base: BTreeMap<_, _> = files
        .iter()
        .filter(|(p, _)| p.starts_with("base/"))
        .collect();
    let added: BTreeMap<_, _> = files
        .iter()
        .filter(|(p, _)| p.starts_with("added/"))
        .collect();
    if base.len() != base_count {
        return Err("workspace reuse base file count".into());
    }
    let p = union(base.values().copied())?;
    let a = union(added.values().copied())?;
    if p.len() != base.values().map(|c| c.len()).sum::<usize>() {
        return Err("unintended duplicate chunk in workspace unique base".into());
    }
    if case.kind == "unique" && a.len() != added.values().map(|c| c.len()).sum::<usize>() {
        return Err("unintended duplicate chunk in unique workspace additions".into());
    }
    if case.kind == "local" {
        let mut distinct = BTreeSet::new();
        for chunks in added.values() {
            let identity: Vec<_> = chunks.iter().map(|c| (&c.raw_sha256, c.len)).collect();
            if !distinct.insert(identity) {
                return Err("duplicate local addition content".into());
            }
        }
    }
    let new_bytes: u64 = a
        .iter()
        .filter(|(id, _)| !p.contains_key(*id))
        .map(|(_, len)| len)
        .sum();
    if case.kind == "exact" && new_bytes != 0 {
        return Err("exact additions inserted new regular payload".into());
    }
    if case.kind == "unique" && a.keys().any(|id| p.contains_key(id)) {
        return Err("unique additions intersect base payload".into());
    }
    for i in 0..if step == 0 { 0 } else { case.tier } {
        if case.kind == "exact"
            && files[&format!("added/a{i:04}.dat")]
                != files[&format!("base/b{:04}.dat", i % base_count)]
        {
            return Err("exact addition differs from selected base".into());
        }
    }
    receipt.insert("base_file_count".into(), base_count.to_string());
    receipt.insert(
        "addition_logical_bytes".into(),
        added
            .values()
            .flat_map(|c| c.iter())
            .map(|c| c.len)
            .sum::<u64>()
            .to_string(),
    );
    receipt.insert("addition_new_payload_bytes".into(), new_bytes.to_string());
    receipt.insert(
        "base_distinct_payload_bytes".into(),
        p.values().sum::<u64>().to_string(),
    );
    Ok(())
}

/// Source contract only; actual persisted output must be compared independently.
pub fn validate_contract(
    id: &str,
    step: usize,
    files: &BTreeMap<String, Vec<Chunk>>,
) -> reference::Result<Receipt> {
    let case = selection(id, step)?;
    let expected_entries = entries(id, step)?;
    let expected_files: BTreeMap<_, _> = expected_entries
        .iter()
        .filter_map(|entry| match &entry.kind {
            EntryKind::File(content) => Some((&entry.path, content.len())),
            _ => None,
        })
        .collect();
    if files.keys().collect::<Vec<_>>() != expected_files.keys().copied().collect::<Vec<_>>() {
        return Err("independent source regular-file path cardinality differs".into());
    }
    for (path, chunks) in files {
        unique(chunks)?;
        if chunks.iter().map(|c| c.len).sum::<u64>() != expected_files[path] {
            return Err("independent source transcript logical length differs".into());
        }
    }
    let payloads = union(files.values())?;
    let mut receipt = Receipt::new();
    receipt.insert("dedup_transcript_status".into(), "pass".into());
    receipt.insert(
        "regular_file_logical_bytes".into(),
        payload_logical(files).to_string(),
    );
    receipt.insert(
        "distinct_payload_bytes".into(),
        payloads.values().sum::<u64>().to_string(),
    );
    receipt.insert("distinct_payload_count".into(), payloads.len().to_string());
    receipt.insert("regular_file_count".into(), files.len().to_string());
    if reference::workspace_registry::is_import(&case) {
        receipt.insert(
            "new_payload_bytes".into(),
            payloads.values().sum::<u64>().to_string(),
        );
        receipt.insert("preexisting_payload_bytes".into(), "0".into());
    }
    match case.family {
        "dedup_cdc_locality" if case.kind == "boundaries" => {
            boundary_contract(files, &mut receipt)?
        }
        "dedup_cdc_locality" => cdc_contract(&case, files, &mut receipt)?,
        "dedup_cross_file" => cross_contract(&case, files, &mut receipt)?,
        "dedup_workspace_reuse" => reuse_contract(&case, step, files, &mut receipt)?,
        _ => unreachable!(),
    }
    receipt.insert(
        "identity_scope".into(),
        "independent raw-chunk SHA256, not legacy or current canonical ObjectID".into(),
    );
    receipt.insert(
        "sharing_metrics_scope".into(),
        "diagnostic; exact transcript/source contracts required; no numeric sharing threshold"
            .into(),
    );
    Ok(receipt)
}

fn payload_logical(files: &BTreeMap<String, Vec<Chunk>>) -> u64 {
    files.values().flatten().map(|c| c.len).sum()
}

/// Full native bytes/metadata and CDC source qualification; no Store is opened.
pub fn qualify_native(id: &str, step: usize, root: &Path) -> reference::Result<Qualification> {
    let rows = entries(id, step)?;
    reference::workspace_common::verify_native(root, &rows)?;
    let transcripts = expected(id, step)?;
    for (path, wanted) in &transcripts {
        if transcript(fs::File::open(root.join(path))?)? != *wanted {
            return Err(format!("native independent source transcript differs: {path}").into());
        }
    }
    let mut receipt = validate_contract(id, step, &transcripts)?;
    let mut hash = reference::Sha256::new();
    for (path, chunks) in &transcripts {
        hash.update(path.as_bytes());
        hash.update(&[0]);
        for chunk in chunks {
            hash.update(&chunk.logical_start.to_le_bytes());
            hash.update(&chunk.len.to_le_bytes());
            hash.update(chunk.raw_sha256.as_bytes());
        }
    }
    let transcript_sha256 = reference::hex(&hash.finish());
    receipt.insert("input_transcript_sha256".into(), transcript_sha256.clone());
    receipt.insert(
        "input_transcript_schema".into(),
        "original-dedup-raw-chunk-sha256-v1".into(),
    );
    receipt.insert("scope".into(), "independent source bytes/metadata/transcripts/sharing before admission; not product verification; no Store operation".into());
    Ok(Qualification {
        files: transcripts.len() as u64,
        logical_bytes: payload_logical(&transcripts),
        transcript_sha256,
        receipt,
        transcripts,
    })
}

pub fn scan(
    mut input: impl Read,
    mut emit: impl FnMut(&[u8]) -> reference::Result<()>,
) -> reference::Result<()> {
    let mut window = Vec::with_capacity(32768);
    let mut scratch = [0u8; 32768];
    let mut eof = false;
    loop {
        while window.len() < 32768 && !eof {
            let room = 32768 - window.len();
            match input.read(&mut scratch[..room]) {
                Ok(0) => eof = true,
                Ok(n) => window.extend_from_slice(&scratch[..n]),
                Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                Err(error) => return Err(error.into()),
            }
        }
        if window.is_empty() {
            break;
        }
        let mut cut = window.len();
        let mut position = 8192;
        let mut hash = 0u64;
        while position + 1 < window.len() {
            let small = position < 16384;
            hash = hash
                .wrapping_mul(4)
                .wrapping_add(GEAR[window[position] as usize].wrapping_mul(2));
            if hash
                & if small {
                    0x0001_b206_06a6_e000
                } else {
                    0x0001_b202_06a6_0000
                }
                == 0
            {
                cut = position;
                break;
            }
            hash = hash.wrapping_add(GEAR[window[position + 1] as usize]);
            if hash
                & if small {
                    0x0000_d903_0353_7000
                } else {
                    0x0000_d901_0353_0000
                }
                == 0
            {
                cut = position + 1;
                break;
            }
            position += 2;
        }
        emit(&window[..cut])?;
        window.drain(..cut);
    }
    Ok(())
}

const GEAR: [u64; 256] = [
    0x3b5d3c7d207e37dc,
    0x784d68ba91123086,
    0xcd52880f882e7298,
    0xeacf8e4e19fdcca7,
    0xc31f385dfbd1632b,
    0x1d5f27001e25abe6,
    0x83130bde3c9ad991,
    0xc4b225676e9b7649,
    0xaa329b29e08eb499,
    0xb67fcbd21e577d58,
    0x0027baaada2acf6b,
    0xe3ef2d5ac73c2226,
    0x0890f24d6ed312b7,
    0xa809e036851d7c7e,
    0xf0a6fe5e0013d81b,
    0x1d026304452cec14,
    0x03864632648e248f,
    0xcdaacf3dcd92b9b4,
    0xf5e012e63c187856,
    0x8862f9d3821c00b6,
    0xa82f7338750f6f8a,
    0x1e583dc6c1cb0b6f,
    0x7a3145b69743a7f1,
    0xabb20fee404807eb,
    0xb14b3cfe07b83a5d,
    0xb9dc27898adb9a0f,
    0x3703f5e91baa62be,
    0xcf0bb866815f7d98,
    0x3d9867c41ea9dcd3,
    0x1be1fa65442bf22c,
    0x14300da4c55631d9,
    0xe698e9cbc6545c99,
    0x4763107ec64e92a5,
    0xc65821fc65696a24,
    0x76196c064822f0b7,
    0x485be841f3525e01,
    0xf652bc9c85974ff5,
    0xcad8352face9e3e9,
    0x2a6ed1dceb35e98e,
    0xc6f483badc11680f,
    0x3cfd8c17e9cf12f1,
    0x89b83c5e2ea56471,
    0xae665cfd24e392a9,
    0xec33c4e504cb8915,
    0x3fb9b15fc9fe7451,
    0xd7fd1fd1945f2195,
    0x31ade0853443efd8,
    0x255efc9863e1e2d2,
    0x10eab6008d5642cf,
    0x46f04863257ac804,
    0xa52dc42a789a27d3,
    0xdaaadf9ce77af565,
    0x6b479cd53d87febb,
    0x6309e2d3f93db72f,
    0xc5738ffbaa1ff9d6,
    0x6bd57f3f25af7968,
    0x67605486d90d0a4a,
    0xe14d0b9663bfbdae,
    0xb7bbd8d816eb0414,
    0xdef8a4f16b35a116,
    0xe7932d85aaaffed6,
    0x08161cbae90cfd48,
    0x855507beb294f08b,
    0x91234ea6ffd399b2,
    0xad70cf4b2435f302,
    0xd289a97565bc2d27,
    0x8e558437ffca99de,
    0x96d2704b7115c040,
    0x0889bbcdfc660e41,
    0x5e0d4e67dc92128d,
    0x72a9f8917063ed97,
    0x438b69d409e016e3,
    0xdf4fed8a5d8a4397,
    0x00f41dcf41d403f7,
    0x4814eb038e52603f,
    0x9dafbacc58e2d651,
    0xfe2f458e4be170af,
    0x4457ec414df6a940,
    0x06e62f1451123314,
    0xbd1014d173ba92cc,
    0xdef318e25ed57760,
    0x9fea0de9dfca8525,
    0x459de1e76c20624b,
    0xaeec189617e2d666,
    0x126a2c06ab5a83cb,
    0xb1321532360f6132,
    0x65421503dbb40123,
    0x2d67c287ea089ab3,
    0x6c93bff5a56bd6b6,
    0x4ffb2036cab6d98d,
    0xce7b785b1be7ad4f,
    0xedb42ef6189fd163,
    0xdc905288703988f6,
    0x365f9c1d2c691884,
    0xc640583680d99bfe,
    0x3cd4624c07593ec6,
    0x7f1ea8d85d7c5805,
    0x014842d480b57149,
    0x0b649bcb5a828688,
    0xbcd5708ed79b18f0,
    0xe987c862fbd2f2f0,
    0x982731671f0cd82c,
    0xbaf13e8b16d8c063,
    0x8ea3109cbd951bba,
    0xd141045bfb385cad,
    0x2acbc1a0af1f7d30,
    0xe6444d89df03bfdf,
    0xa18cc771b8188ff9,
    0x9834429db01c39bb,
    0x214add07fe086a1f,
    0x8f07c19b1f6b3ff9,
    0x56a297b1bf4ffe55,
    0x94d558e493c54fc7,
    0x40bfc24c764552cb,
    0x931a706f8a8520cb,
    0x32229d322935bd52,
    0x2560d0f5dc4fefaf,
    0x9dbcc48355969bb6,
    0x0fd81c3985c0b56a,
    0xe03817e1560f2bda,
    0xc1bb4f81d892b2d5,
    0xb0c4864f4e28d2d7,
    0x3ecc49f9d9d6c263,
    0x51307e99b52ba65e,
    0x8af2b688da84a752,
    0xf5d72523b91b20b6,
    0x6d95ff1ff4634806,
    0x562f21555458339a,
    0xc0ce47f889336346,
    0x487823e5089b40d8,
    0xe4727c7ebc6d9592,
    0x5a8f7277e94970ba,
    0xfca2f406b1c8bb50,
    0x5b1f8a95f1791070,
    0xd304af9fc9028605,
    0x5440ab7fc930e748,
    0x312d25fbca2ab5a1,
    0x10f4a4b234a4d575,
    0x90301d55047e7473,
    0x3b6372886c61591e,
    0x293402b77c444e06,
    0x451f34a4d3e97dd7,
    0x3158d814d81bc57b,
    0x034942425b9bda69,
    0xe2032ff9e532d9bb,
    0x62ae066b8b2179e5,
    0x9545e10c2f8d71d8,
    0x7ff7483eb2d23fc0,
    0x00945fcebdc98d86,
    0x8764bbbe99b26ca2,
    0x1b1ec62284c0bfc3,
    0x58e0fcc4f0aa362b,
    0x5f4abefa878d458d,
    0xfd74ac2f9607c519,
    0xa4e3fb37df8cbfa9,
    0xbf697e43cac574e5,
    0x86f14a3f68f4cd53,
    0x24a23d076f1ce522,
    0xe725cd8048868cc8,
    0xbf3c729eb2464362,
    0xd8f6cd57b3cc1ed8,
    0x6329e52425541577,
    0x62aa688ad5ae1ac0,
    0x0a242566269bf845,
    0x168b1a4753aca74b,
    0xf789afefff2e7e3c,
    0x6c3362093b6fccdb,
    0x4ce8f50bd28c09b2,
    0x006a2db95ae8aa93,
    0x975b0d623c3d1a8c,
    0x18605d3935338c5b,
    0x5bb6f6136cad3c71,
    0x0f53a20701f8d8a6,
    0xab8c5ad2e7e93c67,
    0x40b5ac5127acaa29,
    0x8c7bf63c2075895f,
    0x78bd9f7e014a805c,
    0xb2c9e9f4f9c8c032,
    0xefd6049827eb91f3,
    0x2be459f482c16fbd,
    0xd92ce0c5745aaa8c,
    0x0aaa8fb298d965b9,
    0x2b37f92c6c803b15,
    0x8c54a5e94e0f0e78,
    0x95f9b6e90c0a3032,
    0xe7939faa436c7874,
    0xd16bfe8f6a8a40c9,
    0x44982b86263fd2fa,
    0xe285fb39f984e583,
    0x779a8df72d7619d3,
    0xf2d79a8de8d5dd1e,
    0xd1037354d66684e2,
    0x004c82a4e668a8e5,
    0x31d40a7668b044e6,
    0xd70578538bd02c11,
    0xdb45431078c5f482,
    0x977121bb7f6a51ad,
    0x73d5ccbd34eff8dd,
    0xe437a07d356e17cd,
    0x47b2782043c95627,
    0x9fb251413e41d49a,
    0xccd70b60652513d3,
    0x1c95b31e8a1b49b2,
    0xcae73dfd1bcb4c1b,
    0x34d98331b1f5b70f,
    0x784e39f22338d92f,
    0x18613d4a064df420,
    0xf1d8dae25f0bcebe,
    0x33f77c15ae855efc,
    0x3c88b3b912eb109c,
    0x956a2ec96bafeea5,
    0x1aa005b5e0ad0e87,
    0x5500d70527c4bb8e,
    0xe36c57196421cc44,
    0x13c4d286cc36ee39,
    0x5654a23d818b2a81,
    0x77b1dc13d161abdc,
    0x734f44de5f8d5eb5,
    0x60717e174a6c89a2,
    0xd47d9649266a211e,
    0x5b13a4322bb69e90,
    0xf7669609f8b5fc3c,
    0x21e6ac55bedcdac9,
    0x9b56b62b61166dea,
    0xf48f66b939797e9c,
    0x35f332f9c0e6ae9a,
    0xcc733f6a9a878db0,
    0x3da161e41cc108c2,
    0xb7d74ae535914d51,
    0x4d493b0b11d36469,
    0xce264d1dfba9741a,
    0xa9d1f2dc7436dc06,
    0x70738016604c2a27,
    0x231d36e96e93f3d5,
    0x7666881197838d19,
    0x4a2a83090aaad40c,
    0xf1e761591668b35d,
    0x7363236497f730a7,
    0x301080e37379dd4d,
    0x502dea2971827042,
    0xc2c5eb858f32625f,
    0x786afb9edfafbdff,
    0xdaee0d868490b2a4,
    0x617366b3268609f6,
    0xae0e35a0fe46173e,
    0xd1a07de93e824f11,
    0x079b8b115ea4cca8,
    0x93a99274558faebb,
    0xfb1e6e22e08a03b3,
    0xea635fdba3698dd0,
    0xcf53659328503a5c,
    0xcde3b31e6fd5d780,
    0x8e3e4221d3614413,
    0xef14d0d86bf1a22c,
    0xe1d830d3f16c5ddb,
    0xaabd2b2a451504e1,
];

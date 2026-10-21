//! Native-only transcription of the frozen namespace fixture write loop.
#[allow(dead_code)]
#[path = "../../workload/main.rs"]
pub(crate) mod reference;

use std::{collections::BTreeSet, fs, io::Write, path::Path};

pub(crate) fn samples(plan: &reference::NamespacePlan) -> BTreeSet<usize> {
    use reference::NamespaceClass;
    let mut indices = BTreeSet::new();
    for directory in [
        0,
        plan.scenario.data_directories / 2,
        plan.scenario.data_directories - 1,
    ] {
        let first = (directory * reference::NAMESPACE_FILES_PER_DIRECTORY) as usize;
        indices.extend([
            first,
            first + reference::NAMESPACE_FILES_PER_DIRECTORY as usize - 1,
        ]);
    }
    for class in [
        NamespaceClass::Empty,
        NamespaceClass::Tiny,
        NamespaceClass::Small,
        NamespaceClass::Medium,
        NamespaceClass::Anchor,
    ] {
        if let Some(index) = plan.files.iter().position(|file| file.class == class) {
            indices.insert(index);
        }
    }
    indices
}

pub(crate) fn generate(root: &Path, case: &str) -> reference::Result<()> {
    let plan = reference::namespace_plan(case)?;
    fs::create_dir(root)?;
    for directory in 0..plan.scenario.data_directories {
        fs::create_dir(root.join(format!("d{directory:04}")))?;
    }
    let mut buffer = vec![0; reference::NAMESPACE_SCRATCH_BYTES];
    let mut digests = Vec::with_capacity(plan.files.len());
    let mut total = 0;
    for file in &plan.files {
        let path = root.join(&file.relative_path);
        let mut output = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)?;
        let mut stream = reference::NamespaceContentStream::new(plan.scenario, file);
        let mut hash = reference::Sha256::new();
        let mut left = file.size;
        while left != 0 {
            let count = left.min(buffer.len() as u64) as usize;
            stream.fill(&mut buffer[..count]);
            output.write_all(&buffer[..count])?;
            hash.update(&buffer[..count]);
            left -= count as u64;
            total += count as u64;
        }
        drop(output);
        reference::set_namespace_metadata(&path, false)?;
        digests.push(Some(hash.finish()));
    }
    for directory in 0..plan.scenario.data_directories {
        reference::set_namespace_metadata(&root.join(format!("d{directory:04}")), true)?;
    }
    reference::set_namespace_metadata(root, true)?;
    let digest = reference::namespace_tree_digest(&plan, &digests)?;
    if total != plan.scenario.logical_bytes {
        return Err("frozen fixture byte count differs".into());
    }
    println!("{{\"case\":\"{case}\",\"files\":{},\"directories\":{},\"logical_bytes\":{total},\"fixture_digest\":\"{digest}\",\"seed\":1}}",
        plan.files.len(), plan.scenario.data_directories + 1);
    Ok(())
}

#[allow(dead_code)]
fn main() -> reference::Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 {
        return Err("CASE FRESH_NATIVE_ROOT required".into());
    }
    generate(Path::new(&args[2]), &args[1])
}

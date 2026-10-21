"""Original canonical plans, count guards and byte pins survive the POSIX port."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "benchmark/fs-bench-pro/families/edit_canonical_chunk_count/family.json"
FLAGS = ("--cfg", "aes_armv8", "--cfg", "polyval_armv8", "--cfg", "chacha20_force_neon",
         "-C", "target-feature=+aes,+sha2")


class CanonicalPort(unittest.TestCase):
    def test_all_original_plans_and_frozen_counts_digests_remain_exact(self):
        source = '''#[allow(dead_code)]
#[path = SOURCE]
mod reference;
fn main() {
    reference::edit_canonical_chunk_count::self_check().unwrap();
    let rows = reference::edit_canonical_chunk_count::registry();
    print!("{}", reference::sdk_edit_common::registry_tsv(&rows));
    for row in rows {
        let e = reference::edit_canonical_chunk_count::expected(&row);
        let i = reference::sdk_edit_common::fixture_index(row.fixture_bytes).unwrap();
        eprintln!("{}\\t{}\\t{}\\t{}\\t{}", row.id, e.initial_count, e.final_count,
                  e.final_sha256, reference::sdk_edit_common::FIXTURE_SHA256[i]);
    }
}
'''.replace("SOURCE", json.dumps(str(ROOT / "benchmark/fs-bench-pro/workload/main.rs")))
        with tempfile.TemporaryDirectory(prefix="canonical-registry-", dir=ROOT / "core/target") as temporary:
            path, binary = Path(temporary) / "registry.rs", Path(temporary) / "registry"
            path.write_text(source)
            compiled = subprocess.run(["rustup", "run", "1.85.1", "rustc", "--edition=2021", *FLAGS,
                                       str(path), "-o", str(binary)], cwd=ROOT,
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            output = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(output.returncode, 0, output.stderr)
        family = json.loads(FAMILY.read_text())
        self.assertEqual(hashlib.sha256(output.stdout.encode()).hexdigest(), family["original_registry_sha256"])
        plans = list(csv.DictReader(io.StringIO(output.stdout), delimiter="\t"))
        pins = {fields[0]: fields[1:] for fields in (line.split("\t") for line in output.stderr.splitlines())}
        self.assertEqual(len(plans), 12)
        by_id = {plan["scenario_id"]: plan for plan in plans}
        self.assertEqual(len(family["cases"]), 3)
        for case in family["cases"]:
            plan = by_id[case["id"]]
            with self.subTest(case=case["id"]):
                self.assertEqual({k: str(v) for k, v in case["sdk_scenario"].items()}, plan)
                initial, final, digest, fixture_digest = pins[case["id"]]
                expected = case["original_canonical"]
                self.assertEqual((expected["initial_count"], expected["final_count"], expected["final_sha256"]),
                                 (int(initial), int(final), digest))
                self.assertEqual(case["fixture"]["content_sha256"], fixture_digest)
                self.assertEqual(case["status"], "ported")
                self.assertEqual(case["budget"]["command_ms"], 15000)
                self.assertEqual(case["budget"]["operation_watchdog_ms"], 120000)
                self.assertEqual(case["steps"], [{"run": "workload.sh apply " + case["id"], "commit": True}])
                review = case["port_review"]
                self.assertEqual(review["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")
                self.assertEqual(review["source_tag_object"], "ae3310fada4a1fe35cb99ab02270b7538a0d03f7")
                for name, wanted in review["files"].items():
                    self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), wanted)


if __name__ == "__main__":
    unittest.main()

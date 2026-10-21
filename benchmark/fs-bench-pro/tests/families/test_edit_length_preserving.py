"""Check the POSIX port against the frozen SDK scenario and payload algebra."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "benchmark/fs-bench-pro/families/edit_length_preserving/family.json"
FLAGS = ("--cfg", "aes_armv8", "--cfg", "polyval_armv8", "--cfg", "chacha20_force_neon",
         "-C", "target-feature=+aes,+sha2")


class OriginalSdkScenarios(unittest.TestCase):
    def test_complete_original_plans_payloads_and_fixture_hashes_match(self):
        # The exporter calls only original std-only metadata/byte self-checks.
        # It links no retired product and executes no workload, Store or mount.
        original = ROOT / "benchmark/fs-bench-pro/workload/main.rs"
        source = """#[allow(dead_code)]
#[path = SOURCE]
mod reference;
fn main() {
    reference::edit_length_preserving::self_check().unwrap();
    print!("{}", reference::sdk_edit_common::registry_tsv(&reference::edit_length_preserving::registry()));
    for index in [0, 1, 2, 5] {
        eprintln!("{}\t{}", reference::sdk_edit_common::PREPARED_SIZES[index], reference::sdk_edit_common::FIXTURE_SHA256[index]);
    }
}
""".replace("SOURCE", json.dumps(str(original)))
        (ROOT / "core/target").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="edit-preserving-registry-", dir=ROOT / "core/target") as tmp:
            path, binary = Path(tmp) / "registry.rs", Path(tmp) / "registry"
            path.write_text(source)
            compiled = subprocess.run(["rustup", "run", "1.85.1", "rustc", "--edition=2021", *FLAGS,
                                       str(path), "-o", str(binary)], cwd=ROOT,
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            output = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(output.returncode, 0, output.stderr)
        rows = list(csv.DictReader(io.StringIO(output.stdout), delimiter="\t"))
        family = json.loads(FAMILY.read_text())
        cases = family["cases"]
        self.assertEqual(len(rows), 12)
        by_id = {row["scenario_id"]: row for row in rows}
        rows = [by_id[case["id"]] for case in cases]
        self.assertEqual(len(rows), 5)
        self.assertEqual(hashlib.sha256(output.stdout.encode()).hexdigest(),
                         "daa3bcb8ba94da6dc28f7ca87dc2b27612c9988cf42fe5398cdddb3a5b386324")
        hashes = dict(line.split("\t", 1) for line in output.stderr.splitlines())
        review = cases[0]["port_review"]
        for path, wanted in review["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), wanted)
            frozen = subprocess.check_output(["git", "show", "reference-v0.1.6-final:" + path], cwd=ROOT)
            self.assertEqual(hashlib.sha256(frozen).hexdigest(), wanted)
        for path, wanted in review["retired_source_reads"].items():
            self.assertFalse((ROOT / path).exists())
            frozen = subprocess.check_output(["git", "show", "reference-v0.1.6-final:" + path], cwd=ROOT)
            self.assertEqual(hashlib.sha256(frozen).hexdigest(), wanted)
        for row, case in zip(rows, cases):
            with self.subTest(case=case["id"]):
                self.assertEqual({k: str(v) for k, v in case["sdk_scenario"].items()}, row)
                self.assertEqual(case["fixture"]["bytes"], int(row["fixture_bytes"]))
                self.assertEqual(case["fixture"]["content_sha256"], hashes[row["fixture_bytes"]])
                self.assertEqual(case["fixture"]["directory_mode"], 0o750)
                self.assertEqual(case["fixture"]["file_mode"], 0o640)
                self.assertEqual(case["fixture"]["mtime_seconds"], 1700000000)
                self.assertEqual(case["expected_commit"], "Committed")
                review = case["port_review"]
                self.assertEqual(review["source_commit"], "d296981ace76fe751bebf00dee52818fe18a3eef")
                self.assertEqual(review["source_tag_object"], "ae3310fada4a1fe35cb99ab02270b7538a0d03f7")


if __name__ == "__main__":
    unittest.main()

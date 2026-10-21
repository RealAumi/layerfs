"""Frozen capped-splice contract: membership, original byte identities and limits."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/edit_length_changing_capped"
FROZEN = ROOT / "benchmark/fs-bench-pro/families/edit_length_changing_capped/mod.rs"
MASK = (1 << 64) - 1


def original_replacement(seed, length):
    output = bytearray()
    while len(output) < length:
        seed = (seed + 0x9E3779B97F4A7C15) & MASK
        value = ((seed ^ (seed >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK
        output.extend((value ^ (value >> 31)).to_bytes(8, "little"))
    return bytes(output[:length])


class CappedSplices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((FAMILY / "family.json").read_text())["cases"]

    def test_original_five_capped_ids_and_byte_equations(self):
        operations = ["insert-middle-4k", "append-tail-4k", "prepend-head-4k",
                      "replace-grow-middle-2k-to-4k", "zero-extend-tail-4k"]
        self.assertEqual(len(self.cases), 5)
        for index, (row, operation) in enumerate(zip(self.cases, operations)):
            scenario = row["sdk_scenario"]
            fixture_bytes = 524285952 if index == 3 else 524283904
            identifier = f"{operation}-input-{fixture_bytes}b-result-500mib-ops-1-capped-v1"
            self.assertEqual(row["id"], identifier)
            self.assertEqual(row["v016_case"], identifier)
            self.assertEqual(scenario["scenario_id"], identifier)
            self.assertEqual(scenario["operation_key"], operation)
            self.assertEqual(scenario["fixture_bytes"], fixture_bytes)
            self.assertEqual(scenario["start"], [fixture_bytes // 2, fixture_bytes, 0,
                                               fixture_bytes // 2 - 1024, fixture_bytes][index])
            self.assertEqual(scenario["delete_len"], 2048 if index == 3 else 0)
            self.assertEqual(scenario["replacement_len"], 4096)
            self.assertEqual(scenario["final_bytes"], 524288000)
            self.assertEqual(fixture_bytes - scenario["delete_len"] + 4096, 524288000)
            self.assertEqual(row["fixture"]["recipe"], identifier)
            self.assertEqual(row["fixture"]["logical_bytes"], fixture_bytes)

    def test_replacement_hashes_plan_and_original_registry_manifest(self):
        columns = ["family_id", "scenario_id", "operation_key", "fixture_bytes", "start",
                   "delete_len", "replacement_kind", "replacement_len", "payload_seed",
                   "payload_sha256", "final_bytes", "plan_sha256"]
        transcript = "\t".join(columns) + "\n"
        original = FROZEN.read_text()
        for row in self.cases:
            scenario = row["sdk_scenario"]
            replacement = (bytes(4096) if scenario["replacement_kind"] == "zero"
                           else original_replacement(scenario["payload_seed"], 4096))
            self.assertEqual(hashlib.sha256(replacement).hexdigest(), scenario["payload_sha256"])
            plan = (b"layerfs/fs-bench-pro/sdk-file-edit-plan/v1\0"
                    + scenario["family_id"].encode() + b"\0" + scenario["scenario_id"].encode()
                    + b"\0" + struct.pack(">QQQ", scenario["fixture_bytes"], scenario["start"],
                                           scenario["delete_len"])
                    + (b"Z" if scenario["replacement_kind"] == "zero" else b"I")
                    + struct.pack(">Q", 4096) + bytes.fromhex(scenario["payload_sha256"]))
            self.assertEqual(hashlib.sha256(plan).hexdigest(), scenario["plan_sha256"])
            self.assertIn('"' + scenario["plan_sha256"] + '"', original)
            transcript += "\t".join(str(scenario[column]) for column in columns) + "\n"
        self.assertEqual(hashlib.sha256(transcript.encode()).hexdigest(),
                         "a1dab17cf1a4a01b19322c8651ade025f64621f67848b59bcbc7e6c9fa2e3c2e")

    def test_fixture_metadata_review_pins_and_declared_route_differences(self):
        pinned = subprocess.check_output(
            ["git", "rev-parse", "reference-v0.1.6-final^{commit}"], cwd=ROOT, text=True
        ).strip()
        original = FROZEN.read_text()
        for row in self.cases:
            self.assertEqual(row["status"], "ported")
            self.assertEqual(row["fixture"]["profile"], "sdk-edit-standard-content-capped-prefix-v1")
            self.assertEqual(row["fixture"]["seed"], 1)
            self.assertEqual(row["fixture"]["generator_seed"], 0x4C41594552465331)
            self.assertEqual(row["fixture"]["files"], 1)
            self.assertEqual(row["fixture"]["entries"], 2)
            self.assertEqual(row["fixture"]["root_mode"], 0o750)
            self.assertEqual(row["fixture"]["file_mode"], 0o640)
            self.assertEqual(row["fixture"]["mtime_seconds"], 1700000000)
            self.assertEqual(row["fixture"]["mtime_nanoseconds"], 0)
            self.assertIn('"' + row["fixture"]["payload_sha256"] + '"', original)
            self.assertEqual(row["reference"], {})
            self.assertEqual(row["port_review"]["source_commit"], pinned)
            for name, digest in row["port_review"]["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
            self.assertTrue(any("P-3" in difference for difference in row["differences"]))
            self.assertIn("retired canonical encoding", row["oracle"]["omissions"])
            self.assertIn("canonical inode continuity", row["oracle"]["scope"])
            self.assertIn("untouched payload-ID/source-offset retention", row["oracle"]["scope"])
            self.assertIn("exhaustive current canonical inode-table membership", row["oracle"]["scope"])

    def test_original_limits_and_single_edit_commit_schedule(self):
        for row in self.cases:
            self.assertEqual(row["steps"], [{"run": "workload.sh apply " + row["id"], "commit": True}])
            self.assertEqual(row["expected_commit"], "Committed")
            self.assertEqual(row["cache_class"], "B")
            self.assertEqual(row["budget"]["command_ms"], 15000)
            self.assertEqual(row["budget"]["verifier_ms"], 45000)
            self.assertEqual(row["budget"]["operation_watchdog_ms"], 120000)
            self.assertEqual(row["budget"]["verification_hard_watchdog_ms"], 59000)
            self.assertEqual(row["budget"]["historical_edit_commit_end_watchdog_ms"], 2000)
            self.assertEqual(row["budget"]["commit_watchdog_ms"], 2000)


if __name__ == "__main__":
    unittest.main()

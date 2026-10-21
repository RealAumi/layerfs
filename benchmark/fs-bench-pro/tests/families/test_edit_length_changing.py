"""Qualify the complete original SDK plan transcription before POSIX sampling."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/edit_length_changing"
FIELDS = ("family_id", "scenario_id", "operation_key", "fixture_bytes", "start", "delete_len",
          "replacement_kind", "replacement_len", "payload_seed", "payload_sha256", "final_bytes", "plan_sha256")
FROZEN_REGISTRY = "f59a1a68a19b95e1dcc8e6e5e273c7279c69fca373adca9980a9a9ffbd9fa517"


def replacement(seed, length):
    state = seed
    output = bytearray()
    mask = (1 << 64) - 1
    while len(output) < length:
        state = (state + 0x9e3779b97f4a7c15) & mask
        z = ((state ^ (state >> 30)) * 0xbf58476d1ce4e5b9) & mask
        z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & mask
        output.extend((z ^ (z >> 31)).to_bytes(8, "little"))
    return output[:length]


class LengthChanging(unittest.TestCase):
    def setUp(self):
        self.family = json.loads((FAMILY / "family.json").read_text())

    def test_twenty_kept_plans_preserve_original_payload_and_plan_digests(self):
        rows = self.family["cases"]
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({r["id"] for r in rows}), 20)
        tsv = "\t".join(FIELDS) + "\n"
        for row in rows:
            plan = row["sdk_scenario"]
            self.assertEqual(row["id"], plan["scenario_id"])
            self.assertEqual(plan["family_id"], "edit_length_changing")
            self.assertEqual(plan["final_bytes"], plan["fixture_bytes"] - plan["delete_len"] + plan["replacement_len"])
            self.assertNotEqual(plan["fixture_bytes"], plan["final_bytes"])
            self.assertEqual(row["fixture"]["logical_bytes"], plan["fixture_bytes"])
            logical = (bytes(plan["replacement_len"]) if plan["replacement_kind"] == "zero"
                       else replacement(plan["payload_seed"], plan["replacement_len"]))
            self.assertEqual(hashlib.sha256(logical).hexdigest(), plan["payload_sha256"])
            data = (b"layerfs/fs-bench-pro/sdk-file-edit-plan/v1\0" + plan["family_id"].encode() + b"\0"
                    + plan["scenario_id"].encode() + b"\0"
                    + struct.pack(">QQQ", plan["fixture_bytes"], plan["start"], plan["delete_len"])
                    + (b"Z" if plan["replacement_kind"] == "zero" else b"I")
                    + struct.pack(">Q", plan["replacement_len"]) + bytes.fromhex(plan["payload_sha256"]))
            self.assertEqual(hashlib.sha256(data).hexdigest(), plan["plan_sha256"])
            tsv += "\t".join(str(plan[field]) for field in FIELDS) + "\n"
        self.assertEqual(hashlib.sha256(tsv.encode()).hexdigest(), "66b6ecced2f74f69d2fe5bcdaddf6dd86f1d99531a03623402ff6159db96e88d")
        self.assertEqual(self.family["original_registry_sha256"], FROZEN_REGISTRY)

    def test_existing_capped_inputs_metadata_and_source_commit_are_preserved(self):
        capped = [r for r in self.family["cases"] if "500mib-result-capped-v2" in r["id"]]
        self.assertEqual(len(capped), 2)
        self.assertEqual({r["sdk_scenario"]["fixture_bytes"] for r in capped}, {524283904})
        self.assertEqual({r["sdk_scenario"]["final_bytes"] for r in capped}, {524288000})
        commit = subprocess.check_output(["git", "rev-parse", "reference-v0.1.6-final^{}"], cwd=ROOT, text=True).strip()
        tag = subprocess.check_output(["git", "rev-parse", "reference-v0.1.6-final"], cwd=ROOT, text=True).strip()
        for row in self.family["cases"]:
            self.assertEqual(row["port_review"]["source_commit"], commit)
            self.assertEqual(row["port_review"]["source_tag_object"], tag)
            for name, digest in row["port_review"]["files"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
            self.assertEqual(row["status"], "ported")
            self.assertEqual(row["expected_commit"], "Committed")
            self.assertEqual(row["steps"], [{"run": "workload.sh apply " + row["id"], "commit": True}])
            self.assertEqual(row["fixture"]["generator_seed"], 0x4c41594552465331)
            self.assertEqual((row["fixture"]["directory_mode"], row["fixture"]["file_mode"]), (0o750, 0o640))
            self.assertEqual(row["fixture"]["mtime_seconds"], 1700000000)
            self.assertEqual(row["budget"], {"command_ms": 15000, "verifier_ms": 45000,
                                           "operation_watchdog_ms": 120000, "verification_hard_watchdog_ms": 59000})


if __name__ == "__main__":
    unittest.main()

"""Case membership comes from the frozen definitions, not release CSV counts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


bench = module("bench", BENCH / "bench.py")
identity = module("identity", BENCH / "engine/identity.py")


class Catalogue(unittest.TestCase):
    def test_every_active_contract_case_and_family_is_present(self):
        reference = identity.reference_catalogue(ROOT / "core/target/fs-bench-pro-catalogue")
        actual = bench.catalogue()
        selection = json.loads((ROOT / "core/docs/issues/319/checks/benchmark-simplification.json").read_text())
        removed = {(row["family"], row["case"]) for row in selection["removed"]}
        self.assertEqual(len(actual), 160)  # 157 active plus three owner-set-aside histories.
        self.assertEqual(len({r["id"] for r in actual}), 160)
        self.assertEqual({(r["family"], r["id"]) for r in actual},
                         {(r["family"], r["case"]) for r in reference if r["family"] != "workspace_reliability" and (r["family"], r["case"]) not in removed})
        families = {p.name for p in (ROOT / "benchmark/fs-bench-pro/families").iterdir() if p.is_dir()}
        self.assertEqual(len(families), 25)
        self.assertEqual({r["family"] for r in actual}, families - {"workspace_reliability"})
        self.assertEqual(len({r["family"] for r in actual}), 24)
        self.assertEqual(len([r for r in actual if r["family"] == "repository_history"]), 3)
        for row in actual:
            original = {k: v for k, v in row.items() if k != "family"}
            digest = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(digest, selection["preserved_rows"][row["family"]][row["id"]])
            self.assertEqual(row["id"], row["v016_case"])
            self.assertIn(row["status"], ("pending", "ported", "not-applicable"))
            if row["status"] == "not-applicable":
                self.assertTrue(row.get("reason"))

    def test_two_tiers_cover_exactly_the_selected_cases_and_keep_capped_oracles(self):
        everyday, heavy = bench.catalogue("everyday"), bench.catalogue("heavy")
        self.assertEqual((len(everyday), len(heavy)), (108, 49))
        keys = [(row["family"], row["id"]) for row in everyday + heavy]
        self.assertEqual(len(set(keys)), 157)
        self.assertEqual(set(keys), {(row["family"], row["id"]) for row in bench.catalogue()
                                     if row["family"] != "repository_history"})
        self.assertEqual(sum(row["family"] == "edit_length_changing_capped" for row in heavy), 5)
        self.assertFalse(any(row["family"] == "edit_length_changing_capped" for row in everyday))
        with self.assertRaises(ValueError):
            bench.catalogue("undeclared")

    def test_python_wrapper_profiles_match_the_original_registry(self):
        original = module("repository_history", ROOT / "benchmark/fs-bench-pro/shared/repository_history.py")
        expected = {(row["scenario"], row["profile"], row["state_count"]) for row in original.registry()}
        actual = {(r["id"], r["registry"]["kind"], int(r["registry"]["tier"]))
                  for r in bench.catalogue() if r["family"] == "repository_history"}
        self.assertEqual(actual, expected)
        small = [r for r in bench.catalogue() if r["family"] == "small_file_delta_smoke"]
        self.assertEqual([r["id"] for r in small], ["small-file-delta-10x30-v1"])

    def test_list_runs_without_a_product_or_build(self):
        result = subprocess.run(["python3", "-B", str(BENCH / "bench.py"), "list", "--json"],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), bench.catalogue())


if __name__ == "__main__":
    unittest.main()

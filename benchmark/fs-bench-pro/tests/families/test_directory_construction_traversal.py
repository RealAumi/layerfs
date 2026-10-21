"""Original directory selection, independent fixture algebra and proof contracts."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import unittest

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parents[1]
FAMILY = BENCH / "families/directory_construction_traversal"
KINDS = ("directory-construct", "directory-metadata-scan", "directory-content-scan")
TIERS = (1, 100, 500)
DEPTHS = (1, 4, 2, 8, 3, 10, 5, 7, 6, 9)
SOURCE = "d296981ace76fe751bebf00dee52818fe18a3eef"
TAG_OBJECT = "ae3310fada4a1fe35cb99ab02270b7538a0d03f7"
COUNTS = {
    1: (50, 134, 184, 1, 186),
    100: (2000, 143, 2143, 550, 2694),
    500: (5000, 158, 5158, 2750, 7909),
}


def fixture_paths(tier):
    """Independent path-only census; creates no fixture or filesystem objects."""
    shards = tier if tier <= 10 else {100: 10, 500: 25}[tier]
    ordinals = (list(range(32)) + list(range(64, 80)) + [128, 199]
                if tier <= 10 else list(range(200)))
    directories, files = {".", "dest"}, set()
    for shard in range(shards):
        for ordinal in ordinals:
            if ordinal < 64:
                path = f"wide/s{shard:03}-f{ordinal:03}.dat"
            elif ordinal < 199:
                path = f"regular/s{shard:03}/f{ordinal:03}.dat"
            else:
                spine = "/".join(f"d{depth:03}" for depth in range(1, 129))
                path = f"spine/{spine}/s{shard:03}.dat"
            files.add(path)
            parent = PurePosixPath(path).parent
            while str(parent) != ".":
                directories.add(str(parent))
                parent = parent.parent
    return directories, files


class DirectoryConstructionTraversal(unittest.TestCase):
    def setUp(self):
        self.family = json.loads((FAMILY / "family.json").read_text())

    def test_exact_original_selection_and_fixture_census(self):
        expected = [f"{kind}-{tier}-" + ("compact-v2" if tier <= 10 else "mixed-v4")
                    for kind in KINDS for tier in TIERS]
        rows = self.family["cases"]
        self.assertEqual(self.family["family"], "directory_construction_traversal")
        self.assertEqual(self.family["engine"], "workspace")
        self.assertEqual([row["id"] for row in rows], expected)
        self.assertEqual(len({row["id"] for row in rows}), 9)
        for row in rows:
            kind, tier = row["registry"]["kind"], int(row["registry"]["tier"])
            construct = kind == "directory-construct"
            files, dirs, paths, added, final = COUNTS[tier]
            actual_dirs, actual_files = fixture_paths(tier)
            self.assertEqual((len(actual_files), len(actual_dirs),
                              len(actual_files) + len(actual_dirs)), (files, dirs, paths))
            fixture = row["fixture"]
            self.assertEqual(fixture["recipe"], row["id"])
            self.assertEqual(fixture["seed"], 1)
            self.assertEqual(fixture["profile"], "ordinary-low-tier-compact-v2"
                             if tier <= 10 else "workspace-mixed-v4")
            self.assertEqual((fixture["regular_files"], fixture["directories"], fixture["paths"]),
                             (files, dirs + int(construct), paths + int(construct)))
            self.assertEqual(fixture["logical_bytes"], tier * 1048576)
            self.assertEqual((fixture["directory_mode"], fixture["file_mode"],
                              fixture["mtime_seconds"], fixture["mtime_nanoseconds"]),
                             (0o750, 0o640, 1700000000, 0))
            model = row["operation_model"]
            self.assertEqual(model["final_paths"], final if construct else paths)
            self.assertEqual(model["final_regular_files"], files)
            self.assertEqual(model["final_logical_bytes"], fixture["logical_bytes"])
            if construct:
                self.assertEqual(tuple(model["depth_cycle"]), DEPTHS)
                self.assertEqual(model["added_directories"], added)
                self.assertEqual(sum(DEPTHS[k % 10] for k in range(tier)), added)
                self.assertEqual(model["rank_domain"], "directory-construction")
                self.assertEqual(model["chain_count"], tier)
                self.assertEqual(model["rank_candidates"], 500)
                self.assertEqual(model["compact_rank_filters_ordinals_below_tier"], tier <= 10)

    def test_original_semantic_counts_and_unchanged_limits(self):
        for row in self.family["cases"]:
            kind, tier = row["registry"]["kind"], int(row["registry"]["tier"])
            construct = kind == "directory-construct"
            files, _, paths, _, _ = COUNTS[tier]
            counts = ({"completed_chain_count": tier} if construct else {
                "visited_path_count": paths, "visited_file_count": files,
                "directory_entry_count": paths - 1,
            })
            if kind == "directory-content-scan":
                counts["completed_read_bytes"] = tier * 1048576
                self.assertEqual(row["operation_model"]["read_scratch_bytes"], 1048576)
            self.assertEqual(row["original_operation_counts"], counts)
            self.assertEqual(row["expected_commit"], "Committed" if construct else "UpToDate")
            self.assertEqual(row["status"], "ported")
            self.assertEqual(row["steps"], [{"run": "workload.sh apply " + row["id"], "commit": True}])
            self.assertEqual(row["budget"], {"command_ms": 15000, "verifier_ms": 45000,
                                           "operation_watchdog_ms": 120000,
                                           "verification_hard_watchdog_ms": 59000})
            self.assertIs(row["original_ordinary_guards"], True)
            guard = row["original_resource_guards"]
            self.assertEqual((guard["container_cpus"], guard["container_memory_bytes"],
                              guard["container_memory_swap_bytes"], guard["container_pids_limit"]),
                             (2, 2147483648, 2147483648, 256))
            self.assertEqual((guard["main_store_logical_bytes_max"],
                              guard["main_store_allocated_bytes_max"]),
                             (4294967296, 4294967296))
            self.assertIn("main Store file only", guard["store_scope"])
            self.assertEqual(row["cache_class"], "B")
            self.assertEqual(row["cache_contract"]["all_paid_backing_metadata_sqlite_phase_evidence"],
                             "UNAVAILABLE")
            self.assertIn("INELIGIBLE under strict H-5", row["cache_contract"]["numeric_result"])
            self.assertIn("exhaustive current inode-table membership", row["oracle"]["scope"])
            self.assertIn("sampled", row["oracle"]["omissions"])
            self.assertEqual(row["reference"]["release"], "0.1.5")

    def test_review_hashes_match_frozen_recovery_source_and_shell_route(self):
        self.assertEqual(subprocess.check_output(
            ["git", "rev-parse", "reference-v0.1.6-final^{commit}"], cwd=ROOT, text=True).strip(), SOURCE)
        self.assertEqual(subprocess.check_output(
            ["git", "rev-parse", "reference-v0.1.6-final"], cwd=ROOT, text=True).strip(), TAG_OBJECT)
        review = self.family["cases"][0]["port_review"]
        for name, digest in review["files"].items():
            current = (ROOT / name).read_bytes()
            frozen = subprocess.check_output(["git", "show", SOURCE + ":" + name], cwd=ROOT)
            self.assertEqual(current, frozen, name)
            self.assertEqual(hashlib.sha256(current).hexdigest(), digest, name)
        for row in self.family["cases"]:
            self.assertEqual(row["port_review"]["source_commit"], SOURCE)
            self.assertEqual(row["port_review"]["source_tag_object"], TAG_OBJECT)
            self.assertEqual(row["port_review"]["files"], review["files"])
        script = (FAMILY / "workload.sh").read_text()
        self.assertIn('writer=${WORKLOAD_WRITER:-/code/writers/workload}', script)
        self.assertIn('workspace-apply "$2" 1 0 performance', script)
        self.assertIn('workspace-verify-tree "$2" 1 1', script)
        self.assertNotIn("SDK", script)
        self.assertEqual((FAMILY / "workload.sh").stat().st_mode & 0o777, 0o755)


if __name__ == "__main__":
    unittest.main()

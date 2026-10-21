"""A supplemental census binds the old root without mutating old evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures, project, receipts


class MembershipAudit(unittest.TestCase):
    def test_census_uses_an_independent_copy_and_rejects_a_different_root(self):
        for observed_root, status in (("original-root", "PASS"), ("wrong-root", "FAIL")):
            with self.subTest(observed_root=observed_root), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                run = root / "old-run"
                old_folder = run / "case"
                store = old_folder / "graph-store/store.sqlite"
                store.parent.mkdir(parents=True)
                store.write_bytes(b"original closed Store")
                receipts.manifest(old_folder)
                case = {"id": "case", "v016_case": "frozen-case", "fixture": {"recipe": "recipe"}}
                selection = {"family": "payload_create_read", "source_commit": "old-source", "cases": [case]}
                old = {"proof_status": "PASS", "custody": "KNOWN_STOP", "cleanup": "Gone",
                       "product_tree": "product", "prepared": "prepared",
                       "commit": {"fields": {"root": "original-root"}}}
                prepared = {"provision": {"manifest": "old-manifest"}, "source_uid": 501, "source_gid": 20}
                build = {"socket": "/socket", "binaries": {"runtime": {"path": "runtime", "sha256": "binary"},
                                                            "daemon": {"path": "daemon"}}}
                def census(argv, folder, label, seconds, **options):
                    self.assertEqual(argv[1], "verify-membership")
                    copy = Path(argv[argv.index("--sealed") + 1])
                    self.assertNotEqual(copy, store)
                    self.assertEqual(copy.read_bytes(), store.read_bytes())
                    copy.write_bytes(b"Store lifecycle may modify this independent copy")
                    events = [{"event": "workspace_verified", "fields": {"root": observed_root}},
                              {"event": "finished"}]
                    (folder / "census.events.jsonl").write_text("\n".join(map(json.dumps, events)))
                    return {"status": "PASS"}
                with patch.object(project.identity, "ROOT", root), \
                        patch.object(project.identity, "source_identity", return_value={"product_tree": "product"}), \
                        patch.object(project.identity, "load_build", return_value=build), \
                        patch.object(project.receipts, "load_run", return_value=(selection, {"case": old})), \
                        patch.object(fixtures, "load", return_value=prepared), \
                        patch.object(project.receipts, "command", side_effect=census) as attempted:
                    result = project.audit_membership(run, "build", root / "benchmark-results/fs-bench-pro/audit")
                self.assertEqual(result["status"], status)
                self.assertEqual(result["samples"], 0)
                self.assertEqual(attempted.call_count, 1)
                self.assertEqual(store.read_bytes(), b"original closed Store")
                self.assertEqual(result["cases"][0]["original_store_sha256"], hashlib.sha256(store.read_bytes()).hexdigest())
                if status == "FAIL":
                    self.assertIn("root differs", result["cases"][0]["original_failure"])


if __name__ == "__main__":
    unittest.main()

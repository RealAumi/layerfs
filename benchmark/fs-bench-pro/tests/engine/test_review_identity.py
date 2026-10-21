"""An annotated recovery tag must not masquerade as its source commit."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures, identity, project


class ReviewIdentity(unittest.TestCase):
    def parity(self, kind, source_commit, tag_object, directory):
        family = "init_namespace" if kind == "init" else "payload_create_read"
        case = {"id": "review-case", "v016_case": "review-case",
                "fixture": {"recipe": "review-case"}, "oracle": {}, "differences": [],
                "port_review": {"source_commit": source_commit,
                                "source_tag_object": tag_object, "files": {}}}
        registered = [{"family": family, "case": case["id"],
                       "fixture_files": "1", "fixture_bytes": "2"}]
        prepared = {"family": family, "case": case["id"],
                    "fixture": {"files": 1, "logical_bytes": 2}, "expectation": {},
                    "original_verification": {},
                    "native_verification": {"fixture": {"verification_status": "pass"}}}
        method = project.parity_namespace if kind == "init" else project.parity_workspace
        with patch.object(identity, "reference_catalogue", return_value=registered), \
                patch.object(fixtures, "load", return_value=prepared):
            return method({"family": family, "cases": [case]}, directory, Path(directory) / kind)

    def test_annotated_tag_is_rejected_as_source_commit_by_both_routes(self):
        tag = identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final")
        self.assertEqual(identity.git(identity.ROOT, "cat-file", "-t", tag), "tag")
        for kind in ("init", "workspace"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, "pin"):
                    self.parity(kind, tag, tag, directory)

    def test_peeled_commit_and_exact_tag_object_are_admitted_by_both_routes(self):
        tag = identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final")
        commit = identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final^{commit}")
        self.assertEqual(identity.git(identity.ROOT, "cat-file", "-t", commit), "commit")
        for kind in ("init", "workspace"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                self.assertEqual(self.parity(kind, commit, tag, directory)["status"], "PASS")

    def test_all_ported_review_metadata_preserves_both_distinct_objects(self):
        tag = identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final")
        commit = identity.git(identity.ROOT, "rev-parse", "reference-v0.1.6-final^{commit}")
        for path in (BENCH / "families").glob("*/family.json"):
            for case in json.loads(path.read_text())["cases"]:
                if case["status"] == "ported":
                    with self.subTest(family=path.parent.name, case=case["id"]):
                        self.assertEqual(case["port_review"]["source_commit"], commit)
                        self.assertEqual(case["port_review"]["source_tag_object"], tag)


if __name__ == "__main__":
    unittest.main()

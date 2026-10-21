"""Workspace parity retains every case without weakening any original guard."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import identity, project, receipts


class ParityFailures(unittest.TestCase):
    def setup_family(self, root):
        source = root / "reviewed.rs"
        source.write_text("reviewed operation source\n")
        cases, registered, prepared = [], [], {}
        for index in range(3):
            name = f"case-{index}"
            cases.append({"id": name, "v016_case": name, "fixture": {"recipe": name},
                          "oracle": {"scope": "original scope"}, "differences": [],
                          "port_review": {"source_commit": "commit", "source_tag_object": "tag",
                                          "files": {"reviewed.rs": identity.sha256(source)}}})
            registered.append({"family": "mixed_load_bearing", "case": name})
            folder = root / "prepared" / name
            folder.mkdir(parents=True)
            store, manifest = folder / "store", folder / "installed.manifest"
            store.write_bytes(b"external unit fixture Store seal")
            manifest.write_bytes(b"external unit fixture installed manifest seal")
            prepared[name] = {"schema": "fs-bench-pro-prepared-workspace-v1", "status": "PASS",
                              "recipe": name, "family": "mixed_load_bearing", "case": name,
                              "fixture": {"files": 1, "logical_bytes": 2}, "expectation": {},
                              "native_verification": {"fixture": {"verification_status": "pass"}},
                              "provision": {"sealed_store": str(store), "store_sha256": identity.sha256(store),
                                            "manifest": str(manifest), "manifest_sha256": identity.sha256(manifest)},
                              "helpers": {"root": str(folder), "files": {}}}
            self.seal(folder, prepared[name])
        return {"family": "mixed_load_bearing", "cases": cases}, registered, prepared

    def seal(self, folder, prepared):
        for name in ("prepared.json", "manifest.json"):
            path = folder / name
            if path.exists():
                path.unlink()
        receipts.write_new(folder / "prepared.json", prepared)
        receipts.manifest(folder)

    def parity(self, root, family, registered):
        def git(_root, *arguments):
            return "commit" if arguments[-1].endswith("^{commit}") else "tag"
        with patch.object(identity, "ROOT", root), \
                patch.object(identity, "reference_catalogue", return_value=registered), \
                patch.object(identity, "git", side_effect=git):
            return project.parity_workspace(family, root / "prepared", root / "parity")

    def retained_failure(self, root, family, registered):
        with self.assertRaises(Exception) as raised:
            self.parity(root, family, registered)
        self.assertTrue((root / "parity/parity.json").is_file(),
                        "a failed preparation must not discard the family's parity outcomes")
        failure = raised.exception
        self.assertIsInstance(failure, ValueError)
        result = json.loads((root / "parity/parity.json").read_text())
        self.assertEqual(failure.result, result)
        self.assertEqual(failure.output, (root / "parity").resolve())
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["samples"], 0)
        self.assertEqual([row["case"] for row in result["cases"]], ["case-0", "case-1", "case-2"])
        self.assertEqual([row["status"] for row in result["cases"]], ["PASS", "FAIL", "PASS"])
        receipts.verify_manifest(root / "parity")
        return failure, result["cases"][1]

    def test_missing_middle_preparation_retains_every_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            family, registered, _ = self.setup_family(root)
            (root / "prepared/case-1/prepared.json").unlink()
            failure, row = self.retained_failure(root, family, registered)
            self.assertEqual(row["error_type"], "FileNotFoundError")
            self.assertIn("prepared.json", row["reason"])
            self.assertIn(row["reason"], str(failure))

    def test_original_guards_keep_exact_failure_reasons_and_later_cases(self):
        variants = (
            ("membership", "frozen original case membership differs"),
            ("prepared-case", "original fixture was prepared for another case"),
            ("prepared-family", "original fixture was prepared for another case"),
            ("source-commit", "reviewed operation pin differs"),
            ("tag-object", "reviewed operation pin differs"),
            ("source-bytes", "reviewed original fixture/operation/oracle source changed"),
            ("native-check", "original complete native fixture/oracle check not passed"),
            ("store-seal", "sealed host Store changed"),
        )
        for kind, reason in variants:
            with self.subTest(guard=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                family, registered, prepared = self.setup_family(root)
                case = family["cases"][1]
                value = copy.deepcopy(prepared["case-1"])
                if kind == "membership":
                    registered.pop(1)
                elif kind == "prepared-case":
                    value["case"] = "another-case"
                elif kind == "prepared-family":
                    value["family"] = "another-family"
                elif kind == "source-commit":
                    case["port_review"]["source_commit"] = "tag"
                elif kind == "tag-object":
                    case["port_review"]["source_tag_object"] = "commit"
                elif kind == "source-bytes":
                    case["port_review"]["files"]["reviewed.rs"] = "0" * 64
                elif kind == "native-check":
                    value["native_verification"]["fixture"]["verification_status"] = "fail"
                else:
                    value["provision"]["store_sha256"] = "0" * 64
                self.seal(root / "prepared/case-1", value)
                failure, row = self.retained_failure(root, family, registered)
                self.assertEqual(row["error_type"], "ValueError")
                self.assertEqual(row["reason"], reason)
                self.assertIn(reason, str(failure))

    def test_all_pass_api_and_append_only_failure_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            family, registered, _ = self.setup_family(root)
            result = self.parity(root, family, registered)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["cases"]), 3)
            self.assertTrue(all(row["status"] == "PASS" for row in result["cases"]))
            receipts.verify_manifest(root / "parity")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            family, registered, _ = self.setup_family(root)
            (root / "prepared/case-1/prepared.json").unlink()
            self.retained_failure(root, family, registered)
            before = {path.name: path.read_bytes() for path in (root / "parity").iterdir()}
            with self.assertRaises(FileExistsError):
                self.parity(root, family, registered)
            self.assertEqual(before, {path.name: path.read_bytes() for path in (root / "parity").iterdir()})

    def test_catalogue_failure_remains_original_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            family, _, _ = self.setup_family(root)
            with patch.object(identity, "reference_catalogue", side_effect=RuntimeError("catalogue unavailable")):
                with self.assertRaisesRegex(RuntimeError, "catalogue unavailable"):
                    project.parity_workspace(family, root / "prepared", root / "parity")
            self.assertFalse((root / "parity/parity.json").exists())


if __name__ == "__main__":
    unittest.main()

"""Shared setup must retain full input integrity and exact producer invalidation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import prepared_inputs


class PreparedInputs(unittest.TestCase):
    def test_context_producer_supplies_checked_ordinary_initial_summary_without_regeneration(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(prepared_inputs, "CACHE", Path(temporary) / "inputs"):
            first, second, build = self.case("first"), self.case("second"), self.build()
            root = prepared_inputs.source_path(first, build)
            def generate(argv, output, label, seconds, **options):
                root.mkdir(); (root / "payload.bin").write_bytes(b"closed input")
                manifest = root.with_suffix(".manifest.tsv")
                manifest.write_text("workspace-independent-manifest-v1\n.\tdirectory\n"+
                    "payload.bin\tfile\n")
                out = output / (label + ".stdout")
                out.write_text(json.dumps({"case": "first", "role": "a", "step": 0, "seed": 1,
                    "manifest_sha256": prepared_inputs.identity.sha256(manifest), "recipe_sha256": "b" * 64}))
                return {"argv": argv, "stdout": str(out), "attempts": 1, "exit_code": 0}
            with patch.object(prepared_inputs.receipts, "command", side_effect=generate) as generated:
                one = prepared_inputs.make_initial(first, build,
                    ["writer", "materialize-context", "first", "a", "0", str(root)], Path(temporary) / "one")
                two = prepared_inputs.make_initial(second, build,
                    ["writer", "fixture", "second", str(root)], Path(temporary) / "two")
            self.assertEqual(generated.call_count, 1)
            self.assertEqual(one["fixture_digest"], two["fixture_digest"])
            self.assertEqual((two["files"], two["recipe_identity"], two["case"]), (1, "b" * 64, "second"))
            self.assertNotIn("fixture_digest", prepared_inputs.load_source(second, build)["fixture"])

    def case(self, name):
        return {"id": name, "v016_case": name, "sdk_scenario": {"fixture_bytes": 16},
                "fixture": {"recipe": name, "definition_source": "original", "generator_seed": 1,
                            "content_sha256": "a" * 64, "directory_mode": 0o750, "file_mode": 0o640,
                            "mtime_seconds": 1700000000, "mtime_nanoseconds": 0}}

    def build(self):
        return {"binaries": {name: {"sha256": str(i) * 64} for i, name in enumerate(
            ("namespace-writer", "workspace-writer", "workload-host", "edit-host"), 1)},
                "flags": "fixture test", "explicit_rustflags": None}

    def test_one_native_generation_serves_two_cases_and_keeps_original_producer(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(prepared_inputs, "CACHE", Path(temporary) / "inputs"):
            first, second, build = self.case("first"), self.case("second"), self.build()
            root = prepared_inputs.source_path(first, build)
            calls = []
            def generate(argv, output, label, seconds, **options):
                calls.append(argv)
                root.mkdir(); (root / "payload.bin").write_bytes(b"closed input")
                out = output / (label + ".stdout")
                out.write_text(json.dumps({"case": "first", "fixture_digest": "a" * 64}))
                return {"argv": argv, "stdout": str(out), "attempts": 1, "exit_code": 0}
            with patch.object(prepared_inputs.receipts, "command", side_effect=generate):
                one = prepared_inputs.make_initial(first, build, ["writer", "first", str(root)], Path(temporary) / "one")
                two = prepared_inputs.make_initial(second, build, ["writer", "second", str(root)], Path(temporary) / "two")
            self.assertEqual(len(calls), 1)
            self.assertEqual(one["case"], "first"); self.assertEqual(two["case"], "second")
            reuse = json.loads((Path(temporary) / "two/native-fixture-input.json").read_text())
            self.assertEqual((reuse["producer_case"], reuse["requested_case"], reuse["attempts"]), ("first", "second", 0))
            original = prepared_inputs.load_source(second, build)
            self.assertEqual(original["fixture"]["case"], "first")
            (root / "payload.bin").write_bytes(b"mutated input")
            with self.assertRaises(ValueError):
                prepared_inputs.load_source(second, build)

    def test_input_bytes_modes_generators_and_identity_cannot_alias(self):
        case, build = self.case("first"), self.build()
        original = prepared_inputs.native_key(case, build)
        for field, value in [("file_mode", 0o600), ("generator_seed", 2), ("content_sha256", "b" * 64)]:
            other = copy.deepcopy(case); other["fixture"][field] = value
            self.assertNotEqual(original, prepared_inputs.native_key(other, build))
        other = copy.deepcopy(case); other["sdk_scenario"]["fixture_bytes"] = 17
        self.assertNotEqual(original, prepared_inputs.native_key(other, build))
        other = copy.deepcopy(build); other["binaries"]["workspace-writer"]["sha256"] = "f" * 64
        self.assertNotEqual(original, prepared_inputs.native_key(case, other))

    def test_store_key_includes_product_builder_but_excludes_external_tests_and_docs(self):
        source = {"files": {"core/crates/product/src/lib.rs": "a", "core/crates/product/sql/schema.sql": "b",
                            "core/crates/product/Cargo.toml": "c", "core/Cargo.lock": "d",
                            "core/crates/product/tests/check.rs": "test", "core/crates/product/README.md": "doc"}}
        original = prepared_inputs.product_store_key(source)
        other = copy.deepcopy(source); other["files"]["core/crates/product/tests/check.rs"] = "new test"
        other["files"]["core/crates/product/README.md"] = "new doc"
        self.assertEqual(original, prepared_inputs.product_store_key(other))
        for name in ["core/crates/product/src/lib.rs", "core/crates/product/sql/schema.sql", "core/Cargo.lock"]:
            other = copy.deepcopy(source); other["files"][name] = "new producer"
            self.assertNotEqual(original, prepared_inputs.product_store_key(other))

    def test_incomplete_or_changed_input_is_retained_and_never_rebuilt(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(prepared_inputs, "CACHE", Path(temporary) / "inputs"):
            case, build = self.case("first"), self.build(); root = prepared_inputs.source_path(case, build)
            root.mkdir(parents=True)
            with patch.object(prepared_inputs.receipts, "command") as generated:
                with self.assertRaises(ValueError):
                    prepared_inputs.make_initial(case, build, ["writer", str(root)], Path(temporary) / "out")
                generated.assert_not_called()

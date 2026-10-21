"""One shared initial input, both preparation orders: the same ordinary view or a named-order refusal."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import fixtures

prepared_inputs = fixtures.prepared_inputs
# Both writers hash the same step-0 entries with workspace_common::recipe_identity;
# the retained receipts of this pair carry one value under the two field names.
RECIPE = "7" * 64
ORDINARY_VIEW = ("case", "seed", "files", "entries", "logical_bytes", "fixture_digest", "recipe_identity")


def declared(family, position):
    return json.loads((BENCH / "families" / family / "family.json").read_text())["cases"][position]


def tools(folder):
    result = {"socket": "mock-socket", "binaries": {}, "flags": "mock sealed inputs", "explicit_rustflags": None}
    for name in ("namespace-writer", "workspace-writer", "workload-host", "edit-host"):
        path = folder / name
        path.write_text("mocked sealed tool " + name)
        result["binaries"][name] = {"path": str(path), "sha256": fixtures.identity.sha256(path)}
    return result


def tree(root, data):
    """The complete tree and manifest either synthetic writer leaves beside its root."""
    root.mkdir(parents=True); (root / "payload.bin").write_bytes(data)
    manifest = root.with_suffix(".manifest.tsv")
    manifest.write_text("workspace-independent-manifest-v1\n.\tdirectory\t0\t755\t1700000000\t0\t-\n"
                        + f"payload.bin\tfile\t{len(data)}\t640\t1700000000\t0\t{hashlib.sha256(data).hexdigest()}\n")
    return manifest


def writers(calls):
    def command(argv, out, label, seconds, **options):
        calls.append(argv)
        output = Path(out) / (label + ".stdout")
        mode = argv[1]
        if mode == "fixture":
            _, _, name, destination = argv
            manifest = tree(Path(destination), b"shared initial")
            output.write_text(json.dumps({"case": name, "seed": 1, "files": 1, "entries": 2, "logical_bytes": 14,
                "fixture_digest": fixtures.identity.sha256(manifest), "recipe_identity": RECIPE}))
        elif mode == "materialize-context":
            _, _, name, role, step, destination = argv
            data = b"shared initial" if step == "0" else (role + step).encode()
            manifest = tree(Path(destination), data)
            scope = Path(destination).with_suffix(".scope.tsv")
            scope.write_text("original-m1-selective-scope-v1\n.\tdirectory\t0\t-\t-\t-\t-\t-\n")
            output.write_text(json.dumps({"case": name, "role": role, "step": int(step), "seed": 1,
                "manifest_sha256": fixtures.identity.sha256(manifest),
                "context_manifest_sha256": fixtures.identity.sha256(scope),
                "recipe_sha256": RECIPE if step == "0" else "8" * 64, "entries": 2, "logical_bytes": len(data)}))
        elif mode == "verify-context":
            output.write_text(json.dumps({"case": argv[2], "role": argv[3], "step": 0, "verification_status": "pass"}))
        elif mode == "verify-manifest":
            output.write_text("verification_status=pass\n")
        else:
            raise AssertionError("undeclared mocked tool invocation " + repr(argv))
        return {"argv": argv, "stdout": str(output), "status": "PASS", "exit_code": 0}
    return command


class SharedInitialOrder(unittest.TestCase):
    ordinary = declared("mixed_load_bearing", 4)
    context = declared("multi_workspace_development", 4)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        patcher = patch.object(prepared_inputs, "CACHE", self.folder / "inputs")
        patcher.start(); self.addCleanup(patcher.stop)
        self.build, self.calls = tools(self.folder), []
        patcher = patch.object(fixtures.receipts, "command", side_effect=writers(self.calls))
        patcher.start(); self.addCleanup(patcher.stop)
        self.current = {"source_commit": "mock-source", "source_tree": "mock-tree", "product_tree": "mock-product",
                        "files": {path: fixtures.identity.sha256(fixtures.identity.ROOT / path)
                                  for path in fixtures.CONTEXT_SOURCE_FILES}}

    def ordinary_view(self, name):
        output = self.folder / name; output.mkdir()
        source = prepared_inputs.source_path(self.ordinary, self.build)
        return prepared_inputs.make_initial(self.ordinary, self.build,
            [self.build["binaries"]["workspace-writer"]["path"], "fixture", self.ordinary["v016_case"], str(source)], output)

    def context_view(self, name):
        output = self.folder / name; output.mkdir()
        binding = fixtures.context_source_binding(self.context, self.current)
        return fixtures.prepare_context_native(self.context, output, self.build, binding)

    def initial_generations(self):
        return [argv[1] for argv in self.calls
                if argv[1] == "fixture" or argv[1] == "materialize-context" and argv[4] == "0"]

    def context_first(self, label):
        initial, _, _, states, recipe = self.context_view(label + "-context")
        ordinary = self.ordinary_view(label + "-ordinary")
        self.assertEqual(self.initial_generations(), ["materialize-context"])
        self.assertEqual((initial["role"], initial["recipe_identity"], len(states)), ("0", RECIPE, 4))
        self.assertEqual(recipe["input_reuse"]["producer_case"], self.context["id"])
        self.assertEqual(ordinary["case"], self.ordinary["v016_case"])
        self.assertEqual((ordinary["fixture_digest"], ordinary["recipe_identity"]),
                         (initial["manifest_sha256"], initial["recipe_sha256"]))
        return ordinary

    def ordinary_first(self, label):
        ordinary = self.ordinary_view(label + "-ordinary")
        home = prepared_inputs.source_path(self.context, self.build).parent
        sealed, invoked = fixtures.identity.sha256(home / "manifest.json"), len(self.calls)
        with self.assertRaises(ValueError) as refused:
            self.context_view(label + "-context")
        message = str(refused.exception)
        for part in ("Required order: prepare a context case", "before any ordinary case", self.context["id"],
                     "first produced by case " + self.ordinary["id"], "`fixture`", "recipe_sha256", str(home)):
            self.assertIn(part, message)
        # Refused before a tool, a reuse claim or any change to the closed input.
        self.assertEqual(len(self.calls), invoked)
        self.assertEqual([path.name for path in (self.folder / (label + "-context")).iterdir()], ["context-manifests"])
        self.assertEqual(fixtures.identity.sha256(home / "manifest.json"), sealed)
        target = self.folder / (label + "-prepared")
        with patch.object(fixtures.identity, "load_build", return_value=self.build), \
             patch.object(fixtures.identity, "source_identity", return_value=self.current), \
             patch.object(fixtures.project, "provision") as provision, \
             self.assertRaises(ValueError) as whole:
            fixtures.prepare_context_workspace({"family": "multi_workspace_development"}, self.context, target, "mock-build")
        self.assertEqual(str(whole.exception), message)
        self.assertFalse(target.exists()); provision.assert_not_called()
        # The ordinary cases keep their closed input: still one generation.
        self.assertEqual(self.ordinary_view(label + "-again"), ordinary)
        self.assertEqual(self.initial_generations(), ["fixture"])
        return ordinary

    def test_the_declared_pair_selects_one_shared_input(self):
        self.assertTrue(self.context.get("topology_schedule") and not self.ordinary.get("topology_schedule"))
        self.assertEqual(prepared_inputs.native_key(self.ordinary, self.build),
                         prepared_inputs.native_key(self.context, self.build))

    def test_context_first_serves_both_cases_from_one_generation(self):
        self.context_first("one")

    def test_ordinary_first_refuses_the_context_case_and_names_the_order(self):
        self.ordinary_first("one")

    def test_the_ordinary_view_does_not_depend_on_the_order(self):
        first = self.context_first("first")
        self.calls.clear()
        with patch.object(prepared_inputs, "CACHE", self.folder / "other-inputs"):
            second = self.ordinary_first("second")
        self.assertEqual({key: first[key] for key in ORDINARY_VIEW}, {key: second[key] for key in ORDINARY_VIEW})

    def test_a_context_summary_without_its_receipt_fields_is_refused_not_a_key_error(self):
        self.context_view("context")
        summary = prepared_inputs.source_path(self.context, self.build).parent / "input.json"
        record = json.loads(summary.read_text()); del record["fixture"]["recipe_sha256"]
        summary.write_text(json.dumps(record))
        with self.assertRaises(ValueError) as refused:
            prepared_inputs.require_context_producer(self.context, self.build)
        self.assertIn("its summary lacks recipe_sha256", str(refused.exception))


if __name__ == "__main__":
    unittest.main()

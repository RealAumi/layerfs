"""Build admission rejects dirty/untracked source before external operations."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import identity


class BuildIdentity(unittest.TestCase):
    def test_changed_edit_model_or_writer_refuses_an_old_build_before_binary_use(self):
        from engine import receipts
        for name in ("benchmark/fs-bench-pro/engine/recipes/edit_model.rs",
                     "benchmark/fs-bench-pro/writers/edit.rs"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                (folder / "build.json").write_text(json.dumps({"identity": {"files": {name: "old"}},
                                                               "binaries": {}}))
                with patch.object(receipts, "verify_manifest"), \
                        patch.object(identity, "source_identity", return_value={"files": {name: "changed"}}), \
                        patch.object(identity, "sha256", side_effect=AssertionError("cannot use old executable")):
                    with self.assertRaisesRegex(ValueError, "build inputs differ"):
                        identity.load_build(folder)

    def test_dirty_tracked_source_is_refused_before_hashing(self):
        with patch.object(identity, "git", return_value="core/crates/changed.rs"), \
                patch.object(identity, "sha256", side_effect=AssertionError("must not seal dirty input")):
            with self.assertRaisesRegex(ValueError, "commit the tracked source"):
                identity.source_identity()

    def test_an_untracked_source_cannot_enter_the_build(self):
        def git(root, *arguments):
            return "benchmark/fs-bench-pro/engine/unsealed.py" if arguments[0] == "ls-files" else ""
        with patch.object(identity, "git", side_effect=git):
            with self.assertRaisesRegex(ValueError, "untracked source"):
                identity.source_identity()

    def test_protected_handoff_is_recorded_without_becoming_compilation_input(self):
        protected = "core/docs/issues/307/PROMPT-R8-R9-NEXT-AGENT-20261010.md"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / protected).parent.mkdir(parents=True)
            (root / protected).write_text("retained handoff")
            def git(root, *arguments):
                if arguments[0] == "diff":
                    return ""
                if arguments[:2] == ("ls-files", "--others"):
                    return protected
                if arguments[0] == "ls-files":
                    return ""
                return "a" * 40
            with patch.object(identity, "git", side_effect=git):
                result = identity.source_identity(root)
            self.assertEqual(result["files"], {})
            self.assertEqual(result["excluded_untracked"][0]["path"], protected)
            self.assertEqual(len(result["excluded_untracked"][0]["sha256"]), 64)


class RuntimeBuildReuse(unittest.TestCase):
    def qualified(self):
        files = {"core/crates/content/src/lib.rs": "product", ".cargo/config.toml": "flags",
                 "benchmark/fs-bench-pro/runtime/src/main.rs": "old-runtime",
                 "benchmark/fs-bench-pro/writers/edit.rs": "writer",
                 "benchmark/fs-bench-pro/engine/recipes/workspace.rs": "recipe",
                 "benchmark/fs-bench-pro/workload/main.rs": "workload"}
        return {"schema": "fs-bench-pro-build-v1", "status": "PASS", "image": identity.IMAGE,
                "global_profile": "Disposable/WAL/OFF", "overlay_profile": "MEMORY/OFF/EXCLUSIVE",
                "construction_workers": 1, "explicit_rustflags": None,
                "durable": "NOT_RUN — disabled by owner until explicit reauthorization",
                "flags": ".cargo/config.toml ARM64 profile; explicit override recorded",
                "fuser_disposition": "OWNER-3's two passthrough refusals retained; no checker PASS claimed",
                "identity": {"files": files, "product_tree": "exact-product-tree", "source_clean": True},
                "binaries": {name: {"path": "/immutable/" + name, "sha256": "digest", "bytes": 123}
                             for name in identity.BINARY_KEYS}, "socket": "/original/socket"}

    def test_only_host_runtime_change_is_admitted(self):
        previous = self.qualified()
        before = {**previous["identity"], "files": {**previous["identity"]["files"],
                   "benchmark/fs-bench-pro/runtime/src/main.rs": "new-runtime"}}
        self.assertEqual(identity.reuse_runtime_inputs(before, previous, None),
                         ["benchmark/fs-bench-pro/runtime/src/main.rs"])
        for name in ("core/crates/content/src/lib.rs", ".cargo/config.toml",
                     "benchmark/fs-bench-pro/writers/edit.rs",
                     "benchmark/fs-bench-pro/engine/recipes/workspace.rs",
                     "benchmark/fs-bench-pro/workload/main.rs"):
            with self.subTest(name=name):
                changed = {**before, "files": {**before["files"], name: "changed"}}
                with self.assertRaisesRegex(ValueError, "compiled inputs differ"):
                    identity.reuse_runtime_inputs(changed, previous, None)

    def test_missing_binary_profile_image_flags_and_product_tree_are_refused(self):
        previous = self.qualified()
        for field, value in (("image", "other-image"), ("global_profile", "Durable"),
                             ("construction_workers", 2), ("explicit_rustflags", "other-flags"),
                             ("fuser_disposition", "PASS")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "profile, image, flags or disposition"):
                identity.reuse_runtime_inputs(previous["identity"], {**previous, field: value}, None)
        with self.assertRaisesRegex(ValueError, "nine sealed binary"):
            identity.reuse_runtime_inputs(previous["identity"], {**previous, "binaries": {}}, None)
        legacy = {name: value for name, value in previous["binaries"].items() if name != "workspace-linux"}
        with self.assertRaisesRegex(ValueError, "nine sealed binary"):
            identity.reuse_runtime_inputs(previous["identity"], {**previous, "binaries": legacy}, None)
        with self.assertRaisesRegex(ValueError, "product tree differs"):
            identity.reuse_runtime_inputs({**previous["identity"], "product_tree": "changed"}, previous, None)

    def test_sqlite_compile_flags_refuse_reuse_of_a_different_binary_arm(self):
        previous = self.qualified()
        flags = "-USQLITE_ENABLE_MEMORY_MANAGEMENT"
        with patch.dict(identity.os.environ, {"LIBSQLITE3_FLAGS": flags}):
            with self.assertRaisesRegex(ValueError, "profile, image, flags or disposition"):
                identity.reuse_runtime_inputs(previous["identity"], previous, None)
            previous["explicit_sqlite_flags"] = flags
            self.assertEqual(identity.reuse_runtime_inputs(previous["identity"], previous, None), [])

    def test_failed_host_build_retains_declared_reuse_without_a_successful_seal(self):
        from engine import receipts
        previous = self.qualified()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            original, output = base / "original", base / "fresh"
            original.mkdir()
            (original / "build.json").write_text(json.dumps(previous))
            (original / "manifest.json").write_text("original-evidence")
            with patch.object(identity, "source_identity", return_value=previous["identity"]), \
                    patch.object(identity, "original_build_evidence"), \
                    patch.object(identity, "docker_socket", return_value=previous["socket"]), \
                    patch.object(receipts, "command", side_effect=RuntimeError("compiler failed")) as attempted:
                with self.assertRaisesRegex(RuntimeError, "compiler failed"):
                    identity.build_runtime(output, original, base)
            self.assertEqual(attempted.call_count, 1)
            self.assertTrue((output / "source-before.json").exists())
            self.assertTrue((output / "reuse-scope.json").exists())
            self.assertFalse((output / "build.json").exists())
            self.assertEqual(json.loads((original / "build.json").read_text()), previous)


    def test_tampered_reused_binary_is_refused_even_with_valid_source_receipts(self):
        from engine import receipts
        previous = self.qualified()
        linux = {"status": "PASS"}
        refusal = {"exit_code": 1}
        previous.update(builds=[linux], fuser_check=refusal)
        files = previous["identity"]["files"]
        evidence = {
            "build.json": json.dumps(previous),
            "source-before.json": json.dumps(previous["identity"]),
            "source-after.json": json.dumps(previous["identity"]),
            "container-source.sha256": "".join(d + "  /work/" + n + "\n" for n, d in files.items()),
            "linux-release.completion.json": json.dumps(linux),
            "linux-release.stdout": "".join("/work/" + n + ": OK\n" for n in files) * 2,
            "linux-create.attempt.json": json.dumps({"argv": [identity.IMAGE, identity.shlex.join(identity.ARM64_FLAGS)]}),
            "image.stdout": identity.IMAGE,
            "fuser-integrity.completion.json": json.dumps(refusal),
            "fuser-integrity.stdout": json.dumps({"errors": sorted(identity.FUSER_REFUSALS)}),
        }
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name, content in evidence.items():
                (folder / name).write_text(content)
            with patch.object(receipts, "verify_manifest", return_value={"files": evidence}), \
                    patch.object(identity, "sha256", return_value="tampered"):
                with self.assertRaisesRegex(ValueError, "sealed executable bytes changed"):
                    identity.original_build_evidence(folder, previous)

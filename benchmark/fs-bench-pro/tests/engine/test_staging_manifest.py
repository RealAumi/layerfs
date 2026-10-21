"""Complete file-backed checksum staging, including a pinned GNU checker proof."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
fixtures = importlib.import_module("engine.fixtures")
receipts = importlib.import_module("engine.receipts")
identity = importlib.import_module("engine.identity")


def helpers(home, steps=500):
    code = home / "code"
    code.mkdir()
    files = {}
    for index in range(1, steps + 1):
        for suffix in (f"history/payloads/step-{index}/descriptor.tsv", f"history/payloads/step-{index}/member-1.bin", f"history/steps/step-{index}.sh"):
            path = code / suffix
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((suffix + "\n").encode())
            files[suffix] = identity.sha256(path)
    return {"helpers": {"root": str(code), "files": files}}


class StagingManifest(unittest.TestCase):
    def test_500_steps_preserve_every_ordered_entry_without_embedding_argv(self):
        with tempfile.TemporaryDirectory(prefix="fsb-stage-manifest-") as temporary:
            home = Path(temporary)
            prepared = helpers(home)
            commands = []
            def command(argv, folder, label, seconds):
                commands.append((argv, label))
                return {"argv": argv, "status": "PASS"}
            with patch.object(receipts, "command", side_effect=command):
                result = fixtures.stage("a" * 64, prepared, home / "stage", {"socket": "/test.sock"})
            script = commands[-1][0][-1]
            self.assertNotIn("history/steps/step-500.sh", script)
            record = result["helper_checksum_manifest"]
            expected = "".join(digest + "  /code/" + name + "\n" for name, digest in prepared["helpers"]["files"].items())
            self.assertEqual(Path(record["path"]).read_text(), expected)
            self.assertEqual(record["sha256"], hashlib.sha256(expected.encode()).hexdigest())
            self.assertEqual(record["files"], 1500)
            self.assertIn(record["sha256"], script)
            self.assertIn("sha256sum --check " + record["remote"], script)
            self.assertTrue(any(label == "stage-code-checksum-manifest" for _, label in commands))

    def test_manifest_argument_shape_does_not_grow_with_helpers(self):
        scripts = []
        with tempfile.TemporaryDirectory(prefix="fsb-stage-shape-") as temporary:
            for count in (1, 500):
                home = Path(temporary) / str(count)
                home.mkdir()
                prepared = helpers(home, count)
                with patch.object(receipts, "command", side_effect=lambda argv, *args: {"argv": argv}):
                    result = fixtures.stage("a" * 64, prepared, home / "stage", {"socket": "/test.sock"})
                scripts.append(result["actual_helper_byte_check"]["argv"][-1])
        self.assertEqual(len(scripts[0]), len(scripts[1]))

    def test_invalid_paths_digests_and_reserved_collision_are_refused(self):
        for name, digest in [("../outside", "a" * 64), ("/absolute", "a" * 64), ("line\nbreak", "a" * 64),
                             ("a//b", "a" * 64), (".", "a" * 64), ("okay", "BAD"),
                             (".fs-bench-pro-helpers.sha256", "a" * 64), (".fs-bench-pro-helpers.sha256/child", "a" * 64)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix="fsb-stage-refuse-") as temporary:
                home = Path(temporary)
                prepared = {"helpers": {"root": str(home), "files": {name: digest}}}
                with patch.object(receipts, "command") as command:
                    with self.assertRaises(ValueError):
                        fixtures.stage("a" * 64, prepared, home / "stage", {"socket": "/test.sock"})
                command.assert_not_called()

    @unittest.skipUnless(os.environ.get("LAYERFS_STAGING_SOCKET"), "explicit pinned-image staging proof socket required")
    def test_pinned_gnu_checker_authenticates_full_manifest_and_last_payload(self):
        socket = os.environ["LAYERFS_STAGING_SOCKET"]
        raw = Path(os.environ["LAYERFS_STAGING_RAW"]).resolve()
        raw.mkdir(parents=True, exist_ok=False)
        prepared = helpers(raw)
        token = uuid.uuid4().hex[:16]
        docker = ["docker", "--host", "unix://" + socket]
        container = "layerfs-fsb-staging-guard-" + token
        passed = False
        try:
            made = receipts.command([*docker, "create", "--name", container, "--network", "none", "--cpus", "2", "--memory", "2g", "--memory-swap", "2g", "--pids-limit", "256", "-e", "LAYERFS_CONSTRUCTION_WORKERS=1", identity.IMAGE, "/bin/bash", "-c", "sleep 110"], raw, "create", 15)
            container_id = Path(made["stdout"]).read_text().strip()
            receipts.write_new(raw / "resource-claim.json", {"container": container_id, "name": container, "image": identity.IMAGE, "profile": "bare helper files only; no Store/product/mount/sample", "failure_disposition": "retained", "construction_workers": 1})
            receipts.command([*docker, "start", container], raw, "start", 15)
            result = fixtures.stage(container_id, prepared, raw / "stage", {"socket": socket})
            checker = result["actual_helper_byte_check"]
            stdout = Path(checker["stdout"]).read_text()
            self.assertEqual(stdout.count(": OK\n"), 1501)
            self.assertIn("/code/history/steps/step-500.sh: OK", stdout)
            manifest = result["helper_checksum_manifest"]
            original = Path(manifest["path"]).read_text()
            for kind in ("omitted-row", "rehashed-unknown", "last-payload"):
                changed = raw / (kind + ".sha256")
                if kind == "omitted-row":
                    changed.write_text("\n".join(original.splitlines()[:-1]) + "\n")
                elif kind == "rehashed-unknown":
                    changed.write_text("0" * 64 + "  /code/unknown\n")
                else:
                    changed.write_text(original)
                receipts.command([*docker, "cp", str(changed), container_id + ":" + manifest["remote"]], raw, kind + "-manifest", 15)
                if kind == "last-payload":
                    receipts.command([*docker, "exec", container_id, "/bin/bash", "-c", "printf changed >> /code/history/payloads/step-500/member-1.bin"], raw, kind + "-mutation", 15)
                with self.assertRaises(RuntimeError):
                    receipts.command(checker["argv"], raw, kind + "-check", 15)
                failed = json.loads((raw / (kind + "-check.completion.json")).read_text())
                self.assertEqual(failed["exit_code"], 1)
                if kind == "last-payload":
                    self.assertIn("/code/history/payloads/step-500/member-1.bin: FAILED", Path(failed["stdout"]).read_text())
            passed = True
        finally:
            if passed:
                receipts.command([*docker, "stop", "--time", "2", container], raw, "stop-passing", 15)
                receipts.command([*docker, "rm", container], raw, "remove-passing", 15)
                receipts.write_new(raw / "resource-disposition.json", {"container": container, "status": "REMOVED", "no_volume_created": True})


if __name__ == "__main__":
    unittest.main()

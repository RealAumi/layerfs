"""Actual mount acknowledgement drives both unchanged repository helpers."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shlex
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import project, workspace
import test_repository_controller as repository_fixture


def acknowledgement(key, namespace=1):
    return {"event": "mount", "fields": {"key": key, "directory": f"/workspaces/{namespace}",
            "workspace_incarnation": key, "workspace_namespace": namespace}, "span": {"duration_ns": 3}}


class RepositoryMountRoot(unittest.TestCase):
    def exercise(self, drift=None, bad_phase="performance"):
        """Choreography mocks only; execute no SDK, Docker, native helper or Store."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            selected = repository_fixture.case()
            prepared = repository_fixture.RepositoryController().prepared(root, selected)
            output = root / "benchmark-results/fs-bench-pro/case"
            calls, mount_roots = [], {}

            class Runtime:
                selector = raw = stderr = None
                def __init__(self, label):
                    self.label = label
                    self.container = ("1" if label == "performance" else "2") * 64
                    self.index = 0
                    self.process = SimpleNamespace(stdin=None, stdout=None)
                    self.rows = [{"event": "history_initial_root", "fields": {
                        "root": "0" * 64, "stack": "31" + "3" * 32, "base_layer": "32" + "4" * 64}}]

                def send(self, operation, key="", path=None, deadline=None):
                    if operation in ("command", "verify"):
                        words = shlex.split(Path(path).read_text())
                        expected = "LAYERFS_WORKSPACE_ROOT=" + mount_roots[key]
                        if not words or words[0] != expected:
                            raise ValueError("storage smoke target is not the acknowledged FUSE mount")
                        self_words = words[1:]
                        action = "apply" if operation == "command" else "verify"
                        if self_words[:4] != ["/bin/bash", "/code/workload.sh", action, selected["id"]]:
                            raise ValueError("original repository operation changed")
                        if len(self_words) != 6:
                            raise ValueError("original repository helper argument count changed")
                        calls.append((self.label, operation, words))
                        return {"fields": {"exit_code": "0"}, "span": {"duration_ns": 10}}
                    if operation == "commit":
                        self.index += 1
                        return {"fields": {"commit_kind": "Committed", "commit_id": "12" + f"{self.index:064x}",
                            "parent": "-" if self.index == 1 else "12" + f"{self.index-1:064x}",
                            "root": f"{self.index:064x}", "stack": "31" + "3" * 32,
                            "base_layer": "32" + "4" * 64}, "span": {"duration_ns": 20}}
                    return {"fields": {}, "span": {"duration_ns": 1}}

                def retain(self, error):
                    return {"container": self.container, "cause": str(error), "scope": "choreography mock"}

            def start(prepared, build, output, clone, label, stop):
                folder = Path(output) / label
                folder.mkdir()
                return Runtime(label), folder

            def context(runtime, operation, key="", path=None, deadline=None):
                if operation == "mount-branch":
                    namespace = 1 if runtime.label == "performance" else 100 + int(path.split("-")[-1])
                    event = acknowledgement(key, namespace)
                    mount_roots[key] = event["fields"]["directory"]
                    if drift is not None and runtime.label == bad_phase:
                        drift(event)
                    return event
                index = int(key.split("-")[-1])
                return {"fields": {"root": f"{index:064x}", "head": "12" + f"{index:064x}"}}

            def fork(runtime, selected, spec, graph, output, stop):
                graph["branches"]["history"] = {"commits": [], "source_role": None,
                                                  "final_head": "-", "final_root": "0" * 64}
                return {"fields": {"branch_id": "11" + "5" * 32, "root": "0" * 64,
                                   "stack": "31" + "3" * 32, "base_layer": "32" + "4" * 64}}

            def command(argv, folder, label, seconds, **kwargs):
                if label.startswith("observed-copy-"):
                    Path(argv[-1]).write_text("100644\t1\t" + hashlib.sha256(b"x").hexdigest() + "\t66696c65\n")
                return {"status": "PASS", "exit_code": 0, "attempts": 1}

            build = {"socket": "/owned/docker", "binaries": {
                name: {"path": "/" + name, "sha256": name} for name in ("runtime", "daemon")}}
            with ExitStack() as stack:
                for module, name, options in [
                    (project.identity, "ROOT", {"new": root}),
                    (project.identity, "source_identity", {"return_value": {"source_commit": "a" * 40, "product_tree": "b" * 40}}),
                    (project.identity, "load_build", {"return_value": build}),
                    (workspace.fixtures, "load", {"return_value": prepared}),
                    (workspace.fixtures, "clone", {"return_value": {"volume": "layerfs-fsb-sample-" + "6" * 16}}),
                    (workspace.fixtures, "stage", {"return_value": {"status": "PASS"}}),
                    (project, "repository_runtime", {"side_effect": start}),
                    (project, "repository_host_check", {"return_value": {"status": "PASS"}}),
                    (project, "repository_stop", {"return_value": {"status": "PASS"}}),
                    (workspace, "context_send", {"side_effect": context}),
                    (workspace, "context_fork", {"side_effect": fork}),
                    (workspace, "context_end", {"return_value": {"span": {"duration_ns": 4}}}),
                    (workspace, "history_container_profile", {"return_value": {}}),
                    (workspace, "history_resource_guard", {"return_value": {}}),
                    (workspace, "context_observations", {"return_value": None}),
                    (workspace, "context_history", {"return_value": {"status": "PASS"}}),
                    (project.receipts, "command", {"side_effect": command}),
                    (workspace.oracle, "prepare_closed_store", {"return_value": {
                        "path": "independent-copy", "normalized_identity": {"sha256": "f" * 64}, "raw_files": {}}}),
                    (project, "repository_graph_proof", {"return_value": {"status": "PASS"}}),
                ]:
                    stack.enter_context(patch.object(module, name, **options))
                row = project.one_repository_history(selected, "prepared", "build", output)
            return row, calls, mount_roots

    def test_paid_and_every_fresh_native_helper_use_actual_mount_acknowledgement(self):
        row, calls, roots = self.exercise()
        self.assertEqual(row["status"], "INELIGIBLE", row.get("original_failure"))
        self.assertEqual(row["functional_status"], "PASS")
        self.assertEqual(row["proof_status"], "PASS")
        self.assertEqual(len(row["repository"]["records"]), 17)
        self.assertEqual(len(row["repository"]["native_proofs"]), 17)
        self.assertEqual(len(calls), 34)
        self.assertEqual([call[2][0] for call in calls[:17]], ["LAYERFS_WORKSPACE_ROOT=/workspaces/1"] * 17)
        self.assertEqual([call[2][0] for call in calls[17:]],
                         [f"LAYERFS_WORKSPACE_ROOT=/workspaces/{n}" for n in range(101, 118)])
        self.assertEqual({call[2][3] for call in calls[:17]}, {"apply"})
        self.assertEqual({call[2][3] for call in calls[17:]}, {"verify"})
        self.assertEqual(row["complete_wall_ns"], 510)

    def test_wrong_or_missing_mount_ack_refuses_before_original_importer(self):
        mutations = [lambda event: event["fields"].pop("directory"),
                     lambda event: event["fields"].update(directory="/workspace"),
                     lambda event: event["fields"].update(key="f" * 64),
                     lambda event: event["fields"].update(workspace_incarnation="f" * 64),
                     lambda event: event["fields"].update(workspace_namespace=2),
                     lambda event: event["fields"].pop("workspace_namespace"),
                     lambda event: event["fields"].update(workspace_namespace=True),
                     lambda event: event["fields"].update(workspace_namespace=0),
                     lambda event: event["fields"].update(workspace_namespace=2**64),
                     lambda event: event.update(event="command")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                row, calls, roots = self.exercise(mutation)
                self.assertEqual(row["status"], "FAIL")
                self.assertIn("mount acknowledgement", row["original_failure"])
                self.assertEqual(calls, [])
                self.assertEqual(row["repository"]["records"], [])
                self.assertEqual(row["verification_attempt_count"], 0)
                self.assertTrue(row["leaked_mount_keys"])
                self.assertFalse(row["resource_removal_pending"])

    def test_fresh_verifier_ack_drift_preserves_completed_history_and_actual_mount_custody(self):
        for drift in (lambda event: event["fields"].pop("directory"),
                      lambda event: event["fields"].update(directory="/workspaces/1")):
            with self.subTest(drift=drift):
                row, calls, roots = self.exercise(drift, bad_phase="verification")
                self.assertEqual(row["status"], "FAIL")
                self.assertEqual(row["proof_status"], "FAIL")
                self.assertIn("mount acknowledgement", row["original_failure"])
                self.assertEqual(len(row["repository"]["records"]), 17)
                self.assertEqual(row["repository"]["native_proofs"], [])
                self.assertEqual(len(calls), 17)
                self.assertTrue(all(call[1] == "command" for call in calls))
                self.assertEqual(row["verification_attempt_count"], 1)
                self.assertIn("2" * 64, row["leaked_mount_keys"])
                self.assertEqual(row["retained_containers"], ["1" * 64, "2" * 64])
                self.assertFalse(row["resource_removal_pending"])


if __name__ == "__main__":
    unittest.main()

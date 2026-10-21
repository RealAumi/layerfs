"""Complete Git custody cannot replace independently authored source/semantics."""
import hashlib
import importlib.util
import io
import json
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import workspace, receipts


def custody(index=b"raw index including stat cache", extra=""):
    return ("workspace-independent-manifest-v1\n"
            ".\tdirectory\t0\t750\t1700000000\t0\t-\n"
            ".git\tdirectory\t0\t750\t1700000000\t0\t-\n"
            f".git/index\tfile\t{len(index)}\t640\t1700000000\t0\t{hashlib.sha256(index).hexdigest()}\n" + extra).encode()


def fields(body):
    return {"repository_manifest_sha256": hashlib.sha256(body).hexdigest(),
            "repository_path_count": str(len(body.splitlines())-2)}


class GitCustody(unittest.TestCase):
    def test_outer_driver_acknowledges_only_a_known_returned_finalization(self):
        spec = importlib.util.spec_from_file_location("fsb_git_driver", BENCH / "bench.py")
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                calls = []
                case_id = "git-tool-1-compact-v2"
                row = {"case": case_id, "status": "INELIGIBLE", "proof_status": "PASS",
                       "publication_guard": {"schema": "fs-bench-pro-publication-guard-v1"}}
                def sampled(*args):
                    calls.append("sample")
                    if interrupted:
                        raise OSError("original finalizer did not return")
                    calls.append("known-return")
                    return row
                def acknowledged(folder, returned):
                    calls.append("outer-ack")
                    self.assertEqual(folder.name, case_id)
                    self.assertIs(returned, row)
                current = {"source_commit": "a"*40, "source_tree": "b"*40, "product_tree": "c"*40}
                output = root / "benchmark-results/fs-bench-pro/run"
                with patch.object(workspace.identity, "ROOT", root), \
                        patch.object(workspace.identity, "source_identity", return_value=current), \
                        patch.object(workspace, "one_family_case", side_effect=sampled), \
                        patch.object(receipts, "acknowledge_guarded", side_effect=acknowledged), \
                        redirect_stdout(io.StringIO()):
                    args = ["run", "git_tool_workflow", "--case", case_id, "--build", str(root / "build"),
                            "--prepared", str(root / "prepared"), "--out", str(output)]
                    if interrupted:
                        with self.assertRaisesRegex(OSError, "did not return"):
                            bench.main(args)
                    else:
                        self.assertEqual(bench.main(args), 1)  # Numeric INELIGIBLE remains visible.
                self.assertEqual(calls, ["sample"] if interrupted else ["sample", "known-return", "outer-ack"])

    def test_frozen_deadlines_charge_prior_work_and_keep_cleanup_and_publication_distinct(self):
        case = {"git_workflow": True, "budget": {"verifier_ms": 45000, "verification_hard_watchdog_ms": 59000}}
        with patch.object(workspace.time, "monotonic", return_value=100):
            self.assertEqual(workspace.git_proof_deadlines(case, 3_000_000_000),
                             {"work": 138, "cleanup": 142, "publication": 156})
        for charged in (True, -1, None, "0"):
            with self.subTest(charged=charged), self.assertRaises(ValueError):
                workspace.git_proof_deadlines(case, charged)
        for changed in (44000, 46000):
            with self.assertRaises(ValueError):
                workspace.git_proof_deadlines({**case, "budget": {**case["budget"], "verifier_ms": changed}}, 0)

    def test_controller_discards_prior_qualification_and_orders_custody_before_commit_and_git(self):
        for fail_at in ("commit", "fresh-custody"):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                calls = []
                class Runtime:
                    container = "owned-container"
                    selector = raw = stderr = None
                    process = SimpleNamespace(stdin=None, stdout=None)
                    rows = []
                    def event(self, *args):
                        return None
                    def send(self, operation, key="", path=None, **options):
                        label = operation
                        if operation == "command":
                            label = "prior" if Path(path).name == "prior-qualification.sh" else "performance"
                        calls.append(label)
                        if operation == "commit" and fail_at == "commit":
                            raise ValueError("known Commit refusal")
                        result = {"sequence": len(calls), "event": operation, "span": {"duration_ns": 1},
                                  "fields": {"state": "Gone", "commit_kind": "Committed", "root": "acknowledged-root"}}
                        if operation == "snapshot":
                            result["event"] = "workspace_status"
                        self.rows.append(result)
                        return result
                    def retain(self, error):
                        return {"cause": str(error), "remote_stop": "NOT_ESTABLISHED"}
                runtime = Runtime()
                current = dict(source_commit="source", product_tree="product", files={})
                build = dict(socket="/socket", binaries={name: {"sha256": name, "path": "/"+name} for name in ("runtime", "daemon")})
                prepared = dict(fixture={"fixture_sha256": "fixture"}, helpers={"files": {}},
                                provision={"manifest": "/manifest"}, source_uid=1, source_gid=1)
                case = {"id": "git-tool-1-compact-v2", "v016_case": "git-tool-1-compact-v2", "git_workflow": True,
                        "git_qualification": {"run": "workload.sh qualify git-tool-1-compact-v2"}, "expected_commit": "Committed",
                        "fixture": {"recipe": "git-tool-1-compact-v2"}, "budget": {"command_ms": 15000,
                        "verifier_ms": 45000, "verification_hard_watchdog_ms": 59000}}
                def precommit(*args):
                    calls.append("precommit-custody")
                    self.assertLessEqual(args[-1], 41)
                    return {"path": str(root / "exact-original-index-manifest")}
                def fresh(*args):
                    calls.append("fresh-custody")
                    self.assertLessEqual(args[-1], 41)
                    raise ValueError("known fresh index stat bytes differ")
                with ExitStack() as patches:
                    for module, name, options in (
                        (workspace.identity, "ROOT", {"new": root}),
                        (workspace.identity, "source_identity", {"return_value": current}),
                        (workspace.identity, "load_build", {"return_value": build}),
                        (workspace.fixtures, "load", {"return_value": prepared}),
                        (workspace.fixtures, "clone", {"return_value": {"volume": "owned-volume"}}),
                        (workspace.fixtures, "stage", {"return_value": {"status": "PASS"}}),
                        (workspace.cell_runner, "EventProcess", {"return_value": runtime}),
                        (workspace, "verify_git_qualification", {"return_value": {"status": "PASS"}}),
                        (workspace, "before_git_commit", {"side_effect": precommit}),
                        (workspace, "verify_git_custody", {"side_effect": fresh}),
                        (workspace, "terminal_cache_observation", {"return_value": ([{"fields": {"state": "Gone"}}], {})}),
                    ):
                        patches.enter_context(patch.object(module, name, **options))
                    result = workspace.one_family_case("git_tool_workflow", case, "prepared", "build", root / "case")
                self.assertEqual(calls[:5], ["mount", "prior", "unmount", "cleanup", "mount"])
                self.assertEqual(calls[5:8], ["performance", "precommit-custody", "commit"])
                self.assertEqual(calls.count("commit"), 1)
                self.assertEqual(calls.count("performance"), 1)
                self.assertEqual(calls.count("prior"), 1)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["proof_status"], "FAIL")
                self.assertEqual(result["sample_count"], 1)
                self.assertGreater(result["prior_proof_wall_ns"], 0)
                self.assertGreaterEqual(result["proof_wall_ns"], result["prior_proof_wall_ns"])
                self.assertEqual(len(result["retained_mount_keys"]), 1)
                self.assertTrue(result.get("publication_guard"))
                self.assertNotIn("verify", calls)
                self.assertNotIn("stop", calls)
                if fail_at == "fresh-custody":
                    self.assertEqual(calls[-2:], ["mount", "fresh-custody"])
                    self.assertEqual(result["cleanup"], "Gone")
                receipts.verify_manifest(root / "case")

    def test_complete_index_bytes_canonical_names_and_identity_are_required(self):
        original = custody()
        self.assertEqual(workspace.git_custody_values(original, fields(original))["repository_paths"], 2)
        for damaged in (original.replace(b".git/index", b"tracked/source.dat"),
                        original + original.splitlines(keepends=True)[-1],
                        original.replace(b".git/index", b".git/../index"),
                        original.replace(b"file\t", b"symlink\t"),
                        original.replace(b"640\t1700000000", b"640\t1700000000\t0"),
                        original.replace(b".git/index", b".git/config")):
            with self.subTest(damaged=damaged), self.assertRaises(ValueError):
                workspace.git_custody_values(damaged, fields(damaged))
        for changed in ({"repository_manifest_sha256": "0"*64}, {"repository_path_count": "0"}):
            with self.assertRaises(ValueError):
                workspace.git_custody_values(original, {**fields(original), **changed})

    def test_fresh_custody_detects_index_stat_byte_change_before_semantic_git(self):
        for fresh_body in (custody(), custody(b"same semantics, DIFFERENT index stat bytes")):
            with self.subTest(fresh=fresh_body), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary); bodies = [custody(), fresh_body]
                prepared = {"family": "git_tool_workflow", "case": "git-tool-1-compact-v2",
                            "git_reference": {"case": "git-tool-1-compact-v2"}}
                calls = []
                class Runtime:
                    container = "owned-sample"
                    def send(self, operation, key, path, deadline):
                        calls.append((operation, key, Path(path).read_text()))
                        out = Path(path).parent / "capture.stdout"
                        out.write_text("".join(f"{name}={value}\n" for name, value in fields(bodies[len(calls)-1]).items()))
                        return {"fields": {"stdout": str(out)}}
                def exported(argv, folder, label, seconds):
                    self.assertEqual(argv[-3], "cp")
                    self.assertLessEqual(seconds, 15)
                    Path(argv[-1]).write_bytes(bodies[len(calls)-1])
                    return {"status": "PASS"}
                with patch.object(workspace.receipts, "command", side_effect=exported):
                    prior = workspace.before_git_commit(Runtime(), "measured-key", prepared, {"socket": "/socket"}, home, 45)
                    if fresh_body == custody():
                        result = workspace.verify_git_custody(Runtime(), "fresh-key", prepared, {"socket": "/socket"}, home, prior, 45)
                        self.assertEqual(result["status"], "PASS")
                    else:
                        with self.assertRaisesRegex(ValueError, "precommit/reopened"):
                            workspace.verify_git_custody(Runtime(), "fresh-key", prepared, {"socket": "/socket"}, home, prior, 45)
                self.assertEqual([call[0] for call in calls], ["verify", "verify"])
                self.assertTrue(all("workspace-git-custody-out /tmp/" in call[2] for call in calls))
                self.assertTrue(all("workspace-git-verify" not in call[2] for call in calls))
                receipts.verify_manifest(home / "git-precommit")
                receipts.verify_manifest(home / "git-reopened")
                self.assertEqual(Path(prior["path"]).read_bytes(), custody())

    def test_independent_git_semantics_require_all_three_ids_and_original_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); bundle = root / "git-reference"; bundle.mkdir()
            for name in ("head", "tree", "parent"):
                (bundle / ("expected-"+name)).write_text(name+"-independent\n")
            prepared = {"helpers": {"root": str(root)}}
            good = {"git_"+name: name+"-independent" for name in ("head", "tree", "parent")}
            good.update(verification_status="pass", git_semantic_verification_status="pass",
                        git_custody_status="requires_precommit_reopen_comparison")
            self.assertEqual(workspace.verify_git_semantic_fields(good, prepared)["status"], "PASS")
            for name in good:
                damaged = dict(good); damaged[name] = "unknown"
                with self.subTest(name=name), self.assertRaises(ValueError):
                    workspace.verify_git_semantic_fields(damaged, prepared)

    def test_prior_mounted_verification_cannot_be_replaced_by_performance_variant(self):
        case = {"git_workflow": True, "git_qualification": {"run": "qualify"}, "v016_case": "git-tool-1-compact-v2",
                "original_operation_counts": {"git_process_count": 6, "completed_target_count": 1, "benchmark_verifier_count": 0}}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "original.stdout"
            command = {"fields": {"stdout": str(output)}}
            good = "git_process_count=6\ncompleted_target_count=1\nbenchmark_verifier_count=1\nworkload_status=pass\nscenario_id=git-tool-1-compact-v2\nseed=1\n"
            output.write_text(good)
            self.assertEqual(workspace.verify_git_qualification(command, case)["status"], "PASS")
            for changed in (good.replace("benchmark_verifier_count=1", "benchmark_verifier_count=0"),
                            good.replace("git_process_count=6", "git_process_count=5"), good.replace("seed=1", "seed=2"),
                            good.replace("workload_status=pass", "workload_status=unknown")):
                output.write_text(changed)
                with self.assertRaises(ValueError):
                    workspace.verify_git_qualification(command, case)


if __name__ == "__main__":
    unittest.main()

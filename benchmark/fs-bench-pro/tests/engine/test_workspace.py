"""Missing evidence and custody never become a successful mounted sample."""
import json
import importlib.util
import io
from contextlib import redirect_stderr
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import cache, receipts, workspace


def phase_proof():
    files = {"store": {"device": 1, "inode": 2}, "overlay": {"device": 1, "inode": 3}}
    return {
        "phase_input_boundaries": {phase: {"files": files, "started_monotonic_ns": 100 + index * 100}
                                   for index, phase in enumerate(cache.PHASES)},
        "phase_cache_observations": {phase: {"files": files, "identity_checked": True,
            "all_paid_input_scopes_complete": True, "clock_id": "monotonic",
            "observed_monotonic_ns": 99 + index * 100, "status": "VERIFIED_COLD",
            "resident_pages": 0, "metadata_state": "VERIFIED_COLD",
            "sqlite_reader_cache_state": "VERIFIED_COLD"} for index, phase in enumerate(cache.PHASES)},
    }


class WorkspaceEvidence(unittest.TestCase):
    def test_current_history_batch_routes_remain_unsampleable_until_ported(self):
        spec = importlib.util.spec_from_file_location("fsb_pending_driver", Path(__file__).resolve().parents[2] / "bench.py")
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        for family in ("file_size_transition", "dedup_branch_history", "mixed_load_bearing"):
            self.assertIn(family, workspace.fixtures.WORKSPACE_FAMILIES)
            with self.subTest(family=family), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                output = root / "benchmark-results/fs-bench-pro/run"
                definition = root / "families" / family / "family.json"
                definition.parent.mkdir(parents=True)
                definition.write_text(json.dumps({"family": family, "cases": [{"id": "pending-original-case", "status": "pending"}]}))
                with patch.object(bench, "HERE", root), \
                        patch.object(workspace.identity, "source_identity", return_value={}), \
                        patch.object(workspace, "one_family_case") as attempted, redirect_stderr(io.StringIO()) as error:
                    with self.assertRaises(SystemExit) as rejected:
                        bench.main(["run", family, "--build", str(root / "build"), "--prepared", str(root / "prepared"), "--out", str(output)])
                self.assertEqual(rejected.exception.code, 2)
                self.assertIn("pending cases cannot be sampled", error.getvalue())
                attempted.assert_not_called()
                self.assertFalse(output.exists())

    def test_control_only_case_reaches_commit_without_warm_or_measured_exec(self):
        class Runtime:
            container = "original-container"
            selector = raw = stderr = None
            process = SimpleNamespace(stdin=None, stdout=None)
            def __init__(self):
                self.calls = []
            def event(self, *args):
                return None
            def send(self, operation, key="", **options):
                self.calls.append(operation)
                if operation == "command":
                    raise AssertionError("clean Commit must never launch an Exec")
                if operation == "commit":
                    raise ValueError("known original Commit refusal")
                return {"sequence": len(self.calls), "event": operation,
                        "span": {"duration_ns": 1}, "fields": {"state": "Gone"}}
            def retain(self, error):
                return {"cause": str(error), "remote_stop": "NOT_ESTABLISHED"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            runtime = Runtime()
            current = dict(source_commit="source", product_tree="product", files={})
            build = dict(socket="/socket", binaries={name: {"sha256": name, "path": "/"+name} for name in ("runtime", "daemon")})
            prepared = dict(fixture={"fixture_sha256": "fixture"}, helpers={"files": {}},
                            provision={"manifest": "/manifest"}, source_uid=1, source_gid=1)
            case = {"id": "clean", "v016_case": "clean", "control_only": True, "steps": [],
                    "fixture": {"recipe": "clean"}, "budget": {"command_ms": 15000, "verifier_ms": 45000}}
            with patch.object(workspace.identity, "ROOT", root), \
                    patch.object(workspace.identity, "source_identity", return_value=current), \
                    patch.object(workspace.identity, "load_build", return_value=build), \
                    patch.object(workspace.fixtures, "load", return_value=prepared), \
                    patch.object(workspace.fixtures, "clone", return_value={"volume": "original-volume"}), \
                    patch.object(workspace.fixtures, "stage", return_value={"status": "PASS"}), \
                    patch.object(workspace.cell_runner, "EventProcess", return_value=runtime):
                result = workspace.one_family_case("workspace_change_locality", case, "prepared", "build", root / "case")
            self.assertEqual(runtime.calls, ["mount", "unmount", "cleanup", "mount", "commit"])
            self.assertEqual(result["original_failure"], "known original Commit refusal")
            self.assertEqual(result["phases"]["command_ns"], 0)
            self.assertEqual(result["sample_count"], 1)
            self.assertEqual(result["completed_operation_count"], 0)
            self.assertEqual(result["status"], "FAIL")
            receipts.verify_manifest(root / "case")

    def test_original_ordinary_resource_guards_reject_missing_warm_oom_and_overflow(self):
        good = dict(store_main_logical_bytes=100, store_main_allocated_bytes=4096,
                    oom=0, oom_kill=0, swap_current=0)
        self.assertEqual(workspace.ordinary_resource_values(good, good), good)
        exact = {**good, "store_main_logical_bytes": 4*1024**3, "store_main_allocated_bytes": 4*1024**3}
        self.assertEqual(workspace.ordinary_resource_values(exact, good), exact)
        for key in good:
            for value in (None, True, -1, "0"):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    workspace.ordinary_resource_values({**good, key: value}, good)
        for key in ("store_main_logical_bytes", "store_main_allocated_bytes"):
            with self.assertRaisesRegex(RuntimeError, "4 GiB"):
                workspace.ordinary_resource_values({**good, key: 4*1024**3+1}, good)
        for key in ("oom", "oom_kill", "swap_current"):
            with self.assertRaisesRegex(RuntimeError, "OOM/swap"):
                workspace.ordinary_resource_values({**good, key: 1}, good)

    def test_measured_traversal_counters_must_be_complete_exact_and_unambiguous(self):
        wanted = {"visited_path_count": 184, "visited_file_count": 50, "directory_entry_count": 183}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "original.stdout"
            command = {"fields": {"stdout": str(output)}}
            text = "\n".join(f"{key}={value}" for key, value in wanted.items())+"\n"
            output.write_text(text)
            self.assertEqual(workspace.original_operation_counts(command, wanted), wanted)
            for damaged in (text.replace("184", "183"), text.replace("visited_file_count=50\n", ""),
                            text+"visited_path_count=184\n", text.replace("183", "unknown")):
                output.write_text(damaged)
                with self.assertRaisesRegex(ValueError, "semantic count differs"):
                    workspace.original_operation_counts(command, wanted)
            with self.assertRaisesRegex(ValueError, "acknowledged workload"):
                workspace.original_operation_counts(None, wanted)

    def test_family_clone_failure_has_no_mount_or_completed_sample_credit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            current = dict(source_commit="source", product_tree="product", files={})
            build = dict(binaries={name: {"sha256": name} for name in ("runtime", "daemon")})
            prepared = dict(fixture={"fixture_sha256": "fixture"}, helpers={"files": {}})
            case = {"id": "payload", "v016_case": "payload", "fixture": {"recipe": "payload"},
                    "budget": {"command_ms": 15000, "verifier_ms": 45000}}
            with patch.object(workspace.identity, "ROOT", root), \
                    patch.object(workspace.identity, "source_identity", return_value=current), \
                    patch.object(workspace.identity, "load_build", return_value=build), \
                    patch.object(workspace.fixtures, "load", return_value=prepared), \
                    patch.object(workspace.fixtures, "clone", side_effect=ValueError("original clone mismatch")):
                result = workspace.one_family_case("payload_create_read", case, "prepared", "build", root / "case")
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["original_failure"], "original clone mismatch")
            self.assertEqual(result["sample_count"], 0)
            self.assertEqual(result["completed_operation_count"], 0)
            self.assertNotIn("complete_wall_ns", result)
            self.assertEqual(result["retained_mount_keys"], [])
            receipts.verify_manifest(root / "case")

    def test_backing_observer_waits_for_original_reclamation_to_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            states = iter(("Queued", "Gone"))
            observed = []
            def send(operation, key, **options):
                self.assertEqual((operation, key), ("cleanup", "original-key"))
                state = next(states)
                observed.append(state)
                return {"fields": {"state": state}}
            runtime = SimpleNamespace(container="original-container", send=send)
            def command(argv, folder, label, seconds, *, allow_failure=False):
                self.assertEqual(observed, ["Queued", "Gone"])
                self.assertNotIn("--evict", argv)
                path = Path(folder) / "observer.stdout"
                path.write_text('{"resident_pages": 1}')
                return {"exit_code": 0, "stdout": str(path)}
            with patch.object(workspace.receipts, "command", side_effect=command):
                cleaned, residency = workspace.terminal_cache_observation(runtime, "original-key", {"socket": "/socket"}, directory)
            self.assertEqual([row["fields"]["state"] for row in cleaned], ["Queued", "Gone"])
            self.assertEqual(residency, {"resident_pages": 1})

    def test_b_requires_original_terminal_cleanup_and_actual_zero_demands(self):
        good = dict(fresh_mount=True, warmup_terminal_unmount=True, warmup_cleanup="Gone",
                    object_demands=0, has_own_write_input=False, **phase_proof())
        self.assertEqual(cache.validate("B", good), "ELIGIBLE")
        for name in good:
            self.assertEqual(cache.validate("B", {key: value for key, value in good.items() if key != name}), "INELIGIBLE")
        for value in (True, -1, 1, "0", None):
            self.assertEqual(cache.validate("B", {**good, "object_demands": value}), "INELIGIBLE")

    def test_content_pages_alone_do_not_prove_a_and_c_lifetime_is_bounded(self):
        self.assertEqual(cache.validate("A", {"resident_pages": 0}), "INELIGIBLE")
        self.assertEqual(cache.validate("A", {"resident_pages": False, "metadata_state": "VERIFIED_COLD"}), "INELIGIBLE")
        self.assertEqual(cache.validate("C", {"same_mount": True, "warm_interval_ns": 60_000_000_000}), "INELIGIBLE")
        self.assertEqual(cache.validate("C", {"same_mount": True, "warm_interval_ns": 59_999_999_999,
                                               "has_own_write_input": False, **phase_proof()}), "ELIGIBLE")

    def test_zero_source_demands_cannot_credit_own_written_commit_input(self):
        good = dict(fresh_mount=True, warmup_terminal_unmount=True, warmup_cleanup="Gone",
                    object_demands=0, has_own_write_input=True, **phase_proof())
        self.assertEqual(cache.validate("B", good), "INELIGIBLE")
        self.assertEqual(cache.validate("B", {**good, "own_write_cache_state": "UNAVAILABLE"}), "INELIGIBLE")

    def test_zero_object_demands_do_not_qualify_unobserved_paid_phase_inputs(self):
        evidence = dict(fresh_mount=True, warmup_terminal_unmount=True, warmup_cleanup="Gone",
                        object_demands=0, has_own_write_input=False,
                        residency={"status": "ELIGIBLE", "scope": "after_terminal_unmount"})
        self.assertEqual(cache.validate("B", evidence), "INELIGIBLE")
        self.assertEqual(cache.validate("C", {**evidence, "same_mount": True, "warm_interval_ns": 1}), "INELIGIBLE")

    def test_each_phase_proof_rejects_late_unknown_wrong_identity_or_warm_inputs(self):
        import copy
        good = dict(fresh_mount=True, warmup_terminal_unmount=True, warmup_cleanup="Gone",
                    object_demands=0, has_own_write_input=False, **phase_proof())
        self.assertEqual(cache.regime_status("B", good), "ELIGIBLE")
        for phase in cache.PHASES:
            for changed in ({"observed_monotonic_ns": good["phase_input_boundaries"][phase]["started_monotonic_ns"]},
                            {"files": {"store": {"inode": 99}, "overlay": {"inode": 3}}},
                            {"resident_pages": 1}, {"resident_pages": False},
                            {"metadata_state": "UNAVAILABLE"}, {"sqlite_reader_cache_state": "UNAVAILABLE"},
                            {"all_paid_input_scopes_complete": False}):
                broken = copy.deepcopy(good)
                broken["phase_cache_observations"][phase].update(changed)
                self.assertEqual(cache.validate("B", broken), "INELIGIBLE")

    def test_original_group_deadline_is_shared_and_never_extended_per_call(self):
        with patch.object(workspace.time, "monotonic", return_value=10.0):
            self.assertEqual(workspace.operation_deadline(12.0, 120), 12.0)
            self.assertEqual(workspace.operation_deadline(None, 15), 25.0)
        with patch.object(workspace.time, "monotonic", return_value=11.5):
            self.assertEqual(workspace.operation_deadline(12.0, 120), 12.0)
        with patch.object(workspace.time, "monotonic", return_value=12.0):
            with self.assertRaisesRegex(TimeoutError, "group watchdog expired"):
                workspace.operation_deadline(12.0, 120)

    def test_completed_metrics_collection_keeps_a_separate_graph_failure(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            stdout, stderr = output / "logs.stdout", output / "logs.stderr"
            stdout.write_text("")
            stderr.write_text("")
            runtime = SimpleNamespace(container="owned-stopped", daemon_instance="a" * 64,
                                      scope="b" * 64, rows=[])
            row = {"status": "FAIL", "original_failure": "untouched mapping differs",
                   "observations": {}, "cache": {"has_own_write_input": True}}
            with patch.object(workspace.receipts, "command", return_value={"stdout": str(stdout), "stderr": str(stderr)}) as read, \
                    patch.object(workspace.cell_runner, "telemetry", return_value={}), \
                    patch.object(workspace, "price", return_value=({"requests": 16, "owner_jobs": 140, "statements": 645}, [], {})), \
                    patch.object(workspace.cell_runner, "snapshot_observations"), \
                    patch.object(workspace.cell_runner, "ingest_observations"):
                workspace.collect_family_observations(runtime, row, {"socket": "/socket"}, output, {})
            self.assertEqual(row["original_failure"], "untouched mapping differs")
            self.assertEqual(row["status"], "FAIL")
            self.assertEqual(row["counts"], {"requests": 16, "owner_jobs": 140, "statements": 645})
            self.assertEqual(row["cache"]["status"], "INELIGIBLE")
            self.assertEqual(read.call_count, 1)
            self.assertEqual(read.call_args.args[0][3:5], ["logs", "--timestamps=false"])

    def test_failed_clone_retains_original_failure_and_has_no_sample_credit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = dict(source_commit="source", product_tree="product", files={})
            build = dict(binaries={name: {"sha256": name} for name in ("runtime", "daemon")})
            prepared = dict(fixture={"fixture_sha256": "fixture"})
            with patch.object(workspace.identity, "ROOT", root), \
                    patch.object(workspace.identity, "source_identity", return_value=current), \
                    patch.object(workspace.identity, "load_build", return_value=build), \
                    patch.object(workspace.fixtures, "load", return_value=prepared), \
                    patch.object(workspace.fixtures, "clone", side_effect=ValueError("original clone mismatch")):
                result = workspace.one_cell("C01", "prepared", "build", root / "result")
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["original_failure"], "original clone mismatch")
                self.assertEqual((result["sample_count"], result["completed_operation_count"]), (0, 0))
                self.assertNotIn("complete_wall_ns", result)
                self.assertEqual(receipts.verify_manifest(root / "result")["schema"], "fs-bench-pro-evidence-v1")
                with self.assertRaises(FileExistsError):
                    workspace.one_cell("C01", "prepared", "build", root / "another")

    def test_report_keeps_every_case_and_exceeded_is_independent_of_pass(self):
        selection = {"family": "cluster-two/cells", "cases": [{"id": "C01"}, {"id": "C02"}, {"id": "C03"}]}
        recorded = {"C01": {"status": "PASS", "proof_status": "PASS", "complete_wall_ns": 16,
                            "declared_limit_ns": 15, "counts": {"requests": 0}, "cleanup": "Gone"},
                    "C02": {"status": "FAIL", "original_failure": "original refused operation"}}
        performance, proof = receipts.result_rows(selection, recorded)
        self.assertEqual(len(performance), 3)
        self.assertEqual([row["status"] for row in performance], ["PASS", "FAIL", "NOT_RUN"])
        self.assertEqual(performance[0]["limit_status"], "EXCEEDED")
        self.assertEqual(performance[0]["requests"], 0)
        self.assertEqual(performance[1]["requests"], "UNAVAILABLE")
        self.assertEqual(performance[1]["tag"], "original refused operation")
        self.assertEqual(proof[0]["proof_status"], "PASS")
        self.assertEqual(set(performance[0]), set(receipts.PERFORMANCE_COLUMNS))
        self.assertEqual(set(proof[0]), set(receipts.VERIFICATION_COLUMNS))

    def test_csv_output_is_generated_once_and_missing_metrics_stay_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            run = home / "run"
            run.mkdir()
            receipts.write_new(run / "run.json", {"family": "cluster-two/cells", "cases": [{"id": "C01"}],
                                                   "date": "2026-10-10", "source_commit": "commit", "product_tree": "product"})
            result = receipts.report(run, home / "csv")
            self.assertEqual(result["cases"], 1)
            self.assertIn("NOT_RUN", (home / "csv/performance.csv").read_text())
            self.assertIn("UNAVAILABLE", (home / "csv/verification.csv").read_text())
            with self.assertRaises(FileExistsError):
                receipts.report(run, home / "csv")

    def test_report_uses_preserved_source_row_and_never_promotes_proof_time(self):
        selection = {"family": "init_namespace", "cases": [{"id": "namespace-100-compact-v3", "reference": {
            "kind": "performance", "source_file": "release-notes/0.1.5/benchmark-performance.csv", "source_row": "110"}}]}
        performance, _ = receipts.result_rows(selection, {})
        self.assertEqual(performance[0]["reference_release"], "0.1.5")
        self.assertEqual(performance[0]["reference_timer"], "layerstack_init_ns")
        self.assertTrue(performance[0]["reference_ns"].isdigit())
        selection["cases"][0]["reference"]["kind"] = "verification"
        performance, _ = receipts.result_rows(selection, {})
        self.assertEqual(performance[0]["reference_ns"], "")

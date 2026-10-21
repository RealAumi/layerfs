"""Late publication can only downgrade exact immutable receipt evidence."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from engine import receipts


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class Publication(unittest.TestCase):
    def row(self):
        return {"schema": "fs-bench-pro-workspace-family-v1", "family": "git_tool_workflow",
                "case": "git-tool-1-compact-v2", "source_commit": "a"*40, "product_tree": "b"*40,
                "image": "pinned-image", "status": "INELIGIBLE", "proof_status": "PASS",
                "functional_status": "PASS", "tag": "original cache ineligible",
                "complete_wall_ns": 123456, "proof_wall_ns": 765432, "declared_limit_ns": 15000000000,
                "verifier_limit_ns": 45000000000, "phases": {"mount_ns": 10, "command_ns": 20,
                "commit_ns": 30, "unmount_ns": 40}, "counts": {"requests": 17, "owner_jobs": 19, "statements": 23},
                "observations": {"store_allocated_bytes": {"status": "AVAILABLE", "value": 4096}},
                "cleanup": "Gone", "custody": "KNOWN_STOP", "cache_class": "B",
                "verification": {"scope": "complete original bytes and custody", "omissions": "retired format"}}

    def selection(self, run, row):
        receipts.write_new(run / "run.json", {"family": row["family"], "source_commit": row["source_commit"],
            "product_tree": row["product_tree"], "image": row["image"], "date": "2026-10-10", "cases": [{"id": row["case"]}]})

    def test_process_death_leaving_provisional_link_without_outer_ack_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); row["status"] = "PASS"
            self.selection(run, row); folder = run / row["case"]
            source = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
from engine import receipts
real_link = receipts.os.link
def die_after_link(source, target):
    real_link(source, target)
    os._exit(91)
receipts.os.link = die_after_link
receipts.time.monotonic = lambda: 9.5
receipts.finalize_guarded(sys.argv[2], json.loads(sys.argv[3]), 10.0)
"""
            child = subprocess.run([sys.executable, "-B", "-c", source, str(BENCH), str(folder), json.dumps(row)],
                                   capture_output=True, text=True, timeout=10)
            self.assertEqual(child.returncode, 91, child.stderr)
            self.assertTrue((folder / "publication-completion.json").exists())
            self.assertFalse((folder / "publication-outer-acknowledgement.json").exists())
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))
            self.assertIn("outer finalization acknowledgement unavailable", loaded[row["case"]]["tag"])
            self.assertEqual(loaded[row["case"]]["counts"], row["counts"])

    def test_known_return_outer_ack_is_required_and_outside_original_timer(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]
            with patch.object(receipts.time, "monotonic", Clock(9.5)):
                returned = receipts.finalize_guarded(folder, row, 10.0)
            receipt_bytes, manifest_bytes = (folder / "receipt.json").read_bytes(), (folder / "manifest.json").read_bytes()
            _, missing = receipts.load_run(run)
            self.assertEqual((missing[row["case"]]["status"], missing[row["case"]]["proof_status"]), ("FAIL", "FAIL"))
            with patch.object(receipts.time, "monotonic", Clock(12.0)):
                acknowledgement = receipts.acknowledge_guarded(folder, returned)
            self.assertEqual(acknowledgement["observed_return_monotonic"], 12.0)
            self.assertIn("outside the original family publication timer", acknowledgement["scope"])
            _, loaded = receipts.load_run(run)
            self.assertEqual(loaded[row["case"]], returned)
            self.assertEqual((folder / "receipt.json").read_bytes(), receipt_bytes)
            self.assertEqual((folder / "manifest.json").read_bytes(), manifest_bytes)

    def test_outer_acknowledgement_binding_tamper_or_promotion_rejects(self):
        for altered in ("receipt_sha256", "manifest_sha256", "identity", "publication_completion_sha256",
                        "finalizer_return_observed", "scope", "observed_return_monotonic", "returned_status",
                        "returned_proof_status", "returned_verdict_sha256"):
            with self.subTest(field=altered), tempfile.TemporaryDirectory() as temporary:
                run = Path(temporary); row = self.row(); self.selection(run, row)
                folder = run / row["case"]
                with patch.object(receipts.time, "monotonic", Clock(9.5)):
                    returned = receipts.finalize_guarded(folder, row, 10.0)
                receipts.acknowledge_guarded(folder, returned)
                path = folder / "publication-outer-acknowledgement.json"
                acknowledgement = json.loads(path.read_text())
                acknowledgement[altered] = (True if altered == "observed_return_monotonic" else
                                             "FAIL" if altered == "returned_proof_status" else "PASS")
                path.write_text(json.dumps(acknowledgement))
                with self.assertRaisesRegex(ValueError, "outer acknowledgement"):
                    receipts.load_run(run)

    def test_partial_outer_ack_reports_fail_with_authenticated_metrics_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]
            with patch.object(receipts.time, "monotonic", Clock(9.5)):
                returned = receipts.finalize_guarded(folder, row, 10.0)
            real_write = receipts.write_new
            def interrupted_ack(path, value):
                if Path(path).name == "publication-outer-acknowledgement.json":
                    Path(path).write_text('{"partial":')
                    raise OSError("outer acknowledgement emission interrupted")
                real_write(path, value)
            with patch.object(receipts, "write_new", interrupted_ack):
                with self.assertRaisesRegex(OSError, "emission interrupted"):
                    receipts.acknowledge_guarded(folder, returned)
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))
            self.assertIn("acknowledgement incomplete", loaded[row["case"]]["tag"])
            for name in ("complete_wall_ns", "proof_wall_ns", "counts", "phases", "observations", "cleanup"):
                self.assertEqual(loaded[row["case"]][name], row[name])
            receipts.report(run, run / "csv")
            with (run / "csv/verification.csv").open(newline="") as stream:
                proof = next(csv.DictReader(stream))
            self.assertEqual(proof["proof_status"], "FAIL")
            self.assertEqual(proof["proof_wall_ns"], str(row["proof_wall_ns"]))

    def test_outer_returned_failure_is_retained_and_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]
            with patch.object(receipts.time, "monotonic", Clock(9.5)):
                returned = receipts.finalize_guarded(folder, row, 10.0)
            with self.assertRaisesRegex(ValueError, "cannot promote"):
                receipts.acknowledge_guarded(folder, {**returned, "status": "PASS"})
            with self.assertRaisesRegex(ValueError, "returned identity differs"):
                receipts.acknowledge_guarded(folder, {**returned, "source_commit": "different"})
            self.assertFalse((folder / "publication-outer-acknowledgement.json").exists())
            receipts.acknowledge_guarded(folder, {**returned, "status": "FAIL", "proof_status": "FAIL"})
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))
            self.assertEqual(loaded[row["case"]]["counts"], row["counts"])

    def test_frozen_margin_and_numeric_deadline_cannot_be_overridden(self):
        invalid = ((10.0, 0), (10.0, 0.5), (10.0, True), (10.0, float("nan")),
                   (True, 0.25), (float("nan"), 0.25), ("10", 0.25))
        for stop, margin in invalid:
            with self.subTest(stop=stop, margin=margin), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary) / "case"
                with patch.object(receipts.time, "monotonic", Clock(9.5)):
                    with self.assertRaises(ValueError):
                        receipts.finalize_guarded(folder, self.row(), stop, margin)
                self.assertFalse(folder.exists())

    def test_coherently_rebound_zero_margin_is_rejected_by_loader(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]
            with patch.object(receipts.time, "monotonic", Clock(9.5)):
                result = receipts.finalize_guarded(folder, row, 10.0)
            receipts.acknowledge_guarded(folder, result)
            receipt = json.loads((folder / "receipt.json").read_text())
            receipt["publication_guard"]["publication_guard_seconds"] = 0
            (folder / "receipt.json").write_text(json.dumps(receipt))
            manifest = json.loads((folder / "manifest.json").read_text())
            manifest["files"]["receipt.json"] = hashlib.sha256((folder / "receipt.json").read_bytes()).hexdigest()
            (folder / "manifest.json").write_text(json.dumps(manifest))
            binding = receipts._publication_binding(folder, receipt)
            observation = json.loads((folder / "publication.json").read_text())
            observation.update(binding, publication_guard_seconds=0)
            (folder / "publication.json").write_text(json.dumps(observation))
            completion = json.loads((folder / "publication-completion.attempt.json").read_text())
            completion.update(binding, publication_guard_seconds=0,
                publication_observation_sha256=hashlib.sha256((folder / "publication.json").read_bytes()).hexdigest())
            (folder / "publication-completion.attempt.json").write_text(json.dumps(completion))
            receipts.verify_manifest(folder)
            with self.assertRaisesRegex(ValueError, "clock declaration differs"):
                receipts.load_run(run)

    def test_nonfinite_or_bool_completion_clock_revokes_provisional_link(self):
        for value in (True, float("nan"), float("inf")):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                run = Path(temporary); row = self.row(); self.selection(run, row)
                folder = run / row["case"]; clock = Clock(9.5); real_link = receipts.os.link
                def altered_clock(source, target):
                    real_link(source, target); clock.value = value
                with patch.object(receipts.time, "monotonic", clock), patch.object(receipts.os, "link", altered_clock):
                    with self.assertRaisesRegex(ValueError, "monotonic publication clock"):
                        receipts.finalize_guarded(folder, row, 10.0)
                self.assertFalse((folder / "publication-completion.json").exists())
                self.assertTrue((folder / "publication-completion.attempt.json").exists())
                _, loaded = receipts.load_run(run)
                self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))

    def test_reaching_original_publication_margin_rejects_before_receipt_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            clock = Clock(9.75); folder = run / row["case"]
            with patch.object(receipts.time, "monotonic", clock):
                result = receipts.finalize_guarded(folder, row, 10.0)
            original = json.loads((folder / "receipt.json").read_text())
            self.assertEqual((original["status"], original["proof_status"]), ("FAIL", "FAIL"))
            self.assertEqual(result["counts"], row["counts"])
            self.assertEqual(row["proof_status"], "PASS")
            _, loaded = receipts.load_run(run)
            self.assertEqual(loaded[row["case"]]["tag"].count("receipt publication FAIL:"), 1)
            self.assertEqual(loaded[row["case"]]["complete_wall_ns"], row["complete_wall_ns"])

    def test_late_manifest_binds_failure_retains_original_metrics_and_reports_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]; clock = Clock(9.5)
            real_manifest = receipts.manifest
            def slow_manifest(path):
                real_manifest(path); clock.value = 10.1
            with patch.object(receipts.time, "monotonic", clock), patch.object(receipts, "manifest", slow_manifest):
                result = receipts.finalize_guarded(folder, row, 10.0)
            original_bytes = (folder / "receipt.json").read_bytes()
            original_manifest = (folder / "manifest.json").read_bytes()
            original = json.loads(original_bytes)
            self.assertEqual((original["status"], original["proof_status"]), ("INELIGIBLE", "PASS"))
            self.assertEqual((result["status"], result["proof_status"]), ("FAIL", "FAIL"))
            disposition = json.loads((folder / "publication-failure.json").read_text())
            self.assertEqual(disposition["receipt_sha256"], hashlib.sha256(original_bytes).hexdigest())
            self.assertEqual(disposition["manifest_sha256"], hashlib.sha256(original_manifest).hexdigest())
            self.assertGreaterEqual(disposition["finished_monotonic"], disposition["absolute_stop_monotonic"])
            _, loaded = receipts.load_run(run)
            for field in ("complete_wall_ns", "proof_wall_ns", "counts", "phases", "observations", "cleanup", "custody"):
                self.assertEqual(loaded[row["case"]][field], row[field])
            report = receipts.report(run, run / "csv")
            self.assertEqual(report["cases"], 1)
            with (run / "csv/performance.csv").open(newline="") as stream:
                performance = next(csv.DictReader(stream))
            with (run / "csv/verification.csv").open(newline="") as stream:
                proof = next(csv.DictReader(stream))
            self.assertEqual((performance["status"], proof["proof_status"]), ("FAIL", "FAIL"))
            self.assertEqual(performance["requests"], "17")
            self.assertEqual(performance["complete_wall_ns"], str(row["complete_wall_ns"]))
            self.assertEqual(proof["proof_wall_ns"], str(row["proof_wall_ns"]))
            self.assertEqual((folder / "receipt.json").read_bytes(), original_bytes)
            self.assertEqual((folder / "manifest.json").read_bytes(), original_manifest)

    def test_failure_binding_tamper_cannot_be_applied_or_promote_original(self):
        for altered in ("receipt_sha256", "manifest_sha256", "identity", "status", "publication_observation_sha256"):
            with self.subTest(field=altered), tempfile.TemporaryDirectory() as temporary:
                run = Path(temporary); row = self.row(); self.selection(run, row)
                folder = run / row["case"]; clock = Clock(9.5); real_manifest = receipts.manifest
                def slow_manifest(path):
                    real_manifest(path); clock.value = 10.1
                with patch.object(receipts.time, "monotonic", clock), patch.object(receipts, "manifest", slow_manifest):
                    receipts.finalize_guarded(folder, row, 10.0)
                path = folder / "publication-failure.json"
                failure = json.loads(path.read_text())
                failure[altered] = {"case": "another-case"} if altered == "identity" else "PASS"
                path.write_text(json.dumps(failure))
                with self.assertRaisesRegex(ValueError, "publication failure.*binding differs"):
                    receipts.load_run(run)

    def test_changed_registered_family_or_image_cannot_rebind_guarded_case(self):
        for name in ("family", "image"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                run = Path(temporary); row = self.row(); self.selection(run, row)
                with patch.object(receipts.time, "monotonic", Clock(9.5)):
                    result = receipts.finalize_guarded(run / row["case"], row, 10.0)
                receipts.acknowledge_guarded(run / row["case"], result)
                path = run / "run.json"
                selected = json.loads(path.read_text()); selected[name] = "different-identity"
                path.write_text(json.dumps(selected))
                with self.assertRaisesRegex(ValueError, "run identity differs"):
                    receipts.load_run(run)

    def test_auxiliary_observation_publication_crossing_stop_also_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            clock = Clock(9.5); real_write = receipts.write_new
            def slow_observation(path, value):
                real_write(path, value)
                if Path(path).name == "publication.json":
                    clock.value = 10.1
            with patch.object(receipts.time, "monotonic", clock), patch.object(receipts, "write_new", slow_observation):
                result = receipts.finalize_guarded(run / row["case"], row, 10.0)
            self.assertEqual(result["status"], "FAIL")
            _, loaded = receipts.load_run(run)
            self.assertEqual(loaded[row["case"]]["proof_status"], "FAIL")

    def test_late_observation_and_failed_failure_record_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); row["status"] = "PASS"
            self.selection(run, row)
            folder = run / row["case"]; clock = Clock(9.5); real_write = receipts.write_new
            def incomplete_publication(path, value):
                if Path(path).name == "publication-failure.json":
                    raise OSError("failure disposition could not be written")
                real_write(path, value)
                if Path(path).name == "publication.json":
                    clock.value = 10.1
            with patch.object(receipts.time, "monotonic", clock), patch.object(receipts, "write_new", incomplete_publication):
                with self.assertRaisesRegex(OSError, "disposition could not be written"):
                    receipts.finalize_guarded(folder, row, 10.0)
            original_bytes = (folder / "receipt.json").read_bytes()
            original_manifest = (folder / "manifest.json").read_bytes()
            self.assertEqual(json.loads(original_bytes)["status"], "PASS")
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))
            self.assertIn("completion unavailable", loaded[row["case"]]["tag"])
            for field in ("complete_wall_ns", "proof_wall_ns", "counts", "phases", "observations", "cleanup", "custody"):
                self.assertEqual(loaded[row["case"]][field], row[field])
            receipts.report(run, run / "csv")
            with (run / "csv/performance.csv").open(newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["status"], "FAIL")
            with (run / "csv/verification.csv").open(newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["proof_status"], "FAIL")
            self.assertEqual((folder / "receipt.json").read_bytes(), original_bytes)
            self.assertEqual((folder / "manifest.json").read_bytes(), original_manifest)

    def test_late_completion_and_failed_failure_record_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); row["status"] = "PASS"
            self.selection(run, row)
            folder = run / row["case"]; clock = Clock(9.5); real_write = receipts.write_new
            def incomplete_publication(path, value):
                if Path(path).name == "publication-failure.json":
                    raise OSError("failure disposition could not be written")
                real_write(path, value)
                if Path(path).name in ("publication-completion.json", "publication-completion.attempt.json"):
                    clock.value = 10.1
            with patch.object(receipts.time, "monotonic", clock), patch.object(receipts, "write_new", incomplete_publication):
                with self.assertRaisesRegex(OSError, "disposition could not be written"):
                    receipts.finalize_guarded(folder, row, 10.0)
            self.assertFalse((folder / "publication-completion.json").exists())
            self.assertTrue((folder / "publication-completion.attempt.json").exists())
            self.assertEqual(json.loads((folder / "receipt.json").read_text())["status"], "PASS")
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))
            self.assertIn("completion unavailable", loaded[row["case"]]["tag"])
            self.assertEqual(loaded[row["case"]]["counts"], row["counts"])

    def test_late_provisional_link_is_revoked_before_failed_failure_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); row["status"] = "PASS"
            self.selection(run, row)
            folder = run / row["case"]; clock = Clock(9.5)
            real_write, real_link = receipts.write_new, receipts.os.link
            def failed_disposition(path, value):
                if Path(path).name == "publication-failure.json":
                    raise OSError("failure disposition could not be written")
                real_write(path, value)
            def slow_link(source, target):
                real_link(source, target); clock.value = 10.1
            with patch.object(receipts.time, "monotonic", clock), patch.object(receipts, "write_new", failed_disposition), patch.object(receipts.os, "link", slow_link):
                with self.assertRaisesRegex(OSError, "disposition could not be written"):
                    receipts.finalize_guarded(folder, row, 10.0)
            self.assertFalse((folder / "publication-completion.json").exists())
            self.assertTrue((folder / "publication-completion.attempt.json").exists())
            receipts.verify_manifest(folder)
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))
            self.assertIn("completion unavailable", loaded[row["case"]]["tag"])

    def test_completion_requires_exact_retained_attempt_and_original_bindings(self):
        for altered in ("receipt_sha256", "manifest_sha256", "identity", "publication_observation_sha256", "status", "attempt"):
            with self.subTest(field=altered), tempfile.TemporaryDirectory() as temporary:
                run = Path(temporary); row = self.row(); self.selection(run, row)
                folder = run / row["case"]
                with patch.object(receipts.time, "monotonic", Clock(9.5)):
                    result = receipts.finalize_guarded(folder, row, 10.0)
                receipts.acknowledge_guarded(folder, result)
                _, loaded = receipts.load_run(run)
                self.assertEqual(loaded[row["case"]], result)
                path = folder / ("publication-completion.attempt.json" if altered == "attempt" else "publication-completion.json")
                value = json.loads(path.read_text())
                value["status" if altered == "attempt" else altered] = "changed"
                path.unlink(); path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "publication completion.*binding differs"):
                    receipts.load_run(run)

    def test_failed_completion_attempt_retains_bytes_and_never_publishes_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]; real_write = receipts.write_new
            def incomplete_attempt(path, value):
                if Path(path).name == "publication-completion.attempt.json":
                    Path(path).write_text('{"unfinished":')
                    raise OSError("completion attempt interrupted")
                real_write(path, value)
            with patch.object(receipts.time, "monotonic", Clock(9.5)), patch.object(receipts, "write_new", incomplete_attempt):
                with self.assertRaisesRegex(OSError, "attempt interrupted"):
                    receipts.finalize_guarded(folder, row, 10.0)
            self.assertEqual((folder / "publication-completion.attempt.json").read_text(), '{"unfinished":')
            self.assertFalse((folder / "publication-completion.json").exists())
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))

    def test_completion_margin_is_enforced_before_attempt_and_link(self):
        for selected in ("publication.json", "publication-completion.attempt.json"):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as temporary:
                run = Path(temporary); row = self.row(); self.selection(run, row)
                folder = run / row["case"]; clock = Clock(9.5); real_write = receipts.write_new
                def reach_margin(path, value):
                    real_write(path, value)
                    if Path(path).name == selected:
                        clock.value = 9.75
                with patch.object(receipts.time, "monotonic", clock), patch.object(receipts, "write_new", reach_margin):
                    result = receipts.finalize_guarded(folder, row, 10.0)
                self.assertFalse((folder / "publication-completion.json").exists())
                self.assertEqual((result["status"], result["proof_status"]), ("FAIL", "FAIL"))
                _, loaded = receipts.load_run(run)
                self.assertIn("guard reached before completion publication", loaded[row["case"]]["tag"])

    def test_interrupted_link_validation_revokes_only_owned_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]; real_read = Path.read_bytes
            def interrupted_read(path):
                if path.name == "publication-completion.json":
                    raise OSError("completion post-publication read failed")
                return real_read(path)
            with patch.object(receipts.time, "monotonic", Clock(9.5)), patch.object(Path, "read_bytes", interrupted_read):
                with self.assertRaisesRegex(OSError, "post-publication read failed"):
                    receipts.finalize_guarded(folder, row, 10.0)
            self.assertFalse((folder / "publication-completion.json").exists())
            self.assertTrue((folder / "publication-completion.attempt.json").exists())
            receipts.verify_manifest(folder)
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))

    def test_absent_guarded_manifest_reports_failure_without_unauthenticated_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]
            untrusted = {**row, "case": "wrong-case", "source_commit": "untrusted-source"}
            with patch.object(receipts.time, "monotonic", Clock(9.5)), patch.object(receipts, "manifest", side_effect=OSError("manifest write failed")):
                with self.assertRaisesRegex(OSError, "manifest write failed"):
                    receipts.finalize_guarded(folder, untrusted, 10.0)
            original = (folder / "receipt.json").read_bytes()
            _, loaded = receipts.load_run(run)
            result = loaded[row["case"]]
            self.assertEqual((result["status"], result["proof_status"]), ("FAIL", "FAIL"))
            for name in ("family", "case", "source_commit", "product_tree", "image"):
                self.assertEqual(result[name], row[name])
            receipts.report(run, run / "csv")
            with (run / "csv/performance.csv").open(newline="") as stream:
                performance = next(csv.DictReader(stream))
            with (run / "csv/verification.csv").open(newline="") as stream:
                proof = next(csv.DictReader(stream))
            self.assertEqual((performance["status"], proof["proof_status"]), ("FAIL", "FAIL"))
            self.assertIn("authentication/publication incomplete", performance["tag"])
            for name in ("complete_wall_ns", "requests", "owner_jobs", "statements", "mount_ns", "command_ns", "commit_ns", "unmount_ns", "store_allocated_bytes", "cleanup", "daemon_sha256"):
                self.assertEqual(performance[name], "UNAVAILABLE")
            self.assertEqual(proof["proof_wall_ns"], "UNAVAILABLE")
            self.assertEqual((folder / "receipt.json").read_bytes(), original)

    def test_missing_legacy_manifest_and_tampered_existing_manifest_still_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            receipts.write_new(run / row["case"] / "receipt.json", row)
            with self.assertRaises(FileNotFoundError):
                receipts.load_run(run)
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]
            with patch.object(receipts.time, "monotonic", Clock(9.5)):
                result = receipts.finalize_guarded(folder, row, 10.0)
            receipts.acknowledge_guarded(folder, result)
            path = folder / "manifest.json"
            record = json.loads(path.read_text()); record["files"]["receipt.json"] = "bad-hash"
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "retained evidence changed"):
                receipts.load_run(run)

    def test_missing_completion_fails_closed_and_legacy_finalization_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]
            receipts.write_new(folder / "receipt.json", row); receipts.manifest(folder)
            _, loaded = receipts.load_run(run)
            self.assertEqual(loaded[row["case"]], row)
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary); row = self.row(); self.selection(run, row)
            folder = run / row["case"]; clock = Clock(9.5); real_write = receipts.write_new
            def absent_observation(path, value):
                if Path(path).name == "publication.json":
                    raise OSError("publication observer failed")
                real_write(path, value)
            with patch.object(receipts.time, "monotonic", clock), patch.object(receipts, "write_new", absent_observation):
                with self.assertRaisesRegex(OSError, "observer failed"):
                    receipts.finalize_guarded(folder, row, 10.0)
            _, loaded = receipts.load_run(run)
            self.assertEqual((loaded[row["case"]]["status"], loaded[row["case"]]["proof_status"]), ("FAIL", "FAIL"))
            self.assertIn("completion unavailable", loaded[row["case"]]["tag"])


if __name__ == "__main__":
    unittest.main()

"""The I/O-stall label: Commit-interval counts from observer rows, label threshold, no verdict change."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import io_observer, receipts

CONTAINER = "abcdef012345" + "0" * 52
HOST_MINUS_VM = 2.5


def cgroup(io_us, dirty):
    return {"memory_current": 2**30, "io_pressure": [io_us, io_us], "memory_pressure": [0, 0],
            "memory": {"file": 2**29, "file_dirty": dirty, "file_writeback": 0, "pgscan": 0, "pgsteal": 0},
            "events": {"max": 0}, "io": {"wbytes": 0}, "cpu": {"usage_usec": 0}}


def vm():
    return {"nr_free_pages": 1000, "nr_dirty": 10, "nr_writeback": 5, "nr_dirty_threshold": 160000,
            "nr_dirty_background_threshold": 80000, "pgscan_kswapd": 0, "pgscan_direct": 0, "pgpgout": 0}


def observer(origin, wait_per_second):
    """Rows every 100 ms for 6 s of runtime time; I/O wait accrues only from 1 s to 3 s."""
    lines, arrivals, waited = [], [], 0
    for step in range(61):
        at = step / 10
        if 1 < at <= 3:
            waited += int(wait_per_second * 1e5)
        wall = origin + at - HOST_MINUS_VM
        lines.append((json.dumps({"wall": wall, "vm": vm(), "vm_io_pressure": [0, 0], "vm_memory_pressure": [0, 0],
                                  "cgroups": {CONTAINER[:12]: cgroup(waited, 2**20)}}) + "\n").encode())
        arrivals.append(wall + HOST_MINUS_VM + 0.004 + (step % 3) * 0.01)
    result = object.__new__(io_observer.Observer)
    result.name, result.lines, result.arrivals, result.lock = "layerfs-fsb-observer-test", lines, arrivals, threading.Lock()
    result.record = {"script": "core/docs/issues/320/tools/cgroup_observer.py", "script_sha256": "0" * 64}
    return result


@unittest.skipUnless(hasattr(os.stat_result, "st_birthtime"), "host file birth time is the runtime origin")
class IoStallLabel(unittest.TestCase):
    def sample(self, wait_per_second, events=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.events.jsonl"
            commit = {"sequence": 2, "event": "commit", "span": {"start_ns": 1_000_000_000, "end_ns": 3_000_000_000,
                                                                 "duration_ns": 2_000_000_000}}
            path.write_text("".join(json.dumps(row) + "\n" for row in (events if events is not None else
                                    [{"sequence": 1, "event": "command", "span": None}, commit])))
            row = {"interference": "declared", "container": CONTAINER, "status": "PASS"}
            io_observer.CURRENT = observer(os.stat(path).st_birthtime, wait_per_second)
            try:
                io_observer.attach(directory, row)
            finally:
                io_observer.CURRENT = None
            return row

    def test_wait_above_threshold_is_io_stalled_without_status_change(self):
        row = self.sample(0.5)
        result = row["io_observer"]
        self.assertEqual((result["status"], result["label"], row["status"]), ("AVAILABLE", "IO_STALLED", "PASS"))
        self.assertAlmostEqual(result["ct_io_pressure_fraction"], 0.5, delta=0.06)
        self.assertAlmostEqual(result["alignment"]["host_minus_vm_s"], HOST_MINUS_VM + 0.004, places=4)
        commit = result["commits"][0]
        self.assertEqual(commit["commit_ms"], 2000.0)
        self.assertEqual(commit["ct_file_dirty_max_MiB"], 1.0)
        self.assertEqual(commit["vm_dirty_plus_wb_max_MiB"], 0.1)
        self.assertIn("ct_pgscan", commit)
        self.assertIn("vm_pgscan_kswapd", commit)
        self.assertIn("read-only cgroup observer container layerfs-fsb-observer-test", row["interference"])
        self.assertTrue(row["interference"].startswith("declared; "))

    def test_wait_below_threshold_is_not_stalled(self):
        result = self.sample(0.1)["io_observer"]
        self.assertEqual(result["label"], "NOT_STALLED")
        self.assertLessEqual(result["ct_io_pressure_fraction"], io_observer.STALL_FRACTION)

    def test_no_commit_and_uncovered_commit(self):
        self.assertEqual(self.sample(0.5, [{"sequence": 1, "event": "command", "span": None}])["io_observer"]["label"], "NO_COMMIT")
        late = {"sequence": 1, "event": "commit", "span": {"start_ns": 5_000_000_000, "end_ns": 9_000_000_000, "duration_ns": 4_000_000_000}}
        result = self.sample(0.5, [late])["io_observer"]
        self.assertEqual((result["status"], result["label"]), ("UNAVAILABLE", "UNAVAILABLE"))

    def test_without_observer_receipt_says_not_run(self):
        row = {"interference": "declared"}
        io_observer.attach("/nonexistent", row)
        self.assertEqual((row["io_observer"]["status"], row["interference"]), ("NOT_RUN", "declared"))


class IoStallReport(unittest.TestCase):
    def test_label_is_appended_to_report_tag_only(self):
        selection = {"family": "workspace_change_locality", "cases": [{"id": "case", "cache_class": "B"}]}
        recorded = {"case": {"status": "INELIGIBLE", "tag": "original", "io_observer": {"label": "IO_STALLED", "ct_io_pressure_fraction": 0.41}}}
        performance, _ = receipts.result_rows(selection, recorded)
        self.assertEqual(performance[0]["status"], "INELIGIBLE")
        self.assertEqual(performance[0]["tag"], "original; IO_STALLED: container I/O wait 41% of its Commits (diagnostic label; status unchanged)")


if __name__ == "__main__":
    unittest.main()

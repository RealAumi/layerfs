"""Read-only kernel observer beside each sample and its diagnostic I/O-stall label.

`bench.py run` starts `core/docs/issues/320/tools/cgroup_observer.py` in its own
container of the pinned image before each case and stops it after the case
returns. The container binds the Docker VM's cgroup tree read-only, has no
network and writes nothing but its stdout: one row of VM and new-container
kernel counters every 100 ms. Its rows land in `<sample>/io-observer/`.

Before the sample's receipt is written, `attach` adds the counts of
`commit_kernel_window.py` over every Commit of the sampled container and a
label. Clocks: the runtime's event origin is the host birth time of
`runtime.events.jsonl` (the runtime creates it right before taking its origin);
VM wall minus host wall is bounded by the smallest host arrival time minus VM
wall over all rows, so the error is the shortest pipe latency, not clock drift.

Label (diagnostic only; it never changes a status, verdict or limit):
- IO_STALLED: the container waited on I/O ("some" pressure) for more than
  STALL_FRACTION of the observed Commit interval;
- NOT_STALLED: at or below it;
- NO_COMMIT: the runtime recorded no Commit;
- UNAVAILABLE: no observer, no rows covering every Commit, or no alignment.

STALL_FRACTION is 20%. Evidence (core/docs/issues/320/PROGRESS.md, "Issue 321
follow-up — Store-write stall cause"), the same dense-rewrite case each time:
unstalled 8.2 ms of a 6,077.4 ms Commit (0.1%) and 657.0 ms of 7,757.6 ms
(8.5%); stalled 4,483.3 ms of 11,805.2 ms (38.0%) and 5,319.5 ms of 12,168.8 ms
(43.7%). 20% is more than twice the highest unstalled fraction and about half
the lowest stalled one; it is a dividing line from four samples, not a
qualified bound.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time

from . import identity

TOOLS = identity.ROOT / "core/docs/issues/320/tools"
SCRIPT = TOOLS / "cgroup_observer.py"
WINDOW = TOOLS / "commit_kernel_window.py"
STALL_FRACTION = 0.20
SELF_STOP_SECONDS = 300
READY_SECONDS = 15
CURRENT = None
START_FAILURE = None


def _window_module():
    spec = importlib.util.spec_from_file_location("commit_kernel_window", WINDOW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Observer:
    """One observer container; rows and their host arrival times are kept as read."""

    def __init__(self, folder, socket):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.name = "layerfs-fsb-observer-" + secrets.token_hex(8)
        self.docker = ["docker", "--host", "unix://" + socket]
        self.argv = [*self.docker, "run", "--rm", "-i", "--name", self.name, "--network", "none",
                     "--pull", "never", "-v", "/sys/fs/cgroup:/hostcg:ro", identity.IMAGE,
                     "python3", "-B", "-", str(SELF_STOP_SECONDS)]
        self.record = {"schema": "fs-bench-pro-io-observer-v1", "argv": self.argv, "container_name": self.name,
                       "script": str(SCRIPT.relative_to(identity.ROOT)), "script_sha256": identity.sha256(SCRIPT),
                       "window": str(WINDOW.relative_to(identity.ROOT)), "window_sha256": identity.sha256(WINDOW),
                       "self_stop_seconds": SELF_STOP_SECONDS, "status": "ATTEMPT_DECLARED"}
        (self.folder / "attempt.json").write_text(json.dumps(self.record, indent=2, sort_keys=True) + "\n")
        self.lines, self.arrivals = [], []
        self.lock = threading.Lock()
        self.ready = threading.Event()  # first row read, or the stream ended without one
        self.rows = (self.folder / "rows.jsonl").open("xb")
        self.stderr = (self.folder / "observer.stderr").open("xb")
        with SCRIPT.open("rb") as script:
            self.process = subprocess.Popen(self.argv, stdin=script, stdout=subprocess.PIPE, stderr=self.stderr,
                                            start_new_session=True)
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        self.ready.wait(READY_SECONDS)
        with self.lock:
            self.record["ready"] = bool(self.lines)
        self.record["status"] = "RUNNING" if self.record["ready"] else "NOT_READY"

    def _read(self):
        for line in self.process.stdout:
            arrived = time.time()
            self.rows.write(line)
            self.rows.flush()
            with self.lock:
                self.lines.append(line)
                self.arrivals.append(arrived)
            self.ready.set()
        self.rows.close()
        self.ready.set()

    def declaration(self):
        return (f"read-only cgroup observer container {self.name} ({self.record['script']}, sha256 "
                f"{self.record['script_sha256'][:12]}) beside this sample: 100 ms reads of /sys/fs/cgroup and /proc, no writes")

    def summary(self, output, container):
        with self.lock:
            lines, arrivals = list(self.lines), list(self.arrivals)
        base = {"status": "UNAVAILABLE", "label": "UNAVAILABLE", "stall_fraction_threshold": STALL_FRACTION,
                "observer": self.name, "rows_used": len(lines),
                "rows_prefix_sha256": hashlib.sha256(b"".join(lines)).hexdigest(),
                "rows": "io-observer/rows.jsonl (moved there after the case returns)",
                "scope": "diagnostic label only; no status, verdict or limit depends on it"}
        events_path = Path(output) / "runtime.events.jsonl"
        if not lines:
            return {**base, "reason": "observer produced no rows"}
        if not events_path.exists():
            return {**base, "reason": "no runtime.events.jsonl"}
        events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
        commits = [event for event in events if event["event"] == "commit" and event.get("span")]
        if not commits:
            return {**base, "status": "AVAILABLE", "label": "NO_COMMIT", "reason": "the runtime recorded no Commit"}
        if not isinstance(container, str) or len(container) != 64:
            return {**base, "reason": "exact sample container identity unavailable"}
        origin = getattr(os.stat(events_path), "st_birthtime", None)
        if origin is None:
            return {**base, "reason": "host file birth time unavailable for the runtime origin"}
        rows = [json.loads(line) for line in lines]
        host_minus_vm = min(arrived - row["wall"] for arrived, row in zip(arrivals, rows))
        window = _window_module()
        name = container[:12]
        measured, waited, observed = [], 0.0, 0.0
        for event in commits:
            span = event["span"]
            start = origin + span["start_ns"] / 1e9 - host_minus_vm
            end = origin + span["end_ns"] / 1e9 - host_minus_vm
            rows_in = window.window(rows, name, start, end, enclosing=True)
            entry = {"sequence": event["sequence"], "commit_ms": round(span["duration_ns"] / 1e6, 1), "rows": len(rows_in)}
            if len(rows_in) < 2:
                measured.append({**entry, "status": "UNAVAILABLE", "reason": "observer rows do not cover this Commit"})
                continue
            values = window.counts(rows_in, name)
            interval = (rows_in[-1]["wall"] - rows_in[0]["wall"]) * 1e3
            waited += values["ct_io_pressure_some_ms"]
            observed += interval
            measured.append({**entry, "status": "AVAILABLE", "observed_ms": round(interval, 1),
                             "ct_io_pressure_fraction": round(values["ct_io_pressure_some_ms"] / interval, 4), **values})
        result = {**base, "commits": measured,
                  "alignment": {"host_minus_vm_s": round(host_minus_vm, 6),
                                "method": "runtime origin = host birth time of runtime.events.jsonl; VM wall = host wall - min(host arrival - VM wall) over rows; each Commit's rows from the last at or before its start to the first at or after its end"}}
        if any(entry["status"] != "AVAILABLE" for entry in measured):
            return {**result, "reason": "observer rows do not cover every Commit"}
        fraction = waited / observed
        return {**result, "status": "AVAILABLE", "ct_io_pressure_some_ms": round(waited, 1), "observed_ms": round(observed, 1),
                "ct_io_pressure_fraction": round(fraction, 4),
                "label": "IO_STALLED" if fraction > STALL_FRACTION else "NOT_STALLED"}

    def stop(self, destination):
        """Kill the observer once, wait for its stream and move its folder into `destination` if it exists."""
        try:
            kill = subprocess.run([*self.docker, "kill", self.name], capture_output=True, text=True, timeout=15, check=False)
            self.record["kill"] = {"exit_code": kill.returncode, "stderr": kill.stderr.strip()[-500:]}
        except Exception as error:
            self.record["kill"] = {"exit_code": None, "failure": f"{type(error).__name__}: {error}"}
        try:
            self.record["exit_code"] = self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.record["exit_code"] = None
            self.record["custody"] = "docker run client still running after 15 s; its container stops itself after self_stop_seconds"
        self.thread.join(5)
        self.stderr.close()
        with self.lock:
            lines, arrivals = list(self.lines), list(self.arrivals)
        (self.folder / "arrivals.txt").write_text("".join(f"{value:.6f}\n" for value in arrivals))
        self.record.update(status="STOPPED", rows=len(lines), rows_sha256=hashlib.sha256(b"".join(lines)).hexdigest())
        (self.folder / "observer.json").write_text(json.dumps(self.record, indent=2, sort_keys=True) + "\n")
        destination = Path(destination)
        if destination.is_dir() and not (destination / "io-observer").exists():
            shutil.move(str(self.folder), str(destination / "io-observer"))
            return destination / "io-observer"
        return self.folder


def start(folder, build_folder):
    """Start one observer on the build's Docker socket.

    A failure to start is recorded and leaves the case to run without one.
    """
    global CURRENT, START_FAILURE
    CURRENT, START_FAILURE = None, None
    try:
        CURRENT = Observer(folder, json.loads((Path(build_folder) / "build.json").read_text())["socket"])
    except Exception as error:
        START_FAILURE = f"{type(error).__name__}: {error}"
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder) / "start-failure.txt").write_text(START_FAILURE + "\n")
    return CURRENT


def stop(destination):
    global CURRENT
    observer, CURRENT = CURRENT, None
    return observer.stop(destination) if observer is not None else None


def attach(output, row):
    """Add the observer's Commit counts and label to a receipt row before it is written."""
    if CURRENT is None:
        row["io_observer"] = {"status": "NOT_RUN", "label": "UNAVAILABLE", "reason": (
            "observer failed to start: " + START_FAILURE if START_FAILURE
            else "no observer was started for this invocation; bench.py run starts one per case")}
        return
    row["interference"] = "; ".join(filter(None, (row.get("interference"), CURRENT.declaration())))
    try:
        row["io_observer"] = CURRENT.summary(output, row.get("container"))
    except Exception as error:
        row["io_observer"] = {"status": "UNAVAILABLE", "label": "UNAVAILABLE", "observer": CURRENT.name,
                              "reason": f"{type(error).__name__}: {error}"}

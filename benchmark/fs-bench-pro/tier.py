#!/usr/bin/env python3
"""Kept workload tiers: all for the owner's terminal; next for exactly one agent case."""
import argparse
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import bench
from engine import fixtures, identity, prepared_inputs, sample_cleanup

ROOT = identity.ROOT
HOME = ROOT / "core/target/sdk-refactor"
RESULTS = ROOT / "benchmark-results/fs-bench-pro"
PREPARED = RESULTS / "kept-fixtures"
EXTENDED_RUNS = {
    "v016-mixed-exhaustive-500mb-30000-k100-v1",
    "v016-workspace-mixed-500mb-30000-k100-v1",
    "v016-branch-mixed-500mb-30000-k10-v1",
    "v016-branch-mixed-500mb-30000-k100-v1",
    "dedup-history-distributed-500", "dedup-history-unrelated-500-mixed-v2",
}
EXTENDED_PREPARATIONS = {
    "v016-mixed-exhaustive-500mb-30000-k100-v1",
    "v016-branch-mixed-500mb-30000-k100-v1",
}


def policy(kind, case):
    extended = case in (EXTENDED_RUNS if kind == "run" else EXTENDED_PREPARATIONS)
    return 300 if extended else 118


def prepared_folder(case, current, build):
    key = prepared_inputs.preparation_key(case["fixture"]["recipe"],
        {k: v for k, v in case.items() if k != "family"}, current, build)
    return PREPARED / prepared_inputs.digest(key) / case["fixture"]["recipe"], key


def invoke(argv, limit, log):
    """One bounded invocation, no retries; kill its process group at the declared ceiling."""
    started = time.monotonic_ns()
    started_unix = time.time_ns()
    child = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True, env={**os.environ, "LAYERFS_CONSTRUCTION_WORKERS": "1"})
    expired = False
    try:
        output, _ = child.communicate(timeout=limit - 5)
    except subprocess.TimeoutExpired:
        expired = True
        os.killpg(child.pid, signal.SIGKILL)
        output, _ = child.communicate(timeout=1)
    record = {"argv": argv, "exit": child.returncode, "expired": expired,
              "started_unix_ns": started_unix, "completed_unix_ns": time.time_ns(),
              "whole_run_wall_ns": time.monotonic_ns() - started, "wall_stop_seconds": limit - 5}
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("x") as stream:
        stream.write(json.dumps(record) + "\n" + output)
    return record


def compare_counts(family, case, counts):
    reference = ROOT / "core/docs/issues/319/TERMINAL-RESULTS.csv"
    with reference.open() as stream:
        row = next(value for value in csv.DictReader(stream) if (value["family"], value["case"]) == (family, case))
    expected = {key: int(row[key]) if row[key].isdigit() else None
                for key in ("requests", "owner_jobs", "statements")}
    raw = {key: (counts or {}).get(key) for key in expected}
    actual = {key: value if type(value) is int else None for key, value in raw.items()}
    return {"status": ("UNAVAILABLE_UNCHANGED" if all(value is None for value in expected.values()) else "PASS")
                if expected == actual else "FAIL", "expected": expected, "actual": actual, "actual_raw": raw,
            "reference_sha256": identity.sha256(reference)}


def ensure_prepared(case, folder, key, build_folder, campaign, owner_all):
    if (folder / "prepared.json").exists():
        prepared = fixtures.load(folder, case["fixture"]["recipe"])
        if prepared.get("preparation_key") != key:
            raise ValueError("closed preparation has another producer identity; never refresh it")
        return prepared
    command = [sys.executable, "-B", str(ROOT / "benchmark/fs-bench-pro/bench.py"),
               "prepare", case["fixture"]["recipe"], "--build", str(build_folder), "--out", str(folder)]
    if not owner_all:
        print(json.dumps({"status": "NOT_READY", "case": case["id"], "reason":
            "prepare this distinct fixture with the bounded tracked harness before next; no sample started",
            "prepare_argv": command, "wall_limit_seconds": policy("prepare", case["id"])}))
        return None
    record = invoke(command, policy("prepare", case["id"]), campaign / "logs" / ("prepare-" + case["id"] + ".log"))
    if record["exit"] != 0 or record["expired"]:
        raise ValueError("failed preparation retained; no automatic retry")
    return fixtures.load(folder, case["fixture"]["recipe"])


def run_case(case, args, campaign, current, build, protected, owner_all):
    family = case["family"]
    output = campaign / ("run-" + family)
    sample = output / case["id"]
    if sample.exists():
        raise ValueError("case already has an attempted output at this identity; never replay")
    folder, key = prepared_folder(case, current, build)
    if ensure_prepared(case, folder, key, args.build, campaign, owner_all) is None:
        return None
    run_started = time.monotonic_ns()
    report = (ROOT / "benchmark_agent_report.md").read_bytes()
    command = [sys.executable, "-B", str(ROOT / "benchmark/fs-bench-pro/bench.py"), "run",
               family, "--case", case["id"], "--build", str(args.build), "--prepared", str(folder), "--out", str(output)]
    record = invoke(command, policy("run", case["id"]), campaign / "logs" / ("run-" + case["id"] + ".log"))
    record.update(tier=args.tier, family=family, case=case["id"], source_commit=current["source_commit"],
                  report_template_sha256=hashlib.sha256(report).hexdigest())
    cleanup = sample_cleanup.drop_test_copy(sample, build["socket"], protected)
    record["cleanup"] = cleanup
    receipt = sample / "receipt.json"
    if receipt.exists():
        row = json.loads(receipt.read_text())
        record.update(receipt_sha256=identity.sha256(receipt), status=row.get("status"),
                      functional_status=row.get("functional_status"), proof_status=row.get("proof_status"),
                      counts=row.get("counts"), phases=row.get("phases"),
                      count_reproduction=compare_counts(family, case["id"], row.get("counts")))
    else:
        record.update(status="FAIL", reason="bounded invocation has no completed receipt; retained, never replayed")
    record["invocation_wall_ns"] = record["whole_run_wall_ns"]
    record["whole_run_wall_ns"] = time.monotonic_ns() - run_started
    record["completed_unix_ns"] = time.time_ns()
    with (campaign / "journal.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)
    if identity.source_identity()["files"] != current["files"]:
        raise ValueError("tracked source changed during the case")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("all", "next"))
    parser.add_argument("tier", choices=("everyday", "heavy"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--case", help="one explicit kept case ID for a family gate; next only")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.tag):
        parser.error("tag must be a stable safe campaign name")
    if args.case and args.mode != "next":
        parser.error("explicit case is confined to next")
    args.build = args.build.resolve()
    HOME.mkdir(parents=True, exist_ok=True)
    with (HOME / "measurement.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current, build = identity.source_identity(), identity.load_build(args.build)
        if not current["source_clean"] or build["identity"]["source_commit"] != current["source_commit"]:
            raise ValueError("commit and seal this exact identity before sampling")
        campaign = RESULTS / ("tier-" + args.tag)
        campaign.mkdir(exist_ok=True)
        registration = campaign / "campaign.json"
        definition = {"source_commit": current["source_commit"], "product_tree": current["product_tree"],
                      "build_sha256": identity.sha256(args.build / "build.json"), "tag": args.tag}
        if registration.exists():
            if json.loads(registration.read_text()) != definition:
                raise ValueError("campaign identity differs; append-only output cannot change source")
        else:
            registration.write_text(json.dumps(definition, indent=2) + "\n")
        protection = campaign / "protected-volumes.json"
        if not protection.exists():
            result = subprocess.run(["docker", "--host", "unix://" + build["socket"], "volume", "ls", "--quiet"],
                                    capture_output=True, text=True, timeout=15, check=True)
            protection.write_text(json.dumps(result.stdout.split()) + "\n")
        protected = set(json.loads(protection.read_text()))
        cases = bench.catalogue(args.tier)
        if args.case:
            cases = [case for case in cases if case["id"] == args.case]
            if len(cases) != 1:
                parser.error("case is not one kept member of the declared tier")
        else:
            cases = [case for case in cases if not (campaign / ("run-" + case["family"]) / case["id"]).exists()]
        selected = cases if args.mode == "all" else cases[:1]
        begun = time.monotonic_ns()
        for case in selected:
            record = run_case(case, args, campaign, current, build, protected, args.mode == "all")
            if record is None:
                return 2
            if (record.get("functional_status") != "PASS" or record.get("proof_status") != "PASS" or record["expired"]
                    or record.get("count_reproduction", {}).get("status") == "FAIL"
                    or record.get("cleanup", {}).get("manifest") != "PASS"):
                # The next invocation can advance to an unrun case after source/receipt diagnosis.
                # The attempted output remains immutable and is never replayed.
                return 1
        if args.mode == "all":
            end = {"tier": args.tier, "source_commit": current["source_commit"], "tier_wall_ns": time.monotonic_ns() - begun,
                   "cases_this_command": len(selected), "scope": "owner whole-tier terminal invocation, including preparation/proof/cleanup"}
            with (campaign / "tier-walls.jsonl").open("a") as stream:
                stream.write(json.dumps(end) + "\n")
            print(json.dumps(end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

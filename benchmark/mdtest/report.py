#!/usr/bin/env python3
"""mdtest report: results.csv, commit.csv and summary.json from a run's receipts.

Reads RUN/results.jsonl (one row per case and arm, case.mjs or run.sh's
pt_case), each case's
mdtest output RUN/cases/<case>-<arm>.txt, RUN/ledger.jsonl (the Commit) and
RUN/commands.log (the 1-minute host load at each client's start). Writes
the three files into RUN, or into OUT when given.

ops_per_s is the Mean column of mdtest's `SUMMARY rate` table and wall_ms
the Mean column of its `SUMMARY time` table (printed with -P; mdtest labels
it ms/op but prints each phase's seconds, 3 decimals), times 1000. With
-i 1 Max, Min and Mean are the same one sample. Phases mdtest did not run
(both values 0, as in the -C and -r passes) are left out.

summary.json's `ratios` are layerfs ÷ sandbox-disk for every phase both
ran. A run with the passthrough-fuse arm also gets ratios.csv and
summary.json `three_arm`: each case and phase all three arms ran, without
the tree creation and removal phases (1-21 folders, below mdtest's 1 ms
resolution), with layerfs ÷ passthrough-fuse (like-for-like FUSE),
layerfs ÷ sandbox-disk and passthrough-fuse ÷ sandbox-disk (FUSE alone).

  report.py RUN [OUT]
"""
import csv
import json
import re
import sys
from pathlib import Path

ROW = re.compile(r"^\s+((?:File|Directory|Tree) \w+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$")


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def tables(text):
    """{phase: (ops_per_s, wall_ms)} from mdtest's rate and time tables."""
    rate, time, current = {}, {}, None
    for line in text.splitlines():
        if line.startswith("SUMMARY rate"):
            current = rate
        elif line.startswith("SUMMARY time"):
            current = time
        elif current is not None and (m := ROW.match(line)):
            current[m.group(1).lower().replace(" ", "_")] = float(m.group(4))
    return {p: (rate[p], round(time.get(p, 0.0) * 1000, 3)) for p in rate if rate[p] or time.get(p)}


def loads(run):
    """{client step name: 1-minute load} for the clients that exited 0."""
    out = {}
    for line in (run / "commands.log").read_text().splitlines():
        name, _, _, status, load = line.split("\t")
        if status == "exit=0":
            out[name] = float(load.split("=")[1])
    return out


def step_load(load, case, arm):
    if case.startswith("commit-"):
        return load.get(case)
    names = [n for n in load if re.fullmatch(rf"case-{re.escape(case)}-{arm}-\d+", n)]
    return load[names[-1]] if names else None


def ratio(a, b):
    return round(a / b, 4) if b else None


def three_arm(by):
    """Rows for each case and phase all three arms ran, tree phases left out."""
    out = []
    for (c, p, a), v in by.items():
        if a != "layerfs" or p in ("tree_creation", "tree_removal"):
            continue
        pt, disk = by.get((c, p, "passthrough-fuse")), by.get((c, p, "sandbox-disk"))
        if pt is None or disk is None:
            continue
        out.append({"case": c, "phase": p, "layerfs": v, "passthrough_fuse": pt, "sandbox_disk": disk,
                    "layerfs_over_pt": ratio(v, pt), "layerfs_over_disk": ratio(v, disk), "pt_over_disk": ratio(pt, disk)})
    return out


def main():
    run = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else run
    out.mkdir(parents=True, exist_ok=True)
    load = loads(run)
    rows, failures = [], []
    for r in jsonl(run / "results.jsonl"):
        text = (run / "cases" / f"{r['case']}-{r['arm']}.txt").read_text()
        phases = tables(text)
        if r["exec_exit"] != 0 or r["rc"] != 0 or not phases:
            failures.append({"case": r["case"], "arm": r["arm"], "rc": r["rc"], "exec_exit": r["exec_exit"],
                             "command": r["command"], "tail": text[-1500:]})
        for phase, (rate, wall) in phases.items():
            rows.append({"case": r["case"], "arm": r["arm"], "procs": r["procs"], "items_per_proc": r["items_per_proc"],
                         "unique_dir": "yes" if "-u" in r["args"].split() else "no", "phase": phase,
                         "ops_per_s": rate, "wall_ms": wall, "load": step_load(load, r["case"], r["arm"])})
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case", "arm", "procs", "items_per_proc", "unique_dir", "phase", "ops_per_s", "wall_ms", "load"])
        w.writeheader()
        w.writerows(rows)

    commits = [r for r in jsonl(run / "ledger.jsonl") if r.get("step") == "commit"]
    created = next((r for r in jsonl(run / "results.jsonl") if r["case"] == "commit-create"), None)
    with open(out / "commit.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["message", "files_left", "commit_ms", "kind", "commit", "base", "logical", "newCanonical", "newStored", "newMetadata", "load"])
        for r in commits:
            c = r["value"].get("commit") or {}
            files = created["procs"] * created["items_per_proc"] if created else None
            w.writerow([r["message"], files, r["commit_ms"], r["value"]["kind"], c.get("id"), c.get("base"), c.get("logical"),
                        c.get("newCanonical"), c.get("newStored"), c.get("newMetadata"), load.get("commit")])

    # layerfs ÷ sandbox-disk ops/s for each case and phase both arms ran.
    by = {(r["case"], r["phase"], r["arm"]): r["ops_per_s"] for r in rows}
    ratios = [{"case": c, "phase": p, "layerfs": v, "sandbox_disk": by[(c, p, "sandbox-disk")],
               "ratio": round(v / by[(c, p, "sandbox-disk")], 4) if by[(c, p, "sandbox-disk")] else None}
              for (c, p, a), v in by.items() if a == "layerfs" and (c, p, "sandbox-disk") in by]
    summary = {"run": run.name, "rows": len(rows), "failures": failures, "ratios": ratios,
               "commit": [{"commit_ms": r["commit_ms"], **r["value"]} for r in commits]}
    if any(r["arm"] == "passthrough-fuse" for r in rows):
        summary["three_arm"] = three_arm(by)
        with open(out / "ratios.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary["three_arm"][0]) if summary["three_arm"] else ["case"])
            w.writeheader()
            w.writerows(summary["three_arm"])
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({"rows": len(rows), "failures": len(failures), "commits": [r["commit_ms"] for r in commits]}))


if __name__ == "__main__":
    main()

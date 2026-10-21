#!/usr/bin/env python3
"""fsx report: results.csv, commit.csv and summary.json from a run's receipts.

Reads RUN/results.jsonl (one row per case and arm, case.mjs), each case's
read-back RUN/cases/<case>.txt (fsx's own output) and RUN/ledger.jsonl (the
Commit). Writes the three files into RUN, or into OUT when given.

  report.py RUN [OUT]
"""
import csv
import json
import re
import sys
from pathlib import Path

INFO = re.compile(r"^(Seed set|.*largest ever|.*disabling!$|skipping |mapped (reads|writes) DISABLED|=== )")


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def unsupported(text):
    """fsx's own 'disabling' lines, as short op names."""
    names = []
    for line in text.splitlines():
        if not line.endswith("disabling!"):
            continue
        m = re.search(r"does not support (.*), disabling!", line)
        if m and m.group(1).startswith("fallocate mode "):
            name = "fallocate(" + m.group(1)[len("fallocate mode "):].replace("FALLOC_FL_", "").replace(" | ", "|") + ")"
        elif m and m.group(1) == "atomic writes":
            name = "atomic writes (IO stack)"
        elif m:
            name = m.group(1)
        elif "atomic writes need O_DIRECT" in line:
            name = "atomic writes (needs -Z)"
        else:
            name = line.split(": ", 1)[-1]
        if name not in names:
            names.append(name)
    return names


def parse(row, text):
    out = text.split("=== f.fsxlog tail")[0]
    ok = re.search(r"All (\d+) operations completed A-OK!", out)
    dump = re.search(r"LOG DUMP \((\d+) total operations\)", out)
    ops = int(ok.group(1)) if ok else int(dump.group(1)) if dump else None
    if row["exec_exit"] != 0 or row["rc"] is None:
        result = "HARNESS"
    elif row["rc"] == 0 and ok:
        result = "PASS"
    else:
        result = "FAIL"
    first = ""
    if result != "PASS":
        before = out.split("LOG DUMP")[0].splitlines()
        bad = next((l for l in before if l.strip() and not INFO.match(l)), "")
        ops_lines = [l for l in out.split("LOG DUMP")[1].splitlines()[1:] if re.match(r"^\s*\d+\(", l)] if dump else []
        first = " ".join((bad + (f" | last op: {ops_lines[-1]}" if ops_lines else "")).split())
        if result == "HARNESS":
            first = first or f"exec exit {row['exec_exit']}: {row['exec_stderr'][:200]}"
    wall_ms = row["tool_ns"] / 1e6 if row["tool_ns"] is not None else None
    return {
        "variant": row["variant"], "arm": row["arm"], "seed": row["seed"], "args": row["args"],
        "ops": ops, "exit": row["rc"], "result": result,
        "wall_ms": round(wall_ms, 1) if wall_ms is not None else None,
        "ops_per_s": round(ops / (wall_ms / 1000), 1) if ops and wall_ms else None,
        "unsupported_ops": ";".join(unsupported(out)), "first_failure": first,
        "ops_requested": row["ops_requested"], "exec_ms": row["exec_ms"],
    }


def main():
    run = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else run
    out.mkdir(parents=True, exist_ok=True)
    rows = [parse(r, (run / "cases" / f"{r['case']}.txt").read_text()) for r in jsonl(run / "results.jsonl")]
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    commits = [r for r in jsonl(run / "ledger.jsonl") if r.get("step") == "commit"]
    with open(out / "commit.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["message", "commit_ms", "kind", "commit", "base", "logical", "newCanonical", "newStored", "newMetadata"])
        for r in commits:
            c = r["value"].get("commit") or {}
            w.writerow([r["message"], r["commit_ms"], r["value"]["kind"], c.get("id"), c.get("base"),
                        c.get("logical"), c.get("newCanonical"), c.get("newStored"), c.get("newMetadata")])

    # Pair the arms: a LayerFS-only difference is a result or unsupported op
    # that the sandbox-disk arm does not share.
    pairs = {}
    for r in rows:
        pairs.setdefault((r["variant"], r["seed"]), {})[r["arm"]] = r
    diffs = []
    for (variant, seed), arms in pairs.items():
        lf, disk = arms.get("layerfs"), arms.get("sandbox-disk")
        if not lf or not disk:
            continue
        only = [u for u in lf["unsupported_ops"].split(";") if u and u not in disk["unsupported_ops"].split(";")]
        if lf["result"] != disk["result"] or only:
            diffs.append({"variant": variant, "seed": seed, "layerfs": lf["result"], "sandbox_disk": disk["result"],
                          "unsupported_layerfs_only": only, "first_failure": lf["first_failure"]})
    totals = {}
    for r in rows:
        t = totals.setdefault(r["arm"], {"cases": 0, "PASS": 0, "FAIL": 0, "HARNESS": 0, "ops": 0, "wall_ms": 0.0})
        t["cases"] += 1
        t[r["result"]] += 1
        t["ops"] += r["ops"] or 0
        t["wall_ms"] = round(t["wall_ms"] + (r["wall_ms"] or 0), 1)
    summary = {"run": run.name, "totals": totals, "layerfs_only": diffs,
               "commit": [{"commit_ms": r["commit_ms"], **r["value"]} for r in commits]}
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({"totals": totals, "layerfs_only": len(diffs), "commits": [r["commit_ms"] for r in commits]}))


if __name__ == "__main__":
    main()

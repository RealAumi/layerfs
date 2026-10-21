#!/usr/bin/env python3
"""smallfile report: results.csv, commit.csv and summary.json from a run's receipts.

Reads RUN/results.jsonl (one row per operation and arm: op.mjs, or run.sh
pt_op for the passthrough-fuse arm), each
read-back RUN/ops/<op>-<arm>.txt (smallfile's output and its --output-json
result), RUN/commands.log (the host's 1-minute load when each client
started) and RUN/ledger.jsonl (the Commit after the layerfs create). Writes
the three files into RUN, or into OUT when given.

  report.py RUN [OUT]
"""
import csv
import json
import sys
from pathlib import Path


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def host_load(run):
    """Client step name (op-<op>-<arm>) -> the 1-minute load commands.log recorded."""
    loads = {}
    for line in (run / "commands.log").read_text().splitlines():
        name, *_, load = line.split("\t")
        loads[name.rsplit("-", 1)[0]] = float(load.split("=", 1)[1])
    return loads


def smallfile_result(text):
    """smallfile's --output-json 'results' object, or {} when it wrote none."""
    body = text.split("=== result.json\n", 1)[1] if "=== result.json\n" in text else ""
    body = body.split("\n=== ", 1)[0]
    try:
        return json.loads(body)["results"]
    except (ValueError, KeyError):
        return {}


def parse(row, text, loads):
    res = smallfile_result(text)
    if row["exec_exit"] != 0 or row["rc"] is None:
        result = "HARNESS"
    elif row["rc"] == 0 and res.get("status") == "Success" and res.get("pctFilesDone") == 100.0:
        result = "PASS"
    else:
        result = "FAIL"
    mib = res.get("MiBps")
    return {
        "op": row["op"], "arm": row["arm"], "threads": row["threads"], "files_per_thread": row["files_per_thread"],
        "file_size_kb": row["file_size_kb"],
        "files_per_s": round(res["filesPerSec"], 1) if "filesPerSec" in res else None,
        "mb_per_s": round(mib, 2) if mib is not None else None,
        "elapsed_s": round(res["elapsed"], 3) if "elapsed" in res else None,
        "pct_files_done": res.get("pctFilesDone"),
        "wall_ms": round(row["tool_ns"] / 1e6, 1) if row["tool_ns"] is not None else None,
        "load": loads.get(f"op-{row['case']}"),
        "result": result, "status": res.get("status"), "files": res.get("files"), "exit": row["rc"],
        "exec_ms": row["exec_ms"], "sandbox_loadavg": row["sandbox_loadavg"],
    }


def main():
    run = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else run
    out.mkdir(parents=True, exist_ok=True)
    loads = host_load(run)
    rows = [parse(r, (run / "ops" / f"{r['case']}.txt").read_text(), loads) for r in jsonl(run / "results.jsonl")]
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    commits = [r for r in jsonl(run / "ledger.jsonl") if r.get("step") == "commit"]
    with open(out / "commit.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["message", "files", "commit_ms", "load", "kind", "commit", "base", "logical", "newCanonical",
                    "newStored", "newMetadata"])
        create = next((r for r in rows if r["op"] == "create" and r["arm"] == "layerfs"), {})
        for r in commits:
            c = r["value"].get("commit") or {}
            w.writerow([r["message"], create.get("files"), r["commit_ms"], loads.get("commit"), r["value"]["kind"],
                        c.get("id"), c.get("base"), c.get("logical"), c.get("newCanonical"), c.get("newStored"),
                        c.get("newMetadata")])

    # Per operation, files/s ratios (above 1 is faster on the first arm) and
    # in-container wall time ratios (above 1 is slower on the first arm):
    # LayerFS ÷ sandbox-disk, and with the passthrough-fuse arm also LayerFS ÷
    # passthrough-fuse (like for like) and passthrough-fuse ÷ sandbox-disk
    # (the cost of FUSE alone).
    by = {(r["op"], r["arm"]): r for r in rows}
    ratios = []
    for op in dict.fromkeys(r["op"] for r in rows):
        lf, disk, pt = (by.get((op, a)) for a in ("layerfs", "sandbox-disk", "passthrough-fuse"))
        if lf and disk and lf["files_per_s"] and disk["files_per_s"]:
            ratio = {"op": op, "layerfs_files_per_s": lf["files_per_s"], "disk_files_per_s": disk["files_per_s"],
                     "files_per_s_ratio": round(lf["files_per_s"] / disk["files_per_s"], 3),
                     "wall_ratio": round(lf["wall_ms"] / disk["wall_ms"], 3),
                     "layerfs": lf["result"], "sandbox_disk": disk["result"]}
            if pt and pt["files_per_s"]:
                ratio.update({"pt_files_per_s": pt["files_per_s"],
                              "layerfs_pt_files_per_s_ratio": round(lf["files_per_s"] / pt["files_per_s"], 3),
                              "pt_disk_files_per_s_ratio": round(pt["files_per_s"] / disk["files_per_s"], 3),
                              "layerfs_pt_wall_ratio": round(lf["wall_ms"] / pt["wall_ms"], 3),
                              "pt_disk_wall_ratio": round(pt["wall_ms"] / disk["wall_ms"], 3),
                              "passthrough_fuse": pt["result"]})
            ratios.append(ratio)
    failures = [r for r in rows if r["result"] != "PASS"]
    summary = {"run": run.name, "ratios": ratios, "failures": failures,
               "commit": [{"commit_ms": r["commit_ms"], **r["value"]} for r in commits]}
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({"ratios": [(r["op"], r["files_per_s_ratio"], r.get("layerfs_pt_files_per_s_ratio")) for r in ratios], "failures": len(failures),
                      "commits": [r["commit_ms"] for r in commits]}))


if __name__ == "__main__":
    main()

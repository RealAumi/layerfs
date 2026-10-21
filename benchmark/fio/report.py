#!/usr/bin/env python3
"""fio report: results.csv, commit.csv and summary.json from a run's receipts.

Reads RUN/results.jsonl (one row per job and arm, job.mjs or pt.mjs), each
read-back RUN/ops/<job>-<arm>.txt (fio's log and --output-format=json result),
RUN/commands.log (the host's 1-minute load when each client started) and
RUN/ledger.jsonl (the Commit after the layerfs jobs). Writes the three files
into RUN, or into OUT when given.

results.csv has one row per job, arm and data direction that moved bytes
(randrw-70-30 has a read row and a write row). bw_mb_s is decimal MB/s
(fio's bw_bytes / 1e6); clat percentiles are fio's completion latency in
µs; sync_p50_us / sync_p99_us are fio's fsync latency (sync-write only).
A run with the passthrough-fuse arm also gets ratios.csv (and
summary.json "three_arm"): per job and direction each arm's MB/s, IOPS,
clat p50 / p99 and the three bandwidth ratios layerfs ÷ passthrough-fuse,
layerfs ÷ sandbox-disk and passthrough-fuse ÷ sandbox-disk.

  report.py RUN [OUT]
"""
import csv
import json
import sys
from pathlib import Path


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def host_load(run):
    """Client step name (job-<job>-<arm>, commit) -> the 1-minute load commands.log recorded."""
    loads = {}
    for line in (run / "commands.log").read_text().splitlines():
        name, *_, load = line.split("\t")
        loads[name.rsplit("-", 1)[0] if name.startswith("job-") else name] = float(load.split("=", 1)[1])
    return loads


def fio_job(text):
    """fio's single (group-reported) job object, or {} when it wrote no JSON."""
    body = text.split("=== json\n", 1)[1] if "=== json\n" in text else ""
    try:
        return json.loads(body[body.find("{"):])["jobs"][0]
    except (ValueError, KeyError, IndexError):
        return {}


def us(ns):
    return round(ns / 1000, 1) if ns is not None else None


def parse(row, text, loads):
    fj = fio_job(text)
    if row["exec_exit"] != 0 or row["rc"] is None:
        result = "HARNESS"
    elif row["rc"] == 0 and fj and fj.get("error") == 0:
        result = "PASS"
    else:
        result = "FAIL"
    dirs = [d for d in ("read", "write") if fj.get(d, {}).get("io_bytes")] or [None]
    sync = fj.get("sync", {}).get("lat_ns", {})
    out = []
    for d in dirs:
        s = fj.get(d, {}) if d else {}
        pct = s.get("clat_ns", {}).get("percentile", {})
        out.append({
            "job": row["job"], "arm": row["arm"], "rw": row["rw"], "bs": row["bs"], "numjobs": row["numjobs"],
            "direct": row["direct"], "sync": row["sync"],
            "runtime_s": round(s["runtime"] / 1000, 3) if "runtime" in s else None, "size": row["size"],
            "bw_mb_s": round(s["bw_bytes"] / 1e6, 2) if "bw_bytes" in s else None,
            "iops": round(s["iops"], 1) if "iops" in s else None,
            "clat_p50_us": us(pct.get("50.000000")), "clat_p99_us": us(pct.get("99.000000")),
            "clat_p999_us": us(pct.get("99.900000")),
            "cache_state": "O_DIRECT; below it warm/unknown" if row["direct"] else "warm own-write",
            "load": loads.get(f"job-{row['case']}"),
            "ddir": d, "bytes": s.get("io_bytes"), "clat_mean_us": us(s.get("clat_ns", {}).get("mean")),
            "sync_p50_us": us(sync.get("percentile", {}).get("50.000000")) if sync.get("N") else None,
            "sync_p99_us": us(sync.get("percentile", {}).get("99.000000")) if sync.get("N") else None,
            "ioengine": fj.get("job options", {}).get("ioengine"), "result": result, "fio_error": fj.get("error"),
            "exit": row["rc"], "wall_ms": round(row["tool_ns"] / 1e6, 1) if row["tool_ns"] is not None else None,
            "exec_ms": row["exec_ms"], "sandbox_loadavg": row["sandbox_loadavg"],
        })
    return out


def three_arm(rows, path):
    """Per job and direction: each arm's MB/s, IOPS, p50, p99 and the three bandwidth ratios; written to PATH."""
    arms = {"lf": "layerfs", "disk": "sandbox-disk", "pt": "passthrough-fuse"}
    by = {(r["job"], r["ddir"], r["arm"]): r for r in rows}
    ratio = lambda a, b: round(a / b, 3) if a and b else None
    # A failed run that moved no bytes has ddir None; it stands in that arm for each direction of its job.
    keys = dict.fromkeys((r["job"], r["ddir"]) for r in rows if r["ddir"])
    keys.update(dict.fromkeys((r["job"], None) for r in rows if not any(k[0] == r["job"] for k in keys)))
    table = []
    for job, ddir in keys:
        got = {k: by.get((job, ddir, arm)) or by.get((job, None, arm), {}) for k, arm in arms.items()}
        row = {"job": job, "ddir": ddir}
        for k in arms:
            for f in ("bw_mb_s", "iops", "clat_p50_us", "clat_p99_us", "result"):
                row[f"{k}_{f}"] = got[k].get(f)
        row["lf_over_pt"] = ratio(row["lf_bw_mb_s"], row["pt_bw_mb_s"])
        row["lf_over_disk"] = ratio(row["lf_bw_mb_s"], row["disk_bw_mb_s"])
        row["pt_over_disk"] = ratio(row["pt_bw_mb_s"], row["disk_bw_mb_s"])
        table.append(row)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    return table


def main():
    run = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else run
    out.mkdir(parents=True, exist_ok=True)
    loads = host_load(run)
    rows = [x for r in jsonl(run / "results.jsonl") for x in parse(r, (run / "ops" / f"{r['case']}.txt").read_text(), loads)]
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    commits = [r for r in jsonl(run / "ledger.jsonl") if r.get("step") == "commit"]
    with open(out / "commit.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["message", "commit_ms", "load", "kind", "commit", "base", "logical", "newCanonical", "newStored",
                    "newMetadata"])
        for r in commits:
            c = r["value"].get("commit") or {}
            w.writerow([r["message"], r["commit_ms"], loads.get("commit"), r["value"]["kind"], c.get("id"),
                        c.get("base"), c.get("logical"), c.get("newCanonical"), c.get("newStored"),
                        c.get("newMetadata")])

    # LayerFS ÷ sandbox-disk per job and direction: bandwidth ratio (above 1
    # is faster on LayerFS) and p99 completion latency ratio (above 1 is slower).
    by = {(r["job"], r["ddir"], r["arm"]): r for r in rows}
    ratios = []
    for job, ddir in dict.fromkeys((r["job"], r["ddir"]) for r in rows):
        lf, disk = by.get((job, ddir, "layerfs")), by.get((job, ddir, "sandbox-disk"))
        if lf and disk and lf["bw_mb_s"] and disk["bw_mb_s"]:
            ratios.append({"job": job, "ddir": ddir, "layerfs_mb_s": lf["bw_mb_s"], "disk_mb_s": disk["bw_mb_s"],
                           "bw_ratio": round(lf["bw_mb_s"] / disk["bw_mb_s"], 3),
                           "p99_ratio": round(lf["clat_p99_us"] / disk["clat_p99_us"], 3),
                           "layerfs": lf["result"], "sandbox_disk": disk["result"]})
    failures = [r for r in rows if r["result"] != "PASS"]
    summary = {"run": run.name, "ratios": ratios, "failures": failures,
               "commit": [{"commit_ms": r["commit_ms"], **r["value"]} for r in commits]}
    if any(r["arm"] == "passthrough-fuse" for r in rows):
        summary["three_arm"] = three_arm(rows, out / "ratios.csv")
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({"ratios": [(r["job"], r["ddir"], r["bw_ratio"]) for r in ratios], "failures": len(failures),
                      "commits": [r["commit_ms"] for r in commits],
                      "three_arm": [(r["job"], r["ddir"], r["lf_over_pt"], r["lf_over_disk"], r["pt_over_disk"])
                                    for r in summary.get("three_arm", [])]}))


if __name__ == "__main__":
    main()

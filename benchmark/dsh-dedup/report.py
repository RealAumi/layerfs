#!/usr/bin/env python3
"""Summarizes one dsh-dedup run from its receipts. Reads only; recomputes
nothing the receipts do not hold.

    report.py RUN [GIT_REFERENCE_RESULT_JSON]

Writes RUN/states.csv (one row per selected state) and RUN/summary.json, and
prints the summary. Timers are the client's wall time around each SDK call:
Init (project.init), apply (sandbox.exec of apply.py), Commit
(sandbox.commit). Verification, mount and unmount are recorded, never summed
into them. Storage is the closed Store's allocated bytes (every file in the
Store volume) and the Store's own totals.
"""
import csv
import json
import os
import sys

run = sys.argv[1]
rows = [json.loads(l) for l in open(os.path.join(run, "ledger.jsonl"))]
history = [json.loads(l) for l in open(os.path.join(run, "history.jsonl"))] if os.path.exists(os.path.join(run, "history.jsonl")) else []
segments = [json.loads(l) for l in open(os.path.join(run, "segments.jsonl"))]
selection = json.load(open(os.path.join(run, "selection.json")))
store = json.load(open(os.path.join(run, "store.json")))
files = [line.split() for line in open(os.path.join(run, "store-files.txt")) if line.strip()]
deploy = dict(line.strip().split("=", 1) for line in open(os.path.join(run, "deploy.env")) if "=" in line)
states = {s["index"]: s for s in json.load(open(os.path.join(deploy["prepared"], "states.json")))["states"]}

init = rows[0]
commits = rows[1:]
assert [r["state"] for r in rows] == selection, "ledger does not cover the selection in order"
assert all(r["kind"] == "Committed" for r in commits), "a state did not commit"
assert all(r["verify"]["mismatches"] == 0 for r in rows), "a live state failed its oracle"
checked = {h["state"] for h in history if h["verify"]["mismatches"] == 0}

with open(os.path.join(run, "states.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["state", "ordinal", "from", "files", "logical_bytes", "apply_ms", "verify_ms", "commit_ms",
                "newCanonical", "newStored", "newMetadata", "removed", "created", "overwritten", "overwritten_bytes", "created_bytes", "history_verified"])
    w.writerow([1, states[1]["ordinal"], "", states[1]["files"], states[1]["logical_bytes"], "", init["verify_ms"], "",
                store["totals"][0]["init_canonical"], store["totals"][0]["init_stored"], store["totals"][0]["init_metadata"], "", "", "", "", "", "init"])
    for r in commits:
        a = r["apply"]
        w.writerow([r["state"], states[r["state"]]["ordinal"], r["from"], states[r["state"]]["files"], states[r["state"]]["logical_bytes"],
                    r["apply_ms"], r["verify_ms"], r["commit_ms"], r["newCanonical"], r["newStored"], r["newMetadata"],
                    a["removed"], a["created"], a["overwritten"], a["overwritten_bytes"], a["created_bytes"], r["state"] in checked])

ms = lambda key: round(sum(r[key] for r in commits), 1)
totals = store["totals"][0]
summary = {
    "run": os.path.basename(run), "stride": int(deploy["stride"]), "states": len(selection),
    "logical_bytes_selected": sum(states[s]["logical_bytes"] for s in selection),
    "store_logical": totals["logical"], "store_canonical": totals["canonical"],
    "store_stored": totals["stored"], "store_metadata": totals["metadata"],
    "store_allocated_bytes": sum(int(f[2]) * int(f[3]) for f in files),
    "store_apparent_bytes": sum(int(f[1]) for f in files),
    "store_files": [f[0] for f in files],
    "init_ms": init["init_ms"], "commit_ms_total": ms("commit_ms"), "apply_ms_total": ms("apply_ms"),
    "commit_ms_max": max(r["commit_ms"] for r in commits), "verify_ms_total": round(init["verify_ms"] + sum(r["verify_ms"] for r in commits), 1),
    "segments": len(segments), "mount_ms": [s["mount_ms"] for s in segments], "unmount_ms": [s["unmount_ms"] for s in segments],
    "history_verified": f"{len(checked)}/{len(commits)}",
    "policy": {k: store["policy"][0][k] for k in ("whole_file_delta_max_depth", "chunk_delta_max_depth", "metadata_delta_max_depth", "schema_version")},
}
if len(sys.argv) > 2:
    git = json.load(open(sys.argv[2]))
    assert git["selection"] == selection, "Git reference is for another selection"
    summary["git"] = {k: git[k] for k in ("pack_bytes", "index_bytes", "objects_allocated_bytes", "repo_allocated_bytes", "git_version", "command")}
    summary["store_allocated_vs_git_pack_idx"] = round(summary["store_allocated_bytes"] / (git["pack_bytes"] + git["index_bytes"]), 4)
json.dump(summary, open(os.path.join(run, "summary.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))

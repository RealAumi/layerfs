#!/usr/bin/env python3
"""fsstress report: CSVs and summary.json from one run's receipts.

  report.py RUN OUT_DIR

Reads RUN/cases.jsonl, RUN/logs/<case>-<arm>.log*.gz (fsstress -v -V, one
file per process) and RUN/capture.jsonl, and writes OUT_DIR/runs.csv,
op-errors.csv and capture.csv, plus RUN/summary.json.

Each fsstress operation is the pair (process, opno). Its outcome is taken
from its first result line: the trailing integer (0, an errno, or -1 where
fsstress prints a raw return code), "error N", "Bus error" (SIGBUS), no
number at all after a range operation (success), or `skip` where fsstress
found no object to act on ("- no filename", "files are too small").
Lines that only add detail (`add id=`, `source entry:`, `...to`,
`fallback to stat()`) are not outcomes. errors_total counts outcomes other
than 0 and skip. op-errors.csv lists every (op, outcome) count, successes
included, so the arms compare op by op.
"""
import csv, gzip, json, re, sys
from collections import Counter
from pathlib import Path

LINUX_ERRNO = {
    1: "EPERM", 2: "ENOENT", 3: "ESRCH", 4: "EINTR", 5: "EIO", 6: "ENXIO", 7: "E2BIG", 8: "ENOEXEC", 9: "EBADF",
    10: "ECHILD", 11: "EAGAIN", 12: "ENOMEM", 13: "EACCES", 14: "EFAULT", 16: "EBUSY", 17: "EEXIST", 18: "EXDEV",
    19: "ENODEV", 20: "ENOTDIR", 21: "EISDIR", 22: "EINVAL", 23: "ENFILE", 24: "EMFILE", 25: "ENOTTY", 26: "ETXTBSY",
    27: "EFBIG", 28: "ENOSPC", 29: "ESPIPE", 30: "EROFS", 31: "EMLINK", 32: "EPIPE", 34: "ERANGE", 36: "ENAMETOOLONG",
    38: "ENOSYS", 39: "ENOTEMPTY", 40: "ELOOP", 61: "ENODATA", 75: "EOVERFLOW", 95: "EOPNOTSUPP", 122: "EDQUOT",
}
LINE = re.compile(r"^(\d+)/(\d+): (.*)$")
DETAIL = re.compile(r"^\S+ (add|del|source|target) |^\.\.\.to |fallback to stat\(\)|^\S+ - xfsctl")
SKIP = re.compile(r" - (no (source |target )?filename|files are too small|.* zero size$|.*has no extended attributes$)| have ancestor-descendant relationship$")
FAILED = re.compile(r" - .*failed (-?\d+)$")


def outcome_name(value):
    if value in ("0", "skip", "SIGBUS"):
        return value
    n = int(value)
    return "-1" if n < 0 else f"{LINUX_ERRNO.get(n, 'errno')}({n})"


def classify(rest):
    """(op, outcome) for a result line, or None for a detail line."""
    if DETAIL.search(rest):
        return None
    words = rest.split()
    op = words[0]
    if op in ("write", "read") and len(words) > 1 and words[1] == "dontcache":
        op += "_dontcache"
    if SKIP.search(rest):
        return op, "skip"
    m = FAILED.search(rest)
    if m:
        return op, m.group(1)
    if rest.endswith("Bus error"):
        return op, "SIGBUS"
    m = re.search(r" error (-?\d+)$", rest)
    if m:
        return op, m.group(1)
    if op == "creat":  # creat PATH x:EXTSIZE E E1: E is creat's result
        return op, words[-2]
    if op == "bulkstat" and len(words) > 1 and words[1] == "nent":
        return op, "0"
    if re.fullmatch(r"-?\d+", words[-1]):
        return op, words[-1]
    return op, "0"


def parse(files):
    """{(proc, opno): (op, outcome)} from the first result line of each operation."""
    result = {}
    for f in files:
        with gzip.open(f, "rt", errors="replace") as fh:
            for line in fh:
                m = LINE.match(line.rstrip("\n"))
                if not m:
                    continue
                key = (int(m.group(1)), int(m.group(2)))
                if key in result:
                    continue
                got = classify(m.group(3))
                if got:
                    result[key] = (got[0], outcome_name(got[1]))
    return result


def normalized_lines(f):
    """Log lines with st_blocks masked: `[ino nlink uid gid BLOCKS size]` depends on the filesystem."""
    with gzip.open(f, "rt", errors="replace") as fh:
        return [re.sub(r"\[(-?\d+) (\d+) (\d+) (\d+) \d+ ", r"[\1 \2 \3 \4 * ", l.rstrip("\n")) for l in fh]


def main(run, out):
    run, out = Path(run), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cases = [json.loads(l) for l in open(run / "cases.jsonl")]
    parsed, summary = {}, {"run": run.name, "cases": [], "differences": [], "c1_alignment": None, "capture": None}
    runs_rows, err_rows = [], []
    for c in cases:
        files = sorted((run / "logs").glob(f"{c['case']}-{c['arm']}.log*.gz"))
        ops = parse(files)
        parsed[(c["case"], c["arm"])] = ops
        counts = Counter(ops.values())
        errors = sum(n for (op, o), n in counts.items() if o not in ("0", "skip"))
        expected = c["procs"] * c["ops"]
        runs_rows.append([c["case"], c["arm"], c["seed"], c["procs"], c["ops"], c["exit"], f"{c['wall_ms']:.3f}",
                          f"{expected / (c['wall_ms'] / 1000):.1f}", errors])
        for (op, o), n in sorted(counts.items()):
            err_rows.append([c["case"], c["arm"], op, n, o])
        summary["cases"].append({"case": c["case"], "arm": c["arm"], "exit": c["exit"], "wall_ms": c["wall_ms"],
                                 "exec_ms": c["exec_ms"], "operations": expected, "outcomes_parsed": len(ops),
                                 "errors_total": errors, "stderr": c["stderr"]["tail"][-500:]})
    for case in sorted({c["case"] for c in cases}):
        a, b = parsed.get((case, "layerfs")), parsed.get((case, "sandbox-disk"))
        if a is None or b is None:
            continue
        ca, cb = Counter(a.values()), Counter(b.values())
        for key in sorted(set(ca) | set(cb)):
            if ca[key] != cb[key]:
                summary["differences"].append({"case": case, "op": key[0], "outcome": key[1],
                                               "layerfs": ca[key], "sandbox-disk": cb[key]})
        if case == "c1":
            keys = sorted(set(a) | set(b))
            mism = [{"opno": k[1], "layerfs": a.get(k), "sandbox-disk": b.get(k)} for k in keys if a.get(k) != b.get(k)]
            la = normalized_lines(run / "logs" / "c1-layerfs.log.0.gz")
            lb = normalized_lines(run / "logs" / "c1-sandbox-disk.log.0.gz")
            first = next((i for i, (x, y) in enumerate(zip(la, lb)) if x != y), None)
            summary["c1_alignment"] = {
                "operations": len(keys), "same_op_and_outcome": len(keys) - len(mism),
                "same_op_other_outcome": sum(1 for m in mism if m["layerfs"] and m["sandbox-disk"] and m["layerfs"][0] == m["sandbox-disk"][0]),
                "different_op": sum(1 for m in mism if not (m["layerfs"] and m["sandbox-disk"]) or m["layerfs"][0] != m["sandbox-disk"][0]),
                "first_mismatches": mism[:100], "log_lines": [len(la), len(lb)],
                "first_divergent_line": None if first is None else {"line": first + 1, "layerfs": la[first], "sandbox-disk": lb[first]},
            }
    with open(out / "runs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "arm", "seed", "procs", "ops", "exit", "wall_ms", "ops_per_s", "errors_total"])
        w.writerows(runs_rows)
    with open(out / "op-errors.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "arm", "op", "count", "errno"])
        w.writerows(err_rows)
    phases = {r.get("phase"): r for r in map(json.loads, open(run / "capture.jsonl"))} if (run / "capture.jsonl").exists() else {}
    if "commit" in phases and "verify" in phases:
        cm, vf = phases["commit"], phases["verify"]
        ledger = [json.loads(l) for l in open(run / "ledger.jsonl")]
        commit_ms = next(r["commit_ms"] for r in ledger if r.get("step") == "commit")
        rec = cm["commit"]["commit"]
        cap = {"entries": cm["live"]["entries"], "bytes": cm["live"]["bytes"], "commit_ms": commit_ms,
               "logical": rec["logical"], "newStored": rec["newStored"], "manifest_equal": vf["compare"]["equal"],
               "differences": vf["compare"]["differences"]}
        summary["capture"] = {**cap, "commit_id": rec["id"], "newCanonical": rec["newCanonical"], "newMetadata": rec["newMetadata"],
                              "captured_entries": vf["captured"]["entries"], "captured_bytes": vf["captured"]["bytes"],
                              "live_manifest_sha256": cm["live"]["manifest_sha256"], "captured_manifest_sha256": vf["captured"]["manifest_sha256"],
                              "first_differences": vf["compare"]["first"], "mount_ms": vf["mount_ms"], "unmount_ms": vf["unmount_ms"]}
        with open(out / "capture.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(list(cap))
            w.writerow(list(cap.values()))
    (run / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({"runs": runs_rows, "differences": len(summary["differences"]), "capture": summary["capture"]}))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])

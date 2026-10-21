#!/usr/bin/env python3
"""pjdfstest results from one run's receipts (plan.json, groups.jsonl and the
tap/ files written by client/group.mjs), into the run folder:

  results-by-file.csv        file, arm, planned, passed, failed, skipped, todo,
                             missing, exit, ms, status
  results-by-dir.csv         the same totals per test directory and arm
  results-by-assertion.csv   file, assertion, both arms' result and detail
  layerfs-only-failures.csv  assertions that fail on layerfs and pass on sandbox-disk,
                             with a cascade hint (see below)
  different-failures.csv     assertions that fail on both arms with a different result
  summary.json               totals per arm and the lists above

TAP semantics: `ok` passes; `not ok ... # TODO` is a known platform failure
(todo, not failed); a planned assertion with no line is missing and counts as
failed. A file that only printed misc.sh's quick_exit "1..1 / ok 1"
(run-group.sh quick_exit=1) is skipped: the suite does not cover it on Linux
or on this filesystem. Random names (pjdfstest_<md5>, and the long hex names
of the NAME_MAX/PATH_MAX cases) read as NAME.

Cascade hint: once a creating call (create, open, mkdir, mkfifo, mknod, bind,
symlink, link, rename) has failed only on layerfs in a file, a later
layerfs-only failure in that file is `cascade` when it names an object that
was not created (unless it got EPERM, which shows the object exists) or got
ENOENT or nothing. A creating call that itself fails with an errno other than
ENOENT stays `primary`. A failure with no detail (a test_check of times) is
`cascade` when such a create failed within the six assertions before it (the
same loop iteration). Every other layerfs-only failure is `primary`. It is a
reading aid from the TAP text, not a proof of cause.

different-failures.csv compares the two results with decimal numbers not
starting with 0 (inodes, times) read as N, so octal modes and errnos differ.

  report.py RUN
"""
import csv
import json
import re
import sys
from pathlib import Path

ARMS = ("layerfs", "sandbox-disk")
CREATES = {"create", "open", "mkdir", "mkfifo", "mknod", "bind", "symlink", "link", "rename"}
NAME = re.compile(r"pjdfstest_[0-9a-f]{32}|[0-9a-f]{40,}")
LINE = re.compile(r"^(not ok|ok) (\d+)(.*)$")
DETAIL = re.compile(r"^ - tried '(.*)', expected (.*), got ?(.*)$")
NUMBER = re.compile(r"\b[1-9][0-9]*\b")
END = re.compile(r"^### end (\S+) exit=(\d+) ms=(\d+) quick_exit=(\d) residue=(\d+)$")


def parse(tap):
    """{file: record} for one tap file."""
    files, cur = {}, None
    for line in tap.read_text().splitlines():
        if line.startswith("### begin "):
            cur = files.setdefault(line.split()[2], {"plan": None, "lines": {}, "end": None})
        elif m := END.match(line):
            cur["end"] = {"exit": int(m[2]), "ms": int(m[3]), "quick_exit": m[4] == "1", "residue": int(m[5])}
            cur = None
        elif cur is None:
            continue
        elif m := re.match(r"^1\.\.(\d+)", line):
            cur["plan"] = int(m[1])
        elif m := LINE.match(line):
            ok, n, rest = m[1] == "ok", int(m[2]), m[3]
            todo = "# TODO" in rest
            skip = "# SKIP" in rest
            status = "skip" if skip else ("pass" if ok else ("todo" if todo else "fail"))
            cur["lines"][n] = {"status": status, "detail": NAME.sub("NAME", rest.strip()), "names": set(NAME.findall(rest))}
    return files


def syscall(detail):
    """The pjdfstest call(s) of a `tried '...'` detail, options dropped; '' when none."""
    m = DETAIL.match(" " + detail) if detail.startswith("-") else None
    if not m:
        return "", "", "", ""
    calls = []
    for part in m[1].split(" : "):
        words = part.split()
        while words and words[0] in ("-u", "-g", "-U", "--"):
            words = words[1:] if words[0] == "--" else words[2:]
        calls.append(words[0] if words else "?")
    return calls[-1], NAME.sub("NAME", m[1]), m[2], m[3]


def main():
    run = Path(sys.argv[1])
    plan = json.loads((run / "plan.json").read_text())
    groups = [json.loads(l) for l in (run / "groups.jsonl").read_text().splitlines() if l]
    results = {a: {} for a in ARMS}
    for g in groups:
        for f, rec in parse(run / "tap" / g["tap"]).items():
            if f in results[g["arm"]]:
                raise SystemExit(f"{f} ran twice in {g['arm']}")
            results[g["arm"]][f] = rec

    by_file, by_assertion, only, differ = [], [], [], []
    totals = {a: dict.fromkeys(("files", "files_pass", "files_fail", "files_skip", "files_not_run", "planned", "passed", "failed", "skipped", "todo", "missing"), 0) for a in ARMS}
    for f in plan:
        per = {}
        for arm in ARMS:
            rec, t = results[arm].get(f), totals[arm]
            t["files"] += 1
            if rec is None:
                t["files_not_run"] += 1
                by_file.append({"file": f, "arm": arm, "status": "not-run"})
                continue
            end = rec["end"] or {}
            skipped_file = end.get("quick_exit") or rec["plan"] == 0
            n = rec["plan"] or 0
            res = {}
            for i in range(1, max(n, max(rec["lines"], default=0)) + 1):
                line = rec["lines"].get(i)
                res[i] = {"status": "skip", "detail": "quick_exit"} if skipped_file else (line or {"status": "missing", "detail": ""})
            per[arm] = res
            c = {s: sum(r["status"] == s for r in res.values()) for s in ("pass", "fail", "skip", "todo", "missing")}
            status = "skip" if skipped_file else ("pass" if c["fail"] + c["missing"] == 0 and rec["end"] else "fail")
            row = {"file": f, "arm": arm, "planned": n, "passed": c["pass"], "failed": c["fail"] + c["missing"], "skipped": c["skip"],
                   "todo": c["todo"], "missing": c["missing"], "exit": end.get("exit", "killed"), "ms": end.get("ms", ""), "status": status}
            by_file.append(row)
            t["files_" + status] += 1
            t["planned"] += n
            for k, s in (("passed", "pass"), ("skipped", "skip"), ("todo", "todo"), ("missing", "missing")):
                t[k] += c[s]
            t["failed"] += c["fail"] + c["missing"]
        if len(per) < 2:
            continue
        uncreated, failed_creates = set(), []
        for i in sorted(set(per["layerfs"]) | set(per["sandbox-disk"])):
            lf = per["layerfs"].get(i, {"status": "absent", "detail": ""})
            sd = per["sandbox-disk"].get(i, {"status": "absent", "detail": ""})
            by_assertion.append({"file": f, "assertion": i, "layerfs": lf["status"], "sandbox_disk": sd["status"],
                                 "layerfs_detail": lf["detail"], "sandbox_disk_detail": sd["detail"]})
            bad = ("fail", "missing")
            if lf["status"] in bad:
                call, tried, expected, got = syscall(lf["detail"])
                row = {"file": f, "assertion": i, "syscall": call or "(no detail: test_check or stat assertion)", "tried": tried,
                       "expected": expected, "layerfs_got": got if call else lf["detail"] or lf["status"],
                       "sandbox_disk": sd["status"], "sandbox_disk_detail": sd["detail"]}
                if sd["status"] in ("pass", "todo"):
                    names = lf.get("names", set())
                    if not call:
                        row["cascade"] = "cascade" if any(i - 6 <= n < i for n in failed_creates) else "primary"
                    elif call in CREATES and got.startswith("E") and got != "ENOENT":
                        row["cascade"] = "primary"
                    else:
                        row["cascade"] = "cascade" if uncreated and (names & uncreated and got != "EPERM" or got in ("ENOENT", "")) else "primary"
                        if got == "EPERM":
                            uncreated -= names
                    if call in CREATES and got not in ("ENOENT", ""):
                        uncreated |= names
                        failed_creates.append(i)
                    only.append(row)
                elif sd["status"] in bad and NUMBER.sub("N", syscall(sd["detail"])[3]) != NUMBER.sub("N", got):
                    differ.append(row)

    def write(name, rows, fields):
        with open(run / name, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    write("results-by-file.csv", by_file, ["file", "arm", "planned", "passed", "failed", "skipped", "todo", "missing", "exit", "ms", "status"])
    by_dir = {}
    for r in by_file:
        d = by_dir.setdefault((r["file"].split("/")[0], r["arm"]), {"dir": r["file"].split("/")[0], "arm": r["arm"], "files": 0, "files_pass": 0, "files_fail": 0, "files_skip": 0, "planned": 0, "passed": 0, "failed": 0, "skipped": 0, "todo": 0})
        d["files"] += 1
        d["files_" + r["status"].replace("not-run", "fail")] += 1
        for k in ("planned", "passed", "failed", "skipped", "todo"):
            d[k] += r.get(k, 0)
    write("results-by-dir.csv", list(by_dir.values()), list(next(iter(by_dir.values()))))
    write("results-by-assertion.csv", by_assertion, ["file", "assertion", "layerfs", "sandbox_disk", "layerfs_detail", "sandbox_disk_detail"])
    fields = ["file", "assertion", "syscall", "tried", "expected", "layerfs_got", "sandbox_disk", "sandbox_disk_detail"]
    write("layerfs-only-failures.csv", only, fields[:6] + ["cascade"] + fields[6:])
    write("different-failures.csv", differ, fields)
    by_call, primary = {}, {}
    for r in only:
        by_call[r["syscall"]] = by_call.get(r["syscall"], 0) + 1
        if r["cascade"] == "primary":
            key = f'{r["syscall"]} -> {r["layerfs_got"]}'
            primary[key] = primary.get(key, 0) + 1
    summary = {"run": run.name, "files": len(plan), "groups": len(groups), "totals": totals,
               "layerfs_only": len(only), "layerfs_only_by_syscall": dict(sorted(by_call.items(), key=lambda x: -x[1])),
               "layerfs_only_primary": dict(sorted(primary.items(), key=lambda x: -x[1])),
               "layerfs_only_cascade": sum(r["cascade"] != "primary" for r in only),
               "layerfs_only_files": sorted({r["file"] for r in only}), "different_failures": len(differ),
               "sandbox_disk_only": sum(a["sandbox_disk"] in ("fail", "missing") and a["layerfs"] in ("pass", "todo") for a in by_assertion)}
    (run / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: summary[k] for k in ("totals", "layerfs_only", "layerfs_only_primary", "layerfs_only_cascade", "different_failures", "sandbox_disk_only")}, indent=1))


if __name__ == "__main__":
    main()

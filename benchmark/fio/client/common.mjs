// Shared by the fio clients: each arm's fio folder, the folder that keeps
// fio's own output, the three data files, the job table and the exact shell
// commands every arm runs. The layerfs arm runs in the mounted Workspace
// (session.json's path), the sandbox-disk arm in the Sandbox container's own
// /tmp (overlayfs), both through sandbox.exec; the passthrough-fuse arm runs
// in /tmp/pt (libfuse passthrough_ll) in the sibling container through
// bench_pt_exec (pt.mjs). fio's JSON and log go to the container's /tmp in
// every arm, so they do not land in the measured filesystem.
import { appendFileSync } from "node:fs";
import { join } from "node:path";

export const DISK = "/tmp/fio";
export const PT = "/tmp/pt/fio";
export const OUT = "/tmp/fio-out";
export const layerfsDir = (path) => `${path}/fio`;
export const armDir = (arm, path) => ({ layerfs: layerfsDir(path), "sandbox-disk": DISK, "passthrough-fuse": PT })[arm];
export const ARMS = ["layerfs", "sandbox-disk", "passthrough-fuse"];

/** Data files, laid out before the timed jobs; each value names its params.env size key. */
export const FILES = { seq: "seq_size", rand: "rand_size", sync: "sync_size" };

/** Options every timed job shares: psync, no fallocate, no cache invalidation, fixed seed. */
export const COMMON = (runtime) => [
  "--ioengine=psync", "--iodepth=1", "--fallocate=none", "--invalidate=0", "--time_based", `--runtime=${runtime}`,
  "--ramp_time=0", "--randrepeat=1", "--randseed=365", "--percentile_list=50:99:99.9", "--group_reporting",
  "--output-format=json",
];

/** The timed jobs in plan order: file, rw, bs, numjobs, direct, sync and any extra fio option. */
export const JOBS = {
  "seq-write": { file: "seq", rw: "write", bs: "1M", numjobs: 1, direct: 0, sync: "end_fsync=1", extra: ["--end_fsync=1"] },
  "seq-read": { file: "seq", rw: "read", bs: "1M", numjobs: 1, direct: 0, sync: "none", extra: [] },
  "rand-write": { file: "rand", rw: "randwrite", bs: "4k", numjobs: 1, direct: 0, sync: "none", extra: [] },
  "rand-read": { file: "rand", rw: "randread", bs: "4k", numjobs: 1, direct: 0, sync: "none", extra: [] },
  "rand-read-4j": { file: "rand", rw: "randread", bs: "4k", numjobs: 4, direct: 0, sync: "none", extra: [] },
  "randrw-70-30": { file: "rand", rw: "randrw", bs: "4k", numjobs: 1, direct: 0, sync: "none", extra: ["--rwmixread=70"] },
  "sync-write": { file: "sync", rw: "write", bs: "4k", numjobs: 1, direct: 0, sync: "fsync=1", extra: ["--fsync=1"] },
  "rand-write-direct": { file: "rand", rw: "randwrite", bs: "4k", numjobs: 1, direct: 1, sync: "none", extra: [] },
  "rand-read-direct": { file: "rand", rw: "randread", bs: "4k", numjobs: 1, direct: 1, sync: "none", extra: [] },
};

/** fio's argv for JOB in DIR: the job's own options, then COMMON. */
export const jobArgs = (job, dir, params) => {
  const j = JOBS[job];
  return [
    `--name=${job}`, `--filename=${dir}/${j.file}`, `--size=${params[FILES[j.file]]}`, `--rw=${j.rw}`,
    `--bs=${j.bs}`, `--numjobs=${j.numjobs}`, `--direct=${j.direct}`, ...j.extra, ...COMMON(params.runtime),
  ];
};

/** RUN/params.env as an object (runtime, the three file sizes, arms, drop). */
export const readParams = (text) => Object.fromEntries(text.split("\n").filter(Boolean).map((l) => l.split("=", 2)));

/** The page-cache figures of the (shared) Docker VM, printed by the untimed commands. */
const MEMINFO = "grep -E '^(MemAvailable|Cached|Dirty):' /proc/meminfo";

/**
 * The measured command of JOB in ARM: fio alone between two date +%s%N
 * stamps, the container's /proc/loadavg first; prints rc, ns and loadavg.
 */
export const jobCommand = (job, arm, dir, params) => {
  const out = `${OUT}/${arm}`;
  const argv = jobArgs(job, dir, params).join(" ");
  const command = [
    `mkdir -p ${out} || exit 90`,
    `l=$(cut -d' ' -f1 /proc/loadavg); s=$(date +%s%N); fio ${argv} --output=${out}/${job}.json >${out}/${job}.log 2>&1; rc=$?; e=$(date +%s%N)`,
    `echo "rc=$rc ns=$((e - s)) loadavg=$l"`,
  ].join("\n");
  return { argv, command };
};

/** The untimed read-back after JOB: the VM's memory figures, fio's log and its JSON. */
export const readbackCommand = (job, arm) =>
  `cd ${OUT}/${arm} || exit 90; echo '=== meminfo'; ${MEMINFO}; echo '=== log'; tail -c 20000 ${job}.log; echo '=== json'; cat ${job}.json`;

/** results.jsonl row of one job: the measured exec RUN and the read-back BACK. */
export const jobRow = (job, arm, params, argv, run, back) => {
  const m = /rc=(\d+) ns=(\d+) loadavg=([\d.]+)/.exec(run.stdout);
  return {
    case: `${job}-${arm}`, job, arm, ...JOBS[job], size: params[`${JOBS[job].file}_size`], runtime: Number(params.runtime), argv,
    rc: m ? Number(m[1]) : null, tool_ns: m ? Number(m[2]) : null, sandbox_loadavg: m ? Number(m[3]) : null,
    exec_ms: run.ms, exec_exit: run.exitCode, exec_stdout: run.stdout.slice(0, 2000), exec_stderr: run.stderr.slice(0, 2000),
    truncated: run.truncated || back.truncated, readback_exit: back.exitCode,
  };
};

/**
 * The untimed layout of one arm's three files: fio's own layout phase
 * (--create_only=1 with a read job writes every byte; --fallocate=none,
 * since LayerFS refuses fallocate) in 1 MiB writes, then the listing and
 * the VM's memory figures.
 */
export const layoutCommand = (arm, dir, params) => {
  const out = `${OUT}/${arm}`;
  const fio = Object.entries(FILES).map(([f, size]) =>
    `fio --name=layout-${f} --filename=${dir}/${f} --size=${params[size]} --rw=read --bs=1M --create_only=1 --fallocate=none --output-format=normal`);
  const command = [
    `mkdir -p ${out} || exit 90`,
    `s=$(date +%s%N); rc=0; for c in ${fio.map((c) => `'${c}'`).join(" ")}; do $c >>${out}/layout.log 2>&1 || rc=$?; done; e=$(date +%s%N)`,
    `echo "rc=$rc ns=$((e - s))"`,
    `ls -l ${dir}; du -k ${dir}/*; ${MEMINFO}; tail -c 20000 ${out}/layout.log`,
  ].join("\n");
  return { fio, command };
};

/** The untimed removal of FILE from ARM's folder, with the VM's memory figures before and after. */
export const dropCommand = (dir, file) =>
  `echo '=== before'; ${MEMINFO}; rm -- ${dir}/${file} || exit 91; ls -l ${dir}; echo '=== after'; ${MEMINFO}`;

/** Append ROW to RUN/NAME (one JSON line) and echo it, as session.mjs append does. */
export const appendRow = (home, name, row) => {
  appendFileSync(join(home, name), JSON.stringify(row) + "\n");
  console.log(JSON.stringify(row).slice(0, 2000));
};

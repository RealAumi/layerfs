// The fixer's record of one optimize or stop finding (#352 SPEC §6,
// Recording a finding): <metrics>/finding-NNN.aK.json answers attempt K of
// range NNN. report.mjs puts it in the range's issue comment: what tripped,
// how it was diagnosed, what was fixed and how much it improved.
//   {
//     range, attempt, verdict: "optimize" | "stop",
//     trigger: { check, value, threshold },         the gate row that tripped
//     diagnosis: { step: "D0".."D6", summary, phase?, counter?, exponent?: { before, after } },
//     fix: { summary, kind: 1 | 2 | 3, commit, test?,  REBUILD.md §4 (a pre-REBUILD finding keeps "code path" | "data" | "format")
//            oldStores, oldData,                    open unchanged · open and migrate (what) · refused (why); read as before · fallback · rewritten
//            compat?,                               kinds 1-2: the old-binary Store the new binary opened and read, and the result
//            justification?: { kind1, kind2, cost, snapshot } },   kind 3: REBUILD.md §3 points 1-4
//     improvement: [ { measure, before, after, unit?, oldBinary, newBinary, snapshot, cache } ],
//                                                    old vs new binary, same snapshots (SPEC §3 F4)
//   A finding closed without a code change has fix { kind: "none", summary } (why it is not a
//   product finding): no commit, regression test or REBUILD.md fields, and no improvement rows;
//   instead its evidence table, and no design or cost:
//     evidence: [ { measure, value, unit?, binary, snapshot, cache } ]
//     recovery,                                      SPEC §6 recovery
//     records: [ { title, path: "fixes/NNN-aK-<slug>.md" } ],   one per cause (F5)
//     ledger: [ { file: "OPTIMIZATIONS.md" | "BUGS.md", entry } ],   its BUGS / OPTIMIZATIONS line
//     record?                                        free-text pointer, kept from older records
//     design: { old, new }                           one line each (REPORT_FORMAT.md §3.5, findings of the binding format)
//     cost                                           what got slower or bigger, stated even when small
//   The attempt-vs-rerun table is generated from the two attempts' metrics (format.mjs withWithout).
//   }
// Paths in records and ledger are relative to core/docs/issues/352/.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export const STEPS = ["D0", "D1", "D2", "D3", "D4", "D5", "D6"];
/** A finding closed without a code change (fix.kind): it carries evidence instead of a fix and its improvement. */
export const NO_CHANGE = "none";
export const closedWithoutChange = (f) => f?.fix?.kind === NO_CHANGE;
/** The evidence table of a finding closed without a code change. */
export const EVIDENCE_COLUMNS = ["Measure", "Value", "Binary", "Snapshot / checkpoint", "Cache"];
/** REBUILD.md §2: 1 forward-only, 2 additive migration, 3 incompatible. */
export const REBUILD_KINDS = { 1: "1 forward-only", 2: "2 additive migration", 3: "3 incompatible" };
/** How a fix kind reads in reports: the REBUILD.md kinds, "none" (no code change), or an older kind as written. */
export const kindText = (kind) => REBUILD_KINDS[kind] ?? (kind === "none" ? "none: no code change" : kind);
/** One evidence row in the report's table (EVIDENCE_COLUMNS). */
export const evidenceRow = (r) => [r.measure, `${r.value}${r.unit ? ` ${r.unit}` : ""}`, `\`${r.binary}\``, r.snapshot, r.cache];
/** The kinds of SPEC §6 before REBUILD.md, kept only by findings recorded before it (PRE_REBUILD). */
export const FIX_KINDS = ["code path", "data", "format"];
/** Findings recorded before REBUILD.md (2026-10-18); never extended. Their records stay as written (F2). */
export const PRE_REBUILD = new Set(["002.a1"]);
/** fixes/ records written before REBUILD.md, whose header has the SPEC §6 kind; never extended. */
export const PRE_REBUILD_RECORDS = new Set(["002-a1-diff-commits-change-walk.md", "002-a1-fork-branch-count.md", "002-a1-gate-same-binary.md",
  "002-a1-grep-tree-chain-reads.md", "002-a1-merge-ancestry.md", "002-a1-project-lookup.md"]);
/** REBUILD.md §3: the four justifications a kind 3 fix states before any rebuild. */
export const JUSTIFICATIONS = { kind1: "why kind 1 is wrong", kind2: "why kind 2 is impossible", cost: "the rebuild's cost", snapshot: "the newest good snapshot" };
const blank = (v) => v == null || /^\s*(|—|-|none|n\/a|pending|tbd)\s*$/i.test(String(v));

/** The REBUILD.md §4 problems of a fix's kind fields: `fix` from a finding, or the header rows of a fixes/ record. */
export function checkRebuild({ kind, oldStores, oldData, recovery, compat, justification }) {
  const p = [];
  if (![1, 2, 3].includes(kind)) return ["kind is 1, 2 or 3 (REBUILD.md §2)"];
  if (blank(oldStores)) p.push("Old Stores is missing (REBUILD.md §4)");
  if (blank(oldData)) p.push("Old data is missing (REBUILD.md §4)");
  if (blank(recovery)) p.push("recovery is missing");
  if (kind < 3 && blank(compat)) p.push(`a kind ${kind} fix needs its compatibility test: a Store written by the old binary opens and reads correctly with the new one`);
  if (kind === 3) for (const [k, what] of Object.entries(JUSTIFICATIONS)) if (blank(justification?.[k])) p.push(`a kind 3 fix needs ${what} (REBUILD.md §3)`);
  return p;
}

/**
 * The problems of a finding record; empty when it is complete. `full`: a
 * finding of an attempt reported in the binding format (REPORT_FORMAT.md),
 * which also needs the old and new design lines and the cost of the fix.
 */
export function checkFinding(f, { full = false } = {}) {
  const p = [];
  const need = (v, what) => { if (v == null || v === "") p.push(`${what} is missing`); };
  need(f.range, "range"); need(f.attempt, "attempt");
  if (!["optimize", "stop"].includes(f.verdict)) p.push("verdict is optimize or stop");
  need(f.trigger?.check, "trigger.check"); need(f.trigger?.value, "trigger.value");
  if (!STEPS.includes(f.diagnosis?.step)) p.push(`diagnosis.step is one of ${STEPS.join(", ")}`);
  need(f.diagnosis?.summary, "diagnosis.summary");
  need(f.fix?.summary, "fix.summary");
  const id = `${String(f.range).padStart(3, "0")}.a${f.attempt}`;
  if (closedWithoutChange(f)) {
    // no code change: no commit, test, REBUILD.md fields or improvement; the evidence table instead
    if (!Array.isArray(f.evidence) || !f.evidence.length) p.push("evidence has at least one row (a finding closed without a code change)");
    for (const r of f.evidence ?? []) {
      if (r.measure == null || r.value == null || r.value === "") p.push("an evidence row needs measure and value");
      for (const k of ["binary", "snapshot", "cache"]) if (r[k] == null || r[k] === "") p.push(`evidence "${r.measure}" needs ${k}`);
    }
    if (f.improvement?.length) p.push("improvement rows need a code change; a finding without one has evidence");
  } else {
    need(f.fix?.commit, "fix.commit");
    if (PRE_REBUILD.has(id) && FIX_KINDS.includes(f.fix?.kind)) { /* recorded before REBUILD.md */ }
    else for (const x of checkRebuild({ ...f.fix, recovery: f.recovery })) p.push(`fix.${x}`);
    if (!Array.isArray(f.improvement) || !f.improvement.length) p.push("improvement has at least one old-vs-new row");
    for (const r of f.improvement ?? []) {
      if (r.measure == null || r.before == null || r.after == null) p.push("an improvement row needs measure, before and after");
      for (const k of ["oldBinary", "newBinary", "snapshot", "cache"]) if (r[k] == null || r[k] === "") p.push(`improvement "${r.measure}" needs ${k}`);
    }
  }
  need(f.recovery, "recovery");
  if (full && !closedWithoutChange(f)) { need(f.design?.old, "design.old"); need(f.design?.new, "design.new"); need(f.cost, "cost"); }
  const prefix = `fixes/${String(f.range).padStart(3, "0")}-a${f.attempt}-`;
  if (!Array.isArray(f.records) || !f.records.length) p.push("records lists the fixes/ record of each cause");
  for (const r of f.records ?? []) if (!r?.title || !/^fixes\/\d{3}-a\d+-[a-z0-9-]+\.md$/.test(r?.path ?? "") || !r.path.startsWith(prefix)) p.push(`record ${JSON.stringify(r)} is { title, path: "${prefix}<slug>.md" }`);
  if (!Array.isArray(f.ledger) || !f.ledger.length) p.push("ledger names its BUGS.md or OPTIMIZATIONS.md line");
  for (const l of f.ledger ?? []) if (!["BUGS.md", "OPTIMIZATIONS.md"].includes(l?.file) || !l?.entry) p.push(`ledger ${JSON.stringify(l)} is { file: BUGS.md | OPTIMIZATIONS.md, entry }`);
  return p;
}

/** The header rows of a fixes/ record ("| Kind | … |") as a map: lowercased field -> cell text. */
export function recordHeader(text) {
  const rows = new Map();
  for (const line of text.split("\n")) {
    if (/^## /.test(line)) break;
    const m = /^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$/.exec(line);
    if (m && m[1] && !/^-+$/.test(m[1])) rows.set(m[1].replace(/\*/g, "").toLowerCase(), m[2]);
  }
  return rows;
}

/**
 * The REBUILD.md §4 problems of one fixes/ record (`name`, its text): Kind,
 * Old Stores, Old data, Recovery, and for kind 1-2 the compatibility test or
 * for kind 3 the four justifications (rows "Why not kind 1", "Why not kind 2",
 * "Rebuild cost", "Start snapshot"). Records before REBUILD.md are exempt. A
 * cause closed without a product change has Kind "none: <why>" and a Recovery.
 * §4 binds the fixer's `NNN-aK-<slug>.md`; another lane's record (`NNN-359-…`,
 * `c01-…`) is checked only when it declares kind 1, 2 or 3 (owner, 2026-10-21).
 */
export function checkRecord(name, text) {
  if (name === "README.md" || PRE_REBUILD_RECORDS.has(name)) return [];
  const h = recordHeader(text), cell = (...ks) => ks.map((k) => h.get(k)).find((v) => v != null);
  if (!/^\d{3}-a\d+-/.test(name) && !/^\**\s*[123]\b/.test(cell("kind") ?? "")) return [];
  // A cause closed without a product change (README.md): "none: <why>", with its recovery.
  if (/^\**\s*none\b/i.test(cell("kind") ?? "")) {
    const p = [];
    if (!/^\**\s*none\**\s*:\s*\S/i.test(cell("kind"))) p.push("a kind none record says why after \"none:\"");
    if (blank(cell("recovery"))) p.push("recovery is missing");
    return p.map((x) => `fixes/${name}: ${x}`);
  }
  const kind = Number(/^\**\s*([123])\b/.exec(cell("kind") ?? "")?.[1]);
  return checkRebuild({ kind, oldStores: cell("old stores"), oldData: cell("old data"), recovery: cell("recovery"),
    compat: cell("compatibility test", "regression test for compatibility"),
    justification: { kind1: cell("why not kind 1"), kind2: cell("why not kind 2"), cost: cell("rebuild cost"), snapshot: cell("start snapshot") } })
    .map((x) => `fixes/${name}: ${x}`);
}

/** The problems of every record in `dir` (core/docs/issues/352/fixes). */
export function checkRecords(dir) {
  return readdirSync(dir).filter((f) => f.endsWith(".md")).sort().flatMap((f) => checkRecord(f, readFileSync(join(dir, f), "utf8")));
}

/** The findings of `dir` by range: range -> [finding, ...] in attempt order. */
export function loadFindings(dir) {
  const byRange = new Map();
  if (!existsSync(dir)) return byRange;
  for (const f of readdirSync(dir).filter((f) => /^finding-\d+\.a\d+\.json$/.test(f))) {
    const x = JSON.parse(readFileSync(join(dir, f), "utf8"));
    (byRange.get(x.range) || byRange.set(x.range, []).get(x.range)).push(x);
  }
  for (const xs of byRange.values()) xs.sort((a, b) => a.attempt - b.attempt);
  return byRange;
}

/** Relative change from before to after, as "−42%" (lower is better for times and bytes). */
export function change(before, after) {
  if (!before) return "—";
  const pct = Math.round(((after - before) / before) * 100);
  return `${pct > 0 ? "+" : pct < 0 ? "−" : "±"}${Math.abs(pct)}%`;
}

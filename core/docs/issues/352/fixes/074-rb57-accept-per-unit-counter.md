# Re-baseline r55–57 · `--accept-counter` takes a per-unit counter

> **Status:** Current fix record. Harness change in `dsh/tools/history/run.mjs`; no product change. Liaison ruling 2026-10-20: accept Counters `glob_tree.statements per tree file` for r57 only.

| | |
| --- | --- |
| Trigger | `rebaseline --write … --accept-counter "glob_tree.statements per tree file" --accept-ranges 57` was refused. `baselineRows` named a counter only as `probe.counter` (`/^[a-z_]+\.[a-z_]+$/`), and the gate names per-unit counters with a tail (" per tree file") |
| Playbook step | the re-baseline write (SCRIPTS §16) |
| Kind | none: which counter name may be accepted; gates unchanged |
| Commits | `run.mjs` `baselineRows` name check; test in `tests/runner.mjs` |
| Recovery | the write ran again and wrote `baseline-c41a86d23822-a1078e6935cd-p3.json` |

## Design

A named counter is `probe.counter`, optionally followed by ` per <unit>`
(lowercase words). The row must still start with the exact name and `: `, so
`glob_tree.statements` does not match `glob_tree.statements per tree file`,
nor the other way round.

## Proof

`tests/runner.mjs` "a per-unit counter can be the named one (fix 074)":
22/22 pass. It covers the accepted row, another counter of the same probe,
the bare name, and a name with other characters.

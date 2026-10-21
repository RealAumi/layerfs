# Public SDK DeepSeek experiment driver

> Status: Dated planning checkpoint; not release evidence or a product contract.

This external first-party harness reproduces the completed issue323 DeepSeek
experiment through public Rust SDK operations. It is outside production LOC.
[Issue323](https://github.com/Ephemeral-AI-Lab/layerfs/issues/323) owns the original
workload; [issue324](https://github.com/Ephemeral-AI-Lab/layerfs/issues/324) owns
Commit optimization. The current registration and result are in
[registration](../../docs/roadmap/0.1/0.1.7/issue324-current-main-deepseek-rerun-20261015.md)
and [result](../../docs/roadmap/0.1/0.1.7/issue324-current-main-deepseek-result-20261015.md).

The copied driver is mechanically adapted to current duplex names and
Workspace-owned readers. Build Cargo1.85.1 locked/offline release, preserving
repository ARM flags and a worktree-local Cargo target. The measured binary is
`deepseek-sdk-measure`; arguments are fresh case directory, existing complete
prepared input, fresh prepared named volume, and sealed current Linux daemon.
The case contains the original workloads and oracle. Before invocation prepare
the empty native-run directory owned by501:20 on the volume, outside all product
and workload timers. The wrapper enforces the120s full diagnostic stop; individual
workloads/verifiers retain their own stops. Failures retain custody; no automatic
teardown/replay. Timings are INELIGIBLE, with no numeric performance claim.

Other copied drivers/preparation scripts retain their earlier experimental
scope; they were not run in this checkpoint. Do not regenerate or overwrite
historical artifacts with them.

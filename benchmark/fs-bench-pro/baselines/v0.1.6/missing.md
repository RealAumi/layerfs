# Missing released observations

> **Status:** Dated planning checkpoint; no release evidence or product contract.

Searched the three CSV sources in `reference.csv`, both release closeouts,
their `derive_tables.py` generators, and the 25 frozen root family definitions.
No new product or reference sample was taken. Stage 0.3 lists exact missing
case IDs below after resolving the complete Rust registry; the source catalogue
already retains every released row, including missing observations.

| Family | Released timing | Released verification |
| --- | --- | --- |
| `branch_development` | 6 | No released proof row found |
| `dedup_branch_history` | 26 | 20 |
| `dedup_cdc_locality` | 20 | 21 |
| `dedup_cross_file` | 10 | 10 |
| `dedup_workspace_reuse` | 14 | 14 |
| `directory_construction_traversal` | 12 | 12 |
| `edit_canonical_chunk_count` | 12 | 12 |
| `edit_length_changing` | 32 | 32 |
| `edit_length_changing_capped` | No released number found | No released proof row found |
| `edit_length_preserving` | 12 | 12 |
| `file_size_transition` | 7 | No released proof row found |
| `git_tool_workflow` | 4 | 4 |
| `historical_access` | No released number found | No released proof row found |
| `init_namespace` | 4 | 4 |
| `local_snapshot` | No released number found | No released proof row found |
| `mixed_load_bearing` | 8 | 4 |
| `multi_workspace_development` | 5 | No released proof row found |
| `namespace_mutation` | 4 | 4 |
| `payload_create_read` | 8 | 8 |
| `repository_history` | No released number found | No released proof row found |
| `small_file_delta_smoke` | No released number found | No released proof row found |
| `store_footprint` | 6 | 6 |
| `tiny_file_churn` | 20 | 20 |
| `workspace_change_locality` | 16 | 16 |
| `workspace_reliability` | No released number found | 28 |

## Catalogue cases without a released timing

The complete root registry resolves to 273 unique cases in 25 families at
`9af29e01efb83785d0e992d257d36b29d5c2b737`. Of these, 47 have no exact-ID released timing
in the harvested sources. Verification-only or unavailable rows stay in
`reference.csv`; their presence is not a timing. No 26th family was found in
the root family directories, Rust registry, SDK edit registry or wrapper
registries. Aliases and storage-smoke profiles are not additional families.

| Family | Case |
| --- | --- |
| `mixed_load_bearing` | `v016-mixed-exhaustive-100mb-5000-k100-v1` |
| `mixed_load_bearing` | `v016-mixed-exhaustive-500mb-30000-k100-v1` |
| `historical_access` | `v016-access-boundary-before-v1` |
| `historical_access` | `v016-access-boundary-after-v1` |
| `historical_access` | `v016-access-inode-before-v1` |
| `historical_access` | `v016-access-inode-after-v1` |
| `historical_access` | `v016-access-fork-point-v1` |
| `historical_access` | `v016-access-divergent-head-v1` |
| `local_snapshot` | `local-snapshot-create-25000-onebyte-v1` |
| `workspace_reliability` | `workspace-invalid-sdk-edit-compact-v2-proof` |
| `workspace_reliability` | `workspace-invalid-namespace-compact-v2-proof` |
| `workspace_reliability` | `workspace-lease-lifecycle-compact-v2-proof` |
| `workspace_reliability` | `workspace-open-writer-busy-compact-v2-proof` |
| `workspace_reliability` | `workspace-live-execution-busy-compact-v2-proof` |
| `workspace_reliability` | `workspace-candidate-failure-retry-compact-v2-proof` |
| `workspace_reliability` | `workspace-admission-batch-failure-retry-compact-v2-proof` |
| `workspace_reliability` | `workspace-final-publication-failure-retry-compact-v2-proof` |
| `workspace_reliability` | `workspace-published-presentation-failure-smoke-v3-proof` |
| `workspace_reliability` | `workspace-dirty-end-discard-compact-v2-proof` |
| `workspace_reliability` | `workspace-dirty-net-zero-compact-v2-proof` |
| `workspace_reliability` | `workspace-short-spool-write-compact-v2-proof` |
| `workspace_reliability` | `workspace-deferred-nospace-compact-v2-proof` |
| `workspace_reliability` | `workspace-workload-cancel-compact-v2-proof` |
| `workspace_reliability` | `workspace-dirty-runtime-disconnect-compact-v2-proof` |
| `workspace_reliability` | `workspace-corrupt-descendant-compact-v2-proof` |
| `workspace_reliability` | `workspace-missing-descendant-compact-v2-proof` |
| `workspace_reliability` | `workspace-parallel-read-write-compact-v2-proof` |
| `workspace_reliability` | `workspace-shared-path-contention-compact-v2-proof` |
| `workspace_reliability` | `workspace-hardlink-alias-compact-v2-proof` |
| `workspace_reliability` | `workspace-symlink-semantics-compact-v2-proof` |
| `workspace_reliability` | `workspace-open-rename-unlink-compact-v2-proof` |
| `workspace_reliability` | `workspace-metadata-chmod-compact-v2-proof` |
| `workspace_reliability` | `workspace-metadata-mtime-compact-v2-proof` |
| `workspace_reliability` | `workspace-metadata-xattr-compact-v2-proof` |
| `workspace_reliability` | `workspace-exec-500-compact-v2-proof` |
| `workspace_reliability` | `workspace-repeat-publication-compact-v2-proof` |
| `workspace_reliability` | `workspace-sustained-600s-compact-v2-proof` |
| `dedup_cdc_locality` | `dedup-cdc-boundaries-proof` |
| `edit_length_changing_capped` | `insert-middle-4k-input-524283904b-result-500mib-ops-1-capped-v1` |
| `edit_length_changing_capped` | `append-tail-4k-input-524283904b-result-500mib-ops-1-capped-v1` |
| `edit_length_changing_capped` | `prepend-head-4k-input-524283904b-result-500mib-ops-1-capped-v1` |
| `edit_length_changing_capped` | `replace-grow-middle-2k-to-4k-input-524285952b-result-500mib-ops-1-capped-v1` |
| `edit_length_changing_capped` | `zero-extend-tail-4k-input-524283904b-result-500mib-ops-1-capped-v1` |
| `repository_history` | `deepseek-full` |
| `repository_history` | `deepseek-stride3` |
| `repository_history` | `deepseek-stride10` |
| `small_file_delta_smoke` | `small-file-delta-10x30-v1` |

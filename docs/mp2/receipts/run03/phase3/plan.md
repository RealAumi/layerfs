# Phase 3 diagnostic selection

> Status: Dated planning checkpoint; not release evidence or a product contract.

Owner-requested three samples per cell supersede the repository's one-sample
default for this diagnostic only. No release/benchmark qualification is claimed.
Order: remote 0, 2, 20 ms added RTT, then native same-machine Store; repetitions
1, 2, 3 each. Each sample starts from an independent writable clone of the same
closed Disposable Store. No other owner/container/image is modified.

Workload: real Dubbo cb05763298f081ed17171d704408b6478cf8fd83, existing sources
and offline Maven repository copied read-only into owned storage. Offline
`package`, tests/checkstyle/RAT/Spotless skipped, produced 5,354 target files,
260,024,428 bytes, 115 target directories. One HelloServiceImpl greeting change
and another offline package generated the incremental pair: 1,430 rewritten
output files / 23,377,148 bytes, of which three have different content, plus
one changed source file. Original full/delta manifests and Maven logs are kept.

Builds run once outside the timed phase. Exact full and incremental output
snapshots are replayed as ordinary FUSE writes into fresh mounts before each
Commit; no synthetic payload or rebuilt/changed measurement input is used.
This measures the cost of committing real output, not Maven execution on FUSE.
The native arm uses the existing local daemon/Store and the same control client,
mount, writes, source snapshot, build outputs and build profile (`test`, opt=1).

Counter interval surrounds explicit Commit, after copy completes. Wall starts
at the controller before Noise control handshake and ends at the returned reply;
container-exec wall is separately recorded. Upload counters count acknowledged
canonical payload bytes and object records, excluding protocol/TCP framing.
Native transport values are zero. Request counters exclude control RPCs.
Each measured operation has a 25 s product timeout / 27 s outer limit; timeouts
remain failed/incomplete rows with no replay. No timeout will be extended after
seeing an outcome. Preparation commands have explicit 120 s limits.

Apply tc netem to A and B egress toward their sole shared link, half the requested
RTT on each end. Five ping probes verify each condition. No added delay is the
unshaped control (not a claim of zero actual RTT). For each sample, cold mount
and git --no-optional-locks status precede output writes. The 2 ms cases supply
the requested cold-status diagnostic; other cases keep preparation matched.
The B object cache and mount are fresh. Source/Store/OS caches may be warm from
setup and earlier samples. Commits deliberately see warm own-write overlay
payload, warm metadata and output file cache. No drop_caches on the shared VM.

Ten mount/edit/Commit/unmount cycles are a correctness proof, separate from
performance. Capture per-cycle idle thread/FD state, then stop the owned daemon
and check no process or listening/established Store/control socket remains.
The existing five-second drain limit is unchanged. Earlier failure receipts in
run03 remain unchanged. Current-source successes do not establish a cause or fix
for an unreproduced historical failure.

Report median and min–max for three completed samples, raw nanoseconds/bytes in
JSONL; fewer samples are INCOMPLETE, never a fabricated median. Keep every
failure, command, source/build/image/harness/workload identity and cleanup result.

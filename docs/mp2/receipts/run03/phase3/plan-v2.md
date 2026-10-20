# Phase 3 matched cohort v2

> Status: Dated planning checkpoint; not release evidence or a product contract.

Before any v2 sample: retain measure/measure-02 and calibration receipts. The
first setup failed because cp -a requested host UID preservation; copy now uses
--no-preserve=ownership (the mount always presents configured UID/GID 1000).
No Commit was attempted in that failed setup.

The first cohort completed three unshaped Commit pairs, then the nominal 2 ms
condition verified at 7.885 ms average, 5.039–13.326 ms. Its cold status timed out
at 25 s. Those samples cannot be pooled with a precise-RTT cohort.

Independent timer calibration showed OrbStack idle-vCPU timer overshoot. With
a low-priority nice=19 CPU loop on CPU 0 and sender pinned to that CPU, one-sided
B egress netem measured 2.010 ms and 20.008 ms mean RTT. All v2 arms, including
native and unshaped, use this same CPU loop and CPU-0 daemon affinity. This is a
controlled-load diagnostic, not an idle-host or deployment-performance claim.
The three earlier unshaped pairs are retained as a different environment.

v2: remote 0/2/20 ms then native, three samples per arm. The requested cold mount
and git status diagnostic runs at 2 ms. The 20 ms arm warms source metadata with
git status at zero delay before applying/verifying 20 ms for output copy/Commit;
its status row is explicitly labeled zero RTT, not a 20 ms measurement. All arms
reach the same warm-cache preparation before Commit. No failed operation is
replayed; each v2 sample has a fresh independent Store, daemon/cache and mount.
The original 25 s per measured operation ceiling remains unchanged. Full and
incremental outputs, build profile, single construction worker and counting
boundaries are unchanged. Freeze the exact harness SHA and image/binaries in
receipts before starting v2.

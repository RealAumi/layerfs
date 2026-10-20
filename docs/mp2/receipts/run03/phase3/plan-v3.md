# Phase 3 matched cohort v3

> Status: Dated planning checkpoint; not release evidence or a product contract.

Freeze before sampling. v2's CPU-affined daemon with a busy loop hit the
25-second unshaped cold-status limit before any Commit. Calibration also
rejected separated-CPU and SCHED_IDLE arrangements: the former retained timer
overshoot; the latter interfered with application scheduling. Keep all receipts.

Final calibrated arrangement: reuse the Phase-2 TCP proxy, affinity CPU 0,
and a nice=19 Python loop on that CPU which continuously calls sched_yield().
The daemon has normal scheduling/affinity; the loop explicitly yields to runnable
application work. netem is on B eth0 egress only, so its full configured delay is
the added RTT. Calibration: 2.009 ms and 20.011 ms average ping RTT; an unshaped
cold-status preparation completes in 2.483 seconds. This is a controlled-load
proxy diagnostic, with one busy/yielding vCPU, not idle-host qualification.
Native uses the same yielding process and idle proxy; it has no Store transport.

Use the original sample order and three samples per cell with fresh cloned
Stores/caches. 20 ms is applied only after the unshaped metadata preparation;
all measured Commit operations occur under their verified target condition.
Record actual ping results for every sample. No limits extended, no failed
operation replay, no earlier successful samples pooled into this cohort.
All raw v1/v2 and calibration results remain visible. Binaries and input snapshots
are unchanged; record the final harness digest before starting.

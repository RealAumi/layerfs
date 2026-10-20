# Receive wait registration correction

Phase 8 found a regression in the Phase 7 stop patch: 4,869 warm stat requests
cost 27.15% more than its parent. A separate count-only trace records 5,586
ppolls and reads, including 717 EAGAIN reads, versus 4,869 reads at the parent.
Both arms perform zero Store requests. Original measurements and failures are
retained under `../receipts/run08/`.

`ReceiveStop::prepare` now registers each receive channel once in its own epoll
instance, with exclusive device wakeups. The stop pipe is nonexclusive: closing
its sole writer remains a persistent broadcast HUP. No receiver consumes it.
`ReceiveWait::receive` prioritizes that HUP, keeps the channel nonblocking, and
still dispatches any request already read. The monitor keeps the pipe alive.
Startup failures retain the existing join path. Detach, active-request drain,
join deadlines, final request proof and custody are unchanged. No abort or replay.

The existing nix dependency enables its event feature; no dependency version or
lock changes. The original Phase 7 provenance remains immutable. This record
pins the additional diff and hashes. Matched performance and native custody
qualification follow the sealed source commit; see the final Phase 8 results.

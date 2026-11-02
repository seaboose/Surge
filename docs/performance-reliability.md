# Performance and reliability acceptance criteria

Criteria fixed before the first milestone measurement, 2026-10-22. These are
development budgets for this Windows host and the owned two-range fixture, not
production requirements or real-cheat accuracy claims. Preserve the ten-minute
session limit and all existing renderer and process-targeting boundaries.

## Acceptance gates

1. Run the complete Electron application, Python worker and native child for one
   default 500 ms, ten-minute capture. Observe automatic stop within 615 seconds,
   at least 1,000 complete samples, zero transport drops and no application errors.
   Retain at most 500 complete samples and an 8 MiB encoded window. Evictions must
   produce Unknown health evidence; measured clean ranges keep their own verdicts.
2. Sample resources every two seconds. Sum private bytes across all Electron
   processes, the Python worker and the native child. Peak sampled private bytes
   must be below 1 GiB. After warm-up/window fill, the last-minute median must be
   no more than 64 MiB above the median at 300–360 seconds. Report working set too,
   but do not sum shared working sets and call that unique physical memory.
3. Average process CPU over the capture must stay below 15% of one logical core
   (100% means one fully occupied core). Include periodic inspections and exports;
   exclude the measurement harness. Report hardware, versions and sampling gaps.
4. Final retained sample interval p95 must be at most 750 ms and maximum at most
   2,500 ms. Measure persistent in-range changes at a 500 ms interval in ten
   separate controlled trials: all detected, acknowledgement-to-evaluated-result
   latency at most 1,500 ms. This excludes between-sample changes and is not a
   bound on scheduling under arbitrary host load.
5. During capture, inspect and export every 60 seconds. Each operation and normal
   stop must finish within 3 seconds. Reopen the final export and saved case with
   identical findings. Background capture must not alter an inspected snapshot.
6. Perform 20 additional desktop start/stop cycles. Each must obtain evidence
   within 3 seconds, use a distinct session identity and release its native child
   within 5 seconds. Final app shutdown must release worker and native child
   within 5 seconds. Post-cycle private-byte growth must be at most 64 MiB versus
   the stopped full-session app (allowing normal allocator caching).
7. Withhold native stdout consumption for 8 seconds at 100 ms sampling, then
   resume. The bounded queue must report loss, the export must remain replayable,
   and loss must produce Unknown health evidence. Native sampled private bytes
   must remain below 32 MiB. Abrupt producer termination and a real >5-second
   producer stall must preserve prior evidence and produce Unknown, never a clean
   health verdict. Recovery from a temporary stall must resume collection.

## Method and evidence

Use fresh, explicit in-memory approval only in controlled detector trials; do not
alter the operator's approval registry. Desktop runs use its ordinary approval
state, so unapproved ranges may correctly require Review. Preserve first-run
failures and explain any harness corrections separately from product fixes.
Record exact and LF-normalized source hashes, binary hashes, environment and raw
measurement summaries. Repeat affected checks after changes; run the relevant
Python, native and desktop regressions on the final implementation. Extended
measurements supplement existing CI and do not establish leak freedom, other-host
performance, arbitrary DLL compatibility or resistance to a privileged attacker.

Results will be appended after execution. No thresholds will be silently relaxed.

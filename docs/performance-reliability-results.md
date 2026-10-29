# Performance and reliability results

The corrected full desktop run passed all [acceptance criteria](performance-reliability.md)
on 22 October 2026. The criteria were fixed before measurement. No production-code
change was needed. New repeatable runners exercise the existing desktop boundary
and controlled failure paths. [Machine-readable evidence](../evidence/performance-reliability-validation.json)
includes the measurement timeline, per-role resources, exact source and binary
fingerprints, environment, operations and pass/fail gates.

## Full desktop measurement

The run used Windows 11 build 26200, an AMD Ryzen 9 5950X with 32 logical processors,
Python 3.12.14 and Electron 44.9.1.
The renderer was rebuilt from current source. The existing native Release binaries
are identified by hashes. No operator approvals were changed; the default v1 build
was unapproved and correctly produced Review for its readable ranges.

- Automatic stop was observed after 601.41 seconds. The collector
  produced 1,189 samples with zero transport drops.
- The final window contained 1,000 range records (500 complete samples),
  plus one Unknown health record for 689 evicted older samples.
  The export occupied 3,246,183 bytes and reopened successfully.
- Average CPU was 2.41% of one logical core, below 15%.
  This is not a percentage of the whole 32-thread machine.
- Peak sampled aggregate private memory was 254.66 MiB,
  below 1 GiB. The final-minute median changed by
  +3.61 MiB relative to seconds 300–360,
  within the 64 MiB growth budget.
- Retained-window sample gaps were 507 ms at p95 and
  516 ms maximum, below 750/2,500 ms.
- Maximum Inspect latency was 397.6 ms and maximum Export
  latency was 84.9 ms. Periodic operations include button
  interaction and rendering. Maximum Stop latency was 376.0 ms
  through the desktop request boundary. All were below 3 seconds.
- All 20 additional start/stop cycles passed, alternating the two owned builds.
  First evidence arrived within 75.8 ms.
  Every session identity was distinct and every native child exited. Private memory
  changed by -0.54 MiB after the cycles.
- Shutdown with an active capture released the worker and collector within
  135.8 ms. No renderer or measurement errors were recorded.
- Background collection preserved each inspected source hash and revision.
  Reopening both the final export and saved case reproduced the findings.

## Controlled failure checks

Ten persistent primary-range changes at a 500 ms interval were all detected.
Acknowledgement-to-decoded-and-evaluated-result latency ranged from
489.0 to 492.8 ms, below 1,500 ms.
Each restoration returned matching bytes. Timing was deliberately near a full
sampling interval; these ten checks are not a population-level latency estimate.

With native stdout unread for eight seconds at a 100 ms interval, the bounded
writer reported 39 drops and delivered
34 samples. Peak sampled native private memory
was 1.03 MiB,
below 32 MiB. The decoded export contained one Unknown health record and preserved
the readable, approved range verdicts.

Suspending only the test-owned producer for six seconds produced Unknown health
evidence. Collection recovered after resume. Killing that producer then preserved
earlier observations, produced Unknown for the incomplete ending, and released
the reader thread. These checks never target another application's process.

## First attempt and corrections

The first full-desktop attempt stopped after the runner selected the same export
filename twice. Surge correctly refused to overwrite it. The runner failed behind
the resulting error dialog; this was not a collection failure. The runner now
uses unique checkpoint filenames and rejects visible error dialogs immediately.
A short rehearsal verified export, replay, 20 restarts and shutdown before the
corrected full run. The failed attempt remains in local verification evidence;
its cause is retained in the public report. Acceptance thresholds were unchanged.

Preliminary runner setup also corrected a Python module-name collision and used
read-only registry CPU identification in place of unavailable system inventory.
Formatting preserved the Python runner's syntax tree. These corrections did not
change Surge's detection or collection implementation.

## Reproduce

Build the desktop and native app using the normal setup instructions, then run
from the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -B scripts/measure_reliability.py --phase faults
.\.venv\Scripts\python.exe -B scripts/measure_reliability.py --phase desktop
```

The desktop phase takes about eleven minutes. Run it separately from other test
suites and heavy workloads. Each invocation creates an isolated profile and unique
evidence folder under `verification/electron/`; existing exports and approval files
are preserved. The short rehearsal is a harness check, not an acceptance run:
`node desktop/reliability.cjs verification/electron/unique-smoke-folder --smoke`.

## Interpretation and limits

Final local regression validation passed all 270 Python tests, three native
CTests, four desktop boundary/runtime checks, the continuous desktop journey
(including graceful and forced shutdown), and the native-evidence journey.
The new runners passed Black/Prettier formatting checks; source hygiene and
Git whitespace checks passed. Existing application code and detection logic were
unchanged. Hosted CI was not rerun for this local, uncommitted milestone.

Resources were sampled 293 times while capture was active,
approximately every two seconds; the longest measurement gap was
2.57 seconds because UI work also takes time.
CPU totals use cumulative process time between samples and exclude the measurement
harness. Two-second sampling can miss transient peaks and short-lived processes.
Per-role working sets are recorded but may share physical pages; their sum is not
unique physical RAM. No forced garbage collection was used.

This is one ten-minute session on one host, followed by twenty short cycles. It
does not establish multi-hour endurance, leak freedom, performance under CPU or
memory saturation, or performance on other hardware. The exported timing window
contains the most recent 500 samples. Only two owned ranges totaling 15 bytes are
checked. Outside-range and between-sample changes, forged local evidence and a
compromised collector remain outside the demonstrated guarantees.

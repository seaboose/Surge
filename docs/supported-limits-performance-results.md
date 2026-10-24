# Bounded desktop performance results

The local working tree passed the [criteria fixed before measurement](supported-limits-performance.md)
on 24 October 2026 UTC. All four journeys and all 32 measured operations passed
in 59.95 seconds, within the 300-second campaign limit. This is one local Windows
host, not a hosted performance run or an unfamiliar-user acceptance result.

The two fixtures were each run twice in fresh profiles, followed by a full app
restart and saved-case reopening. Representative input had 100 records, eight
fields and two rules. Combined-limit input had 10,000 records, 64 fields and 32
rules, padded with valid whitespace to exactly 16 MiB. One rule matched half the
records; the other rules did not match. The larger fixture is a bounded field-rule
workload, not a worst-case representation of every accepted input.

## Measured results

Worst observed times across both repetitions:

- All fresh/restarted openings: 0.70 seconds, below five seconds.
- Representative import, analysis, save and reopen: 0.14, 0.18, 0.15 and
  0.12 seconds respectively, each below three seconds.
- Combined-limit import, analysis, save and reopen: 1.42, 0.62, 0.88 and
  2.38 seconds respectively, each below 15 seconds.
- Search and clear, including debounce and UI update: 0.28 seconds at most,
  below one second. Exact target-row and displayed-total checks passed.
- Renderer 50 ms timer: maximum observed gap 90.1 ms; worst per-journey p95
  82.0 ms, below 500/100 ms. These describe timer gaps, not a universal UI
  latency promise.
- Peak sampled aggregate private memory: 375.91 MiB across 210 samples,
  below 1 GiB. Every sample included the owned Python worker and Electron
  processes. Sampling ran approximately every 250 ms after window readiness;
  the longest gap was 1.013 seconds across a complete application restart.
- Actual saved cases were 52,443 bytes and 22,053,390 bytes. Reopening after
  restart preserved source digests, settings, summaries and every paginated
  result-row descriptor. Both repetitions produced identical result digests.
  Original fixture bytes stayed unchanged. No renderer or resource-reading
  error occurred, and no scenario was skipped or left unrun.

The host was Windows 11 build 26200, Python 3.12.14, Node 24.19.0 and Electron
44.9.1, with 32 logical processors. Exact source and built-renderer fingerprints
are in the [machine-readable evidence](../evidence/supported-limits-performance-validation.json).
The recorded Git HEAD was `937a19b`; the source-state patch and hashes identify
the additional UI/library changes actually measured. A later commit or hosted
qualification must not be described as this exact measurement without comparing
those fingerprints.

## Evidence and failed attempts

The successful attempt is `verification/qualification/supported-limits-661e84cd4276`.
It retains both fixtures, isolated profiles/cases, screenshots, criteria, runner
snapshots, source-state patch, raw process logs, heartbeat samples and memory
readings. Independent verification checked all 276 manifest entries and
112,458,920 bytes against their hashes, as well as fixture sizes, result equality,
all operation budgets and repeated outcomes. Raw manifests do not authenticate
evidence against a privileged local actor.

No campaign attempt failed. A preparation command found that the new virtual
environment lacked the optional Black formatter. Its failed output is preserved
in `supported-limits-preparation/black-unavailable.txt`; the existing configured
formatter completed the check without adding a product dependency. Prettier and
Python/Node syntax checks passed. No production fix or relaxed threshold was
needed for this measurement.

## Reproduce and limits

After normal desktop setup/build, run on Windows:

```powershell
.\.venv\Scripts\python.exe -B scripts/measure_supported_limits.py
```

Each run creates a new evidence directory. Run with a stable source/build and no
competing UI automation. File dialog choices are supplied by the harness; typing
and native-dialog navigation are excluded from action timings. Some checks use
the ordinary desktop request boundary to verify data behind the visible state.

Two repetitions on one host do not establish other-machine performance or a
statistical service level. Memory sampling can miss short peaks and excludes
startup before the window is ready. The runner does not exercise the 64 MiB
case ceiling, very large libraries, numeric-reference analysis, maximum strings,
other import formats, comparison/evaluation, live capture, unsupported disks,
CPU saturation or multi-hour stability. Earlier capture and retention measurements
remain separate evidence. Unfamiliar-tester acceptance and broader fuzzing remain
unfinished.

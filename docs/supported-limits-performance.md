# Bounded desktop performance acceptance

Criteria fixed before measurement for this local Windows host. This is a
development qualification, not a performance promise for other hardware.

## Workloads and bounds

Run two owned, deterministic JSON fixtures twice, each in a fresh desktop profile:

- Representative: 100 records, eight fields, two field rules.
- Combined import limits: 10,000 records, 64 fields, 32 field rules, padded with
  valid JSON whitespace to exactly 16 MiB. Values stay below the 4,096-character
  field limit. One rule matches half of the records; other rules never match.

No native capture or external process targeting is performed. Preserve all
attempts in unique `verification/qualification/supported-limits-*` folders.
The complete runner has a 300-second wall-clock limit. Each action has a
30-second timeout. Do not relax limits after observing results.

## Acceptance criteria

1. Startup to an interactive opening screen completes within five seconds in
   each fresh profile and when restarting with its saved library.
2. Import, analysis, save to library, and reopening complete within three seconds
   for the representative fixture and 15 seconds for the combined-limits fixture.
   Measurements include the real desktop request and resulting UI update; native
   file picker time and typing a case name are excluded.
3. Searching for one exact record and clearing the search each complete within
   one second, including debounce and rendering. The table shows the expected
   record and total; all original results return after clearing.
4. A renderer timer scheduled every 50 ms during the measured journey has a
   maximum observed gap of 500 ms and p95 gap of 100 ms. This is an event-loop
   responsiveness proxy, not a measurement of every interaction or paint.
5. Sample owned Electron process and Python worker private bytes approximately
   every 250 ms. Peak sampled aggregate private bytes stay below 1 GiB. Preserve
   sample timestamps, gaps and per-process readings. Sampling may miss transients;
   working-set sums are not reported as unique physical memory.
6. Imported record/field/source-byte counts match the fixture. Analysis has exactly
   half Review and half No finding, no Unknown. After save and a full application
   restart, reopening preserves the source digest, settings, summary and every
   record result, compared through bounded 100-row result pages. The original
   fixture bytes remain unchanged. No page errors or measurement errors occur.
7. Preserve raw process logs, screenshots, source/criteria hashes, fixture hashes,
   exact measured values and failed/unrun scenarios. An incomplete attempt cannot
   pass. Two repetitions are checks of repeatability, not statistical confidence.

## Explicit exclusions

The 64 MiB saved-case ceiling is not filled artificially. Report actual case sizes.
The combined fixture stresses field rules; numeric reference analysis, maximum
string values, CSV/JSONL, comparison/evaluation, very large case libraries, live
capture, CPU-saturated machines, network disks and multi-hour memory stability
remain unmeasured by this runner. Earlier ten-minute capture and retention tests
remain separate historical evidence. Unfamiliar-tester acceptance and broader
fuzzing remain unfinished.

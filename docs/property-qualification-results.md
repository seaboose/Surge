# Hypothesis qualification results

23 October 2026. **All 19 combined qualification steps passed from a clean checkout in 293.532 seconds.** The property step completed **768 evaluations** in 144.219 seconds, using pinned Hypothesis 6.170.8. All 301 standard Python tests passed without skips, and the existing three native CTests passed both normally and under verified ASan instrumentation.

## Results against acceptance criteria

- **Manifest validation: passed.** Generated complete partitions agreed with the independent byte-occupancy model. Each layout also rejected a hole, overlap, wrong coverage total, boolean module size and unsupported descriptor version. Valid input was unchanged after validation.
- **Stream ordering: passed.** Generated delivered/lost slot histories produced the expected sequence and loss counters. Duplicate/reversed sequences, an unexplained gap, decreasing loss counters and backwards time were rejected.
- **Replay consistency: passed.** JSON and JSONL produced equal summaries and records for clean, changed and unavailable approved observations. Counts matched explicit expected No finding, Review and Unknown outcomes, with loss-health evidence retained. Both formats rejected sibling identity changes and reversed histories. Replay did not mutate the supplied rows.
- **Repeatability: passed.** Each of three properties executed 64 examples for seeds 20261023 and 17, then repeated those runs. All six input fingerprints and counts matched across repeats. This is 768 property evaluations, not 768 unique inputs, measured code coverage or a proof of correctness. Stream and replay properties intentionally use the same generated history strategy.
- **Bounded execution and reporting: passed.** The property command stayed within its five-minute outer limit, two-second example deadlines and existing log budget. No skipped cases, filtering or suppressed health checks were used. Regression tests reject absent/malformed/short evidence, mismatched fingerprints, wrong totals and failed child processes.
- **Clean-checkout compatibility: passed.** All 19 steps completed. The checkout began without environment, desktop dependency/build, native build or capture artifacts. Git was clean before and after; the 177 source-package files remained unchanged during execution. The combined run also repeated ASan detection controls, five demos, owned fixture/stream checks and both desktop journeys.

No application defect was found in this bounded set and no production behavior changed. The changes add optional testing dependencies, the property suite, qualification-report integration and report-validation regressions. Hypothesis runs on synthetic in-memory Python data; it does not launch native targets or inspect external applications. The rest of the qualification retains its existing owned-fixture scope.

## Reproduce and trace the evidence

Run `python -B scripts/qualify.py --properties`; add `--asan` to reproduce the combined 19-step profile. Pinned wheel-only dependencies are installed into the checkout's test environment. The default application and standard tests do not acquire a Hypothesis dependency. See the [acceptance specification](property-qualification.md), [qualification guide](qualification.md) and [generated evidence](../evidence/property-qualification-validation.json).

Snapshot commit: `a3885a9869cbf0ffb965e093f744724a3666b5b5`.

Normalized source fingerprint: `6ef1f0ad8a448214eb85a9f7cf89e208276f1282a7b69158b2f0473660ad048f`.

Run: `run-c8ab7817bd5f`. This isolated snapshot did not commit or push the original repository. Implementation files match the tested source; final evidence and results documentation were added afterward. Download caches and the same Windows host were reused, so this is not a fresh OS or independent-machine result. Timing measures qualification execution, not application performance.

## Remaining limitations

The original T1/T2/T3 campaign remains incomplete and original gates 2–6 are not closed. The report's `fuzzing.executed=false` refers to that original campaign; the optional Hypothesis evaluations above did run. This distinction preserves the earlier milestone instead of silently reducing its acceptance criteria.

This suite tests bounded schemas and history patterns, not every malformed manifest field, whole-process integrity, terminal-state/lifecycle interleavings, production retention limits, or the full approval/verdict state space. It supplies no native coverage-guided parser campaign, code-coverage threshold, held-back variants or long-duration endurance result. Generated histories use 2–16 ranges and 2–8 delivered samples. Fixed seeds are repeatable in this recorded environment, not guaranteed across Python or Hypothesis versions. Local unsigned evidence remains forgeable and is not attestation.

The initial package-download attempt could not resolve the package index inside the restricted network environment. Installation succeeded in the authorized normal session. The preliminary property suite and subsequent clean-checkout qualification both passed; no product-code failure was concealed or relabeled.

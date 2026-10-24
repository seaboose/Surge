# UI keyboard readiness investigation and qualification

23 October 2026. **A narrow test-only readiness fix passed all 20 qualification checks from a clean checkout in 353.719 seconds.** No application behavior or parser code changed. The original intermittent failure's exact cause remains unproven.

## Acceptance criteria and results

- Preserve the original failed UI attempt and any new failures: **passed**. The original `run-1a7ea875ea84` report and Python log remain intact, with hashes recorded in the new evidence. The deliberately induced pre-fix failure and disabled-navigation control failure are also retained with separate labels.
- Establish evidence before changing code: **passed with a causal limitation**. The unchanged original scenario passed 30/30 repetitions with keyboard focus diagnostics. A pending focus transfer inside the owned window then reproduced the exact match-index assertion failure (expected 1, observed 0). This establishes a test-readiness gap, not the cause of the historical event for which no focus trace exists.
- Keep the fix narrow and assertions meaningful: **passed**. Only `test_preview_values.py` changed. The test pumps pending UI events, requests entry focus and checks visibility plus actual focus before each generated key. It allows at most one second to establish readiness, with a clear readiness failure if unsuccessful. F3 and Shift-F3 are each generated once; result assertions are unchanged and never retried. No arbitrary long sleep, skip, whole-test retry, timeout increase in qualification, or production focus stealing was added.
- Exercise the regression and existing preview behavior: **passed**. All 40 preview tests passed. A further 40 repetitions alternated 20 original scenarios and 20 pending-focus scenarios; all passed. Disabling navigation with a test-only mock still caused the expected match-index failure, confirming readiness does not conceal broken navigation.
- Verify from a fresh checkout: **passed**. All 305 Python tests, 768 Hypothesis evaluations, native tests, both sanitizer control profiles, owned fixture/stream checks, desktop journeys and source hygiene passed. The 20-step combined profile completed with a clean Git state before and after and unchanged source during execution. All generated check-log and retained parser-corpus hashes were independently checked when assembling this report.

## Investigation and failure record

The historical failure happened after a forced-focus request followed by other UI processing and before the test's focus assertion. Tk keyboard delivery depends on the active focus target. The controlled regression schedules a focus transfer to the preview widget after the first focus request. Before the fix, this produced the same `0 != 1` assertion. After the fix, readiness is re-established before key delivery and both forward/backward match navigation assertions pass. No concurrent external windows or third-party application manipulation were needed.

The historical failed UI test remains a failure. Its subsequent isolated pass and later clean passes do not retroactively change that result. The deliberately disabled-navigation control is an expected test failure, not an application defect. The earlier parser-toolchain failures and corpus-monitor failure remain documented in [parser pilot results](libfuzzer-pilot-results.md) and their evidence; none were overwritten.

## Clean-checkout provenance

Snapshot commit: `2642afcd3182507ad9107aa1ef84852ae94bc761`.

Normalized source fingerprint: `6701cec9e0f876302280cdfcdd3fb531846aca04ff066db5feacbbf4b84785f6`.

Qualification run: `run-effe35827b56`.

Command: `python -B scripts/qualify.py --asan --properties --libfuzzer --llvm-bin <LLVM-bin-directory>`.

The source snapshot was copied without existing virtual environments, dependency directories or build artifacts, then committed and cloned locally for verification. The working repository was not committed or pushed. The tested application source matches the source from the original failing run. Documentation and evidence for this result were added after qualification.

## Parser pilot and remaining limits

This qualification independently repeated the bounded parser pilot: two seeds, 5,000 executions each, 10,000 total, with verified ASan detection and libFuzzer instrumentation. Retained-corpus coverage was 227/267 lines and 176/220 branch outcomes. All 111 retained inputs replayed consistently. These are this run's counts, not a cumulative total across earlier attempts.

The UI results are finite, same-host evidence. They do not prove every focus race is eliminated, behavior under continuous external focus interference, or operation on another Windows host. The original event's cause remains unknown. The readiness helper can fail explicitly if focus cannot be obtained within its bound; the event loop itself is not independently preempted by that bound and remains subject to the outer suite timeout.

The original T1/T2/T3 campaign remains incomplete. The parser pilot does not supply comprehensive semantic validation, full relocation/boundary coverage, a held-back final phase, or a memory-safety/whole-process integrity proof. See the [pilot acceptance criteria](libfuzzer-pilot.md) for its narrower scope.

[Generated evidence](../evidence/qualification-ui-validation.json) includes the full new qualification report, repetition observations, artifact hashes, negative-control result and limitations.

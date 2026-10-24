# Replay correctness fixes and bounded-campaign status

23 October 2026. **The two confirmed replay defects are fixed and regression-tested. The full fuzzing milestone is incomplete: no development or final fuzz campaign ran.**

This report evaluates the unchanged acceptance gates in [the adversarial review and specification](adversarial-correctness-review.md). Machine-readable results and source fingerprints are in [the validation record](../evidence/adversarial-correctness-validation.json). Work remains local and uncommitted, based on `2b9e3c8bbfc22c7a82827f39e404fa87e7eb8fb5`, with the earlier performance/reliability changes preserved.

## Changes and evidence

`native_stream.py` now explicitly rejects nonincreasing sample sequences and decreasing cumulative transport-loss counters during replay. The existing difference equations still account for legitimate loss; opposite counter changes can no longer cancel each other and conceal missing health evidence.

One shared live-identity check now serves collection and replay. It validates a positive 32-bit PID, the existing decimal process-creation representation, a supported build, and consistent session/process/module/build identity across sibling observations and samples. Existing one-shot formats remain readable. Older live evidence without an integrity manifest still works. Session identifiers remain opaque, and the existing decimal string/integer creation representation was preserved.

The new `test_native_replay_contract.py` contains 15 tests. Before changing production code, it exposed **46 failing import subcases** across JSON and JSONL, with no unexpected errors. After the fix, all 15 tests pass. Positive controls also verify that valid approved evidence remains No finding, declared transport loss retains Unknown health, and legitimate older formats remain readable. These counts are deterministic checks, not a detection-accuracy estimate.

Two contract clarifications have regression coverage and documentation:

- An unreadable approved observation is Unknown. An unreadable unapproved observation is Review with gaps: the missing approval finding takes precedence, and unavailable comparisons remain explicit. The general verdict policy did not change.
- Staleness describes current collection health. Recovery clears the current stale condition; a retained pause is visible in elapsed timestamps but need not leave a health row in the final export. No historical-stall logging feature was added.

Only `native_stream.py` changed in production. The native parser, producer, retention algorithm, approval rules, and verdict engine did not change.

## Validation performed

- New contract suite: **15 tests passed**, 0.104 seconds; the original-source run had 46 expected failing import subcases in 15 tests.
- Focused integrity, manifest, stream, window, session and contract suite: **62 passed**, 12.654 seconds.
- Full Python suite: **285 passed**, 67.743 seconds.
- Existing native CTests: **3 passed** (`bounded_pe_parser`, `versioned_manifest_parser`, `collector_without_scenarios`). These used the existing native build; no C++ production change required rebuilding it.
- Published demo replay: **5 cases passed** with their expected No finding, Review and Unknown outcomes.
- Native desktop journey: passed automatic mapping, changed-byte evidence, approved updates and unavailable observations.
- Continuous desktop journey: passed start, stable inspection, stop, export, case replay, restart, keyboard/text scaling, and graceful/forced shutdown checks.

The focused suite initially encountered sandbox temporary-directory write errors. Using a workspace-local temporary directory resolved those setup errors. The first native desktop launch also failed under the workspace launch restriction; it passed after the ordinary reviewed execution request. These were environment failures, preserved in local logs, and did not require product changes. Formatting used single-file invocations after the formatter's multi-file invocation stalled. The final formatting check caught four wrapping differences; applying the repository's 96-column setting preserved both Python syntax trees exactly. The evidence records evaluated and final formatted hashes separately.

## Acceptance-gate assessment

1. **C1/C2 closed — PASS.** Both defects were demonstrated before the fix and rejected afterward through encoded import. Sibling and cross-sample identity conflicts, invalid PID/creation values, supported build values, valid loss, positive controls and older formats are covered. C3 and A1 have explicit semantics, tests and documentation.
2. **Native safety — INCOMPLETE.** Tool discovery found an installed MSVC AddressSanitizer runtime and no available LLVM/libFuzzer toolchain. There is no completed instrumented harness build or successful instrumentation self-check in the evidence. The existing CTests do not replace sanitizer-backed fuzzing. No new memory-safety conclusion is claimed.
3. **Semantic correctness — INCOMPLETE.** The known defects and existing deterministic cases pass. The planned independent generated-layout, approval/verdict and stream-model oracles were not completed or run. Passing regressions cannot establish the broader gate.
4. **Reachability — INCOMPLETE.** No campaign category counts, rejection distributions or instrumented deep-branch evidence were collected. Existing parser tests are useful compatibility checks, not the proposed reachability measurement.
5. **Retention and replay — INCOMPLETE for the new campaign.** Existing window/session tests and both desktop replay journeys pass. The newly specified deterministic production-limit pack and generated retention-model comparisons did not run.
6. **Determinism and final separation — INCOMPLETE.** The known defects have named regression tests and recorded pre/post source hashes. No complete fuzz corpus, generator freeze, held-back final run or twice-replayed minimized final corpus exists. The final phase was never started.
7. **Existing compatibility preserved — PASS.** The required focused Python checks, three native CTests and native/continuous desktop journeys passed. Native layout behavior did not change, so the prior build-layout matrix was not repeated. The ten-minute performance campaign was not rerun: this change adds bounded identity/counter validation and does not alter producer, buffering, lifecycle or retention policy. No fresh performance result is claimed.

Overall: **2 gates passed; 5 remain incomplete.** T1, T2 and T3 are all incomplete under the original specification. The acceptance criteria were not relaxed to turn this partial result into a pass.

## Why fuzzing did not run

During implementation, both the Python harness task and the native harness task were stopped by an automated cybersecurity safeguard reporting possible cybersecurity risk and directing the user to Daybreak access. This is an execution/access limitation, not a finding about Surge. The blocked tasks were not retried under different wording, moved to another model, or completed by another agent.

Partial native harness sources were preserved outside the publishable repository as unexecuted work. They are not a usable or verified test deliverable. No campaign inputs, final variants, minimized corpus or sanitizer findings are reported. The 90-minute campaign budget was not started; reaching a safeguard before execution is not a successful zero-failure run.

OpenAI describes Daybreak as an approved-access program scoped to a particular identity, workspace or organization, model and product surface. It does not replace local scope, sandboxing or action review. Enrollment for this session could not be verified. Official guidance acknowledges that legitimate work can be flagged and describes feedback/support routes. See [Models and Trusted Access](https://learn.chatgpt.com/docs/cyber-safety) and [Cybersecurity checks](https://developers.openai.com/api/docs/guides/safety-checks/cybersecurity). Requesting access does not itself establish approval. No account, model-access or safeguard configuration was changed.

## Reproduce the completed checks

Run from the Surge root with the existing environment and native build. Use a writable temporary directory when the execution sandbox restricts the default temporary location.

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v test_native_replay_contract
.\.venv\Scripts\python.exe -B -m unittest -v test_native_integrity test_native_manifest_security test_native_stream test_native_window test_native_session test_native_replay_contract
.\.venv\Scripts\python.exe -B scripts/test.py
ctest --test-dir native/build -C Release --output-on-failure
.\.venv\Scripts\python.exe -B scripts/verify_native_demo.py
```

From `desktop`, run `node native.test.cjs` and `node stream.test.cjs`. The former uses the existing owned-fixture capture set named by `native/captures/latest.json`; both create isolated test profiles. Raw logs remain in local workspace scratch because they contain local paths. The checked-in evidence records sanitized summaries and hashes.

## Remaining limits and continuation

These changes enforce internal consistency of live evidence and its replay. They do not authenticate unsigned local captures, establish resistance to a privileged attacker, broaden the measured byte ranges, or detect changes outside coverage or between reads. The parser's broader malformed-input space, memory safety under instrumentation, generated manifest/approval interactions, and generated stream/retention histories remain untested by the proposed campaign. The collector's 64 MiB outer file-size boundary remains excluded as originally specified.

No new campaign result, whole-process integrity claim, real-cheat accuracy claim or leak-freedom claim is justified. Existing performance measurements describe their recorded source version; this pass supplies correctness and compatibility evidence only. Protected network holdouts and archived evaluation evidence were unchanged. No commit, push, release package or hosted CI run was made.

Continuation requires resolving the safeguard/access restriction through the appropriate product access or false-positive review route. Once resolved, review the partial harness sources afresh, finish and verify the three harnesses and their controls, then follow the original development/freeze/final sequence. Do not reuse this regression pass as a substitute for those missing acceptance gates.

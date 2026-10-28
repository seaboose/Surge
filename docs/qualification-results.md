# Clean-checkout qualification results

**Later working-tree milestone (23 October 2026):** the combined opening and local Case library have separate [acceptance results](case-library-results.md). Their focused tests passed, but clean-checkout qualification has not been repeated for those changes. The clean-checkout results and fingerprint below describe the earlier snapshot only. The unfinished fuzzing campaign remains incomplete.

23 October 2026. **All 12 defensive qualification steps passed from a clean local checkout in 139.297 seconds. The unfinished fuzzing campaign remains incomplete and was not run.**

The [qualification command and acceptance criteria](qualification.md) define this check. Its [generated evidence](../evidence/qualification-validation.json) records every command, result, timing, source fingerprint, environment and the earlier failed attempts.

## What was verified

The successful run started without `.venv`, `desktop/node_modules`, `desktop/dist`, `native/build`, `native/captures` or `native/baselines.json`. It installed locked dependencies, built the renderer and owned native fixtures, generated new fixture captures and ran the existing tests. Git reported a clean worktree before and after, and all 168 source-package files remained byte-for-byte unchanged throughout the run.

The tested commit, `cef5c2c9eef34924eabe0de7f10d4823700e3dd9`, is an isolated local snapshot of the proposed working-tree source, based on upstream commit `2b9e3c8bbfc22c7a82827f39e404fa87e7eb8fb5`. It was cloned into a new directory with spaces in its path. This did not commit or push the original repository. The original working tree's evaluated code matches the clean checkout after line-ending normalization; final result prose and evidence were added afterward.

Source tree fingerprint, normalized for line endings: `9d182437c9fd568d0eb646c1083d25fb6c42d7d4231eeb1abcfc54b9fa87f448`.

Environment: one Windows AMD64 host, OS version 10.0.26200, Python 3.12.14, Node 24.19.0, pnpm 11.25.0 and CMake 4.4.4. This was a fresh source/dependency/build directory on the same host; package-download caches were reused. It is not an independent-machine or fresh-OS result.

## Completed checks

- **Setup, native configure and native build:** passed. The checkout's environment, renderer and Release binaries were created from scratch.
- **Python suite:** 295 tests passed with no skips, including ten runner tests and the fifteen replay-contract tests.
- **Native CTests:** all three passed after the fresh build.
- **Published demo replay:** all five expected-outcome cases passed.
- **Owned-fixture capture/replay:** the existing runner generated fresh cases and isolated approvals, verified expected observations and reopened saved cases.
- **Owned stream checks:** the existing bounded short-session/lifecycle suite passed.
- **Desktop boundary checks:** passed.
- **Native desktop journey:** passed automatic mapping, changed-byte evidence, approved updates and unavailable evidence.
- **Continuous desktop journey:** passed collection, stable inspection, stopping, export, saved-case replay, restart and shutdown checks.
- **Source hygiene:** passed.

The qualification's four acceptance criteria pass: every required step succeeded; Python had zero skips and the three native checks executed; source was unchanged; and the report identifies the evaluated source while separately recording T1/T2/T3 as not run. Both additional clean-checkout conditions also pass: clean Git status before/after and no reused environment/build/capture directories.

## Failures found and fixed

The first qualification stopped at setup. Windows PowerShell stripped double quotes from the inline Node version check. `Setup-Surge.ps1` now uses single-quoted literals inside its Python/JavaScript command arguments, preserving them through Windows PowerShell. Later steps were correctly left `not_run`.

The second clean run passed setup, the build, the Python suite and all three native tests, but qualification stopped because its CTest summary parser expected an older wording that included “0 tests failed.” The parser now accepts both observed success forms. A regression checks both forms while retaining rejection of absent/empty native results. This was a runner failure; the native tests themselves passed.

The third attempt used another fresh checkout and passed the entire unchanged test plan. The evidence retains all three candidate commit IDs and the earlier failure statuses. Earlier attempts were not relabeled as rehearsals or successes.

Read-only review also caught two runner issues before qualification: cleanup errors could obscure a timeout, and inherited `PYTHONOPTIMIZE` could disable assertions in existing checks. Scoped best-effort cleanup now preserves the original outcome, and child environments clear assertion/runtime overrides. Unit tests cover these paths, fail-fast behavior, launch errors, cancellation, deadlines, skipped tests, and exclusion of generated files from source packaging. The runner does not disable Electron's sandbox or alter approval settings.

## Claims connected to evidence

- **Imported history and identity must be consistent:** the Python suite executes the existing replay-contract regressions, including valid controls and older formats.
- **Observed changes and missing information remain distinguishable:** demo, fixture and native desktop checks exercise the expected No finding, Review and Unknown outcomes.
- **Snapshots and saved evidence remain usable:** existing window/session tests and desktop export/case replay verify the implemented behavior.
- **Collection lifecycle is bounded and recoverable:** existing stream/session checks and desktop shutdown journeys verify their declared cases.

These links identify existing deterministic evidence. They do not imply that newly generated histories, arbitrary executable layouts or every possible resource boundary were explored.

## Work explicitly not completed

The blocked T1/T2/T3 fuzzing work was not resumed or repackaged into this runner. No sanitizer campaign, new input generator, independent generated oracle, campaign reachability measurement, new boundary pack or held-back fuzz variant ran. The original adversarial milestone still has gates 1 and 7 passed and gates 2–6 incomplete. A successful qualification does not close those five gates.

The wider full-CI UI/evaluation/accessibility suite, native build-configuration matrix, archived-evaluation reproduction and ten-minute performance campaign were not repeated by this qualification. The recorded 139 seconds is runner execution time, not an application performance benchmark. Previous measurements retain their original source provenance.

Unsigned local evidence remains forgeable by an equally privileged actor. Changes outside coverage or between samples can still be missed. No whole-process integrity, client attestation, real-cheat accuracy, memory-safety proof or long-duration reliability claim is added.

No application or detector behavior changed in this milestone. The changes are the qualification runner, its tests/reporting, setup quoting, generated-output exclusions and documentation. Existing performance work, replay fixes and archived evaluation evidence were preserved. No hosted CI run, source release or public push was made.

## Subsequent AddressSanitizer qualification

The optional ASan profile has now passed a separate clean-checkout run. See [ASan results and limits](qualification-asan-results.md) and [generated ASan evidence](../evidence/qualification-asan-validation.json). The original 12-step result above retains its original provenance; the fuzzing campaign remains incomplete.

## Subsequent Hypothesis qualification

The bounded synthetic property profile passed a combined 19-step clean-checkout run with ASan. See [results and limits](property-qualification-results.md) and [generated property evidence](../evidence/property-qualification-validation.json). The original fuzzing campaign remains incomplete.

## Subsequent bounded libFuzzer pilot

The integrated 20-step clean-checkout qualification passed, including the bounded non-loading parser pilot. See [pilot results, failed attempts and limits](libfuzzer-pilot-results.md) and [generated evidence](../evidence/libfuzzer-pilot-validation.json). The original campaign remains incomplete.

## Subsequent UI readiness verification

A narrow test-only keyboard-readiness fix and controlled regression passed all 20 checks from a fresh checkout. The original intermittent failure remains preserved and its exact cause unproven. See [UI investigation and final results](qualification-ui-results.md) and [evidence](../evidence/qualification-ui-validation.json).

## Subsequent bounded relocation and parser-boundary verification

The 65-case fixed pack passed twice with selected relocation guard coverage verified; the 18-check native/ASan profile passed from a clean checkout. The full 20-check profile failed an existing Hypothesis deadline; full-profile compatibility remains incomplete. Both this timing failure and the first fixture failure remain preserved, and the original campaign is incomplete. See [results and limitations](parser-boundary-results.md) and [evidence](../evidence/parser-boundary-validation.json).

## Subsequent replay timing fix and full qualification

A bounded per-call manifest-validation optimization passed all 20 checks from a fresh checkout with unchanged Hypothesis limits. The earlier full-profile timing failure remains preserved. See [results](replay-timing-results.md) and [evidence](../evidence/replay-timing-validation.json). The original fuzzing campaign remains incomplete.

## Subsequent export-count and manifest-cardinality verification

All 23 new cases passed twice within the 88-case pack, and all 20 checks passed from a clean checkout. See [verified results and limits](export-cardinality-results.md) and [evidence](../evidence/export-cardinality-validation.json). Historical failures remain preserved; the original broader campaign remains incomplete.

## Subsequent bounded retention verification

All 24 retention scenarios passed twice and all 21 checks passed from a fresh clean checkout. A failed fixture-repeatability attempt remains preserved; no production retention fix or limit change was needed. See [results and limitations](retention-results.md) and [evidence](../evidence/retention-validation.json). The original broader fuzz campaign remains incomplete.

# Permanent first-use release check — local validation

The permanent runner and CI integration are implemented. **All 16 local release-check steps passed. Unfamiliar-tester acceptance remains pending. Hosted CI has not been run.**

## Implementation

Run `python -B scripts/check_first_use.py` from the repository root. It freezes publishable source, runs the source packager, verifies the ZIP/manifest and extraction, verifies the pnpm store and Electron cache, and runs the bounded first-use workflow. Replay occurs before native compilation; unapproved capture precedes explicit approval of only the extracted v2 sample. Library, deletion and saved-case regressions are mandatory. Successful process exits with missing/short/failed UI evidence cannot pass.

The runner uses the existing command supervisor for per-command/overall deadlines, bounded logs and process-tree cleanup on timeout, cancellation or log-budget failure. Reports update incrementally; later steps remain `not_run` after failure. Every invocation has new evidence and a new short temporary workspace. The latter avoids native build-tool path limits and is retained for diagnosis. The source checkout and user baseline are not used as the capture environment.

The separate **First-use release check** Windows CI job executes runner unit checks and the same command on push, pull request and manual dispatch. An `always()` upload step retains curated reports, log files, screenshots, source ZIP and manifest for 30 days, using a commit-pinned official upload action. It does not upload dependency caches, environments or app profiles. Unit logs are included even if the runner cannot start. No step uses `continue-on-error`.

## Local results

- 32 runner/supervisor unit tests passed, including ten new tests for failure propagation, interruption, deadline behavior, cache mismatch, source drift, missing or invalid UI evidence and artifact filtering.
- All 16 end-to-end steps passed in 63.766 seconds, using a new archive/extraction and empty task-local dependency caches.
- The six UI journeys supplied 8 replay, 5 unapproved, 6 approved, 9 library, 3 deletion and 10 saved-flow assertion groups.
- Source manifest matched before packaging, after extraction and after execution. Git identity (including dirty status) is recorded; this is a local working-tree candidate, not a published commit.
- Archive SHA-256: `93a00ab8455e4415b1dd0cc3380572e34ffd3dedeab143b01b009e7aa9a7e1bf`.
- Workflow YAML parsed successfully. Action pin was checked against the official repository. Hosted workflow behavior, artifact upload and merge blocking were not exercised locally.

Final raw evidence: `verification/qualification/first-use-90e5ff9b14c5/artifacts/`. Published structured summary: `evidence/first-use-release-validation.json`.

## Preserved failed attempts

1. Unit attempt 1 had one error: the new UI-evidence reader indexed a set. Integration `first-use-19c4538f449c` reproduced it after successful setup/replay. The runner reported failure and left later steps unrun. The fix reads the single validated evidence item without assuming list indexing.
2. Integration `first-use-67060d11e0f3` failed native configuration with MSVC FileTracker FTK1011 errors in the deeply nested extraction. Moving the disposable extraction/cache workspace to a short system-temporary path resolved this; the failed logs and source package remain intact. No deadline or expected result was relaxed.
3. Integration `first-use-90e5ff9b14c5` passed all steps. The final 32-test unit run also passed. Earlier first-use and qualification evidence was not replaced.

Raw unit logs are retained under `verification/qualification/first-use-runner-unit-attempt-*.log`; each integration attempt retains its own artifacts. A YAML parser was not installed in the bootstrap Python, so the existing local Prettier YAML parser was used instead; that tooling probe was not an application test failure.

## Remaining limits

Unfamiliar-user tasks H1-H4 remain pending: prerequisite installation, normal launcher, real file dialogs, uncoached navigation and interpretation. The automated journeys use isolated Electron entry wrappers and known owned-fixture dialog selections. A successful same-host run does not establish independent-machine compatibility or comprehension.

CI is configured in the working tree but has not been pushed or executed on GitHub in this milestone. Repository branch protection was not changed; an administrator must separately require the new check if merge blocking is desired. Runner loss, cancellation or upload failure can prevent artifact transfer despite `always()`; local incremental reports reduce but cannot eliminate this risk.

Original T1/T2/T3 fuzzing remains unfinished. This milestone did not rerun the full 21-step qualification, ASan, Hypothesis/libFuzzer or endurance benchmarks. Those historical results retain their original scope. This result document and structured summary were added after the passing run and are outside its immutable source archive; no runner, workflow or application code changed after that run.

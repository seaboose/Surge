# Permanent first-use release check

Acceptance fixed before validation:

- One command, `python -B scripts/check_first_use.py`, creates a unique source archive, manifest, short temporary extraction and empty task-local caches, with reports under ignored qualification output. It records Git identity and exact source hashes, including uncommitted files.
- Package verification and cache-location checks must fail closed. Replay runs before native compilation; unapproved capture runs before explicit approval of only the extracted v2 fixture. Library, deletion and saved-case regressions are required.
- A failed command, missing test evidence, timeout, source drift or cache mismatch prevents success. Later steps remain `not_run`. Reports are written incrementally. Existing 10-minute setup, 5-minute build, 3-minute UI and 30-minute overall limits remain; commands use the existing qualification process/log limits and cleanup.
- Unit checks exercise failure propagation, missing evidence, cache mismatch, interrupted runs and source mismatch. Local validation must run the complete release check from its packaged source.
- A separate Windows CI job runs the same command. `always()` uploads only the curated reports, logs, screenshots, manifest and source package, including failed attempts; it excludes installed dependencies, caches and app profiles. Upload failure is visible. No `continue-on-error` or implicit pass on skipped work.
- Every report, including failures, states unfamiliar-tester acceptance is pending. This check does not run or complete original T1/T2/T3 fuzzing, sanitizer or endurance campaigns. Hosted CI execution and branch-protection configuration cannot be claimed from local checks.


## Running and retaining evidence

Run from the repository root in a Windows graphical session with the setup/native build prerequisites installed. The runner is standard-library Python and uses the existing bounded command supervisor from `qualify.py`. It creates `verification/qualification/first-use-<id>/artifacts/report.json` and `report.md`, plus a source ZIP/manifest, logs and UI evidence. Each run is new; failed artifacts are not overwritten.

The extraction and caches use a fresh short system-temporary path to avoid MSVC file-tracker path limits. Its location is recorded in the report and retained locally for diagnosis; it is not part of the source package or CI upload. Host-level caches, installed toolchains, native dialogs and the normal application launcher are not independently qualified by this runner.

CI runs a separate `First-use release check` job on push, pull request and manual dispatch. Artifact retention is 30 days; download evidence for longer retention. `always()` requests upload on failures, but cancellation, runner loss or upload-service failure can prevent upload. Branch protection must separately require this check if merge blocking is desired; editing the workflow does not change repository policy. A local pass is not evidence of a hosted CI pass.

[Local validation results](first-use-release-results.md) record completed checks, preserved failures and hosted/human acceptance still pending.

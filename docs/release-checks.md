# Release verification

## Versioned integrity and compatibility

The [compatibility report](../evidence/native-compatibility-validation.json) records Release and Debug development checks followed by a fresh MinSizeRel build with a third declared range. All three passed with the same frozen implementation. Across those controlled checks, 116 clean observations stayed clear, all 18 persistent changes observed inside checked ranges required review, and 20 unavailable observations stayed Unknown. Seven unapproved observations required review. All 161 records replayed through the workspace and saved cases. These are correctness checks, not real-cheat accuracy estimates.

Local validation passed all 270 Python tests, three native CTests, four desktop boundary checks, native evidence and continuous collection journeys, and all five published demo cases. The new native parser test rejects 21 malformed or unsupported images. The security review added regression coverage for stale approvals, metadata stripping, exact coverage accounting and larger native windows.

Testing exposed Debug incremental-link export stubs, which are avoided by explicitly disabling incremental linking for the owned fixture DLLs. It also exposed larger declared manifests exceeding the old field and retained-window limits. Native metadata now has narrow size bounds, and complete samples are retained within both 500 samples and an 8 MiB encoded budget. Eviction remains visible as Unknown health evidence. Existing imports retain their ordinary field limits.

The existing investigation workflow remains unchanged. Current captures require explicit approval of the complete versioned manifest; older cases still replay. The archived network evaluation and published demo cases remain unchanged. Earlier performance measurements below describe their recorded builds, not a fresh performance benchmark of this milestone.

## Continuous owned-app collection

Version 0.4 adds bounded C++ collection, stable investigation snapshots and independent scenario validation. The existing interface and file import workflow remain available. Local validation passed 249 Python tests, two native CTests, 20 existing desktop investigation/evaluation journeys, the native evidence journey, and the new continuous-capture journey. Scaling and keyboard checks cover 24 display/text combinations. Capture-specific checks cover restarts, retained-window omissions, failed processes, stale evidence, normal shutdown and forced worker shutdown.

The [native validation report](../evidence/native-stream-validation.json) records zero false positives across 38 clean covered-range checks, all four persistent covered changes detected, and six unavailable observations kept Unknown. Controlled changes outside coverage and wholly between samples demonstrate known misses. These are fixture checks, not real-cheat accuracy or a representative production holdout.

The 90-second native measurement collected 817 samples at a requested 100 ms interval, using approximately 0.577% of one CPU core and 6.2 MB peak working memory. Private bytes decreased from 1,040,384 to 995,328 between the first and last measurements. Per-range collection time was about 0.133 ms at the 95th percentile. These figures measure the native process on one Windows host, not the complete Electron application, and do not establish long-term leak freedom. Actual intervals can exceed the target; transport loss and delayed sampling are separate conditions.

The archived network evaluation remains byte-for-byte unchanged. The source package now includes that already-published archive, while excluding local baselines, captures, environments and test output. CI rebuilds the native app and repeats collection, replay, desktop and release-hygiene checks on a fresh Windows runner.

The milestone package was also extracted into a new local folder and installed independently. Fresh setup, the native build, 249 Python tests, both native CTests, four desktop boundary checks, the continuous desktop journey and archived evaluation reproduction passed. The first complete [hosted Windows run](https://github.com/seaboose/Surge/actions/runs/39730467188) passed every step. A direct native unit command exposed a test-directory assumption during the local check; that test now creates its own temporary directory.

## Earlier portable release

The portable source package was extracted into a separate Windows folder with spaces in its path. It contained no Python environment, installed Node packages, or renderer build. Setup created a new environment, installed from the lockfile, and built the interface. Package downloads reused the package manager's cache where available.

The extracted copy passed:

- 222 Python checks: 206 application tests and 16 evaluation-protocol tests.
- 19 Electron journeys: 15 investigation checks and four external-label evaluation checks.
- Three runtime and renderer-boundary checks.
- JavaScript formatting and source-hygiene checks.
- The dependency advisory audit, with no known vulnerabilities reported at the time of this pass.
- Both archived round-three cases and their complete evaluation reports reproduced with the portable engine: 193 to 167 false positives, with one missed target in each case.

The local fresh setup used the same Windows host. [GitHub Actions](https://github.com/seaboose/Surge/actions/workflows/ci.yml) repeats installation, Python tests, desktop checks, evaluation reproduction, formatting, and release hygiene on a clean Windows runner. Each run records its commit and individual check results.

The first hosted runs exposed two portability issues: HTML and JSON line endings varied on checkout, and a desktop test read Details before its asynchronous response arrived. Explicit line-ending rules and a content-based wait address these issues. The Details test now includes a deliberate response delay. No application behavior or detection logic changed.

All 13 production Python modules retain the original syntax tree after formatting. Runtime selection now uses the project environment or an explicit interpreter path. The renderer, engine decisions, saved-case formats, and security boundaries retain their behavior. The working source archive and evaluation records were not changed.

No new effectiveness improvement or long-duration memory result is claimed for this release. Existing benchmark limitations still apply.

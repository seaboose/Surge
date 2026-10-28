# Current release qualification — 23 October 2026

Status: **passed within the declared scope**. Acceptance criteria were recorded before testing in `current-release-acceptance.md`. The original broader fuzzing campaign remains unfinished.

## Change and regression

Deleting an opened library case now detaches its library identity while preserving the loaded snapshot and saved-case provenance. Deleting a recently saved copy clears its confirmation and stale reopen action. Canceled deletion and unrelated-case deletion retain the correct membership. Original evidence is unchanged.

The new desktop regression reproduced the old stale badge, then passed after the narrow state fix. Three regression groups also passed in the clean checkout. The existing library journey passed nine groups covering import/open/save/rename/export/delete/restart. The standard qualification's desktop boundary step now includes the existing case-library unit tests; its top-level count and time limits are unchanged.

README instructions now use Try Demo and Case library, describe the separate v2 sample and exact-build approval, and distinguish saved evidence from live collection. New opening and saved-results screenshots were captured from the updated app and visually inspected. All 19 README links/targets passed the local check before qualification.

## Clean-checkout evidence

- Snapshot commit: `d16eabad50b76cd6faeb08911e61b50c594318b5` (isolated local verification snapshot, not an upstream commit).
- Normalized source fingerprint: `c6d764c7cb711f045a27ca7edad1d919c122367f14648f3f6500831b757267af`.
- 238 publishable files; source contents matched the working tree after Git line-ending normalization. Original and checkout hashes are retained. The original repository was not staged, committed or reset.
- All **21 qualification steps passed** in **391.766 seconds**. Source hashes were unchanged and Git was clean before and after.
- `.venv`, desktop dependencies/build, native build/captures and baseline registry were absent before setup.
- **361 Python tests**, zero skips; native CTests; MSVC ASan safe and deliberate-fault controls plus instrumented tests; **768 Hypothesis evaluations**; **10,000 libFuzzer executions**; **88 fixed parser-boundary cases repeated twice**; **24 retention cases repeated twice (48 evaluations)**; demo/owned-fixture/stream checks; desktop boundary/native/stream checks; source hygiene all passed.
- Parser retained-corpus replay measured **227/267 lines (85.02%)** and **176/220 branch outcomes (80%)** in the targeted parser. This is not whole-application coverage or coverage of every discarded mutation. The fixed boundary pack is reported separately.

Raw report and logs remain under the isolated checkout's `verification/qualification/run-f27c6d10ed17/`. Published structured evidence: `evidence/current-release-validation.json`. The full generated report retains each command, deadline, exit code, log hash and profile evidence.

## Additional checks on the same checkout

Seven desktop journeys passed: deletion regression, case library, Results flow, saved flow, saved context, parity and accessibility. Formatting passed. Accessibility includes 24 display/text/zoom combinations and keyboard/focus checks, not screen-reader certification.

These ran after the 21-step qualification. An explicit approval was created only for the exact v2 build inside this isolated test checkout; no working-tree or user baseline was changed. The registry hash and individual logs are retained in the additional UI report. Git remained clean afterward. The qualification snapshot and all application/test files remained unchanged.

## Preserved failures and attempts

- The deletion regression failed before the fix: the badge remained present after confirmed deletion. Raw assertion and desktop artifact folder retained.
- Initial Python alias and sandboxed Electron launches did not execute application assertions; a later graphical-session run reproduced the real bug.
- Runner unit tests initially had five sandbox temporary-directory permission errors; the unchanged 22-test suite passed outside that sandbox.
- Initial sandboxed local clone failed; the retry succeeded. An attempted qualification launch before the checkout existed executed no checks.
- Initial raw-byte comparison rejected Git line-ending conversion; normalized comparison passed, with both hashes retained.
- A README write hit Windows text encoding and a test-edit script failed its text-match assertion; explicit UTF-8 and the corrected match resolved these before the snapshot.

The attempt ledger and all logs remain under the current-release work area and the original `work/` and `verification/electron/` folders. No previous milestone evidence was deleted or rewritten. The first actual full qualification run passed; no test bounds or acceptance thresholds were relaxed.

## Limitations and provenance

This was one Windows host using existing system toolchains and download caches, not a fresh OS or independent machine. No new ten-minute benchmark, multi-hour endurance run, full native build matrix or complete CI evaluation matrix was performed. The original T1/T2/T3 campaign and its unmet acceptance gates remain incomplete. Bounded generated tests do not establish arbitrary-history, race or whole-program correctness. Clang/MSVC STL container annotations remain disabled as documented; compiler ASan is verified, not universal memory safety.

Local unsigned evidence is not attestation. Outside-range and between-sample changes can be missed; reopening a case does not check current integrity.

This results document, the evidence JSON and the README result link are post-run documentation additions, outside the immutable qualified snapshot. No application or test code changed after qualification. Historical reports retain their original scope and identity.

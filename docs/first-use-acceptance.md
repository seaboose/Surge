# Independent first-use acceptance criteria

Defined before milestone execution, 23 October 2026. This milestone has separate machine checks and human acceptance. Automated success cannot mark unfamiliar-user acceptance complete.

## Scope and frozen limits

Only Surge, its included owned sample and sanitized fixtures. No third-party targets, external attestation, new adversarial campaign or global machine configuration changes. Every attempt gets its own log/results directory. No overwrite of failures, lowered timeouts or altered expected outcomes to obtain a pass. Fix an observed blocker narrowly, record it, and repeat the affected checks against a new package when source changes.

## Machine checks

M1. Freeze a source-package manifest and archive hash. Extract into a new directory containing spaces. Verify every file against the manifest; no virtual environment, desktop dependencies/build, native build/captures/approvals or user cases may exist initially. Record OS/tool versions and environment reuse explicitly.

M2. Run the documented setup with the documented explicit-Python option when needed. Use initially empty task-local pnpm/Electron download caches and a fresh temporary directory, with no inherited Surge/Python overrides. Setup must exit zero within 10 minutes and launch an isolated desktop profile. Download failure is retained as environmental failure, not a pass. Reuse of system Python, Node, pnpm, CMake, compiler, OS/user account remains a limitation.

M3. Before native compilation or approval, portable case replay works. Try Demo must not pretend a missing collector is ready: it presents actionable build guidance. Included approved, changed, unreadable and outside-coverage cases yield their declared visible outcomes; originals stay byte-identical. Native file dialogs may be substituted in automation, but manual navigation remains a human test.

M4. Build only the included native sample using documented commands (5 minutes per configure/build). Before approval, captured observations require Review, never an approved/no-finding summary. Explicitly approve only this extracted v2 build; approval must produce a nonempty registry and subsequent unchanged, complete live observations must have No finding. The normal capture must show observations, not an empty screen. Each desktop journey has a 3-minute outer limit, with bounded locator waits.

M5. Save/reopen/rename/export/import/delete/restart work through isolated UI journeys. Saved cases explicitly describe recorded evidence rather than live integrity. Deletion preserves original evidence and the loaded investigation; canceled and unrelated deletion preserve correct state. All required assertions pass; no unexpected renderer errors or orphaned test-owned capture process. Preserve source hashes and check code unchanged after testing.

M6. Record setup duration, individual outcomes and failures, source identity, test artifacts, baseline identity and limitations. Passing this milestone is only automated partial acceptance until H1-H4 are independently observed. No full qualification, sanitizer, fuzzing or performance rerun is implied.

## Unfamiliar tester acceptance (pending until a real participant completes it)

H1. Someone who has not developed or been coached on Surge uses only the packaged README and linked documentation on an independent Windows environment. Record prerequisite installation separately from application setup; record OS/hardware/tool versions and all deviations. They install and open Surge without undocumented help. Observe for up to 45 minutes, then mark unfinished tasks incomplete; this is a session cap, not a performance guarantee.

H2. They complete the normal demo and case lifecycle in M4-M5, using actual native file dialogs, and inspect the four included scenarios in M3. Record time, wrong turns, assistance and blockers. Required tasks must succeed without facilitator coaching; clarify only the task, never the controls or expected answers. Preserve the first attempt before any assisted retry.

H3. After using the tool, ask neutral questions. They independently explain what was measured, why no findings is limited to the measured ranges/approved build, what missing evidence means, why outside-coverage changes can be missed, whether reopened evidence is live, and what deleting a case removes. All six concepts must be substantively correct. Do not give the scoring key before these questions.

H4. Use their observed difficulties to prioritize narrow fixes, repeat affected tasks, and keep assisted/unassisted and initial/retest results separate. Automated agents, developers and simulated personas do not qualify as unfamiliar testers.

## Completion rule

Report M1-M6 individually as passed/failed/not run/partial and H1-H4 as pending unless actually observed. A new VM or account is not implied by a clean extraction. Original T1/T2/T3 fuzzing, multi-hour endurance and broader production anti-cheat claims remain outside this milestone.

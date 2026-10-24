# Saved demo flow — 23 October 2026

All six recommendations were implemented. A short isolated desktop check ran after each change, using the included approved v2 sample and a temporary case library. Original evidence and baseline approvals were not changed.

## Acceptance and staged results

1. **Visible observations on reopen — passed.** All-normal saved cases open with Findings only off. Show all observations recovers from an empty filtered view and clears search, priority, and findings filters. Stage evidence: `verification/electron/saved-flow-1-H46xdX/`.
2. **Saved and live contexts separated — passed.** Opening a case hides the demo controls and identifies the case by name. An existing capture remains separate and can be reached explicitly through View demo capture. Inspecting or stopping from that panel explains that it will replace the viewed workspace; the saved copy stays unchanged. Stage evidence: `saved-flow-2-pKSPi2/`.
3. **Historical summary from verified evidence — passed.** Saved observations is derived only after case verification and native evidence validation. It uses the recorded bytes, verdicts, coverage, and analysis; it never uses current collector counts or assumes the demo succeeded. Reopening does not restore runtime capture provenance. Unapproved, changed, unreadable, incomplete, or inconsistent native evidence cannot yield a success summary. Generic cases receive no native summary. Stage evidence: `saved-flow-3-p3QC3z/` and the focused Python tests.
4. **Clear next action after inspection — passed.** Stop collection becomes primary after the first inspection; Inspect newer snapshot becomes secondary. Stage evidence: `saved-flow-4-ttoPg1/`.
5. **Contextual status and terminology — passed.** The footer follows the current demo step. The native observation table has an Observations caption. Operation failures and cancellation messages remain available. Stage evidence: `saved-flow-5-hU3bFm/`.
6. **Direct return to the saved case — passed.** The save confirmation offers Open saved case for that exact library ID, plus Open library. Stage evidence: `saved-flow-6-nc8uqw/`.

All abbreviated stage paths above are under `verification/electron/`. The repeatable combined test is `desktop/saved-flow.test.cjs`. Its final run, `saved-flow-6-D609oA/`, passed ten checks, including restart/reopen, a separate active collector, minimum 720×540 layout, and rename without evidence changes. Screenshots were visually checked; the small window requires vertical scrolling but has no horizontal overflow.

## Additional verification and fixes

- Existing library UI journey: 9 checks passed (`case-library-B4b8xD/`).
- Library unit tests: 6 passed after updating the expected response to include the verified-open result and the case display identity. Renaming updates the identity without changing evidence bytes.
- Final focused Python run: 37 tests passed across saved-summary, demo-summary, capture-provenance, and desktop-worker checks. Five shipped native cases and the legacy generic case also reopened successfully. Export retained the same historical summary without creating a live association.
- Existing stream, seven-stage demo flow, desktop parity (16 checks), and reliability smoke journeys passed. The smoke included 20 restart cycles; it was not the full performance workload.
- Final review identified two state-label issues: an earlier snapshot could be called final after an automatic stop, and exporting an edited reopened case could restore an unmodified label. The final-snapshot claim now requires a stopped snapshot from the same session at the stopped collector's endpoint. The edited-case context now persists across export. Three focused desktop regressions passed in `saved-context-DOJlkk/`, including byte-for-byte preservation of the original library case.
- Renderer build and formatting checks passed. The final combined journey and edge-case tests ran after those fixes. The earlier broad regressions preceded those last narrow state-label fixes; they were not counted as a full final qualification.

## Preserved attempts

- Saved-summary test setup initially encountered sandbox temporary-directory access failures. The test then used the repository's existing temporary-test directory convention and passed. Formatting attempts recorded a missing Black installation in the bundled interpreter and an interrupted sandbox run; the repository interpreter formatted the files successfully.
- The first library unit attempt failed on sandbox temporary-directory renames. Its truncated tool output is preserved as a failure summary, explicitly not a full raw log. The next attempt ran outside the sandbox and exposed the outdated response assertion. The updated assertion checks the added identity fields; all six tests then passed. Evidence: `work/saved-flow-library-attempt-{1,2,3}` in the repository.
- Stream test attempts retained an incorrect test wait for recovery after a simulated failed capture, then an obsolete assumption that demo controls remain visible after reopening a case. The tests now preserve the failed-state behavior and explicitly return to the separate demo controls. Evidence: `verification/qualification/usability-7c952acbaa/` and `verification/qualification/usability-d15ea17ffc/`. Passing broad runs: `usability-930a6b40b7/` and `inspect-label-smoke-4a1d28c189/` in the same folder.
- Two new edge-case test attempts needed harness corrections: explicit bounded polling for a newer sample, and using the fixture's actual recorded state in assertions. Evidence remains in `verification/electron/saved-context-Hw915X/`, `saved-context-tvNih7/`, and the parent workspace's `work/saved-context-provenance.log`. The corrected desktop and provenance tests passed.

No failed attempt was counted as a completed check. Assertions about evidence integrity were retained.

## Limits

This is targeted working-tree verification on one Windows host, using existing dependencies, native binaries, and the exact local v2 approval. Case verification checks saved-content integrity and consistency; it is not remote attestation, proof of trustworthy capture, or a fresh check of the application's current state. Matching configured ranges does not establish whole-process safety or cover bytes outside those ranges.

The automatic-stop display path is tested through a controlled stop outside the renderer's normal action, not a ten-minute wall-clock run. This work is not a clean-checkout qualification, full performance run, or new ASan, Hypothesis, or libFuzzer campaign. The broader unfinished fuzzing campaign remains unfinished.

# Demo clarity refinements — 23 October 2026

All six recommendations implemented, with an isolated desktop check immediately after each implementation. Scope remained the included owned sample, local evidence, and isolated case libraries. No baseline approval or capture target changed.

## Acceptance and results

1. Navigation names its destination: Back to start before evidence is loaded, Hide demo controls afterward. Hiding retains the investigation; navigation remains disabled during collection. Passed: `demo-clarity-1-p7vgJO`.
2. Inspect snapshot is disabled when the exact final stopped snapshot is already open. A stopped collector with an older viewed snapshot still requires and permits inspection. Passed: `demo-clarity-2-2uT4Pb` and the final saved-context regression.
3. Reopened cases retain their name, evidence-derived result, and one scope statement. Running capture remains prominent and separate; previous stopped capture controls are collapsed. Passed: `demo-clarity-3-aeMEb7`.
4. Unchanged library cases show Saved in library and Save a copy. Edited reopened cases offer Save as new case, keeping the existing saved copy unchanged. Dialog titles follow the action. Passed: `demo-clarity-4-8GM0q7` and the edited-case regression.
5. Count explanations use the viewed stream rows, grouping samples by session and sequence. They count actual observations and collection notices separately. Uneven samples receive explicit variable-count wording; non-stream evidence receives no invented sample count. Counts remain the same after reopening. Passed: `demo-clarity-5-PdpcGz` and three focused count tests.
6. Selected native records begin with a plain-language explanation of their recorded approval, code comparison, protection comparison, and read completeness. Unapproved, changed, unreadable, missing-verdict, and health-notice states cannot claim a match. Rule-based Review/Unknown results remain explicit even when the range itself matches. Hashes and supporting details remain immediately below. Passed: `demo-clarity-6-B1bxVx` and three focused explanation tests.

Stage folders are under `verification/electron/`. The repeatable staged test is `node desktop/demo-clarity.test.cjs [1–6]` (normally run from the desktop directory as `node demo-clarity.test.cjs`).

## Final verification

- All six staged checks passed; final combined clarity check passed in `demo-clarity-6-uYtV97`. The reopened screenshot was visually checked.
- 43 focused Python tests passed: clarity, saved summaries, demo summaries, capture provenance, and desktop worker (`work/demo-clarity-python.log`).
- Saved-flow journey passed ten checks, including separate running capture, app restart, minimum window size, and rename (`saved-flow-6-S9MAvd`).
- Three saved-context checks passed, including an out-of-band stop and edited-case export with byte-for-byte preservation of the original case (`saved-context-cDrgHx`).
- Existing library UI journey passed nine checks (`case-library-1AngeE`).
- Existing seven-stage demo journey passed, including the unapproved internal v1 fixture (`demo-flow-7-S2ADz2`).
- Existing continuous stream journey passed start, inspection, stop, export, replay, restart, keyboard/text scaling, and shutdown (`work/clarity-stream-final.log`).
- Renderer build and formatting completed. Existing tests were updated to use the new exact labels and explicitly expand the stopped-capture disclosure.

## Preserved failed attempt

The first existing demo-flow regression timed out trying to click the correctly disabled final-snapshot inspection button. That test had started v1 directly through the internal API without updating React's stopped state. The test now reloads the initial state after this out-of-band fixture start. The unchanged production disabled-state behavior and the unapproved-evidence assertion both passed on rerun. Original log: `work/clarity-final-demo-flow.test.cjs.log`; rerun: `work/clarity-demo-flow-attempt-2.log`. The initial sequential batch stopped at that failure; the stream journey ran separately afterward and passed.

## Limits

This is targeted working-tree verification on one Windows host. Explanations describe recorded evidence and configured ranges, not whole-process safety, remote attestation, or the current state of a reopened application's process. Read completeness refers to the selected range; collection notices and sampling limits remain distinct.

The automatic-stop display path uses a controlled out-of-band stop, not a ten-minute timer run. No clean-checkout/full qualification, benchmark, ASan, Hypothesis, or libFuzzer campaign was rerun. The broader unfinished fuzzing campaign remains unfinished.

# Try Demo flow refinement — 23 October 2026

Implemented all seven recommendations. Short isolated desktop checks ran after each stage, followed by a combined walkthrough and targeted regressions. No baseline approvals or capture targets were changed.

## Staged acceptance checks

1. Dedicated demo view replaces the welcome cards; Back returns to the prior screen. Passed (`demo-step-1-WPVPWw`). Back is disabled during collection so leaving cannot silently strand a running capture.
2. One next-step instruction is visible; explanations and collection details are expandable. The separate-process design is explained once. Passed (`demo-step-2-wW5PhK`).
3. Expected-result summary comes from the inspected evidence, not live counters or a hard-coded assumption. Passed (`demo-step-3-vq5uNw`) plus 12 summary/provenance tests.
4. Stop collection explicitly opens the final snapshot; no second inspect action is required. Passed (`demo-step-4-HOmv3k`).
5. Export choices are grouped with descriptions; portable case export still works. Passed (`demo-step-5-OREiYK`).
6. Save case becomes primary after stopping; Start another capture stays secondary. Passed (`demo-step-6-XkTsYN`).
7. Demo names are suggested and editable; save confirms the name and offers Open library. Saving while collecting explicitly describes the fixed snapshot. Passed (`demo-step-7-vc1lz4`).

Staged artifacts remain under the workspace's `work/` directory. The repeatable combined test is `desktop/demo-flow.test.cjs`; final artifacts are `verification/electron/demo-flow-7-Eeu2JS/`. This particular approved-demo test requires the installed v2 baseline approved and v1 unapproved, as verified in this working checkout; it does not grant approvals itself.

## Evidence safeguards

The successful-match message requires nonempty observations, readable ranges, approved baselines, matching code bytes and page protections, and all-normal analysis with no gaps or stream-health records. The summary is attached only to an inspected capture with current analysis. It is recomputed from those records; an earlier session is labeled as such. Imported evidence does not receive a demo success banner.

Synthetic checks cover missing, unapproved, changed, unreadable, incomplete, empty, and inconsistent inputs. The real desktop walkthrough also collects from the unapproved owned v1 fixture and verifies that it cannot display the expected-match success message. The wording describes configured ranges in the inspected snapshot, not whole-application safety.

## Completed verification

- All seven staged short desktop checks passed.
- Final combined demo journey passed, including saving, library navigation, live-save explanation, real unapproved v1 evidence, all export choices at 720×540, and menu dismissal on selection/Escape.
- 27 Python summary, capture-provenance, and desktop-worker tests passed.
- Existing continuous desktop capture journey passed collection, inspection, stop, export/replay, restart, keyboard/text scaling, and shutdown.
- Existing library desktop journey: 9 checks passed.
- Existing usability journey, stage 7: passed.
- Existing published demo replay: 5 fixtures passed.
- Existing accessibility journey: 24 display/text/zoom combinations and navigation checks passed.
- Existing desktop parity: 16 checks passed after the fixes below.
- Renderer build passed. Changed Python and frontend files were formatted.

## Failed attempts and fixes

1. The first parity run timed out finding the new collapsed export menu's button. The test helper now locates hidden menu items and opens their disclosure before interacting.
2. The first stream regression run similarly looked for Export captured records before opening its new menu. The test now opens the menu and checks the relocated control.
3. A later parity attempt timed out inspecting reduced-motion styling of a collapsed export control. That check now opens the menu first; the styling assertion remains.
4. A further parity run exposed a product issue: the export overlay stayed open after an action and intercepted a click on Clear. Export menus now close after selection, on Escape, and on outside pointer interaction. The final parity run and minimum-size export checks passed.

Earlier attempts and isolated test profiles were retained. No assertions about evidence correctness were relaxed to accommodate these changes.

## Limits

This is targeted working-tree verification on one Windows host, using existing dependencies, native binaries, and the exact local v2 approval. It is not a fresh-checkout qualification, a new baseline audit, or a full Python-suite/benchmark/ASan/Hypothesis/libFuzzer run. The broader unfinished fuzzing campaign remains unfinished.

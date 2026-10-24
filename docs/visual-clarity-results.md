# Focused visual clarity results

The final local check passed **24 checks** in approximately four seconds against
the source/build hashes recorded in [the evidence record](../evidence/visual-clarity-validation.json).
The [acceptance criteria](visual-clarity-acceptance.md) were written before edits.
This is a focused UI check, not unfamiliar-tester acceptance or a full audit.

## What changed and what passed

- Results keep actual sample/observation counts visible. Supporting explanation
  moved into **About sample counts**. The owned approved case still showed two
  retained samples, four range observations, four No finding results and zero
  Review/Unknown results; reopening remained recorded evidence, not live capture.
- Case library keeps a short import/open distinction visible, with fuller
  portable-file guidance in **About case files**. Existing actions remain.
- Evaluate presents three setup steps and optional **Labeling guidance**. The
  independent-label requirement and separate-file warning remain visible.
- Case details keeps fingerprints, readable count labels and trust guidance
  visible. **Analysis settings** and **Numeric reference profiles** begin closed
  and reveal strings exactly equal to the reader's original fields.
- All three help panels passed click, Enter, Space, Escape, outside-click,
  keyboard-focus and keyboard-scroll checks. Their bounds and wrapping passed
  at 100%, 125% and 150% zoom in a 900×700 window. Changing window size or zoom
  while help is open now dismisses it, preventing a stale offscreen position.
- The short unsupported-export regression passed seven library checks. The
  message preserves the diagnostic code, existing destination and library
  evidence while directing the user to another local folder.

Final artifacts are in
`verification/qualification/visual-clarity-Xb96Cs/`. The evidence record hashes
127 retained files, including 90 screenshots across nine attempts; earlier
cropped/superseded screenshots remain clearly associated with their attempts.
App profiles are excluded from that public manifest. Original fixture hashes
and renderer-error checks passed. Source/build stability is checked per attempt.

## Preserved attempts and review findings

Short sample, library and evaluation checks passed after their respective edits.
The earlier combined 21-check pass remains recorded separately from the expanded
24-check pass and the repeat that verified the new CI artifact directory.

- Initial Playwright screenshots cropped the physical viewport after zoom.
  The harness now uses Electron's full-surface capture; originals are retained.
- One repeat correctly failed its source-stability check because `main.jsx`
  changed concurrently. Its passing interaction checks were not promoted to an
  overall pass.
- The first expanded Details check omitted the required workspace revision in
  its read-only request. Surge refused it. The harness supplied that revision;
  the next run passed without weakening the application boundary.
- Visual review found that long help needed keyboard focus. Focusable panels
  and Tab/PageDown/Escape checks addressed that issue. Focused code review then
  found that open help retained stale coordinates during resize/zoom. Dismissal
  on resize was verified after the fix; no failing pre-fix execution is claimed.
- A formatter warning and an initial report-generation UTF-8 decoding error
  were preserved and corrected. Neither changed application outcomes.
- The root reviewer reported an initially minimized computer-use window and a
  helper launch that closed with cache access errors against an earlier profile.
  These are explicitly text-only incident records, not invented raw artifacts.
  A fresh owned profile succeeded. Separate retained setup logs show failure
  with the default interpreter selection and success with an explicit interpreter.

The root's manual walkthrough covered opening, demo collection/stop, saving,
reopening, Data, Compare, Evaluate and Case details. Its observed 16-sample,
32-record capture is a walkthrough observation, not the fixed saved fixture used
by the 24-check automated run. Native file dialogs in the automated check select
only the published owned fixture; native shell-dialog interaction is not tested.

## Affected-journey follow-up

After the short visual checks, the retained local batch
`verification/qualification/release-affected-0243383cf1/` passed desktop,
library, saved-flow, saved-context, parity, accessibility and formatting checks.
Its evaluation journey failed after 16.719 seconds: an existing assertion still
expected “Current data is the test source.” to be immediately visible at its
former location. That supporting explanation had intentionally moved into the
Labeling guidance bubble. This was an outdated test expectation, not an observed
application defect or missing explanation.

The narrow test update clicks **Labeling guidance**, checks the visible note
for the current-source explanation and the assurance that labels never enter
detection, then presses Escape before continuing. It does not remove that check
or extend the timeout. The subsequent evaluation run passed all four existing
journeys, including label import, evidence drill-through, invalid-label handling
and recomputation. The original batch result and failed log remain unchanged;
`verification/qualification/visual-release/evaluation-after-help-fix.log`
records the successful rerun. These follow-up logs and the original batch logs
are included in the evidence manifest.

## Remaining limits and milestone review

No further material issue was found in this focused review of the small UI diff.
That does not establish absence of other defects. The local affected-journey
follow-up supplements the short checks; hosted verification of the final
committed candidate remains a separate gate.
The earlier hosted recovery candidate `937a19b` predates these UI changes and
cannot qualify them. OS display/account matrices, screen-reader certification,
long sessions and independent user comprehension remain outside this check.

Ratings remain **8/10 as a scoped defensive engineering tool** and **8.5/10 as an
internship portfolio project**. The changes improve explanation and keyboard
access without expanding detection claims. The highest-value next gate is
qualification of the exact packaged/committed candidate, followed by the
unfamiliar participant's complete first-use session. Unfamiliar-tester acceptance
is **pending**; the broader T1/T2/T3 fuzzing campaign is **unfinished**.

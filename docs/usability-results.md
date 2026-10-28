# Usability implementation and verification

All seven recommendations were implemented. A short real-desktop check followed each implementation; all seven were also repeated together on the integrated build. This was verification of the current working tree, not a new clean-checkout qualification.

## Changes and short checks

1. **Accurate retention guidance.** The interface now says “Retains up to 500 samples, subject to the evidence size limit.” The desktop check verified that wording. No retention limit changed.
2. **Clear opening actions.** The introduction explains Surge's purpose and the three entry points: Import evidence, Open saved case, and Collect from demo app. The check verified these actions and that canceling import preserves the workspace.
3. **Live collection versus viewed evidence.** A separate snapshot panel identifies the inspected sequence, observation timestamp and retained counts. It signals newer observations and earlier collection sessions without comparing unrelated session sequences. Snapshot metadata comes from the exact analyzed rows; import/open clears the live association. Eight new backend regressions plus the real desktop check verify stable evidence, stopping and restart behavior. The 22-test focused backend group passed.
4. **Explicit collection and output actions.** Start collection, Inspect snapshot, Stop collection and Export captured records describe their effects. Build help distinguishes the original and updated demo. Export help distinguishes live JSONL records from the saved investigation. The desktop check verified the labels and disabled export before evidence exists.
5. **Less competing emphasis.** Removed button glow, replaced the decorative opening graphic with useful guidance, and made the opening/collection primary action depend on the current state. The check verified one primary action in the opening collection state and no button glow.
6. **Readable typography.** Increased base text from 13 px to 14 px, used interface typography for controls and retained monospace for structured evidence. Widened the navigation for Case details. Short checks passed at 100%,150%,200% zoom; the existing accessibility journey passed all 24 display/text/zoom combinations, keyboard navigation, copying, modal focus, row keys and resizing.
7. **Navigation and result guidance.** Details became Case details; Compare and Evaluate explain their purpose and prerequisites. A collapsible explanation distinguishes No finding, Review and Unknown. Keyboard shortcuts remain intact. The short test imported valid synthetic evidence and a rule policy, analyzed, traversed the specialist views and used Alt+5.

Implementation order was 1,2,4,5,6,7,3 so collection labels were established before snapshot interaction tests. No permissions, collection targets, approval requirements, detection rules or production limits were broadened.

## Integrated verification

- Complete Python suite: 337 tests passed, zero skips (51.365 seconds reported by unittest).
- All seven final short desktop checks passed.
- Owned-app continuous collection journey passed, including stable inspection, stop/export, saved-case replay, restart and shutdown.
- Native evidence journey passed, including approved/unapproved updates and unavailable evidence.
- Accessibility: 24 display/text/zoom combinations passed.
- Investigation parity journey passed, including chart mouse selection, evidence inspection, navigation, saved cases and comparison.
- Detection evaluation journey passed.
- Four desktop security/runtime boundary tests passed.
- JavaScript formatting, whitespace and publishable-source hygiene passed.

Logs and screenshots remain in ignored verification folders. Generated evidence links their hashes. The final small health-only guidance refinement was followed by another passing snapshot/restart check. No source commit or public push was made.

## Failures preserved and fixes

An initial opening check ran against the old interface after an edit used the wrong working-directory path; its missing-heading failure was retained. The navigation fixture initially omitted a detection policy, so Analyze correctly remained disabled. The fixture was corrected to import an explicit synthetic rule policy; application safeguards were not relaxed.

The first existing stream journey expected the old phrase “records”; the selector now checks “retained records.” Its failed log remains under usability-011a4cadef.

The parity journey revealed a real chart interaction defect. Neighboring SVG points had overlapping invisible click targets: clicking record 2 could select record 4. The diagnostic screenshot and exact diagnostic test source remain under usability-142b7563af, with the original failure under usability-ac8240308a. Selection now resolves the closest displayed stem/point in SVG coordinates, rather than using whichever overlapping element is painted on top. The original mouse-click regression passes; it was not replaced with keyboard selection or forced clicking. Keyboard chart navigation remains available.

Development also encountered a stalled multiworker formatter and a Windows text-encoding error; the formatter was stopped and rerun with one worker, and file reads use UTF-8. Formatting validation subsequently passed. These were tooling issues, not application test failures. A diagnostic log-printing encoding error did not erase the already-written failure log/report.

## Limits

No new clean-checkout, full sanitizer/property/parser qualification, long-duration performance run or fuzz campaign was conducted in this UI milestone. Earlier qualification reports retain their original source identity. The broader T1/T2/T3 campaign remains incomplete.

Health-only metadata is covered by synthetic backend tests. The extra prompt that observations are available after a health-only snapshot was reviewed and followed by the ordinary snapshot/restart check; actual collector failure/recovery was not newly induced in the GUI. Screen-reader speech, touch input and independent-user usability studies were not tested. Dense chart points that occupy exactly the same geometry remain inherently ambiguous; arrow navigation and record inspection are available. These results demonstrate the tested workflows, not universal usability or accessibility certification.

See [machine-readable evidence](../evidence/usability-validation.json).

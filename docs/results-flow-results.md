# Results navigation and table refinement — 23 October 2026

All three approved changes were implemented and checked individually, followed by targeted regression journeys. Tests use the owned sample app and isolated profiles; baseline approvals, capture targets, detection rules, and saved-case evidence formats were unchanged.

## Acceptance and staged results

1. **Readable table:** result labels stay on one line at 1120×740 and 720×540 without page-level horizontal overflow. The normal native reason is now “Matched approved reference”; the complete code, protection, and read-completeness explanation remains in the evidence pane. The success conditions, custom-rule precedence, and missing-evidence behavior did not change. Passed: `verification/electron/results-flow-1-4j9Joc/`.
2. **Consistent Results navigation:** navigation, accessible table name, view routing, status/help text, and descriptions of saved analysis use Results/results. Findings only remains the filter for actual findings; exporting findings still excludes normal observations. Alt+2 reaches Results. Internal worker method names and the persisted split-position key remain compatible. Existing test selectors were updated to the actual UI labels; historical reports remain unchanged. Passed: `results-flow-2-c19o3U/`.
3. **One readiness instruction:** the demo panel retains evidence-derived readiness and next-step instructions. The footer reports brief operational status: Demo ready, Collecting, or Collection stopped. Errors, cancellation, collection failure, and attention messages retain precedence. Saved-case context and its separate-capture indication remain intact. Passed: `results-flow-3-Kp2tFT/`.

Abbreviated folders above are under `verification/electron/`. Run `node results-flow.test.cjs` from `desktop/` for the combined test; optional stages 1–3 support individual checks.

## Final completed verification

- Combined Results journey passed (`results-flow-3-7tzp6c`), including one-line rendering, accessible navigation, optional findings filter, and verified saved-case reopen. Screenshot visually checked.
- Saved-flow journey passed ten checks, including separate active capture, restart/reopen, minimum size, and rename (`saved-flow-6-mity6F`).
- Saved-context journey passed three checks, including an older snapshot after an out-of-band stop and original-case byte preservation after edited export (`saved-context-kK1uRB`).
- Earlier demo-polish journey passed (`demo-polish-6-5rl9iP`).
- Continuous stream journey passed capture, inspect, stop, export/replay, restart, keyboard/text scaling, and shutdown.
- Desktop parity passed sixteen checks, including filters, case identity, reasons, and navigation.
- Accessibility passed 24 display/text/zoom combinations plus keyboard navigation, copying, modal focus, row keys, and resizing.
- 46 focused Python tests passed. The compact-reason negative assertions were additionally rerun after making their case comparison explicit; all three reason tests passed.
- Build, frontend formatting, and whitespace checks passed.

All staged and final test attempts passed. Logs are retained in `work/results-final-*.log` and `work/results-python.log`. Earlier milestone evidence and failures were preserved.

## Limits

This is targeted working-tree verification on one Windows host with existing dependencies and binaries. Recorded range matches do not establish whole-process safety, remote attestation, or current live integrity after reopening a case. The automatic-stop display path uses a controlled out-of-band stop rather than a ten-minute timer wait.

No clean-checkout/full qualification, long-duration benchmark, ASan, Hypothesis, or libFuzzer campaign was rerun. The broader unfinished fuzzing campaign remains unfinished.

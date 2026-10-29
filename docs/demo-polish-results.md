# Try Demo final refinements — 23 October 2026

Implemented the six approved recommendations with a short desktop test after each implementation. Checks use the owned included v2 sample, its existing exact-build approval, and isolated local case libraries. No approval, capture target, evidence format, or detection rule was changed.

## Acceptance and staged results

1. Readiness is conditional on actual retained sample and record counts, not elapsed time. Collection errors take precedence; zero-sample capture displays a waiting message. The positive readiness message only offers inspection, without making a safety claim. Passed: `demo-polish-1-KS95ez`.
2. The running demo explicitly says inspection is optional: inspect while collecting or stop to review the final snapshot. The test stops without an intermediate inspection and successfully opens final evidence. Passed: `demo-polish-2-bEY8Fu`.
3. Native table rows explain normal matches using their validated recorded approval, complete read, code comparison, and page-protection comparison. Custom-rule matches and evidence gaps retain precedence. Unapproved, changed, incomplete, or absent comparison evidence cannot produce the normal-match reason. Generic telemetry keeps its generic reason. Passed: `demo-polish-3-VoA2Rn` and three focused reason tests.
4. Neutral filter/export guidance moved into What the results mean. Active filter descriptions and warnings about evidence hidden by search remain visible. Summary counts and observation counts remain visible. Passed: `demo-polish-4-sHJqQg`; the existing desktop parity filter checks also passed.
5. Save completion is announced in the named confirmation, which explicitly says reopening is optional. The demo instruction now offers continued review or another capture; the footer becomes Ready. Passed: `demo-polish-5-H7PALy`.
6. Saving a copy suggests the existing name with an editable “— copy” suffix. The suggestion fits the 100-character name limit without splitting Unicode code points. The desktop test edits the suggestion, saves an independent case, and reopens it with the same analysis and historical context. Passed: `demo-polish-6-6VwEBt`.

All stage folders are under `verification/electron/`. Run `node demo-polish.test.cjs` from `desktop/` for the combined check; an optional number 1–6 selects a cumulative stage.

## Completed final checks

- Combined six-refinement journey: passed (`demo-polish-6-F4Agdg`); reopened screenshot visually reviewed.
- Previous clarity journey: passed (`demo-clarity-6-oPJgMD`).
- Saved-case journey: ten checks passed, including app restart, separate active capture, minimum window size, and rename (`saved-flow-6-r7V1bF`).
- Saved-context journey: three checks passed, including out-of-band stop and byte-for-byte preservation of original library evidence after edited-case export (`saved-context-KFsmcq`).
- Earlier demo journey: passed, including the unapproved internal v1 fixture (`demo-flow-7-u9IoK3`).
- Library UI journey: nine checks passed (`case-library-roN2zp`).
- Desktop parity journey: sixteen checks passed, including active filters, hidden-evidence behavior, mapping, reasons, and case identity.
- Focused Python checks: 46 tests passed across native reasons, clarity/counts, saved summaries, demo summaries, capture provenance, and desktop worker.
- Renderer build, formatting, and whitespace checks passed.

Final logs are preserved in `work/polish-final-*.log` and `work/demo-polish-python.log`. All staged and final test runs passed. One malformed intermediate patch request was rejected before making any change; the corrected patch applied afterward. Earlier milestone failures and reports remain untouched.

## Limits

This is targeted working-tree verification on one Windows host, with existing binaries and dependencies. Readiness means retained observations exist; it does not establish sufficient statistical coverage or whole-application safety. Native match wording describes a recorded range comparison, not remote attestation or the process's current state after reopening.

No clean-checkout/full qualification, long-duration performance, ASan, Hypothesis, or libFuzzer campaign was rerun. The automatic-stop display check uses a controlled out-of-band stop rather than waiting ten minutes. The broader unfinished fuzzing campaign remains unfinished.

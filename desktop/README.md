# Desktop development

Run `Setup-Surge.ps1` from the repository root before opening the app. It prepares a local Python environment and the locked Node dependencies.

From this directory:

```powershell
pnpm run build
pnpm start
pnpm test
pnpm run test:ui
```

Rebuild after changing `src/`. Generated `dist/` files and installed dependencies stay out of Git. Playwright is a declared development dependency; these tests use the installed Electron executable and do not need browser downloads.

Run `pnpm run format` before submitting JavaScript or interface changes. `pnpm run format:check` checks formatting without edits. Python formatting uses Black 26.10.1 with the settings in `../pyproject.toml`; the optional formatter is listed in `../requirements-dev.txt` and is not a runtime dependency.

`parity.cjs` covers importing, field mapping, full-value inspection, search, copying, charts, cases, comparison, navigation, and bounded rendering. `evaluation.test.cjs` checks label import, counts, evidence links, and invalidation. Each run uses a separate profile. Test output goes to `verification/electron/` and can contain local paths; it is not published.

`memory.cjs` retains the Windows process-memory workload. It is a separate diagnostic, not part of the fast CI suite. Run `node memory.cjs measurement` after setup. Forced-collection diagnostics are separate from ordinary memory measurements.

The full-stack capture workload is `../scripts/measure_reliability.py --phase desktop`, run with the project Python interpreter from the repository root. It launches `reliability.cjs`, measures all Electron processes plus the worker and owned native child, and takes about eleven minutes. Run `--phase faults` separately for controlled change latency, backpressure, a suspended producer and abrupt exit. See the [fixed acceptance criteria](../docs/performance-reliability.md) and [results](../docs/performance-reliability-results.md). These host-specific performance budgets are an explicit diagnostic, not an added timing gate in shared CI.

The benchmark and refinement journeys require their matching archived datasets. Do not substitute unrelated data or open a reserved holdout to make a test pass.

Use clear action labels and one prominent next action per state. The opening screen explains the three entry points: **Import evidence**, **Case library**, and **Try Demo**. Keep investigation views compact; evidence should stay stationary and readable, with live collection clearly distinguished from the inspected snapshot. Use interface typography for controls and monospace for structured evidence. Blur is limited to dialogs; reduced-motion preferences remain supported. Update the learning document for keystone changes rather than routine tuning.

Local cases are managed under the Electron user-data directory. Save case creates a new named snapshot; the library supports open, rename, confirmed deletion, and portable import/export. Deletion preserves external evidence and the active investigation. Open case file and Export case file retain the direct portable-file workflow. Run `pnpm run test:library` for the isolated desktop journey. See [acceptance criteria](../docs/case-library-acceptance.md) and [results and limitations](../docs/case-library-results.md).

Reopening a case leaves the demo controls and labels the evidence as historical. Verified native cases receive a saved-observations summary limited to the recorded build and configured ranges; this does not reattach the case to a collector. All-normal saved cases show observations by default. Run `pnpm run test:saved-flow` for the focused save/reopen journey and snapshot-state regressions. It uses isolated profiles and requires the included v2 sample and its existing exact-build approval. See [saved-demo flow results](../docs/saved-demo-flow-results.md).

Run `node demo-clarity.test.cjs` for the six follow-up clarity refinements: explicit navigation, redundant inspection prevention, compact saved context, copy/save wording, evidence-derived counts, and plain-language record explanations. See [results and limitations](../docs/demo-clarity-results.md).

Run `node demo-polish.test.cjs` for readiness, optional intermediate inspection, native table reasons, compact filter guidance, save confirmation, and editable copy-name suggestions. See [results and limitations](../docs/demo-polish-results.md).

The investigation view is named Results; Findings only filters its records. Run `node results-flow.test.cjs` for the compact table, Results navigation/accessibility labels, single readiness instruction, and saved/live separation. See [results and limitations](../docs/results-flow-results.md).

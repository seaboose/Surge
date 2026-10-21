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

The benchmark and refinement journeys require their matching archived datasets. Do not substitute unrelated data or open a reserved holdout to make a test pass.

Keep labels short and keep the interface free of title banners and section headers. Evidence should stay stationary and readable. Blur is limited to dialogs; reduced-motion preferences remain supported. Update the learning document for keystone changes rather than routine tuning.

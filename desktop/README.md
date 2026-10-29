# Desktop development

Run `Setup-Surge.ps1` from the repository root to prepare Python and the locked
Node dependencies. From `desktop`:

```powershell
pnpm run build
pnpm start
pnpm test
```

Rebuild after changing `src/`. Generated output and dependencies stay outside Git.
For source maps and the docked interface inspector, use `pnpm dev`; F12 or
right-click **Inspect element** opens it. Temporary CSS edits reset on reload.
See [developer inspection](../docs/developer-inspection.md).

## Focused checks

| Command | Coverage |
| --- | --- |
| `pnpm test` | Boundaries, startup, recovery, report export and shared UI logic |
| `pnpm run test:ui` | Imports, mapping, results, cases and evaluation |
| `pnpm run test:survive` | Recording and saved-session review |
| `pnpm run test:investigations` | Drafts, revisions, citations and export |
| `pnpm run test:timeline` | Replay and timeline layout |
| `pnpm run test:accessibility` | Keyboard, scale and accessibility checks |
| `pnpm run format:check` | JavaScript/interface formatting |

GUI checks require a graphical Windows session. They use isolated test profiles
and the installed Electron executable; Playwright needs no browser download.
Some native or historical journeys require their documented fixture builds and
datasets. Never substitute unrelated data or expose a reserved holdout to make
a check pass. Output under `verification/` may contain local paths or records and
is excluded from publication.

`scripts/check_survive_package.py` separately tests an extracted combined release
through real game recording, report export, relocation and saved-data reopening.
See [runtime release scope](../docs/runtime-release-scope.md) and
[validation limits](../docs/validation.md). Automated checks do not establish
unfamiliar-user acceptance.

## Source boundaries

`src/main.jsx` starts React. `case-workspace/App.jsx`, `SurviveWorkspace.jsx` and
`SurviveInvestigations.jsx` own their coordinated workflow state; focused views
live beside them. The main process validates requests and owns dialogs and the
Python worker. The sandboxed renderer cannot choose arbitrary paths or commands.
Follow the [source guide](../docs/code-map.md) for the complete evidence path.

The packaged application excludes DevTools, source maps and test helpers. The
older Tk Workbench is retained only for development compatibility tests. Saved
cases and Survive recordings live outside application files, under the local
user-data directory; package replacement must preserve that data.

Longer performance workloads remain separate diagnostics:
`scripts/measure_reliability.py --phase desktop` and `--phase faults`.
Their [recorded results](../docs/performance-reliability-results.md) apply only
to the identified source and host.

# Learn the product without reading the entire workspace

Keep **one source tree** and produce two different deliverables from it:

- **Release application:** the executable, required runtime libraries, bundled
  interface, backend modules, game assets, profiles, licences and a short user guide.
- **Development workspace:** that same source plus tests, build tools, evaluation
  fixtures, design notes and reproducible validation instructions.

These are different packages of one product, not separate implementations to keep
in sync. Tests belong in the development workspace; users do not need them installed.
The release should identify the source revision and checks used to build it.

## How much code is actually relevant?

**Version 0.4.3:** the module audit counts 23,149 physical runtime-source lines
across 101 files and 70,331 code lines across 338 files in the developer source
package. The runtime figure includes Survive. Version 0.4.2 had 22,589 runtime
lines and 69,500 developer-package lines. The added lines are explicit module
boundaries, imports, display placement and its regression coverage; no second
product implementation was introduced. The inventory receipt is
`verification/modularity-20261028/inventory-release.json`.

Physical lines include comments and blanks and measure neither complexity nor
compiled application size. The case controller is now 496 lines, the Python
dispatcher 483, the recording/replay controller 1,031 and the investigation
controller 920. Their coordinated state remains together; focused views and
handlers live in named modules. The five-line `main.jsx` only starts React.

Generated builds, dependencies, Unreal caches, private recordings, recovery material
and historical verification output were deliberately not traversed or counted.
Consequently this is a count of the maintained first-party source selected by the
audit, not every file on disk. A large `node_modules`, engine build or backup folder
does not mean you need to understand millions of lines of project code.

Regenerate the count from the project root, choosing a **new** output filename:

```text
python scripts/code_inventory.py --output verification/code-inventory-YYYYMMDD.json
```

The script reads the package's literal module declarations without executing the
builder, applies documented path categories, bounds its reads and skips private or
generated trees. It does not delete, rearrange or modify the inputs. It is a learning
aid; it is not a complete dependency-closure or release-qualification test.

For visual learning, run `pnpm --dir desktop dev` and use **F12** or right-click
**Inspect element**. The docked tools connect rendered elements to CSS rules and
readable source maps. Live style edits reset on reload; save lasting changes in
the source files and rebuild. See [developer inspection](developer-inspection.md)
for the source-tracing workflow and the boundary that excludes these tools from
the packaged application.

## A practical reading path

Follow a single session through these areas. Read the named entry points first, then
follow a dependency only when it answers a question about that session.

Start with the small bootstrap, then the controller for the workflow you want to
understand. Shared state has one owner; presentation modules receive that state and
callbacks instead of maintaining another copy:

- `case-workspace/App.jsx` owns shared case state, requests and collection polling.
  `context.jsx` supplies one shared context and read hooks; `controls.jsx` contains
  reusable controls. Data, results, comparison and evaluation panels keep their own
  local view state.
- `SurviveWorkspace.jsx` owns recording, replay and selection state. The `survive/`
  panels render those values; trial setup and study-label forms own only their local
  inputs and remain mounted when a stage is hidden.
- `SurviveInvestigations.jsx` owns the report draft, saved revision, pending work and
  leave guards. Its extracted editor, evidence and readiness views receive current
  values and callbacks; changing views does not reset the draft.

Imports flow from controllers to domain views and shared helpers. Shared helpers
do not import their controllers, avoiding circular imports.

| Order | Start here | Be able to explain |
| --- | --- | --- |
| 1 | `desktop/src/main.jsx` → `case-workspace/App.jsx` | How the interface starts, requests are serialized, views are selected and shared case state reaches panels through context. |
| 2 | `case-workspace/DataView.jsx`, `Results.jsx`, `Compare.jsx`, `Evaluate.jsx`, `Details.jsx` | Follow the panel for the current task; use `controls.jsx` and `context.jsx` only when a shared control or request needs explaining. |
| 3 | `desktop/src/SurviveWorkspace.jsx` → `survive/` | Follow trial setup, recording, arena replay, constraint chart and selected evidence into their named modules; `replay-model.mjs` holds shared projections. |
| 4 | `desktop/src/SurviveFlow.jsx`, `survive-flow.mjs` | How observations become summaries and timelines, and why filtering never changes retained evidence. |
| 5 | `desktop/preload.cjs`, `boundary.cjs`, `main.cjs` | What the renderer may request, where arguments are rejected, and how native dialogs supply paths before Python receives them. |
| 6 | `desktop_worker.py` → `desktop_*.py` modules below | How central admission checks precede explicit domain handlers while one Workspace retains all backend state. |
| 7 | `survive_workspace.py`, `survive_runtime.py`, `survive_capture.py` | How launch and recording share a data root; how exact bytes are finalized and incomplete data remains Unknown. |
| 8 | `unreal/SurgeMovementLab/telemetry/prepare_v3.py` → `engine.py` | How measurements become constraints and Review/Unknown/No finding outcomes. Learn one movement rule before general analysis features. |
| 9 | `desktop/src/SurviveInvestigations.jsx` → `survive/ReportEditor.jsx`, `InvestigationEvidence.jsx`, `InvestigationReadiness.jsx`, `investigation-model.mjs` | How the controller preserves drafts while views render narrative, pinned evidence and export readiness. |
| 10 | `survive_investigations.py`, `survive_study.py`, `survive_recorder_bridge.py` | How revisions and citations remain verifiable, study labels remain independent, and stale stop requests cannot affect a newer recording. |
| 11 | `unreal/SurgeMovementLab/Source/SurgeMovementLab/LabPlayerController.cpp`, `LabCharacter.cpp`, `SurviveSim.h` | How right-click/S/Q/E become movement; which clock and rules govern movement, dash and blink. |
| 12 | The same directory's `SurviveAttackDirector.cpp`, `SurviveThreat.cpp`, `SurviveHUD.cpp` | How attacks are scheduled, hit/expiry events are recorded, and the HUD distinguishes gameplay from recorder health. |

Paths under `case-workspace/` and `survive/` above are relative to `desktop/src/`.
For Python, `desktop_worker.py` retains protocol framing, lifecycle, import and
configuration handling, and revision/source admission checks. Its explicit routes
call four handlers; the fifth extracted module contains shared value helpers:

| Module | Responsibility |
| --- | --- |
| `desktop_records.py` | Raw previews, bounded search highlights, navigation and exact copying. |
| `desktop_findings.py` | Findings, evidence explanations and charts. |
| `desktop_cases.py` | Case saving, alert export, comparisons and provenance details. |
| `desktop_evaluation.py` | Independent labels and evaluation views. |
| `desktop_values.py` | Exact display values, bounds, search spans and row stepping. |

Handlers receive the existing Workspace rather than owning duplicate state. They
never import `desktop_worker.py`; shared helpers do not import handlers. The engine
still owns analysis and case verification. Read `native_stream.py` and `native/`
when tracing the native demo. `app.py` and `comparison_view.py` are alternate
interfaces, not prerequisites for explaining the current Electron workflow.

The Tk Workbench is frozen as a developer-only compatibility interface. It is
excluded from the product. Retiring it currently saves no shipped code and would
require migrating 82 UI regression cases; shared backend tests and modules must
remain. Keep it until that migration has a concrete maintenance benefit.

## How to use the tests while learning

For each area, read **one successful case and one failure case**, then run the
focused tests. Explain the invariant they protect and demonstrate a small change
without breaking it. Useful pairs include:

- `test_survive_capture.py`: complete capture versus truncated or reordered input.
- `desktop/survive.test.cjs`: paused view versus independently advancing recording.
- `desktop/survive-flow.test.cjs`: exact marker selection and replay timing boundaries.
- `test_survive_investigations.py`: immutable revisions versus stale saves or changed sources.
- `test_survive_recorder_bridge.py`: recorder-only stop versus an invalid/stale request.
- `test_desktop_dispatch.py`: stale requests rejected before handler work, while raw
  evidence stays inspectable without analysis.

You do not need to memorize every assertion or understand every qualification tool
before an interview. You should understand the data contracts, a representative
failure path, the limits of the evidence and why the tests give useful confidence.
Be candid about AI assistance and able to trace a real example independently.

## What can stay out of a final application?

Tests and test fixtures, build scripts, compilers, development dependencies, source
maps, old verification runs, screenshots, source-recovery ZIPs and private data all
stay outside the shipped application. Keep them in the repository or appropriate
development/evidence storage so the release remains reproducible.

Do **not** delete a file merely because it has `v1`, `v2`, `legacy` or `test` in its
name. The current v3 adapter still imports helpers from `prepare.py` and
`prepare_v2.py`; these are live dependencies. Native v1 fixtures also preserve
compatibility and corruption tests. Retire code only after checking its callers,
supported data formats and regression coverage.

The simplification audit removed unused styling and repeated implementations; the
later module split made responsibilities easier to follow without changing those
features. Future cleanup should use small dependency-checked moves with the same
test suite, not a second hand-maintained "clean" product folder. See [release scope](runtime-release-scope.md)
for the runtime/development boundary and the checks that qualify a portable release.

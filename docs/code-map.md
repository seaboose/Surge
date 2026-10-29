# Source guide

The repository contains one maintained implementation plus its tests and build
tools. The Windows package contains the required runtimes, game and application
assets; development tools and private recordings stay outside that package.

## Follow one investigation

| Stage | Source | Responsibility |
| --- | --- | --- |
| Start the interface | `desktop/src/main.jsx`, `case-workspace/App.jsx` | Start React and own shared case state. |
| Cross the desktop boundary | `desktop/preload.cjs`, `boundary.cjs`, `main.cjs` | Validate allowed operations; supply paths through native dialogs. |
| Dispatch a request | `desktop_worker.py`, `desktop_*.py` | Check source/revision identity before calling domain handlers. |
| Analyze evidence | `engine.py`, `native_integrity.py` | Parse bounded inputs, apply rules and distinguish missing evidence. |
| Record an owned game | `survive_workspace.py`, `survive_runtime.py`, `survive_capture.py` | Coordinate launch, data locations and exact recording bytes. |
| Derive movement constraints | `unreal/SurgeMovementLab/telemetry/prepare_v3.py` | Turn game observations into rule inputs using reviewed profiles. |
| Review a moment | `desktop/src/SurviveWorkspace.jsx`, `survive/` | Keep replay, timeline and exact source selection aligned. |
| Explain and export | `desktop/src/SurviveInvestigations.jsx`, `survive_investigations.py` | Preserve report revisions and verify evidence citations. |
| Compare trials | `survive_study.py`, `evaluation.py` | Keep independent labels outside detection and expose coverage limits. |

`case-workspace/` and `survive/` in the table are beneath `desktop/src/`.
Controllers own coordinated state; focused views receive that state and callbacks.
Backend handlers share one Workspace and do not import their dispatcher.

The game source is under `unreal/SurgeMovementLab/Source/SurgeMovementLab`.
Start with `LabPlayerController.cpp` for commands, `LabCharacter.cpp` for movement
and capture, `SurviveSim.h` for shared rules, and `SurviveAttackDirector.cpp` for
threat scheduling. The separate native demo starts at `native/owned_app.cpp` and
`native/code_range_collector.cpp`; `native_stream.py` validates its bounded stream.

## Focused checks

- `test_survive_capture.py`: complete versus truncated or reordered recordings.
- `test_survive_investigations.py`: revisions, stale saves and changed sources.
- `test_desktop_dispatch.py`: admission checks before handler work.
- `desktop/survive-flow.test.cjs`: timeline selection and replay boundaries.
- `test_native_manifest_security.py`: coverage declarations and approval identity.

See [desktop development](../desktop/README.md) for commands and
[validation scope](validation.md) for the distinction between recorded results
and a fresh qualification run. `pnpm --dir desktop dev` provides source maps and
the interface inspector; these are excluded from the product.

## Compatibility and packaging

The v3 movement adapter imports helpers from `prepare.py` and `prepare_v2.py`.
Those files are active dependencies, not duplicate obsolete implementations.
Native v1 fixtures preserve supported-format and corruption tests. The Tk
Workbench is a development-only compatibility interface with existing regression
coverage; the packaged product uses Electron.

`scripts/build_windows_package.py` declares runtime modules;
`scripts/release_files.py` selects publishable source. Read
[runtime release scope](runtime-release-scope.md) before changing either list.
To regenerate a bounded source inventory without opening private/generated trees:

```powershell
python scripts/code_inventory.py --output verification/code-inventory.json
```

Choose a new output filename for each saved inventory. Counts are a navigation
aid, not proof of dependency completeness or working release behavior.

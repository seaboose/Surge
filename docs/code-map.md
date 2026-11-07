# Source guide

The repository contains the software implementation and its build support.
Tests and historical validation material are distributed separately. The Windows package contains the required runtimes, game and application
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

## Compatibility and packaging

The v3 movement adapter imports helpers from `prepare.py` and `prepare_v2.py`.
Those files are active dependencies, not duplicate obsolete implementations.
Both native DLL versions support owned demonstrations and baseline approval.
The product interface uses Electron; development-only compatibility interfaces
are retained in the separate validation kit.

`scripts/build_windows_package.py` declares runtime modules;
`scripts/release_files.py` selects publishable source. Read
[runtime release scope](runtime-release-scope.md) before changing either list.
The separate validation kit records the matching product fingerprint.

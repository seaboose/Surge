# Surge

Surge is a Windows application for investigating local telemetry. It combines a
C++ collector, Python analysis, and an Electron/React interface with **Survive**,
an owned Unreal Engine game for controlled movement experiments.

Record a session, replay a moment, inspect its original measurements, and export
an investigation with source-bound evidence. Findings distinguish **Review**,
**Unknown**, and **No finding**; missing data never becomes a clean result.

## Try it

[Open the guided demo](https://seaboose.github.io/Surge/) in your browser, or
download the [Windows app ZIP](https://github.com/seaboose/Surge/releases/download/surge-resume-v0.4.3/Surge-Survive-0.4.3-Windows-x64.zip),
extract it completely, and open **Surge.exe**. The package includes its runtimes
and game; no development tools are needed.

Choose **Survive sessions** for a recorded game experiment, **Try Demo** for native
code-integrity observations, or **Import evidence** for CSV/JSON/JSONL files.
Follow the [five-minute demonstration](docs/standalone-demo.md).

The release is unsigned. Clean-machine and unfamiliar-user acceptance remain
pending. Local hashes establish consistency, not client authenticity. Native
coverage is two ranges totaling 15 bytes; neither demonstration establishes
real-cheat detection accuracy. See [security](SECURITY.md) and
[validation scope](docs/validation.md).

## Build from source

On Windows, install Python 3.11+ with Tcl/Tk, Node.js 22.12+, and pnpm 11.25.0:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Surge.ps1
.\Start-Surge.cmd
```

Native collection additionally needs [CMake and Microsoft C++ tools](native/README.md).
Rebuilding Survive needs [Unreal Engine 5.8.4](unreal/SurgeMovementLab/README.md).

## Code map

| Area | Entry point |
| --- | --- |
| Desktop and investigation views | `desktop/src/main.jsx` |
| Analysis and saved cases | `engine.py`, `desktop_worker.py` |
| Recording and evidence reports | `survive_capture.py`, `survive_investigations.py` |
| Native integrity | `native/`, `native_integrity.py` |
| Owned game and movement analysis | `unreal/SurgeMovementLab/` |

Read the [architecture](docs/architecture.md), [source guide](docs/code-map.md),
and [development commands](desktop/README.md). Application code is MIT licensed;
dependency and reference-data terms are in [NOTICE](NOTICE.md).

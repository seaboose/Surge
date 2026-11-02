# Development

The repository contains the app, game source, tests, and build tools. The Windows
release contains the runnable app and game. Keep private recordings, installed
dependencies, and generated output outside published source.

## Set up on Windows

Install Python 3.11+ with Tcl/Tk, Node.js 22.12+, and pnpm 11.25.0. Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Surge.ps1
.\Start-Surge.cmd
```

Native checks need [CMake and Microsoft C++ tools](../native/README.md).
Rebuilding Survive needs [Unreal Engine 5.8.4](../unreal/SurgeMovementLab/README.md).
The packaged application needs neither toolchain.

## Run checks

```powershell
.\.venv\Scripts\python.exe -B scripts/test.py
.\.venv\Scripts\python.exe -B scripts/verify_native_demo.py
pnpm --dir desktop test
.\.venv\Scripts\python.exe -B scripts/check_release.py
```

Windows CI runs the wider native, desktop, model, and package checks. See
[qualification](qualification.md) and [package checks](windows-package-check.md)
for local prerequisites. Use `pnpm --dir desktop dev` for the UI inspector and
source maps; the product does not include those development controls.

## Make a change

Create a focused branch such as `feature/report-layout` or `fix/replay-selection`.
Keep changes small, run the relevant checks, and explain the result in the commit.
Use the [code guide](code-map.md) to locate each responsibility.

Only reviewed paths in `scripts/source-files.txt` enter source packages. Update
that sorted list when adding or removing source. Packaging rejects missing files,
duplicates, links, and paths outside the project. An exported source package works
without Git. Follow the [release checklist](release-checklist.md) before publishing.

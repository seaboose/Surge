# Standalone runtime package versus developer workspace

The repository already separates the **source package** from the **Windows runtime
candidate**. Keep that design. A source archive is for rebuilding and auditing;
it is not the file bundle an end user should have to navigate or learn.

## Runtime contents

`scripts/build_windows_package.py` declares 25 Python backend modules and eight
Electron main/preload/support modules. It builds the React renderer into minified
assets, bundles Electron and Python, includes the owned native demonstration
executable and approved v2 module, and adds licences and user instructions.

With `--survive-build <standalone-attempt>`, the builder also includes the cooked
Survive game, required Unreal/runtime libraries and licence notices, four analysis
adapters, the movement policy and both reviewed profiles. The game is built
separately and its bounded file manifest is verified before copying. The combined
package is named `Surge-Survive-...-windows-x64.zip`.

Test runners and build tools are used during construction and validation but are
kept outside the payload. The developer's full `node_modules`, `.venv`, source
tests and intermediate build files are not needed in the installed application.
Upstream runtimes still contain many necessary support files; file count alone is
not a useful reason to strip those libraries.

## Application files and saved data

The packaged launcher resolves the owned game from `survive-runtime.json` and its
pinned manifest. It launches the game executable directly, without an editor or
project file. A missing or inconsistent package must fail visibly rather than
falling back to the developer's engine installation.

Electron supplies the trusted user-data location to the backend. Survive stores
telemetry, captures, trials, report revisions and game state outside the installed
files, under `%APPDATA%\surge-desktop\Survive` for ordinary launches. The game
receives the same local data location through bounded launcher arguments. Paths
and executable choices are not renderer inputs.

Developer launches retain the existing lab `Saved` location. No automatic migration
or deletion of developer recordings occurs. Keep those original captures intact;
moving data into a different study context is a separate reviewed operation.

The included cooked **Shipping** configuration retains the explicitly supported
study drivers and runtime visual feedback. This is a standalone game, not an Unreal editor
distribution. Runtime Python modules remain necessary application code; C++ sources,
tests, debug symbols, build tools and private captures stay outside the payload.

## Recommended deliverables

| Deliverable | Intended contents |
| --- | --- |
| End-user release | Surge executable/runtimes, built UI, required backend/adapters/profiles, cooked Survive game/assets, licences, short user guide and release identity. |
| Developer source | The same implementation plus tests, fixtures, build/qualification tools, architecture notes and a locked dependency setup. |
| Validation record | Versioned results and checksums for the exact release; selected shareable examples. Keep private recordings and historical local artifacts separate. |

The combined ZIP contains both application components. A future companion download
can use the same reviewed identity contract. Keep one source tree, not two divergent
implementations.

## Build and acceptance

Build the standalone game with
`python unreal/SurgeMovementLab/scripts/package-standalone.py`. This development
step requires the installed Unreal toolchain; running the resulting game does not.
Pass its reported attempt directory to `scripts/build_windows_package.py` using
`--survive-build`. Optional `--cmake` selects an already installed CMake executable.
Use `--allow-dirty` only for an explicitly labelled development candidate.

Run `scripts/check_survive_package.py --archive <ZIP> --manifest <manifest>
--node <absolute-node.exe>` for the extracted gameplay-to-report journey. It uses
fresh data, restricted application PATH/invalid developer overrides, actual game
rounds, exact evidence, report export, application relocation and preserved-data
reopening. Test tooling stays outside the package. Its report qualifies only its
recorded ZIP/hash; older validation does not qualify a new build.

This host has developer tools installed. Process/module-path and restricted-environment
checks establish which runtimes were used, but do not replace testing on a pristine
Windows machine. Unsigned-candidate status, clean-machine acceptance and later
unfamiliar-user acceptance must remain explicit. User testing is deferred.

The developer archive excludes `_Recovery`, root recovery notes, all local
`verification` output and machine-specific calibration inspection helpers, as
well as generated builds, installed dependencies and personal recordings.
Reproducible tests, build scripts, calibration reports and source remain included.
`scripts/check_release.py` checks the selected files for local user paths and
credential patterns; this is a bounded safeguard, not a guarantee that arbitrary
future files are safe to publish. The archive has a per-file checksum manifest.
Historical material remains in the local workspace.

Create the developer kit with `python scripts/package_source.py --output-root
<new-directory>`. Existing archives are never overwritten. Extract it, follow
`Setup-Surge.ps1` and `desktop/README.md`, and use `Start-Surge.cmd` to run the
development application. Rebuilding Survive additionally requires Unreal and its
documented C++ toolchain. See `docs/code-map.md` for the focused learning path.
Extract the developer kit to a short local path (for example `C:\Dev\Surge`).
Deeply nested test fixtures and Windows toolchains can exceed path-length limits
when the kit is unpacked several directories inside an existing workspace.

The reviewed Shipping game is 375,917,366 bytes (358.5 MiB), 35.6% smaller than the
earlier Development stage. Browser/game runtimes and cooked assets dominate the
application size; tests do not. Keep required DLLs, localisation/accessibility
resources and licence notices. Further reduction should follow a measured build-time
dependency review and another complete acceptance run, not arbitrary file deletion.

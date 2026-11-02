# Packaging

The Windows ZIP contains Surge, Survive, their required runtimes, game assets,
and third-party notices. Tests, build tools, source maps, installed development
dependencies, and personal recordings are excluded.

The source repository contains one maintained implementation plus the tests and
fixtures needed to check it. Compatibility adapters remain where current code
imports them; they are not disposable duplicates.

## Build

Build the game with `python unreal/SurgeMovementLab/scripts/package-standalone.py`.
Pass its attempt directory to `scripts/build_windows_package.py --survive-build`.
These commands require the documented Unreal and Windows toolchains.

Create a source kit with `python scripts/package_source.py --output-root <new-folder>`.
The file list is explicit in `scripts/source-files.txt`. Use a short extraction
path such as `C:\Dev\Surge` to avoid Windows toolchain path limits.

## Check

Run `scripts/check_survive_package.py --archive <ZIP> --manifest <manifest>
--node <node.exe>` for gameplay, recording, analysis, report export, relocation,
and reopening. Test tooling stays outside the product. The result applies only
to its recorded package hash; a host run is not a clean-machine qualification.

The package records a publication version separately from its runtime identity.
Version 0.4.4 republishes the verified 0.4.3 executable and game assets with cleaned
packaging and documentation. It does not claim that current source rebuilt those
binaries. Release manifests identify the exact shipped bytes.

User data stays outside the application under `%APPDATA%\surge-desktop`.
Close the game and Surge before replacing the extracted folder. Keep the saved
data and reports; never copy private recordings into a release ZIP.

Required dependency notices remain included. Notice exclusions are tied to exact
reviewed runtime and notice fingerprints. A changed payload keeps all engine
notices until a fresh dependency review.

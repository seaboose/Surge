# Build and run

This source distribution contains the software and its build dependencies.
It does not contain the validation suite. Installing build dependencies does not
install them into the packaged application.

## Desktop

Use Windows, Python 3.11+, Node.js 22.12+, and pnpm 11.25.0:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Surge.ps1
.\Start-Surge.cmd
```

After changing the interface, run `pnpm --dir desktop build`.
`pnpm --dir desktop dev` enables source maps and the development inspector.
Generated dependencies and build output stay outside Git.

## Capture and game

Build and approve the owned native sample using [native/README.md](../native/README.md).
Build Survive with the documented Unreal toolchain in
[its source guide](../unreal/SurgeMovementLab/README.md).
Existing capture, import, replay, report, and comparison functionality remains
part of this distribution. Compatibility adapters are required dependencies.

## Windows distribution

Build from a clean committed checkout. The package command needs the Microsoft
C++ tools, Windows SDK, CMake, and the installed desktop build dependencies:

```powershell
python scripts/build_windows_package.py --without-backend-tests
```

To include Survive, first build its standalone game and pass that build's attempt
directory with `--survive-build <attempt-directory>`. See
[runtime packaging](runtime-release-scope.md).

`--without-backend-tests` explicitly records that the separate backend validation
suite was not run. Package construction is not release qualification. The builder
still verifies runtime hashes, builds the renderer/native inputs, and checks an
ordinary capture. Use the matching validation kit before publishing a release.

The kit restores tests, their development dependencies, and the complete source
manifest. Use its recorded product fingerprint; do not mix different versions.

# Packaging

The Windows ZIP contains Surge, the chosen Survive game build, required runtimes,
assets, and dependency notices. Tests, source maps, build tools, personal
recordings, and development dependencies stay outside the application.

Build the game with `python unreal/SurgeMovementLab/scripts/package-standalone.py`.
Pass its attempt directory to `scripts/build_windows_package.py --survive-build`.
The software-only source uses the explicit `--without-backend-tests` switch;
the report records the omitted suite. The separate validation kit restores it.
The Unreal and Windows toolchains must already be installed.

Source exports use the reviewed `scripts/source-files.txt` allowlist. Runtime
modules are declared separately in `scripts/build_windows_package.py`.
Use short local build paths to avoid Windows toolchain path limits.

Build success does not establish gameplay acceptance, detection accuracy, or
clean-machine qualification. Validate the exact package before a release and
record its source and file hashes. Reusing a binary is not a rebuild.

User data stays outside the application folder. Close Surge and the game before
replacing a package. Preserve saved cases and reports; never bundle personal
recordings. Keep all required dependency notices with distributed binaries.

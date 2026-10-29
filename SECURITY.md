# Security

Surge processes local evidence. Treat imported files, field names, values, cases, and labels as untrusted input.

- The Electron renderer is sandboxed, context-isolated, and has no Node access.
- Navigation, new windows, network requests, and browser permissions are blocked.
- Native dialogs supply file paths. Renderer requests cannot provide arbitrary paths or shell commands.
- Requests are bounded. Investigation requests are tied to a workspace revision; independent capture commands have a separate fixed allowlist. The worker starts without a shell and runs Python in isolated mode.
- Parsing has byte, row, field, nesting, and rule limits. Failed imports preserve the existing workspace.
- Case and evaluation fingerprints detect changes; they do not authenticate the author.
- The Python worker runs as the current user. Surge is not a hardened file-analysis sandbox.
- Owned-app collection launches only `native/build/surge_owned_app.exe` with a fixed build choice. It accepts no target PID, executable path, DLL path, or test-control flag from the renderer. Its normal control pipe accepts only Stop. Evaluation-only mutation commands require a separate command-line flag and operate solely on our own never-executed probe bytes.
- The native writer queue holds at most 32 frames, frames are limited to 32 KiB, and the worker retains at most 500 full samples within an 8 MiB encoded budget including metadata reserves. Sequence gaps and retention omissions remain visible. Collection stops after ten minutes; worker shutdown closes the child's control pipe. A stalled reader cannot create an unbounded backlog.
- Baselines are loaded once per session and are never approved by collection. Local approval files and observations are unsigned. Neither a hash nor a local pipe authenticates a client that an equally privileged attacker controls.

Do not publish private evidence or raw test profiles. Saved cases include the original records. The repository excludes local datasets, environments, test profiles, and generated outputs by default.

CI has read-only repository permissions, uses pinned action commits, and needs no user-provided secrets. The toolchain bootstrap confines the built-in job token to the fixed official GitHub release-metadata request; it refuses redirects and removes the token before downloads or tool execution. Dependency changes require a lockfile update, a fresh install, and the test suites. Do not disable Electron isolation to work around a failing test.

If you find a vulnerability, contact the maintainer through the repository's private reporting option when available. Otherwise, open an issue describing the affected component without credentials, private records, or exploit details. This is a development project with no guaranteed response time.

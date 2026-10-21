# Security

Surge processes local evidence. Treat imported files, field names, values, cases, and labels as untrusted input.

- The Electron renderer is sandboxed, context-isolated, and has no Node access.
- Navigation, new windows, network requests, and browser permissions are blocked.
- Native dialogs supply file paths. Renderer requests cannot provide arbitrary paths or shell commands.
- Requests are bounded and tied to a workspace revision. The worker starts without a shell and runs Python in isolated mode.
- Parsing has byte, row, field, nesting, and rule limits. Failed imports preserve the existing workspace.
- Case and evaluation fingerprints detect changes; they do not authenticate the author.
- The Python worker runs as the current user. Surge is not a hardened file-analysis sandbox.

Do not publish private evidence or raw test profiles. Saved cases include the original records. The repository excludes local datasets, environments, test profiles, and generated outputs by default.

CI has read-only repository permissions, uses pinned action commits, and does not need secrets. Dependency changes require a lockfile update, a fresh install, and the test suites. Do not disable Electron isolation to work around a failing test.

If you find a vulnerability, contact the maintainer through the repository's private reporting option when available. Otherwise, open an issue describing the affected component without credentials, private records, or exploit details. This is a development project with no guaranteed response time.

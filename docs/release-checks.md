# Release verification

The portable source package was extracted into a separate Windows folder with spaces in its path. It contained no Python environment, installed Node packages, or renderer build. Setup created a new environment, installed from the lockfile, and built the interface. Package downloads reused the package manager's cache where available.

The extracted copy passed:

- 222 Python checks: 206 application tests and 16 evaluation-protocol tests.
- 19 Electron journeys: 15 investigation checks and four external-label evaluation checks.
- Three runtime and renderer-boundary checks.
- JavaScript formatting and source-hygiene checks.
- The dependency advisory audit, with no known vulnerabilities reported at the time of this pass.
- Both archived round-three cases and their complete evaluation reports reproduced with the portable engine: 193 to 167 false positives, with one missed target in each case.

This was a fresh setup on the same Windows host, not an independent test on a second computer. GitHub Actions is configured to repeat the checks on Windows, but no hosted workflow run is claimed until the repository is published and the workflow runs.

All 13 production Python modules retain the original syntax tree after formatting. Runtime selection now uses the project environment or an explicit interpreter path. The renderer, engine decisions, saved-case formats, and security boundaries retain their behavior. The working source archive and evaluation records were not changed.

No new effectiveness improvement or long-duration memory result is claimed for this release. Existing benchmark limitations still apply.

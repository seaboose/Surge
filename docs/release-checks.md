# Release verification

The portable source package was extracted into a separate Windows folder with spaces in its path. It contained no Python environment, installed Node packages, or renderer build. Setup created a new environment, installed from the lockfile, and built the interface. Package downloads reused the package manager's cache where available.

The extracted copy passed:

- 222 Python checks: 206 application tests and 16 evaluation-protocol tests.
- 19 Electron journeys: 15 investigation checks and four external-label evaluation checks.
- Three runtime and renderer-boundary checks.
- JavaScript formatting and source-hygiene checks.
- The dependency advisory audit, with no known vulnerabilities reported at the time of this pass.
- Both archived round-three cases and their complete evaluation reports reproduced with the portable engine: 193 to 167 false positives, with one missed target in each case.

The local fresh setup used the same Windows host. [GitHub Actions](https://github.com/seaboose/Surge/actions/workflows/ci.yml) repeats installation, Python tests, desktop checks, evaluation reproduction, formatting, and release hygiene on a clean Windows runner. Each run records its commit and individual check results.

The first hosted runs exposed two portability issues: HTML and JSON line endings varied on checkout, and a desktop test read Details before its asynchronous response arrived. Explicit line-ending rules and a content-based wait address these issues. The Details test now includes a deliberate response delay. No application behavior or detection logic changed.

All 13 production Python modules retain the original syntax tree after formatting. Runtime selection now uses the project environment or an explicit interpreter path. The renderer, engine decisions, saved-case formats, and security boundaries retain their behavior. The working source archive and evaluation records were not changed.

No new effectiveness improvement or long-duration memory result is claimed for this release. Existing benchmark limitations still apply.

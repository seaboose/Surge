# Hosted Windows candidate acceptance

Scope: an isolated candidate branch, owned fixtures, bounded existing checks.
Do not merge, change branch protection, or claim independent human acceptance.

Acceptance criteria, defined before hosted execution:

1. Record candidate commit, actual tested commit, run IDs, attempt numbers and Windows runner identity. Both Windows jobs must pass for the same candidate.
2. Retrieve the first-use artifact ZIP; inspect the report, logs and UI evidence. Require all 16 release steps to pass, source unchanged, expected UI check counts, and human acceptance pending.
3. Verify the retrieved source ZIP against its manifest and against the tested Git tree. A PR merge commit must be identified separately from its candidate head.
4. On a separate disposable failure-probe branch, introduce one explicit unit-test failure. Require a failed first-use job, skipped release execution, and successful upload/retrieval of the failure log containing the probe marker. Never merge the probe.
5. Retain failed runs and local attempts; document narrow fixes and rerun the committed candidate. Missing artifacts or unexecuted checks are not passes.

Limits: automated first-use coverage is not unfamiliar-tester acceptance, which remains pending. The broader fuzzing campaign remains unfinished. These jobs do not establish hostile-client trust or comprehensive security coverage.

Preparation attempts: initial sandboxed clone failed with a networking initialization error; the isolated clone succeeded outside that sandbox. The first local unit invocation ran 33 tests with 14 temporary-directory permission errors; its terminal output is retained in the task transcript, not a complete file log. The repeat is separately logged. No tests or limits were relaxed.

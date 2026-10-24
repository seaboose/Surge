# First-use partial-report failure probe

Acceptance fixed before execution:

1. Run the real `check_first_use.main()` with its normal package creation, extraction, source validation, cache isolation, command supervisor and report writer. Only this dedicated probe replaces the in-memory `setup` command with an owned Python process that prints an explicit probe marker and exits 73. The production runner gains no bypass, environment switch or changed acceptance limits.
2. The genuine `package` and `cache_path` steps must pass. The injected `setup` command must fail with exit 73 and its marker in the retained log. All subsequent steps must remain `not_run`; the report and wrapper process must fail. A different failure does not satisfy this probe.
3. The failed report must retain unfamiliar-tester acceptance as `pending`, original fuzzing as `incomplete_not_run`, unchanged-source verification, the source ZIP and manifest, completed-step logs and failed-step log. The verifier checks every archived file against the manifest, archive/manifest fingerprints and all three executed logs' hashes/byte lengths recorded by the real runner. Later steps must have neither logs nor execution-result claims.
4. On a disposable hosted branch only, replace the normal first-use execution command with `python -B scripts/probe_first_use_failure.py`. Existing `always()` artifact upload must succeed after the job fails. Retrieve the artifact and independently repeat verification. The passing candidate workflow remains unchanged.
5. Preserve every attempt in its unique first-use output directory, including unexpected failures. Do not classify the intentional failure as a release pass. Record hosted verification separately from local checks.

Run locally with the normal first-use prerequisites available. The expected process exit is **1**, accompanied by `failure-probe.json` with `status: verified_expected_failure`. Exit **2** or a missing verification file means the probe itself was not verified. For a downloaded artifact, run `python -B scripts/probe_first_use_failure.py --verify-artifacts <artifacts-directory>`; successful read-only verification exits 0.

This narrowly checks a supervised command failure after packaging. It does not test runner loss, cancellation, upload-service outages, disk exhaustion, all interruption points, human comprehension, normal-launcher interaction or the unfinished fuzzing campaign. No external processes are scanned and no application evidence is modified.

## Local results, 23 October 2026

The initial local probe completed `package` and `cache_path`, failed the injected `setup` command with exit 73, preserved all 13 later steps as `not_run`, and returned exit 1. The wrapper independently verified the source archive, all 251 file hashes, manifest, partial report, completed/failed log presence and pending human acceptance. A second read-only invocation verified the same retained artifact directory. This is a dirty-worktree local result against base `0200edcd34c6be047ff3aecd0fe23fdb08ec7e90`, not a hosted or clean-candidate claim.

- Artifacts: `verification/qualification/first-use-adbbdc05bdf1/artifacts/`.
- Probe log: `verification/qualification/failure-probe-local-40cde1b90cd9.log`.
- Source archive SHA-256: `7e104f4425960497cb56894fa4ce8580e2821a715162888236df3b89f5c7cf9d`.
- Source manifest SHA-256: `3e9c2a2d9a9aa28a9329793096d751f098875c871d4ab0da5ed8e67b7d280cb1`.
- Real partial report SHA-256: `9239d97fa6b51176cf644337ce96ad0be65e06d3e48bc3bf588753388f3d7e8b`.

Five evidence-verifier tests passed. They reject unrelated failure causes, inflated human/fuzzing claims, wrong step states, missing logs/marker, and corrupted archive content even when its outer fingerprint is updated. The first unit attempt failed before assertions because sandbox temporary files were inaccessible; its full log remains at `verification/qualification/failure-probe-units-9af4568d232e.log`. Repeating with a workspace-local temporary directory passed; log: `verification/qualification/failure-probe-units-237f674484a2.log`. No application or probe logic change was needed for that environmental failure.

Review then tightened criterion 3 to verify all three executed log hashes and byte lengths and reject execution-result claims on skipped steps. Seven updated verifier tests passed, including per-step altered-log rejection: `verification/qualification/failure-probe-units-94216318cdfe.log`. A second real probe and independent read-only verification met the updated criteria 1–3 with the same expected partial-failure pattern and exit 1:

- Artifacts: `verification/qualification/first-use-ddff675a9e87/artifacts/`.
- Probe log: `verification/qualification/failure-probe-local-15920fd8acc7.log`.
- Source archive SHA-256: `0713035862cd79196006fd9b900a4eaa4c80eba2b94045efdb35b723b3d6b353`.
- Source manifest SHA-256: `c6310e4ad2e6ad9e305ca5d0392ee4a28c05a587a3460711b079c42d723404b7`.
- Real partial report SHA-256: `91ff9e0353aa7ebbb52ba207e5a32802caf338694cd80d772fd88d84f769c50e`.
- All three executed logs matched their recorded SHA-256 fingerprints and byte lengths; those identities are retained in `failure-probe.json`.

Criterion 4 (hosted failed job, successful always-upload and independent retrieval verification) remains **pending**. Human acceptance and the broader fuzzing campaign also remain **pending/incomplete**. Each results update follows its immutable local probe, so its source archive intentionally omits that probe's later results text. Both probe attempts and all unit logs remain preserved.

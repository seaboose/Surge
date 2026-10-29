# Hosted recovery candidate results

The scoped recovery candidate `937a19b8f821a72dfc46126948394a223d88c55c`
passed both required hosted Windows checks on its
[push run](https://github.com/seaboose/Surge/actions/runs/40064930011) and
[PR run](https://github.com/seaboose/Surge/actions/runs/40064933427).
Downloaded evidence was independently verified against the committed source
export. All seven [predefined acceptance criteria](hosted-recovery-acceptance.md)
passed. The draft PR remained unmerged; main and merge policy were unchanged.

This result covers that recovery commit only. Later visual-clarity, performance,
release-readiness and approval-contract work is separate and requires its own
qualification. This report was generated after the tested commit and is not
claimed as part of its source archive.

## Verified checks

- Both runs passed exact jobs `test` and `First-use release check` on hosted
  Windows. The PR used checkout `00e5ed68eced4ed3c438bfe2805a826cc016ffcb`;
  its exported source bytes matched the candidate, as did the push checkout.
- Each mandatory deeper profile passed 21/21 checks: push in 353.282 seconds,
  PR in 305.344 seconds, below the unchanged 1,800-second limit and individual
  step budgets. Each passed 429 Python tests with zero skips, native CTest 3/3,
  ASan CTest 3/3, and the expected safe/diagnostic controls (exits 0/86).
- Each run completed 768 Hypothesis evaluations across 12 runs, 24 retention
  cases/48 evaluations, and 28 parser checks with 10,000 fixed-seed executions.
  Fixed parser boundaries completed 88 cases/176 evaluations and both outcomes
  of 14 selected guards. Parser corpus coverage was 230/267 lines and 178/220
  branch outcomes; separate fixed-boundary coverage was 249/267 and 177/220.
  These separate measurements are not a coverage union or broad-fuzzing claim.
- Each `test` job ran the recovery campaign twice: once in the deeper profile
  and once in the normal desktop tests. All four campaigns passed all 96
  executions of 48 scenarios repeated twice, with no unexecuted checks or
  deadline kills. Each had 1,646 explicit assertions, 32 acknowledged child
  interruptions, 96 fresh-process inspections and 48 matching repeat pairs.
  Campaigns took 14.635–18.961 seconds. Aggregate totals are 384 executions,
  6,584 assertions, 128 interruption controls and 384 restarts; they are repeat
  executions of the same fixed scenario inventory.
- Every campaign stayed within the unchanged five-second child, 300-second
  campaign, 256 KiB input, 10 MiB log and 64 MiB evidence limits. Each retained
  about 40.59 MB of evidence and 100,484 bytes of combined logs. Qualification's
  desktop-step limit stayed 120 seconds.
- Each first-use package passed 16/16 steps and all 16 log hashes verified.
  Real desktop assertions covered replay (8), unapproved capture (5), approved
  capture (6), library (9), deletion (3) and saved cases (10). Actual launcher
  checks passed 5/5; observed launch/shutdown times were 5.359/0.282 seconds
  on push and 6.781/0.406 on PR, with no forced cleanup.

## Artifact verification and failure handling

All four original downloaded ZIPs matched GitHub's recorded lengths and SHA-256
digests. Every deep bundle's 401 manifest files verified; all four source ZIPs
contained the same 273 exported files as the preserved candidate archive, with
exact byte equality. This compares Git archive exports, not raw Git blob line
endings. Offline verification executed no archived binaries or test campaigns.

Recovery verification checked all 1,452 manifest entries per campaign, including
44 hidden staging files each: 5,808 file instances, including 176 hidden-file
instances, across the four campaigns. Committed library, harness, child and
criteria snapshots matched exact source bytes. The upload change explicitly
includes hidden files only within the selected evidence paths. Missing files
cannot be concealed by a green CI status.

Verifier development controls passed two retained valid campaigns and refused
six in-memory invalid-evidence variants: omitted hidden file, source mismatch,
unreached cleanup marker, incorrect restart hash, partial published bytes and a
missing execution report. These are verifier controls, not failed hosted runs.
Local preflight passed 47 runner/worker tests, 12 desktop tests (including a
96-execution recovery campaign), release hygiene and whitespace checks.

No new hosted run failed in this milestone. Earlier failures remain preserved:

- The preceding local recovery bundle retains the initial 70/96 campaign, with
  26 failed executions across 13 scenarios. Seven scenario types reproduced
  application defects; six exercised publication controls not yet present.
  Its invalid fixture setup attempts, sandbox restrictions and reporting failure
  remain documented in the [local recovery report](case-recovery-results.md).
- The previous [initial hosted failure probe](https://github.com/seaboose/Surge/actions/runs/40055026442)
  failed at official metadata HTTP403 before reaching its intended control.
  The [corrected probe](https://github.com/seaboose/Surge/actions/runs/40055713287)
  reached the owned exit-73 build failure, failed the required job and preserved
  verified partial evidence. These are historical controls, not rerun here.
- The current bundle includes immutable hash references to the unchanged local
  recovery and previous hosted-deeper bundles, their reports/manifests, original
  new hosted ZIPs, metadata, job logs, verification records, source export and
  local preflight evidence. Extracted hosted binaries are not duplicated.

Read-only policy verification at 2026-10-24T05:21:06Z confirmed both exact checks
bound to GitHub Actions app 15368, up-to-date branches required and administrator
enforcement off. Main remained `2b9e3c8bbfc22c7a82827f39e404fa87e7eb8fb5`;
the candidate was draft/unmerged. No policy mutation or blocked-merge attempt
is claimed. Main adopts the candidate only after a future merge.

## Limits and milestone review

Unfamiliar-tester and native-dialog acceptance remain pending. The broader
T1/T2/T3 fuzzing campaign remains unfinished. The fixed recovery matrix and
bounded parser pilot do not complete it. Controlled child interruption does not
establish whole-app interruption behavior, power-loss durability, physical disk
failure, hostile concurrent writers or network/removable-filesystem support.
Temporary residue may intentionally remain for evidence preservation; safe
publication does not make exported evidence immutable.

Always-upload behavior and historical supervised-command failure handling are
verified within their recorded scope. Cancellation, runner loss and artifact
service outage were not newly tested. Hashes establish identity/consistency,
not trusted client attestation or resistance to a privileged local actor.

Ratings remain **8/10 as a scoped defensive engineering tool** and **8.5/10 as
an internship portfolio project**. This is an incremental evidence-based review,
not a fresh full security audit. Hosted repeatability and preserved failures
strengthen the project; unfamiliar-user comprehension and release acceptance
remain open. The next step is qualification of the current UI/release-readiness
candidate, with exact committed package identity, both required hosted jobs and
verified downloads, while human acceptance stays pending.

Machine-readable results: [hosted-recovery-validation.json](../evidence/hosted-recovery-validation.json).
Portable files are `Surge-hosted-recovery-results.md`,
`Surge-hosted-recovery-validation.json`, `Surge-hosted-recovery-evidence.zip`
and `Surge-hosted-recovery-evidence-manifest.json` in the milestone outputs.

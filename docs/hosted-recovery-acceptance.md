# Hosted recovery candidate acceptance

Recorded before committing or running this milestone on hosted Windows.
Scope: the local case-library fixes and bounded recovery checks, starting from
064c6a1bf62892329585e7666a65ee7919e8a140 on the existing draft candidate branch.

1. Commit only the reviewed recovery implementation, tests, integration and
   documentation. Record the candidate SHA and generated PR checkout identity;
   retain a source export for comparison. Leave the draft PR unmerged.
2. Both exact required jobs, `test` and `First-use release check`, must pass on
   fresh hosted Windows for both push and PR events. A failure remains recorded;
   a retry or corrected commit never changes its status to passed.
3. The mandatory deeper profile must complete all 21 checks within its existing
   1,800-second total and individual limits. Require zero skipped Python tests,
   native and sanitizer controls, property, parser and retention evidence.
   The existing first-use package and real-launcher checks must pass, preserving
   the distinction between automated checks and pending human acceptance.
4. Each required `test` job must execute the recovery campaign in both the
   deeper profile and the normal desktop command: exactly 48 fixed scenarios
   twice per campaign, 96 passing outcomes, no unexecuted checks or deadline
   kills, matched repeat outcomes, 32 acknowledged interruption controls and
   96 fresh-process inspections. Verify the explicit assertions from retained
   records, not merely the headline status. Do not relax the 5-second child,
   300-second campaign, 256 KiB input, 10 MiB log or 64 MiB evidence bounds, nor
   the qualification desktop step's existing 120-second limit.
5. Download the original artifact ZIPs. Verify GitHub digest and length, safe
   extraction, source archives against the preserved candidate export, all deep
   evidence and first-use log hashes, and every recovery manifest entry including
   hidden staging files. Verify recovery source snapshots against the committed
   files. Missing evidence fails this milestone even if CI is green.
6. Retain job logs, metadata, original downloads and all unsuccessful attempts.
   Preserve the preceding local recovery failures and previous hosted controls.
   Existing always-upload behavior remains in place; this milestone does not
   newly claim cancellation, runner-loss, power-loss or upload-outage testing.
7. Read back the unchanged merge policy: both check identities bound to GitHub
   Actions, up-to-date branches required, administrator enforcement off. Main
   remains unchanged; no merge or policy change is part of this milestone.

Only owned bounded fixtures are exercised. The fixed recovery campaign is not
broad fuzzing; the earlier parser pilot remains limited to its measured parser.
Unfamiliar-tester and native-dialog acceptance remain pending. Broader T1/T2/T3
fuzzing remains unfinished. Network/removable filesystem compatibility, hostile
concurrent writers, full-app interruption and physical storage durability remain
outside the recovery claim. Supplemental hosted results are generated after the
tested commit and must not be represented as part of its archived source.

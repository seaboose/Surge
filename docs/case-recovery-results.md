# Case-library interruption and recovery results

23 October 2026. The bounded recovery milestone passed locally after narrow
fixes to export publication, copy progress/cleanup, and rename staging.
Unfamiliar-tester acceptance remains pending; broader T1/T2/T3 fuzzing remains
unfinished. The previously hosted candidate was 064c6a1. These later working-tree
changes had not been committed, pushed, or requalified on hosted Windows at the
close of that local milestone. This is a historical local result; subsequent
hosted qualification is governed by [separate criteria](hosted-recovery-acceptance.md).

## Criteria and scope

[Acceptance criteria](case-recovery-acceptance.md) were recorded before execution
and copied into each attempt with source fingerprints. The campaign uses 48 fixed
scenarios twice, newly created owned cases, one operation child at a time, and a
fresh inspection process after every operation. No user library or external
application is touched.

The unchanged limits are 5 seconds per child, 300 seconds per campaign, 256 KiB
per input, 10 MiB combined logs, and 64 MiB retained campaign evidence excluding
the source snapshot. The existing full qualification desktop-step limit remains
120 seconds. Disk-space and permission faults are simulated; the disk is never
filled and host permissions are not changed.

## Reproduced problems and narrow fixes

1. **Export publication.** Previously the requested final filename was written
   before validation. Interruption during copy or validation could leave partial
   or unverified bytes there. Export now copies into a newly created sibling
   temporary directory, verifies that copy, and publishes the completed file
   without replacing an existing destination. A destination that appears
   immediately before publication remains untouched.
2. **Copy progress and cleanup.** A zero-byte write could loop until the test's
   deadline. Copy now rejects zero or invalid progress and attempts both handle
   closures and owned-output cleanup without masking the primary error.
   Completed export plus failed temporary cleanup is reported as completed with
   an explicit cleanup warning.
3. **Rename recovery.** Interrupted name writes left temporary files inside the
   case directory, causing later deletion to refuse that case. New name staging
   stays at the library root. The original case bytes and old-or-new complete
   metadata survive; another open, rename, and delete work after restart.

Save/import already staged library publication safely at the tested boundaries.
The fixes preserve their original evidence and unrelated cases. Unexpected files
are never broadly removed.

## Campaign attempts

- **Initial unchanged production:** 70/96 passed; 26 failed executions across 13
  scenarios, repeated identically, in 50.951 seconds. Seven scenarios reproduced
  defects (14 executions); six additional export publication/cleanup controls
  could not reach the required new boundary (12 executions). This is not a claim
  of 26 distinct defects. Four deadline terminations exposed the two zero-write
  scenarios, each repeated twice. All 96 scenarios executed.
- **After fixes:** 96/96 passed in 29.038 seconds; all 48 repeat pairs matched.
  There were 1,646 explicit assertions, 32 acknowledged abrupt-interruption
  controls, 96 fresh-process restarts, and no deadline or skipped checks.
  Retained evidence including report/manifest: 40,632,449 bytes; combined
  stdout/stderr/IPC logs: 101,036 bytes.
- **Integrated desktop test command:** the campaign passed again, 96/96 in
  27.767 seconds, with the same 1,646 assertions, 32 interruption controls and
  96 fresh-process restarts. All 96 semantic outcomes match the standalone
  successful campaign. Retained evidence: 40,632,440 bytes.

The original campaign oracle was tightened after preserving its failed attempt:
the successful runs additionally require exact injection markers, primary error
codes, unchanged metadata, and final report/manifest byte accounting. No scenario
or acceptance limit was removed or relaxed. The initial record counted raw logs;
the final records also account for IPC. Independent inspection measured the
initial complete retained evidence at 40,795,917 bytes, within the same limit.

Independent verification checked all retained hashes and source snapshots:
1,462 manifest entries for the initial attempt and 1,452 for each successful
attempt. Both successful source snapshots matched the locally tested implementation.
The initial audit's aggregate failure field counts failed executions, including
unreached controls, rather than independently established application defects.

## Acceptance outcomes

1. **Save/import — passed.** No partial library entry appeared before publication;
   completed publication survived a lost response. Original evidence and
   unrelated cases remained byte-identical.
2. **Rename — passed for new operations.** Names remained complete, evidence bytes
   did not change, and fresh-process recovery could open, rename and delete.
3. **Export — passed on the tested local Windows filesystem.** Partial/unverified
   files never appeared at the requested final destination; successful
   publication contained exact verified bytes. Existing/racing destinations
   survived. An additional simulated unsupported-link test refused publication,
   preserved evidence, cleaned its staging, and succeeded after removing the
   injected failure.
4. **Restart/damaged cases — passed.** Bad metadata was counted unavailable;
   invalid case contents were refused on open. Three real-worker tests used an
   actual 110,491-byte portable case, exercised five truncation lengths and a
   complete-but-modified case, and confirmed rejected verification/open leaves
   the active investigation unchanged. Real desktop journeys also restarted
   and reopened saved cases. Rename recovery uses a byte-identical copy of the
   interrupted directory so the original interrupted state remains preserved.
5. **Failure accuracy — passed at tested points.** Expected controls were reached;
   zero progress failed promptly; paired cleanup failures retained primary
   ENOSPC/EINVAL codes; post-publication cleanup failure was reported accurately.
6. **Repeatability/evidence — passed.** Every fixed case ran twice in fresh
   directories, semantic results matched, and raw records and hashes verified.
7. **Local integration — passed; hosted execution pending.** The recovery test is
   in the normal desktop command and qualification's desktop step. CI's existing
   always-upload path now includes recovery evidence. That upload change is
   configured but has not been exercised by a new hosted run.

## Other completed checks

- Full Python discovery suite: **429 tests passed**, zero skips, 74.559 seconds
  reported by unittest (75.609 seconds including supervision).
- Integrated desktop boundary/runtime/library/recovery command: **12 tests
  passed**, zero failures/skips, supervised duration 28.093 seconds.
- Focused library tests: **7 passed**, including the unsupported-publication
  control.
- Real library desktop journey: **9 checks passed**, including save, rename,
  import/export, invalid import, deletion preservation and restart.
- Library-deletion UI journey: **3 checks passed**.
- Saved-case UI journey: **10 checks passed**, retaining the saved/live
  distinction and unchanged evidence.
- Formatting of the changed desktop files: passed.

These are local targeted checks and the Python suite. They are not a new full
21-step qualification, sanitizer/property/parser campaign, clean-checkout result,
or hosted CI pass.

## Preserved unsuccessful preparation

- Two real-worker fixture setup attempts failed before their assertions: one
  exceeded the existing 4,096-character field limit, and the next requested
  numeric deviation without a reference dataset. The fixture was corrected to
  bounded records and an explicit threshold rule; application limits were not
  changed. The corrected three tests passed, then passed in the full suite.
- The first ordinary library-test run encountered sandbox temporary-directory
  rename restrictions. A workspace-local temporary directory resolved that
  restriction, but sandbox hard-link restrictions still blocked both an existing
  link-security test and the new export path. The same code passed with normal
  Windows file access. Both unsuccessful logs remain preserved.
- The integrated desktop command exited zero and its complete passing log/report
  were saved. The local reporting helper then failed to print a check-mark
  character through Windows cp1252. Its original helper and failure record remain
  preserved; reporting now uses UTF-8. No test result was changed or test rerun
  merely to conceal that console failure.

## Remaining limitations

- Abrupt termination stops only a purpose-built child running the real library
  code. It does not reproduce whole-Electron termination at every boundary,
  power loss, storage corruption or filesystem durability.
- The fast campaign uses a strict owned-fixture byte verifier. Actual engine
  verification and worker state preservation are exercised separately by Python
  and real-desktop integration checks.
- Atomic no-overwrite publication currently uses hard links in the selected
  destination directory. Unsupported filesystems fail safely; removable-media
  and network-share compatibility were not physically tested.
- Abrupt termination can retain clearly named temporary directories/files.
  They are not published library cases and are not automatically deleted.
  Old in-entry name residue from earlier versions remains conservatively refused
  on deletion. Post-publication export staging aliases the completed export until
  cleanup succeeds; it is not an immutable forensic snapshot.
- The close-error control closes the handle before reporting the simulated
  error. Input-close failure, persistent unclosed handles and invalid
  negative/oversized write counts were not individually injected.
- The test uses one local Windows environment, a single writer and deterministic
  fixtures. Hostile concurrent changes, real disk exhaustion, native-dialog
  acceptance and broader platform compatibility are outside this result.
- The separate direct investigation-file export path is not included in this
  case-library recovery claim.
- Unfamiliar-tester acceptance remains pending and broader T1/T2/T3 fuzzing remains
  unfinished. Hashes and passing checks do not establish hostile-host trust.

## Automatic milestone review

**Security engineer: 8/10. Hiring manager: 8.5/10 as an internship or early-career
portfolio project.** Ratings remain unchanged; confidence in case preservation
has improved because concrete failures were reproduced, fixed narrowly, and
checked with explicit recovery oracles. This is an evidence-based milestone
assessment, not a new full security audit or manager-level qualification.

No reproduced defect remains failing in the completed local checks. Important
gaps are release qualification of the new source, unfamiliar-user acceptance,
broader fuzzing and the recovery limitations above.

**Highest-value next milestone:** prepare a scoped committed recovery candidate
and run the required hosted Windows checks on that exact source. Acceptance:
both required jobs pass; the full deeper profile and recovery campaign execute
without skips; downloaded recovery reports, source snapshots and manifests
verify; failed attempts remain retained; the existing required-check policy,
pending human acceptance and unfinished broader campaign remain explicit.
Do not silently apply the earlier 064c6a1 hosted result to this later code.

Machine-readable summary: [case-recovery-validation.json](../evidence/case-recovery-validation.json).
Full attempt directories and audits are retained under the ignored
verification/qualification directory and in the milestone evidence bundle.

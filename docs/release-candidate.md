# Source qualification

The current published app is [Surge 0.4.3](https://github.com/seaboose/Surge/releases/tag/surge-resume-v0.4.3).
For installation and source setup, use the [README](../README.md).
The original release downloads and checksums are retained unchanged; subsequent
source checks identify their own commit and do not retroactively qualify those
downloads. See [validation scope](validation.md).

## Prepare a new source package

1. Select a stable commit. Package it with its source manifest, SHA-256, license,
   dependency notices and known limits. Keep generated qualification reports
   outside the source being packaged.
2. Pass the required hosted Windows checks for that commit. Verify the downloaded
   artifacts and their manifests; preserve failed attempts as well as passes.
3. Check source replacement against the previous reader and case library. This
   tests bounded compatibility, not an installer or every historical case format.
4. Record unfamiliar-user acceptance separately using the
   [participant tasks](first-use-tester.md) and
   [session record](release-candidate-session-record.md). Automated checks cannot
   establish unaided use of native file dialogs or correct interpretation.

If the source changes, repeat the affected checks and identify the new candidate.
The [acceptance criteria](release-candidate-acceptance.md) define the detailed
source-package checks.

## Preserve investigations

Close Surge before switching source folders. Export important cases to a separate
folder, then extract the new source into a new directory and run its setup.
Do not copy installed dependencies from another checkout.

Reopening a case reviews recorded evidence; it does not restart collection.
Deleting an imported library copy leaves the original evidence and external
exports intact. Interrupted writes must not appear as completed cases, and
export must preserve an existing destination. See the
[recovery criteria](case-recovery-acceptance.md).

Clean-machine and unfamiliar-user acceptance remain pending. Hosted checks do
not establish real-world detection accuracy, client authenticity, signed
installation, or support for every filesystem. Broader fuzzing remains unfinished;
the recorded finite checks retain their individual scope and tested source.

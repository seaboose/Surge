# Windows package release check

The [acceptance criteria](windows-package-acceptance.md) were defined before this
milestone. They distinguish a locally built development package, a clean committed
candidate, the downloaded artifact tested by a separate hosted Windows job, and
the still-pending unfamiliar-user session.

## Build and consume

Build from a clean Windows x64 checkout with the documented developer prerequisites
and locked desktop dependencies installed:

```powershell
python -B scripts/build_windows_package.py
```

The builder creates a unique attempt under `verification/qualification`, preserving
its commands, failures, source manifest, runtime provenance and package manifest.
It packages the pinned official Electron and embedded CPython distributions from
`scripts/windows-package-lock.json`. The desktop/backend and native inputs come
from the recorded source. A separate static-runtime build supplies the owned v2
sample; the existing approval path binds a new isolated registry to that exact
build. Developer approvals, environments and personal cases are excluded.

The `--allow-dirty` option is for development attempts only. Such an attempt cannot
qualify the final committed candidate. Matching source and dependency versions
does not imply bit-for-bit reproducible compiler output; retain and test the
actual ZIP being delivered.

Run the consumer with the ZIP and adjacent `package-manifest.json`:

```powershell
python -B scripts/check_windows_package.py --package <candidate.zip> --manifest <package-manifest.json>
```

The consumer needs its own external test driver, but Surge itself runs from the
downloaded payload with developer command lookup unavailable and invalid Python
overrides present. It never builds or approves the sample. Reports retain actual
application/worker paths and process-token elevation. Owned profiles, fixtures,
screenshots and failed attempts remain separate from the immutable ZIP. A local
run refuses to touch an existing selected profile.

The normal application executable is used. Automated workflow checks attach a
debugger through Playwright and substitute native file-dialog selections with
owned fixtures. Missing-component startup controls use the real native error
dialog. These different checks must not be described as an unassisted human run.

## Hosted required checks

`Build Windows package` uploads the candidate ZIP and its build evidence.
`Packaged Windows acceptance` downloads it on a separate fresh Windows runner,
verifies every file and executes the consumer. The existing required
`First-use release check` runs with an explicit dependency-result gate: failed,
skipped or cancelled package work cannot silently satisfy that check. The existing
required `test` job continues to run the deeper qualification and other tests.

The consumer's declared failure probe retains a non-passing report separately
from its expected-failure receipt. Successful detection of an intentional failure
does not turn that failed consumer invocation into a successful application run.
Always-upload steps preserve available evidence; they do not guarantee recovery
from runner loss or an unavailable artifact service.

Download the original artifacts after CI completes. Compare their byte lengths
and SHA-256 with GitHub metadata, then verify the ZIP payload and report evidence.
`scripts/report_windows_package.py` produces a qualification report from the
retained inputs and keeps missing hosted/local evidence incomplete. A clean final
package must be verified again if its source or bytes change. Do not insert a
generated report into the already-tested ZIP or silently repack it.

## What remains separate

Fresh hosted Windows images still contain developer tools. Restricted executable
lookup and recorded bundled paths demonstrate isolation, not their physical
absence. Actual account elevation is recorded; a separate standard-user hosted
account and pristine physical desktop may remain unverified.

The [participant tasks](windows-package-tester.md) and
[blank session record](windows-package-session-record.md) accompany the package.
The H1–H4 criteria in [first-use acceptance](first-use-acceptance.md) still require
an actual unfamiliar participant; package opening replaces source setup for that
session. Native-dialog usability, comprehension and any assisted retries must be
recorded honestly. Acceptance is **pending** until that session is assessed.

The original broader fuzzing campaign remains **unfinished**. Packaging checks
neither reopen the blocked native extension nor establish whole-process integrity,
client attestation, publisher identity, SmartScreen reputation or production
anti-cheat effectiveness.

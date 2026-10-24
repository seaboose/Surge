# Surge source release candidate

This candidate brings bounded case-library interruption recovery, clearer optional
help and strict embedded-manifest validation into the Surge 0.4 source distribution.
Supporting checks cover evidence preservation, limits and case compatibility. It remains a
review candidate, not a signed installer or a published release. The candidate
label and exact source hash are recorded with each package; the application
version remains 0.4.0.

## Open the candidate

1. Extract the versioned `Surge-<label>-source.zip` into a new local folder. Keep
   the previous folder until you have opened your cases successfully. Do not
   overwrite an existing source tree or copy its installed dependencies.
2. Install the prerequisites listed in the [README](../README.md#set-up-from-source-on-windows):
   Python 3.11+ with Tcl/Tk, Node.js 22.12+ and pnpm 11.25.0. The recorded hosted
   checks use Python 3.12 and Node 24.
3. In File Explorer, open the extracted folder containing `README.md` and
   `Start-Surge.cmd`. Click the address bar, type `powershell`, and press Enter.
   In that window run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Surge.ps1
   ```

   Wait for “Surge is ready”, then double-click `Start-Surge.cmd` in File
   Explorer. Setup downloads dependencies; normal evidence analysis runs locally.
4. For a first look without a compiler, open an [included saved case](../demos/native/README.md)
   from **Case library → Open case file**. **Try Demo** additionally requires the
   documented native build. Approval applies only to the exact reviewed build;
   an unapproved build correctly requires review.

If setup reports that Python is missing or too old, use the installed Python
3.11+ executable explicitly, for example add
`-Python 'C:\Python312\python.exe'` to the setup command, replacing that example
with its actual installed location. Keep the error text if setup fails. Do not
continue as though setup completed, and do not copy another installation's
`.venv` or `node_modules` folders into this one.

Close Surge before switching source folders. Keep portable exports of important
cases in a separate folder. A downloaded package contains source and published
examples, not your local case library or machine-specific approvals.

The package manifest lists the SHA-256 of every included source file. The
generated compatibility report records the ZIP hash, the previous committed
source and whether the candidate contained uncommitted changes. A passing
compatibility check on a dirty snapshot is not proof that a later commit or a
different downloaded ZIP passed hosted CI.

## Preserve cases when changing source folders

Use **Export case** to keep a portable copy of important cases before changing
versions. Reopening a saved case reviews recorded evidence; it does not restart
live capture. **Import case** creates a library copy. Deleting that copy leaves
the original evidence and external exported files unchanged.

The bounded update check opens a case created by the recorded previous source
using the candidate reader and library, then verifies rename, export, import,
delete and a fresh-process reopen. It checks a shared owned library under paths
with spaces and non-ASCII characters. This simulates source replacement; it
does not qualify an installer, account migration or every historical case format.

## Recovery behavior and remaining acceptance

Interrupted writes cannot be treated as complete published cases. Export uses
exclusive publication, so an existing destination is preserved. A completed
export may report incomplete temporary cleanup; the successful exported file
and library copy remain available. Do not manually delete uncertain evidence
because a cleanup warning appears.

The [recovery criteria](case-recovery-acceptance.md) and
[release-candidate criteria](release-candidate-acceptance.md) define the bounded
checks. Filesystems without the required hard-link publication capability fail
safely; removable and network-drive behavior has not been physically qualified.

The required hosted Windows checks, package compatibility results and visual
checks each identify their own tested source. Unfamiliar-tester acceptance is
**pending**. The broader T1/T2/T3 fuzzing campaign is **unfinished**. These gates
must not be represented as passed by automated first-use or fixed recovery tests.

No code-signing, signed installer, automatic updater, multi-user support,
whole-process integrity or client-attestation claim is added by this candidate.

Embedded manifest text now uses the same strict JSON rules as the surrounding
evidence. Duplicate object keys are rejected even when their values agree.
Uniquely keyed cases retain their format; the bounded compatibility check does
not promise to reopen previously accepted ambiguous declarations.

## Completion priorities at the local visual checkpoint

The requested next steps remain separate acceptance gates:

1. Hosted qualification: recovery commit `937a19b` precedes the current UI work.
   The final combined committed candidate and downloaded artifacts still need
   their own required Windows checks; no merge or public release is claimed here.
2. Unfamiliar-user acceptance: participant tasks exist, but an actual unfamiliar
   participant is still needed. Automated walkthroughs do not close this gate.
3. Release candidate: versioned source packaging and exact manifests are
   implemented. Final compatibility/package execution awaits a stable source
   snapshot; this remains a source distribution, without a signed installer.
4. Recovery clarity: unsupported safe-export locations now receive actionable
   guidance while preserving evidence and diagnostic codes; cleanup warnings
   still distinguish successful publication from incomplete cleanup.
5. Performance at supported limits: the [bounded local measurement](supported-limits-performance-results.md)
   passed four journeys and 32 measured operations. It records its own tested
   source and is not a worst-case or multi-host performance promise.
6. Compatibility/update preservation: the bounded checker exercises actual old
   and candidate readers/libraries under spaces/non-ASCII paths. Earlier failed
   sandbox and source-drift attempts remain retained; final package qualification
   is a separate result.
7. Broader defensive fuzzing: the [fixed approval/verdict pack](approval-contract-results.md)
   adds useful independent expected outcomes. The [stream model](stream-model-results.md)
   passed 252 executions after the strict JSON fix, and the
   [manifest model](manifest-model-results.md) passed 632 executions across
   development, frozen final variants and two exact replays. A proposed
   further native T1 extension was stopped by a cybersecurity safeguard and was
   not rerun. These finite components identify their exact source and limits;
   subsequent CI runs are known-variant revalidation. Original T1/T2/T3 aggregate acceptance
   remains unfinished; fixed packs are not a completed campaign.
8. Visual clarity: [short checks](visual-clarity-results.md) passed for concise
   optional help, accurate counts, keyboard access and case-details disclosures.
   Existing navigation and evidence semantics remain intact. An affected
   evaluation test initially expected explanatory text in its old location;
   the preserved failure was followed by a narrow help-opening assertion update
   and four passing evaluation journeys, without relaxing the timeout.

Later generated qualification reports take precedence for execution status and
identify the exact source they tested. This checkpoint does not mark pending
hosted, human or broader fuzzing work complete.

## Final candidate delivery checklist

Freeze and commit the final selected source before qualification. Keep later
execution reports outside that frozen publishable tree so recording a result
does not silently change the candidate being delivered. If source changes after
qualification, create a new candidate and repeat the affected release gates.

- Supply one clearly versioned source ZIP, its SHA-256 and complete source
  manifest, exact commit, release notes, setup instructions and known limits.
  Keep the existing source license and notices in the package.
- Run compatibility on the stable source against the recorded prior commit.
  Verify that its extracted files match the candidate manifest. Record source
  replacement as a simulation; do not describe it as an installer upgrade.
- Pass both required hosted Windows jobs for that commit. Download their
  artifacts, validate archive hashes and all evidence manifests, and preserve
  failed attempts. A green status alone does not verify a downloaded package.
- Prefer distributing the exact source archive exercised by the hosted
  first-use check, with a versioned filename but unchanged ZIP bytes. If another
  ZIP layout is delivered, establish exact source-manifest equivalence and
  separately identify which physical archive each check exercised.
- Include the [participant task sheet](first-use-tester.md) and
  [blank session record](release-candidate-session-record.md) identifying
  package/commit, Windows/tool versions, start/end times, assistance, wrong
  turns, task outcomes and evidence filenames. Observe the 45-minute session
  limit, keep prerequisite installation time separate, and preserve the first
  attempt before coaching or retrying.

An unfamiliar participant must use actual native file dialogs and explain the
results unaided. A developer or automated agent cannot sign off that gate.
Packaging, CI success and readable instructions therefore do not remove the
explicit pending human-acceptance and unfinished broader-fuzzing labels.

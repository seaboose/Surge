# Bounded source release-candidate acceptance

These criteria are fixed before the first execution. This milestone qualifies a
versioned **source candidate**, not an installer or a public release.

1. Create a new, retained attempt directory and a versioned ZIP with a complete
   SHA-256 manifest. The ZIP must contain exactly the publishable source files;
   extraction must match every byte. Record the candidate Git identity, working
   tree state and the previous committed source identity separately.
2. Extract previous and candidate source into different paths containing spaces
   and non-ASCII characters. Both must run the real Python case reader from their
   own source tree. No installed dependencies, live captures or personal cases
   may enter the source archive.
3. Generate an owned case with the previous source, import it using the previous
   library, then open the same persisted library with the candidate. Preserve
   the case identifier, name, evidence bytes, configuration and computed results.
   Saved evidence must not acquire live-capture identity.
4. With the candidate, rename, export, import and delete an owned library entry.
   Reopen using a fresh process. The original input, retained library entry and
   portable export must remain byte-for-byte unchanged. Repeat opening the
   retained entry with the previous source as a bounded compatibility check.
5. Refuse overwrite of an existing export destination and reject a modified case
   without publishing a new library entry. Verify the old entry and original
   source remain intact. Existing recovery tests separately exercise simulated
   unsupported hard links; do not infer real removable/network-drive support.
6. Record Windows version, interpreter/runtime versions and the process's actual
   elevation state. A non-elevated process check is not a separate standard-user
   account/session or an installation-permission test.
7. All child commands have a 30-second deadline, the complete run a 300-second
   deadline, retained command output a 2 MiB limit and retained attempt files a
   128 MiB limit. Inputs are owned and below 256 KiB. Any failed or missing check,
   timeout, source drift or mismatched manifest prevents a pass. Preserve failed
   attempts, raw logs and fixtures; never silently retry or overwrite them.

Unfamiliar-tester acceptance remains **pending**. Original T1/T2/T3 broader
fuzzing remains **unfinished**. Source re-extraction with a persistent case
directory is a simulated application update: no installer, migration from every
historical version, launcher/UI relocation, downgrade promise, Windows account
matrix, physical power loss or removable/network filesystem is qualified here.

Run `python -B scripts/check_release_compatibility.py --baseline-ref <commit>`.
The optional `--label` names the source candidate without changing the app's
internal version. Reports and versioned packages are retained beneath
`verification/qualification/release-compatibility-<unique-id>/`.

The runner applies the remaining combined 2 MiB log allowance to each child
supervisor and restores the shared supervisor setting afterward. Its polling
supervision can observe one write beyond the threshold before terminating the
child; exceeding the allowance cannot pass. No output is truncated to disguise
an overrun.

After writing the report and evidence manifest, it verifies their retained file
hashes and measures the complete directory. The sibling
`release-compatibility-<unique-id>-seal.json` records that exact sealed byte
total, report/manifest hashes and status outside the measured directory, avoiding
a self-referential size or hash. Retain this receipt with the attempt. A sealed
size or total-time overrun makes the attempt fail.

Read-only review identified the original generic log-stop allowance and estimated
final-size reserve before final package execution. Six small owned-output and
sealing controls passed after the narrow accounting fix; the retained control
record is `verification/qualification/release-runner-controls-167932cb996d/`.
This was runner hardening, not an observed application failure or a completed
compatibility run. The fixed 300-second, 2 MiB and 128 MiB limits did not change.

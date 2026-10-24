# Combined candidate qualification

These criteria are recorded before qualifying the final combined commit. Earlier
recovery, visual, performance and model reports retain their own source identities.

1. Commit only reviewed Surge source, tests and documentation on the existing
   scoped candidate branch. Record the exact commit and preserve its Git archive.
   Keep the pull request a review candidate while unfamiliar-user acceptance is
   pending; do not publish a stable release merely because automated checks pass.
2. Both required hosted Windows jobs must pass for the candidate: `test` and
   `First-use release check`. Verify the actual checkout identity separately for
   the push and generated pull-request merge. Require the existing 21-step deep
   profile, zero skipped Python tests, native and sanitizer controls, and the
   existing first-use and launcher contracts. Do not weaken any existing limits.
3. Run the new visual checks and bounded approval/model checks as separate named
   steps, preserving their original limits and incomplete broader-campaign status.
   Do not combine their coverage percentages or call known-case revalidation a
   new held-back experiment. Preserve failed and incomplete attempts.
4. Download original hosted artifacts. Verify lengths and SHA-256 against GitHub
   metadata, exact extracted bytes, manifests and required scenario counts.
   Compare embedded source against the committed archive, explicitly recording
   any line-ending normalization. Include hidden owned recovery fixtures. Verify
   the additional UI/model reports rather than relying on a green job alone.
5. Run the bounded release-compatibility check on the stable committed source.
   Require all checks, unchanged source, complete package manifest and preserved
   original cases. Verify its versioned source ZIP against the qualified commit.
   Earlier sandbox and source-drift failures remain failed historical attempts.
6. Deliver the versioned source candidate, package hash/manifest, tester checklist
   and a generated status report. Keep prior logs and failed attempts available.
   Read back required-check policy without changing it or merging the draft.

Unfamiliar-user/native-dialog acceptance needs an actual unfamiliar participant
and stays pending. The original combined T1/T2/T3 campaign remains incomplete:
the broader native-parser extension was stopped by a cybersecurity safeguard.
Existing parser instrumentation, fixed boundaries and bounded Python components
remain separately identified evidence, not a replacement for that missing gate.

This qualifies a source distribution on the recorded Windows hosts, not a signed
installer, automatic update system, host-attestation service, broad Windows/account
matrix, removable/network filesystem, power-loss durability or unrestricted live
capture. No application layout or collection-scope redesign is included.

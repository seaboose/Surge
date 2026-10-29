# Self-contained Windows package acceptance

Criteria recorded before implementation and execution, 23 October 2026
(America/Los_Angeles). Baseline source candidate: ca6e3bb7290a50de737a07859aff0bc4ed32cbec.
This milestone packages existing Surge behavior for Windows x64; it does not
expand collection, detection, case formats or trust claims.

## Required gates

- **W1 — Reproducible package identity.** Produce a versioned ZIP containing
  `Surge.exe`, the pinned Electron runtime, a pinned official embeddable CPython
  runtime, the existing desktop/backend, and the owned v2 sample. Record exact
  source commit/dirty state, upstream URLs and SHA-256, build commands/versions,
  per-file manifest and ZIP digest. Exclude developer environments, tests,
  personal cases, captures, secrets and developer baseline registries. Include
  applicable runtime/component licenses and notices. Build clean final source.
- **W2 — Extract and launch.** Run the actual packaged `Surge.exe` after download
  and extraction on a separate fresh hosted Windows machine/job. The application
  must use only its bundled Python/backend/native files, with developer command
  lookup unavailable and hostile/invalid Python environment overrides ignored in
  packaged mode. It must open without setup, dependency installation, compilation,
  or elevation. Record actual process elevation; exercise a non-elevated process
  locally and seek an isolated standard-user consumer on hosted Windows. A hosted
  image contains tools: isolated lookup plus recorded binary/import paths is not
  a claim that those tools are physically absent from the image. Report any
  unverified account or pristine-desktop scenario explicitly.
- **W3 — Exact sample approval.** Build/package the existing v2 sample using an
  isolated build directory. Generate a fresh approval with the existing reviewed
  approval/validation path, tied to that precise DLL and declaration. Never copy
  the developer baseline or approve at first launch. Live Try Demo must collect
  at least two complete retained samples, show actual nonzero observations and
  expected No finding results, stop and leave no owned sample process running.
  A mismatched owned approval must not produce an approved result. Existing v1
  remains an internal test fixture and need not ship.
- **W4 — Existing workflows.** In the packaged UI import an owned source, analyze
  it, save/open/rename/export/import/delete a case, and reopen after full shutdown.
  Verify actual evidence, identifiers, names and result counts rather than just
  visible labels. Original evidence and external exports must survive deletion;
  reopened cases must remain saved evidence, not live capture.
- **W5 — Location and replacement.** Preserve the existing stable user-data
  identity (`surge-desktop`) with cases outside the application directory. Test
  package paths with spaces and non-ASCII characters, an unrelated working
  directory, and a second extraction/replacement reusing the owned profile.
  Existing source-format cases must open; retained library entries and original
  files must survive replacement unchanged. No writes to the packaged payload.
  This simulates folder replacement, not installer migration or power loss.
- **W6 — Clear failure and complete shutdown.** Exercise missing bundled runtime
  and backend using copies of the package, plus an unavailable sample component.
  Never fall back to a developer Python. Show bounded actionable guidance and a
  diagnostic location, with no permanent loading state. Startup diagnostics may
  contain allowlisted component/phase/status/version data, never imported
  evidence or raw worker request/reply/stderr contents. Verify timeout/failure
  causes a non-passing runner result and retains evidence; stop owned children.
- **W7 — Release automation.** Build and upload the immutable candidate ZIP in CI;
  download and verify it in a separate fresh Windows consumer job. Integrate that
  consumer result into an already-required check so a failed/missing package
  check cannot silently pass required CI. Keep the existing required test and
  first-use checks. Preserve evidence on failure, including screenshots, logs,
  package manifest, input hashes, environment and process identities. Download
  original successful/failing artifacts and verify their lengths/digests and
  report contents locally before declaring completion.
- **W8 — Handoff and status.** Deliver the exact tested binary ZIP, concise
  extract/open instructions, version/hash information, tester tasks, blank session
  record and generated report mapping every gate to evidence. Preserve previous
  source/tester packages and failed attempts. Keep unfamiliar-user acceptance
  pending, the original broader fuzz campaign unfinished, and the candidate a
  draft until reviewed integration. Include the engineering/portfolio milestone
  review without inflating ratings based on repeated test counts.

## Bounds and evidence discipline

Owned fixtures only; no games, third-party processes or new native parser/fuzz
extensions. Package build: 1,200 seconds total, 600 seconds per dependency/build
command, 180 seconds per individual runtime download, 10 MiB command logs.
Distribution: 256 MiB ZIP, 768 MiB expanded payload, 10,000 files. Consumer:
600 seconds total, 30 seconds per ordinary action/startup, 15 seconds shutdown,
10 seconds per startup failure control; sample capture remains within its
existing limits. Inputs remain below 256 KiB. Evidence: 20 MiB logs, 128 MiB
screenshots/profile/fixture evidence excluding the separately fingerprinted
immutable package ZIP; retain failed attempts in new directories, not retries
that overwrite a failure. Store large extracted runtime trees only as necessary
for the attempt; do not upload redundant profile caches or complete application
copies as evidence. No limits may be relaxed to turn a failure into a pass.

Use the current Windows x64 target and existing package identity. A source
version/hash label does not certify the publisher or machine. This milestone
does not promise Authenticode signing, SmartScreen reputation, an installer,
automatic updates, physical offline-host/network-filesystem compatibility,
screen-reader certification, other Windows/CPU variants, or independent human
comprehension. Record the downloaded-file/SmartScreen behavior actually tested;
unavailable certificate or physical-machine checks remain explicit limits.

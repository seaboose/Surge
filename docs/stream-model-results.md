# Isolated stream-model results

24 October 2026 UTC. **Both recorded attempts passed 252 isolated cases each.**
The second attempt revalidates the production source after the strict embedded
manifest JSON fix. It is explicitly a repeat of already-seen variants, not a
fresh held-back discovery. The combined original T1/T2/T3 campaign remains
unfinished.

## Results against the acceptance contract

- Each attempt executed 51 development scenarios, the 24 production retention
  boundaries, 51 final synthetic variants, two exact 51-case final replays, and
  a second 24-case boundary pass. Nothing was skipped. Every final semantic
  fingerprint and boundary fingerprint matched on repeat.
- The independent delivered/lost-slot model matched accepted sequence identities,
  loss totals, per-range conclusions, immutable snapshots, JSON/JSONL replay,
  and saved-case reopening. Ready/sample/end errors, identity conflicts,
  counter/time rollback and types, incomplete ranges, health inconsistency,
  malformed JSON/UTF-8, missing endings, and 32 KiB minus/at/plus one-byte line
  boundaries produced their declared results. Valid prefixes remained available
  with Unknown health after a reader failure.
- Every ordinary case had a five-second deadline; every deterministic boundary
  had fifteen seconds. Each Python child waited for its input until assigned to
  a Windows job with a verified 1 GiB process private-memory limit. A safe 16 MiB
  allocation passed, a 1 GiB allocation was refused, and a deliberately stalled
  worker was stopped at the five-second bound before campaign execution.
- Final-source revalidation took 371.375 seconds, excluding the resource-control
  preflight. Its slowest ordinary case was 0.953 seconds; its slowest boundary
  was 7.609 seconds. Maximum observed job private-memory peak was 202,125,312
  bytes. No application case exceeded its deadline or memory limit.
- The final-source artifact contains 1,037 manifest-listed files plus its
  manifest. Listed files total 37,555,055 bytes; logs total 3,185,637 bytes and
  ordinary recipe files 87,931 bytes. The 32 MiB corpus limit applies to ordinary
  inputs, not duplicate reports/source snapshots. Large deterministic fixtures
  were regenerated and successful temporary case files removed after hashing.
- Source tracing observed 265 lines and 298 executed line-to-line arcs in
  `native_stream.py`, including decoder acceptance, production fake-pipe reading,
  identity, retention append, snapshot, health and replay validation. It also
  reached the manifest, approval and engine paths. These are executed-line/arc
  counts, not a claim of complete branch coverage or native instrumentation.

The first attempt, `stream-model-98d93a4f4d38`, took 379.047 seconds. Its source
and final recipe were frozen before generating the concrete final variants.
The later strict embedded-JSON production fix changed source identity; the
second attempt, `stream-model-1f358369d5e8`, therefore records
`known_variants_revalidation` and points to the first attempt. Both original
bundles remain intact. No application failure or threshold relaxation occurred
in either stream attempt.

## Reproduction and evidence

Run `python -B scripts/run_stream_model.py --revalidation-of stream-model-98d93a4f4d38`.
This is a repeatable regression component; running its known recipe again does
not create a new independent holdout. Offline verification uses
`python -B scripts/verify_model_evidence.py <stream-model-directory>` and executes
no downloaded/frozen source. It checks file hashes, exact inventories, source
snapshots, resource controls, child results, limits, the development checkpoint
bound into the final freeze, and both semantic replays. Failed evidence can be
inspected with `--allow-failed`; its status remains `failed_attempt_preserved`.

The verifier's first development-checkpoint reconstruction omitted Windows CRLF
line endings and refused an otherwise intact artifact. That tooling failure is
preserved. Matching the retained report's actual newline convention corrected
the verifier; neither artifact nor model result was changed.
Eight offline-verifier regression tests now pass, including a CLI assertion
that an invalid report exits unsuccessfully with a diagnostic and no success
JSON. Verification of both finalized stream artifacts and the manifest component
passed after that verifier correction.
The first archive-summary helper also assumed the historical first report had
the later optional variant-status field. That packaging failure and helper source
are preserved; supplying its historical first-run default corrected packaging
without changing any report, frozen source or model outcome.

After those archives were sealed, candidate preflight exposed an import-path
side effect in the verifier: its runner imports left `scripts` first in the
caller's search path, so full-suite discovery selected the wrong same-named
stream test module. The failed preflight remains preserved. The verifier now
restores the caller's search path in a `finally` block. A subprocess regression
failed before that fix and now proves both unchanged search paths and resolution
of the root test module. All nine current verifier tests pass. The sealed model
archives retain their historical verifier and eight-test results unchanged;
the [supplemental receipt](../evidence/model-verifier-import-path-validation.json)
records the later tooling fix separately. No frozen model or production source
changed, and no model campaign was rerun for this verifier-only correction.

See [acceptance criteria](stream-model-acceptance.md) and
[sanitized validation](../evidence/stream-model-validation.json). Hosted execution
must be reported separately against its actual commit and downloaded artifacts.

## Limits

This is a finite defensive stream/retention component. It does not exhaust every
identity value, integer boundary, history, thread schedule, real pipe chunking,
native producer behavior, power-loss sequence, or arbitrary malformed record.
The reader uses a fake in-memory pipe; existing real owned-app journeys remain
separate integration evidence. Tracing reports observed arcs, without an
exhaustive branch-outcome denominator. The ordinary-input and resource limits
are the original specified values; the tests supply no new attestation claim.

The combined original T1/T2/T3 gates still require coordinated source/final-phase
evidence and remaining native/schema coverage. A separate T1 extension was
stopped by a cybersecurity safeguard and is not resumed or counted here.
Unfamiliar-user acceptance remains pending.

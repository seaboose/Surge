# Isolated manifest-model results

24 October 2026 UTC. **All 632 isolated cases passed** in the finite manifest,
approval and verdict component. Its independent oracle exposed an embedded-JSON
consistency issue during prerequisite regressions; a narrow strict-decoding fix
was verified before the source freeze and model campaign. This component does
not complete the original combined T1/T2/T3 campaign.

## Results against the acceptance contract

- Each phase executed the same declared 158-scenario inventory: 48 explicit
  approval/verdict cases, 21 representation/identity transformations, 74 invalid
  manifest declarations, 11 invalid encoded-evidence cases and four invalid
  approval registries. Development, first frozen final, replay 1 and replay 2 all
  completed. Across the four phases, 276 valid cases were accepted, 296 invalid
  declarations refused, 44 encoded inconsistencies refused and 16 invalid
  registries refused. Positive results prevent rejection of everything from
  being mistaken for correctness.
- The independent byte-occupancy oracle matched disjoint checked/excluded
  coverage and exact totals in small authored layouts. The separate truth table
  matched approval availability, readable-byte/protection comparisons, default
  conclusions and gaps. Actual JSON and JSONL import, alternate key order and
  whitespace, legacy/versioned identity separation, changed module/declaration
  identity, range-array reorder, split exclusions and saved-case reopening all
  produced their declared results. Invalid declarations also exercised direct
  validation and conversion; encoded import was not replaced with direct tests.
- All encoded ordinary inputs were checked against 256 KiB before import.
  The largest reported primary encoding was 222,239 bytes. Alternate formatting
  is also capped, but its individual byte sizes are not retained in the result
  summary. Every owned Python worker had a five-second deadline and a Windows
  job with a verified 1 GiB process private-memory limit before receiving its
  recipe. Positive allocation, allocation refusal and enforced timeout controls
  passed before the campaign. The slowest application case took 1.969 seconds;
  maximum observed process private-memory peak was 93,106,176 bytes.
- Development used seed 17 and took 141.344 seconds within its 600-second cap.
  Source, generator, oracle, category inventory, limits and final seed recipe
  were frozen before concrete final generation. Seed 2026102302 varied positions,
  names, lengths, span partitioning and fixture combinations. The first final
  passed in 183.641 seconds within the unchanged 300-second cap. Exact final
  replays passed in 223.360 and 263.515 seconds, together within 900 seconds.
  All final input recipes and semantic result fingerprints matched on replay.
  Total campaign time was 812.032 seconds, excluding resource-control preflight.
- The artifact contains 2,561 manifest-listed files plus its manifest. Listed
  files total 46,399,875 bytes; logs total 8,177,548 bytes and ordinary recipes
  271,396 bytes. The 32 MiB corpus cap applies to retained ordinary recipes, not
  duplicate reports and frozen source snapshots. Successful temporary case files
  were removed after checking their reopened source/configuration/results.
- Tracing observed 63 lines/73 executed arcs in `integrity_manifest.py`,
  341/411 in `native_integrity.py`, 306/314 in `engine.py` and 143/155 in
  `native_stream.py`. Reached functions include manifest and approval validation,
  approval creation, conversion, strict decoding, default analysis, stream
  replay and case reopening. The sanitized receipt records all observed
  functions and 26 distinct rejection messages with their counts. These are
  observed execution counts, not exhaustive branch coverage or native
  instrumentation.

## Finding and preserved attempts

Before the fix, the outer evidence decoder refused duplicate object keys, but
three embedded range/integrity-manifest paths used ordinary JSON decoding.
Both identical and contradictory duplicate keys could therefore be silently
normalized. The predeclared regressions preserved eight failing JSON/JSONL import
subcases; valid controls remained accepted.

The only production change uses the existing strict decoder at those three
sites, imported lazily to preserve module import behavior. Forty-eight focused
manifest/integrity/replay tests passed with a workspace temporary directory. An
earlier attempt at those same tests had one sandbox default-TEMP permission error;
its log is retained separately. No threshold or expected result was relaxed.
The full T2 component then passed on its first run,
`manifest-model-314869383270`, without a model, application or resource failure.

The offline evidence verifier originally refused an intact stream artifact
because its development-checkpoint reconstruction used LF instead of the
retained Windows report's CRLF. The failed output and a diagnostic receipt are
preserved; correcting that verifier did not change the artifact or application.
Eight verifier regression tests now pass, including changed bytes, escaping
paths, missing source claims, weaker limits, incomplete-pass relabeling,
duplicate scenarios, explicit failed-attempt inspection, and CLI failure
diagnostics. Verification executes no downloaded/frozen code.
The first shared archive-summary attempt also failed on an optional field absent
from the historical stream report. Its log and helper source are preserved;
using that report's historical first-run default corrected packaging without
changing any model artifact or result.

After archive sealing, candidate preflight found that verifier imports left
`scripts` first in the caller's module search path and disrupted full test-suite
discovery. The failed preflight and a failing subprocess regression are retained.
A narrow `try`/`finally` now restores the original search path after all trusted
runner imports. All nine current verifier tests pass, including unchanged paths
and correct root stream-test resolution. The existing sealed archives retain
their historical eight-test result and verifier source; the
[supplemental receipt](../evidence/model-verifier-import-path-validation.json)
records this subsequent tooling fix. Frozen model sources, production source
and campaign results are unchanged. No campaign rerun was required.

## Reproduction and evidence

Run `python -B scripts/run_manifest_model.py --revalidation-of manifest-model-314869383270`.
Subsequent execution is a known-variant regression, not a fresh held-back check.
Run `python -B scripts/verify_model_evidence.py <manifest-model-directory>` to
verify exact file inventories and hashes, frozen sources, child/parent results,
resource controls and limits, the development checkpoint bound into the freeze,
final recipes and two exact semantic replays. A failed attempt requires explicit
`--allow-failed` inspection and remains labeled `failed_attempt_preserved`.

See [acceptance criteria](manifest-model-acceptance.md) and
[sanitized validation](../evidence/manifest-model-validation.json). The source
hashes and local raw evidence are preserved. Hosted execution and compatibility
must be reported against their actual committed candidate and downloaded
artifacts; this local component does not claim those future results.

## Limits

This is a finite owned-data model component. It does not exhaust every manifest
field combination, integer/interval boundary, schema downgrade, mixed-range
state or arbitrary encoding. Its small occupancy oracle does not validate native
PE resolution, large-image event sweeps or the native producer's 63-character
name boundary; the separate Python representation accepts 64 characters by the
predeclared contract. Whole-module identity changes are modeled directly, not by
executing or mutating a native image. Hashes establish content identity, not
evidence authenticity or client attestation.

The original combined campaign remains unfinished: a separate native T1
extension was stopped by a cybersecurity safeguard and was not resumed or
recast here. Native resolution/oracle/deep-path requirements and coordinated
cross-target final evidence are not supplied by this component. Existing native
parser pilots remain separate evidence. Unfamiliar-user acceptance is pending.

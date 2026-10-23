# Replay timing investigation and full qualification

**Full clean-checkout qualification passed all 20 checks in 289.625 seconds.** The existing two-second Hypothesis example deadline, 300-second property-command budget, generated input bounds, seeds, repetitions and assertions were unchanged.

## Finding and narrow fix

The failing case was `replay_consistency((16, [0,0,0,0,0,0,0,0], 1))`. Its earlier five direct replays all produced correct results but took 1.70–2.33 seconds; four exceeded two seconds. Profiling identified repeated manifest decoding, validation and hashing in `native_integrity.validate_coverage` as a major cost. The instrumented profile itself took 5.165 seconds and is not an uninstrumented timing comparison.

The production change retains only the most recent validated range manifest and integrity declaration inside each invocation. Reuse requires identical encoded metadata and module context. A changed range manifest invalidates declaration reuse. String bounds, per-row fingerprints, integer module-size type, grouping, identity, stream history, coverage totals and range comparisons are still checked. No global or cross-call cache was introduced, and no property case or assertion was removed.

Three regressions check bounded repeated validation across calls, rejection of changed row metadata/context/fingerprints (including boolean module size), and revalidation when range metadata changes while the declaration stays the same. The focused reuse regression failed before the production fix. Its first expectation was corrected from one call to two because the range and integrity validation layers each validate a manifest; this preserved failure is a test expectation correction, not a relaxed correctness requirement.

## Verified results

- All 53 targeted native/replay/security tests passed.
- Ten direct repetitions of the original case passed with timings of 0.787–1.083 seconds, all below two seconds.
- All 310 Python tests passed in the clean checkout.
- All 768 Hypothesis evaluations passed in 108.421 seconds with the original limits. The normalized property script hash is unchanged (Git checkout line endings differ) and its seeded input fingerprints/evaluation counts match the earlier successful qualification.
- Both sanitizer profiles and detection controls passed. The 65-case boundary pack passed twice (130 evaluations), the separately bounded parser pilot completed 10,000 executions, and desktop/owned-fixture/stream checks passed.
- Git was clean before and after; source was unchanged during the run. Generated log hashes, both boundary-input repetitions and retained fuzz-corpus hashes were independently verified during evidence assembly.

## Preserved failures

The original full-profile Hypothesis deadline failure and its raw log remain preserved. Diagnostic setup also encountered a profiler script filename collision with Python's `profile` module and one regression command launched from the wrong directory. Both were corrected without changing application behavior. The first post-fix focused regression failed on the two-versus-one validation-call expectation described above. A targeted suite attempt then hit a sandbox temporary-file permission error; all 53 tests passed when rerun in the normal Windows session. These failures remain recorded separately from the successful qualification; none was relabeled as passing.

## Provenance and limits

Run: `run-e9136b78052d`. Snapshot commit: `027c57c644c043459ec98bd0434c4322c4808e5a`.

Normalized source fingerprint: `3760763ca9defe46d7ab69764bcfc21e8b9e0d471017d0d8ee9f051c6062d891`.

Command: `python -B scripts/qualify.py --asan --properties --libfuzzer --llvm-bin <LLVM-bin-directory>`.

The original working repository was not committed or pushed. A local snapshot was committed and cloned for verification with no pre-existing build/dependency artifacts. The same Windows host, toolchain and shared download caches were used. Results documentation/evidence were added afterward.

The full-profile acceptance gap reported in [boundary results](parser-boundary-results.md) is resolved by this run; that historical failure remains unchanged. Timings are finite same-host observations, not a guarantee under arbitrary system load or on other machines. The original broader fuzzing campaign is still incomplete; these checks do not establish exhaustive semantics, memory safety, whole-process integrity or attestation.

[Generated evidence](../evidence/replay-timing-validation.json) records the full qualification, preserved failure, measurements and artifact hashes.

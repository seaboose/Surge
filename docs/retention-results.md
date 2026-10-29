# Bounded retention results

**All 24 scenarios passed twice (48 evaluations), and all 21 checks passed from a clean checkout.** No production retention, importer, or detector change was needed. The changes add fixed defensive tests, fail-closed qualification evidence and documentation.

## Acceptance results

1. **Sample boundaries: passed.** Histories of 499/500/501 samples with 2/3/16 ranges went through the real decoder. Every append matched an independent longest-whole-group-suffix model for both count and conservative byte accounting. Group order, exact sizes and sample/eviction counters matched. The 2- and 3-range histories retained 499/500/500 samples; 16-range histories retained 54 complete samples because bytes became the tighter bound.
2. **Retention bytes and rejection: passed.** Single incoming groups and aggregate retained totals exercised 8,372,223 / 8,372,224 / 8,372,225 accounting bytes. Exact fit succeeds; aggregate overflow evicts whole groups; an oversized incoming group is refused with every previous state field unchanged. Multiple evictions, UTF-8 multibyte accounting and empty-group atomic refusal passed. These padded internal unit fixtures do not pass through the native decoder.
3. **Snapshots and replay: passed.** Snapshots taken at sample 498 stayed unchanged after subsequent appends and evictions. All nine final histories exported as JSON and JSONL, with matching conclusions and summaries. Every retained observation was No finding; eviction added exactly one Unknown health row and no Review records. All 18 saved cases across the two repetitions reopened and reproduced exact results. The largest export was 7,975,046 bytes, below the 8 MiB export acceptance limit and 16 MiB import ceiling.
4. **Import bytes: passed.** Valid whitespace-padded JSON and JSONL accepted exactly 16,777,215 and 16,777,216 bytes. Both rejected 16,777,217 bytes at the explicit size guard. This checks the byte gate, not huge-field semantics or all supported formats.
5. **Bounds and repeatability: passed.** All 48 named evaluations completed with matching input and result fingerprints between repetitions, within the unchanged 300-second retention ceiling (60.516 seconds). The evidence validator checks identities, fixed limits, metric hashes, exact accounting/import outcomes and replay status; missing, duplicated, failed or inconsistent evidence cannot qualify.
6. **Full clean qualification: passed.** All 329 Python tests (zero skips), 768 Hypothesis evaluations, native/ASan controls and tests, the 88-case parser boundary pack twice, the separate 10,000-execution bounded libFuzzer pilot, owned fixtures/streams, desktop journeys and source hygiene passed. Total elapsed time was 341.86 seconds. Git was clean before/after, source was unchanged, and no checkout environment, builds or captures were reused. Existing production files and Hypothesis limits match the preceding qualification.

## Observed retained windows

- 16 ranges, 499 samples: 54 retained, 445 evicted; 7,975,045 JSONL bytes.
- 16 ranges, 500 samples: 54 retained, 446 evicted; 7,975,045 JSONL bytes.
- 16 ranges, 501 samples: 54 retained, 447 evicted; 7,975,045 JSONL bytes.
- 2 ranges, 499 samples: 499 retained, 0 evicted; 2,930,246 JSONL bytes.
- 2 ranges, 500 samples: 500 retained, 0 evicted; 2,936,120 JSONL bytes.
- 2 ranges, 501 samples: 500 retained, 1 evicted; 2,936,675 JSONL bytes.
- 3 ranges, 499 samples: 499 retained, 0 evicted; 5,070,516 JSONL bytes.
- 3 ranges, 500 samples: 500 retained, 0 evicted; 5,080,680 JSONL bytes.
- 3 ranges, 501 samples: 500 retained, 1 evicted; 5,081,244 JSONL bytes.

These values describe the fixed fixture shape. Different valid row sizes can reach the byte budget at a different sample count. The accounting counter includes 512 bytes per row plus separators and a separate 16 KiB health reserve; it is neither actual JSON size nor a process memory/RSS ceiling.

## Failed attempts and corrections

The first standalone attempt, `retention-attempt-a5422120b1` / `retention-f0511442985d`, failed overall after completing 48 individual checks. Its exact repeatability assertion found different synthetic approval timestamps and corresponding baseline digests. Input frames, counts, replay conclusions and boundary outcomes agreed. This was a fixture determinism defect, not a demonstrated production retention failure. Its logs, report, cases, original harness and original acceptance text are preserved and hashed.

The narrow correction fixes the synthetic approval clock before creating the registry; timestamps and baseline digests remain in comparisons. The second standalone attempt, `retention-attempt-e8690f04b5`, passed in 71.406 seconds. Review also identified a potential variation in saved-case creation timestamp width; the final fixture fixes that clock before saving. No case-size failure was observed. The clean qualification uses the final fixed health/approval/case clocks. No production limit, assertion, timeout or expected boundary outcome was relaxed.

Read-only review found that the failed first report set its repeatability subfield to passed before validating comparisons. Its overall failed status and error correctly prevented qualification, and that original inconsistent subfield remains preserved. The final runner now validates a candidate report before setting success flags. The first full clean run passed on the earlier runner revision and is preserved separately; a second full clean run verifies this final reporting correction.

The 18 new evidence/report tests and 22 existing qualification tests passed together before final qualification. Two added regressions verify that a report is marked repeatable only after validation succeeds and remains incomplete when repeat fingerprints differ. Historical toolchain, UI, native fixture and Hypothesis timing attempts remain preserved in their earlier evidence; this report links their hashes without rewriting their status. Prior unresolved root-cause limits remain as previously documented.

## Reproduction and provenance

Command (one line): `python -B scripts/qualify.py --asan --properties --libfuzzer --llvm-bin <LLVM-bin-directory> --retention`.

Snapshot commit: `f84003e0b8d592ec3906e9e6321bec8709518ce1`.

Normalized source fingerprint: `2e27675292a0aa3f47a9920fae5c9fd732a5d4c84338ae60064d15819aa7598d`.

Qualification run: `run-081f380a7906`. Retention child: `retention-082483008acd`.

The original working repository was not committed or pushed. A separate local source snapshot was committed and cloned, then verified on the same Windows host with shared system toolchains/download caches. Results documentation and evidence were added after verification. Parent and child log hashes, saved-case hashes, parser binaries/corpus and boundary inputs were checked while assembling this report. Raw logs remain local because they may include machine paths.

See [acceptance criteria](retention-acceptance.md), [qualification instructions](qualification.md) and [generated evidence](../evidence/retention-validation.json).

## Remaining limitations

The original T1/T2/T3 fuzz campaign remains incomplete. These are fixed single-threaded synthetic cases, not arbitrary-history, concurrency/race, multi-hour endurance, or live 501-sample capture tests. Existing short owned-process and desktop checks are separate integration evidence.

No memory/RSS bound, every legal row size, CSV/NDJSON byte boundary, 10,000-row/64-field boundary, 64 MiB case boundary, independent-host run, held-back final variant or successful maximum relocation traversal is added here. The direct padded accounting fixtures are intentionally distinct from decoder-valid captures. Local evidence remains unsigned and forgeable by an equally privileged actor; no attestation or whole-process integrity claim follows.

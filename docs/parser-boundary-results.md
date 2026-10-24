# Bounded relocation and parser-boundary results

23 October 2026. **The 65-case deterministic boundary pack passed twice, and the 18-check native/ASan profile passed from a clean checkout in 182.578 seconds.** One synthetic fixture defect was found and corrected. The production parser was unchanged. The full 20-check profile did not pass: an existing Hypothesis case exceeded its deadline. The original T1/T2/T3 campaign remains incomplete.

## Acceptance results

- **Fixed expected results: passed.** Each repetition had 22 accepted cases and 43 expected refusals, with exact diagnostics. Positive full-parser cases checked range names, RVAs, lengths, expected bytes and executable spans. Mapping cases checked exact offsets or specified refusals. The DIR64 overlap cases used a separate eight-byte enumeration oracle over known declared intervals, not the parser's overlap routine.

- **Bounds and repeatability: passed.** 65 named cases ran twice in separate processes, 130 evaluations in this clean run. Outputs and all input hashes matched. Each process had the specified 15-second outer limit; maximum input size was 14368 bytes against the 65,536-byte cap. No extra mutation budget was introduced. Command logs remained under the existing 10 MiB cap.

- **Instrumentation: passed.** Clang ASan compilation was required; the safe probe and deliberate heap-boundary detection control passed. No unexpected sanitizer finding, exception, timeout or resource breach occurred in the successful pack. The inherited configuration disables extra MSVC string/vector container annotations for toolchain compatibility; compiler ASan remains verified.

- **Relocation reachability: passed.** The relocation-block reader executed. Every branch record at the ten selected validation conditions had both true and false counts: directory cap, directory presence, truncated block header, each of the three block-size conditions, ABSOLUTE handling, supported type, image-target bound and protected-range intersection. Counts and source coordinates are embedded in the evidence.

- **Coverage measured separately.** The deterministic pack covered 243/267 parser lines (91.01%) and 168/220 branch outcomes (76.36%). It leaves 24 lines and 52 branch outcomes uncovered. These totals do not imply full path coverage or exhaustive semantic validation.

- **Clean native-profile verification: passed; full-profile compatibility incomplete.** All 307 Python tests, native tests, MSVC ASan controls/tests, owned fixture and stream checks, desktop journeys and source hygiene passed. Git was clean before and after; source stayed unchanged throughout the run. Qualification logs, boundary inputs in both repetitions, and retained fuzz inputs were independently hash-checked when assembling this report.

The full combined-profile part of acceptance criterion 7 remains incomplete. The first clean run failed an existing Hypothesis replay deadline (2,066.97 ms against 2,000 ms) before the boundary pack. Five direct replays of the exact case `(16, [0,0,0,0,0,0,0,0], 1)` all passed correctness assertions but took 1.70–2.33 seconds, with four exceeding two seconds. This is retained as an unresolved timing limitation, not relabeled as passing. No deadline or case count was relaxed. A second fresh checkout of the identical source snapshot ran the 18-check profile without requesting Hypothesis. The new run supplies no claim of 768 completed property evaluations.

## Cases and scope

Relocation cases cover absent/zero-sized directories, ABSOLUTE padding, header-only and single-word blocks, disjoint DIR64 entries, adjacency and intersection at both declared ranges, a two-block directory, truncated header/tail, invalid block sizes, an unsupported relocation type, image-end target boundaries and wide target-address addition, unmapped directory spans, and encoded directory-size limits.

Other cases exercise structural truncation, section counts 0/96/97, executable-section counts 0/32/33, image-size header bounds, probe lengths 0/1/63/64/65, out-of-range declaration counts, and exact mapping boundaries including maximum RVA and length values. The 96-section positive uses two populated sections and empty remaining section headers; it is not a 96-populated-section layout. The 512 MiB image-size case changes a header value without allocating that image. The exact 1 MiB relocation-directory case is refused by mapping bounds; it does not establish successful maximum-size traversal.

## Preserved failed attempt and narrow correction

The first new attempt (`pilot-532b889a3a`) ran all 65 cases and reported one failure: `section_count_96`. Its first fixture layout placed the large section table over the synthetic code bytes. The parser accepted the input, but the exact-byte oracle correctly failed. The attempt stopped before the random parser pilot. Raw input files, logs, binary, source snapshot and profile remain retained and hashed; the result was not relabeled as passing.

The fixture builder was corrected to reserve sufficient header space and relocate its synthetic code/data and export RVAs consistently. No production-parser behavior or acceptance threshold changed. The corrected standalone attempt (`pilot-de337d9a11`) passed 130 evaluations and its separate 10,000-execution parser pilot. The clean checkout then repeated 130 evaluations and another 10,000 executions. These are distinct runs; the earlier failed attempt additionally executed 65 deterministic cases. Earlier [UI investigation](qualification-ui-results.md) and [toolchain/pilot failures](libfuzzer-pilot-results.md) remain preserved in their original reports.

Report assembly initially stopped on a Windows text-encoding error in the workspace-only collection utility. Its pre-fix source was retained; converting the utility to UTF-8 allowed evidence assembly and hash verification to complete. This did not change or rerun any qualification check.

## Provenance and reproduction

Successful narrower command: `python -B scripts/qualify.py --asan --libfuzzer --llvm-bin <LLVM-bin-directory>`.

The failed full-profile command additionally included `--properties`; both reports and the timing diagnostic are preserved in the evidence. Hypothesis timing remains unfinished follow-up work, rather than being silently removed from the definition of full qualification.

Snapshot commit: `e3da021e43940e3277b1e337485b5410a0d30f06`.

Normalized source fingerprint: `2712fe29352412b3879581fd9188d79633a90a15669cbecee6e795796b4202aa`.

Qualification run: `run-230222759eb2`.

The original repository was not committed or pushed. The source snapshot was locally committed and cloned without existing dependency/build artifacts; the same Windows host, portable LLVM toolchain and shared download caches were used. Result documentation and evidence were added after verification. See [acceptance criteria](parser-boundaries.md), [qualification instructions](qualification.md), and [generated evidence](../evidence/parser-boundary-validation.json).

## What this does not prove

The separately bounded mutation pilot completed 10,000 executions in this qualification; retained-corpus coverage was 227/267 lines and 176/220 branch outcomes. Its retained corpus and the deterministic pack are different workloads. Neither percentages nor counts have been combined into a claimed coverage union.

This work supplies selected relocation and boundary evidence, not the complete original boundary packs or campaign. It does not test loading generated images, applying relocations to executing code, arbitrary PE compatibility, every relocation encoding/layout, actual 1 MiB traversal, maximum export/manifest-cardinality packs, production retention limits, independent-host behavior or held-back final variants. The original campaign gates remain incomplete. No memory-safety, full semantic correctness, whole-process integrity or attestation claim follows from these finite local tests.


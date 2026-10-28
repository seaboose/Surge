# Export-count and manifest-cardinality results

**All 23 new cases passed twice, and the full 20-check qualification passed from a clean checkout in 270.344 seconds.** The expanded deterministic pack contains 88 cases and completed 176 evaluations in this run. No production parser change was needed.

## Acceptance results

- **Export-count boundaries: passed.** Function counts 0/4095/4096/4097 and name counts 0/4095/4096/4097 produced the specified accepted results or refusal diagnostics. Actual full-size arrays and unique bounded filler names are present. Positive function-boundary cases resolve the required manifest through ordinal `count - 1`; positive name-boundary cases find it in name entry `count - 1`.
- **Manifest cardinality: passed.** Counts 2/15/16 resolve every expected range, including its name, RVA, length and exact bytes. Counts 0/1/17 reject. The combined 4,096-function/4,096-name/16-range case passes. Independent byte-level inspections of all eight new positive fixtures confirmed their counts, unique names, final lookup entry and final valid ordinal, separately from the production parser.
- **Malformed boundary cases: passed.** The final requested ordinal one past the function table, three individually truncated table spans, final duplicate declaration, overlapping final range, missing final end export and dirty unused declaration at count 15 all produced their specific expected refusals. Each truncated table extends exactly one byte beyond the file-backed section.
- **Bounds and repetitions: passed.** The 23 additions comprise eight positive cases and 15 expected refusals. With the existing 65 cases, all 88 ran twice under the unchanged 100-case, 64 KiB/input and 15-second/repetition limits. The largest input was 64512 bytes. Both output and input hashes matched between repetitions. The eight new positive controls are pinned to ACCEPT in the report validator, so relabeling both expected and actual results as refusals cannot pass.
- **Instrumentation and selected conditions: passed.** Existing ASan safe/error controls passed, with no unexpected sanitizer finding, crash or timeout in the boundary pack. Both outcomes were recorded for six added Boolean conditions covering function count, name count, ordinal bounds and declaration count, alongside the ten existing relocation conditions. These are 16 branch records across 14 source-prefix groups, not a claim of complete parser coverage.
- **Measured coverage:** the deterministic pack covered 249/267 parser lines (93.26%) and 177/220 branch outcomes (80.45%). The separate fuzz-corpus coverage is retained separately in the evidence; no combined percentage is claimed.
- **Full compatibility: passed.** All 311 Python tests, 768 Hypothesis evaluations, native/ASan checks, owned fixture and stream checks, desktop journeys and source hygiene passed. The Hypothesis script's normalized contents and limits are unchanged. Git was clean before and after, and source remained unchanged during the qualification run.

## Attempts and preservation

The standalone attempt `pilot-b8aa531482` passed 176 deterministic evaluations and its separate 10,000-execution mutation pilot. The clean qualification repeated 176 evaluations and another 10,000 mutation executions under the original budgets. These are two distinct runs. No native test/build failure occurred in these new attempts. Prior toolchain, UI, fixture and Hypothesis timing failures remain retained in their historical evidence; their evidence-file hashes are linked in this report's JSON.

A separate code review checked table bounds, last-entry access, malformed-tail reachability and the complete positive-output oracle. It found no material fixture issue. Report-validation regressions also reject missing upper-limit controls, missing guard outcomes and positive controls relabeled as refusals. Log, binary/input evidence and both input repetitions were verified during report assembly.

## Reproduction and provenance

Command: `python -B scripts/qualify.py --asan --properties --libfuzzer --llvm-bin <LLVM-bin-directory>`.

Snapshot commit: `efd12c954494e66f3271ff7fd4d7e256def6dad8`.

Normalized source fingerprint: `487fef2e995cfe0799c2661cf132e32c66502c463d0962012401b6cc613014c0`.

Run: `run-78d50e799b64`.

The original repository was not committed or pushed. The candidate source was locally committed and cloned without pre-existing dependencies/build outputs. Verification used the same Windows host, toolchain and shared download caches; it is not an independent-host or fresh-OS result. Results documentation and evidence were added afterward.

See [acceptance criteria](export-cardinality.md), [qualification instructions](qualification.md) and [generated evidence](../evidence/export-cardinality-validation.json).

## Remaining limitations

The fixtures are synthetic parser-contract inputs and their export names are not ordered as a Windows loader might require. No generated image was loaded or executed. A successful lookup does not prove validation of every unused function entry, unrequested ordinal, or unrelated trailing name. The combined maximum case covers one bounded layout, not every combination or malformed encoding.

The original T1/T2/T3 campaign remains incomplete. Successful 1 MiB relocation traversal, exhaustive semantic coverage, retention-limit checks, independent-host behavior and held-back final variants remain untested. ASan and finite branch coverage do not prove memory safety, general PE compatibility, whole-process integrity or attestation.

# Bounded libFuzzer parser pilot acceptance criteria

Defined before the pilot run. This is a toolchain/parser pilot, not completion of the original T1/T2/T3 campaign.

Scope: Windows x64, production `LabImage` parser header, synthetic fixtures derived from existing owned parser tests, and in-memory bounded byte inputs. Full descriptor parsing calls `executable_ranges()` and `declared_ranges()`. No collector construction, process attachment, DLL loading, generated-code execution, registry modification or protected holdout access. Expected `std::runtime_error` parser refusals are classified; other exceptions and sanitizer failures stop the run.

Acceptance:

1. Record the compiler, libFuzzer/ASan runtime and coverage-tool versions/hashes. Build with Clang ASan, libFuzzer coverage instrumentation, and source-based coverage. Reject compilation without ASan. Confirm a safe probe exits zero and a separate deliberate heap-boundary probe produces the specific ASan diagnostic and configured nonzero exit code.
2. Known synthetic positive input resolves its two named ranges and executable span exactly. Known short/header and descriptor-invalid inputs reject. Replay controls and generated corpus twice with identical per-file classification and normalized resolved output hashes; rejecting everything cannot pass.
3. Capture baseline and final LLVM source coverage for `code_range_pe.hpp`. Each required family (constructor, executable spans, export lookup, descriptor validation, section mapping, declared range resolution, probe) must execute. Final parser branch-outcome coverage must exceed baseline by at least one outcome. Report actual line/branch totals and missing coverage; no repository-wide percentage substitutes for target evidence. Relocation logic and legacy-only layouts are not guaranteed by this small pilot.
4. Run one worker sequentially for fixed seeds 17 and 20261023. Each run stops at 5,000 executions or 30 seconds, whichever comes first, and must complete at least 1,000 executions to qualify. Inputs are at most 64 KiB; libFuzzer's RSS budget is 512 MiB and per-input timeout is 2 seconds. The wrapper enforces a 60-second outer timeout per fuzz process, a 10 MiB per-command log limit and a monitored 32 MiB corpus budget. Report libFuzzer's measured peak RSS when available; its RSS budget is not claimed as an OS-enforced private-memory cap.
5. No unexplained ASan diagnostic, crash, unexpected exception, timeout or resource-budget breach. A zero exit without libFuzzer statistics/instrumentation or coverage output is insufficient. All findings are preserved; no automatic retry, minimization campaign or threshold reduction after a failed pilot.
6. Add commands, limits, input/binary/source hashes, instrumentation results, coverage counts, corpus replay results and limitations to qualification evidence. Existing deterministic native tests remain passing. The original campaign and its unfulfilled acceptance gates remain explicitly incomplete.

Toolchain downloads are separate from campaign execution. Builds and preflight precede the two short runs. This pilot has no held-back final phase, comprehensive semantic oracle, production-size boundary pack or guarantee of every parser branch. A stable corpus replay demonstrates repeatable classification; it does not require time-bounded libFuzzer mutation discovery to be identical across runs or machines.

References: [libFuzzer](https://llvm.org/docs/LibFuzzer.html) and [Clang source coverage](https://clang.llvm.org/docs/SourceBasedCodeCoverage.html).

## Verified toolchain configuration and failure handling

The portable LLVM 23.1.4 archive is SHA-256 verified against its official release metadata. MSVC string/vector container annotations are disabled consistently to match the prebuilt libFuzzer library; compiler ASan remains enabled. These extra container-bound checks are not claimed. The retained-corpus replay driver performs normalized output formatting outside the fuzz callback. Failed builds and the observed empty-input formatting stall are preserved, not relabeled as passes. The user explicitly authorized continued toolchain resolution after that failure; limits were not raised. A later clean-checkout verification repeats the same two bounded seeds and is accounted for as another pilot run, not hidden within the first run's count.

## Subsequent deterministic boundary extension

The qualification profile now additionally requires the [bounded relocation/parser-boundary pack](parser-boundaries.md), recorded under `boundary_tests`. Its fixed cases, separate source-coverage run and two repetitions do not alter the two mutation-run budgets or close the original campaign. Historical pilot reports predate this extension and retain their original scope.

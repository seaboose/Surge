# Bounded libFuzzer pilot results

23 October 2026. **The bounded parser pilot passed; all 20 combined qualification steps passed from a clean checkout in 361.844 seconds.** The verified pilot ran 10,000 libFuzzer executions with no unexpected sanitizer finding or timeout. The original T1/T2/T3 campaign remains incomplete.

## Acceptance results

- **Toolchain and instrumentation: passed.** Portable LLVM 23.1.4 was verified against the official archive SHA-256. The report hashes compiler, linker, coverage tools, runtime libraries, binaries and parser/harness source. The ASan safe probe exited zero; the deliberate heap-boundary probe produced the required heap-buffer-overflow diagnostic and exit 86. A small caught-exception libFuzzer control passed before parser testing. Actual libFuzzer counters and PC tables were present.
- **Known parser controls: passed.** The existing synthetic two-range layout resolved its exact names, RVAs, byte sequences and executable span. Short/header and invalid-descriptor inputs rejected. Both existing deterministic parser test executables passed with this Clang/ASan configuration.
- **Bounded execution: passed.** Seeds 17 and 20261023 each completed 5,000 executions under unchanged 30-second caps, a two-second input timeout and a 60-second outer process timeout. Inputs were capped at 64 KiB; logs at 10 MiB and corpus storage at 32 MiB. Highest libFuzzer-reported peak RSS was 85 MiB against its 512 MiB setting. This is not an OS-enforced private-memory measurement or cap.
- **Coverage progress: passed.** On `code_range_pe.hpp`, covered lines increased from 205/267 to 227/267 (85.02%). Covered branch outcomes increased from 123/220 to 176/220 (80.00%). Constructor, executable spans, export lookup, descriptor validation, section mapping, declared-range resolution and probe functions all executed.
- **Corpus replay: passed.** All 111 retained inputs replayed twice with identical classifications and normalized output. 1 were accepted; 110 were expected refusals. Corpus size was 309809 bytes, with largest retained input 5120 bytes. The configured 64 KiB cap is not a claim that the whole size range was tested.
- **Compatibility and clean checkout: passed.** All 304 Python tests, 768 bounded Hypothesis evaluations, the separate MSVC ASan profile, native CTests, demo replays, owned fixture/stream checks and desktop journeys passed. Git was clean before and after; source bytes were unchanged during the run.

Coverage comes from replaying the retained corpus through a separate source-instrumented parser driver. It does not measure every discarded mutation or every production component. Raw source-coverage exports, profiles, corpus files, classifications and logs are retained locally; their hashes are in the generated evidence. No generated binary was loaded or executed. Only the test programs ran; parser inputs remained data.

## Failures preserved and resolved

1. **Initial compiler preflight failed:** clang-cl required `-fsanitize=fuzzer`, not the MSVC-style slash spelling. No fuzz inputs ran in that attempt.
2. **Link preflight failed:** the prebuilt libFuzzer library used different MSVC string annotations. String/vector container annotations were disabled consistently for this pilot, retaining compiler ASan. Extra STL container-bound detection is therefore not claimed. No parser behavior or refusal rule changed.
3. **First parser fuzz attempt failed:** libFuzzer timed out on its empty startup input after two seconds, before consuming the seed corpus. The timeout artifact and binaries/logs were preserved. Normal-session replay reproduced the timeout in the fuzzer while the separate replay driver rejected the same empty input promptly. Minimal plain, source-profile and caught-exception controls passed. Diagnostic tracing reached the parser refusal, then stalled during post-refusal result formatting.
4. **Narrow harness correction:** result formatting was removed from the fuzz callback and kept in the separate replay driver. The production parser stayed unchanged. The same limits then passed both 5,000-execution seeds and corpus replay. This resolves the observed harness path; the deeper runtime/library cause of the formatting stall was not established.
5. **First clean-checkout qualification failed:** the existing `test_match_keyboard_scroll_and_warning_visible_at_minimum_size` UI test expected match index 1 after F3 but observed 0. The failed qualification report and Python-suite log are preserved and hashed in the evidence. It stopped before the parser pilot. The unchanged test passed alone in 0.757 seconds; that isolated retry was observed in the session but has no separately retained log. Focus sensitivity is a hypothesis; the cause remains unresolved and no UI fix is claimed.
6. **Second clean-checkout qualification failed:** corpus monitoring encountered a removed file between enumeration and its size query. The first seed log records 5,000 completed executions, but the runner aborted before the second seed, final coverage and repeatability checks. Its raw report, logs and binaries remain preserved. A narrow runner fix ignores only vanished entries while continuing to propagate other filesystem errors; a regression test verifies both behaviors. No parser change or increased resource limit was needed.
7. **Third clean-checkout verification:** the integrated runner repeated the bounded pilot in a new checkout and produced the result above. Both successful pilot runs are recorded: 10,000 executions during the corrected working-tree run and 10,000 during clean verification. The failed startup attempt reported one execution; the failed corpus-monitor attempt additionally logged 5,000 executions; fixed-input and tiny runtime-control diagnostics were separate. No earlier failure was relabeled as passing, and no timeout/coverage threshold was weakened.

The focused runner tests initially encountered five temporary-directory permission errors in the sandbox; all 19 passed in a normal session. This environment failure was not a parser finding.

Early preflight reports predated per-file source hashing; their command logs, binaries and failure artifacts remain preserved. The final qualified run includes source hashes. Toolchain extraction also required a workspace-local zstandard decoder because Windows' built-in archive extractor could not handle the official archive's compression window. LLVM was not installed system-wide.

## Provenance and reproduction

Run `python -B scripts/qualify.py --libfuzzer --llvm-bin <LLVM-bin-directory>`. Add `--asan --properties` for the combined 20-step profile. The supplied LLVM directory must contain the compiler, linker and coverage tools with matching runtimes. Current discovery expects the documented Visual Studio 2022 Build Tools/Windows SDK layout.

See [acceptance criteria](libfuzzer-pilot.md), [qualification instructions](qualification.md) and [generated evidence](../evidence/libfuzzer-pilot-validation.json).

Snapshot commit: `c4e46c0f84a0f6ae257f6bf27e0c169e93bcb065`.

Normalized source fingerprint: `75021a2f1f9c40f98185143acad157191de5203561dfd886f068983b78701fa3`.

Run: `run-529dbbc11b2b`. The original repository was not committed or pushed. Implementation files match the tested snapshot; results documentation/evidence were added afterward. This is a clean checkout on the same Windows host with shared download caches and toolchain, not a fresh OS or independent-host result.

## What remains incomplete

The retained corpus did not reach the relocation-block reader; 40 parser lines and 44 branch outcomes remain uncovered. Function-entry reachability does not imply all internal branches ran. The accepted corpus cases and known positive seed do not constitute a comprehensive independent semantic oracle for arbitrary layouts.

This pilot does not supply the original max-dimension and relocation boundary packs, all intended branch families, production retention-limit testing, held-back final variants or a full native/Python campaign. Original campaign gates 2–6 remain incomplete. The report's original campaign flag remains false while the separate pilot evidence records the native executions that actually occurred. Local evidence is unsigned, not attestation; no memory-safety proof, whole-process integrity or arbitrary-PE compatibility claim is made.

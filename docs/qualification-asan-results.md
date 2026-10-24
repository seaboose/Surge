# AddressSanitizer qualification results

23 October 2026. **All 17 qualification checks passed from a clean local checkout in 153.328 seconds.** This includes the three existing native tests under AddressSanitizer and 298 Python tests with zero skips. The T1/T2/T3 fuzzing campaign remains incomplete and was not run.

## Instrumentation acceptance criteria

- **Compiler instrumentation: passed.** All owned C++ translation units compiled with `/fsanitize=address`, `/Zi` and a forced header that rejects compilation without `__SANITIZE_ADDRESS__`. The build used Release x64, MSVC 19.44.35229.0 and the runtime paired with that compiler.
- **Safe control: passed.** The isolated test probe exited zero and printed its completion marker.
- **Detection control: passed.** The same probe deliberately wrote one integer beyond its own small heap allocation. ASan reported `heap-buffer-overflow` and exited 86, without reaching the completion marker. The runner requires this specific diagnostic and exit code; generic crashes, missing runtimes and timeouts do not qualify. This expected failure belongs only to the test probe, which is not linked into the application.
- **Existing native tests: passed.** `bounded_pe_parser`, `versioned_manifest_parser` and `collector_without_scenarios` all passed under ASan with no reported sanitizer errors.
- **Qualification and provenance: passed.** All 17 steps passed. Source bytes were unchanged; Git was clean before and after. The checkout began without its Python environment, desktop dependencies/build, native build, captures or baseline registry. The ASan build was also new in this fresh checkout.

The generated evidence records each command, exit code, timing, log hash, source hash, runtime options and instrumented binary/runtime hashes. The standard native suite, five demo replays, owned fixture/stream checks and both desktop journeys also passed in this run. Those journeys use the normal build; only the three native CTests and probe are claimed as executed under ASan.

## Reproduce and identify the run

Run `python -B scripts/qualify.py --asan` from the Surge root with the documented Windows prerequisites. See [qualification instructions](qualification.md) and [generated evidence](../evidence/qualification-asan-validation.json).

Local snapshot commit: `c69aef6fcc968b33d6befbdc1ae00bbcc7c85c20`.

Normalized source fingerprint: `2c5e2d9477d7be555d33f0efc5eb34c654fc935c702fb2e82df6d013eaa38878`.

Run identifier: `run-54dbeb60e8d0`. Original source was not committed or pushed. Result prose and evidence were added after the tested snapshot; implementation files match that snapshot. This is a new checkout on the same host, with download caches reused, not a fresh OS or second-machine result. Duration is test-run time, not an application performance benchmark.

## Attempts and remaining limitations

An initial restricted-session run passed 298 Python tests and ordinary native/fixture/stream checks, then Electron failed to launch. Later checks, including ASan, were not run in that attempt. ASan steps were then placed before desktop journeys. A normal-session working-tree run passed all 17 checks in 136.063 seconds, followed by a fresh-checkout attempt that stopped at ASan configuration: the deeply nested build path caused MSVC file-tracker FTK1011 errors. The ASan build directory was shortened to `native/build-asan` and excluded from Git/source packaging. Another new checkout then produced the successful result above. Earlier failures remain in the evidence. The tests did not disable Electron's sandbox or change approval settings.

No application memory error was found by these existing instrumented tests. No application logic fix was needed. This is not a memory-safety proof: unexecuted paths, handwritten assembly and external libraries are not covered by the C++ instrumentation. Leak detection, optional stack-use-after-return instrumentation, other native configurations, generated-input coverage and long-duration performance tests were not run. Symbolization was disabled for bounded diagnostic verification; debug information was generated.

The original fuzzing gates 2–6 remain incomplete. This work adds limited native memory-error evidence and does not resume the blocked harnesses, provide coverage-guided testing, independent generated oracles, production-limit boundary campaigns or held-back variants. Local evidence remains unsigned and is not attestation.

# Defensive qualification

The desktop step includes the bounded [case-library recovery campaign](case-recovery-acceptance.md):
48 owned scenarios repeated twice, fresh-process inspection, fixed budgets and
retained fault evidence. Hosted artifacts include its hidden staging residue so
the complete evidence manifests can be checked after download. See the
[local recovery results](case-recovery-results.md) and
[hosted recovery acceptance criteria](hosted-recovery-acceptance.md).

The hosted Windows `test` job requires the full 21-step profile described in
[hosted acceptance criteria](hosted-deep-qualification.md), using a pinned portable
LLVM toolchain. `scripts/check_deep_qualification.py` checks a clean starting
checkout, packages dependent evidence and verifies the complete result. Its
`--verify <artifact-folder>` mode verifies a downloaded bundle without depending
on the original machine paths. Failed attempts remain failed and retain partial
evidence. Unfamiliar-tester acceptance remains pending; T1/T2/T3 remain incomplete.

From the Surge root in a Windows graphical session, run:

```powershell
python -B scripts/qualify.py
```

Prerequisites: Python 3.11+ with Tcl/Tk, Node 22.12+, pnpm 11.25.0, CMake 3.25+, and Visual Studio C++ Build Tools with x64 tools and the Windows SDK. Setup uses the pinned dependency lockfile and may download packages. The command creates or reuses the checkout's `.venv` and installed desktop dependencies; it does not claim a clean install unless those were absent before the run.

The runner invokes the existing setup, builds the owned native fixtures, then runs the full Python suite, native CTests, five demo replays, existing owned-fixture and short stream checks, desktop boundary checks, native desktop replay and continuous desktop journey, and source hygiene. Fixture captures are regenerated before desktop replay. Test approvals stay in their isolated fixture/session registries; the runner does not approve an operator baseline.

This command assembles existing tests. It does not generate new adversarial inputs, resume the blocked fuzz harnesses, attach to external applications, or expand collection scope.

## Report and acceptance criteria

Every run creates `verification/qualification/run-<id>/report.json` and `report.md`, with raw command logs alongside. The console prints the report path. JSON includes command status, elapsed time, exit codes, timeouts, log hashes, Git identity, source hashes and machine/software details. Raw logs can contain local paths and should remain private. Reports are written before prerequisites and updated after each check; a power loss, forcibly killed runner or unwritable disk can still interrupt reporting.

Qualification passes only when:

1. All 12 standard steps exit successfully (plus five ASan checks when requested, with the expected probe exit described below). Launch errors, timeouts and nonzero exits stop the run; remaining checks stay `not_run`.
2. The Python suite executes tests with zero skips, and at least the three expected native CTests execute successfully.
3. The publishable source files and their bytes remain unchanged during the checks.
4. A generated report names the exact evaluated source and explicitly keeps T1/T2/T3 fuzzing incomplete and unexecuted.

For a **clean-checkout verification**, additionally record that the Git worktree is clean before and after, and that `.venv`, `desktop/node_modules`, `desktop/dist`, `native/build`, `native/captures`, and `native/baselines.json` were absent before starting. A clean source checkout on the same host may reuse system package-download caches; that is not a fresh operating system or independent host.

The total execution ceiling is 30 minutes. Setup has ten minutes; native configure/build and the Python suite have five minutes each; other checks have one to five minutes, always constrained by the remaining total budget. Logs are monitored against 20 MiB per command. On a timeout, cancellation or log-budget failure, cleanup targets only the launched process tree. These are execution safeguards, not measured application performance budgets. The runner does not disable Electron's sandbox or change machine approval settings.

## Interpreting results

`qualification_status: passed` means the listed existing checks passed on the recorded source and host. It does not mean the unfinished fuzzing milestone passed. The runner always records the latter separately as incomplete, with T1, T2 and T3 not run. The default profile supplies no sanitizer evidence. Neither profile supplies generated-oracle, reachability or held-back fuzzing evidence.

The qualification is also a subset of full CI: the wider UI/evaluation/accessibility journeys, native build-configuration matrix, archived-evaluation reproduction and long performance campaign are outside this command. Existing results for those checks retain their original provenance.

The runner's own tests cover failure propagation, missing/empty/skipped tests, launch errors, total and per-command deadlines, cancellation cleanup, and exclusion of generated temporary files from source packaging. Run them with `python -B -m unittest -v test_qualification`.

## Optional AddressSanitizer profile

Run `python -B scripts/qualify.py --asan` to add five bounded checks: instrumented configure/build, safe probe, detection probe and the three existing native CTests. Builds live under ignored `native/build-asan`; Release x64 is the qualified configuration. The selected MSVC installation must include its matching ASan runtime. No extra dependency is downloaded for ASan.

Acceptance requires every C++ translation unit to compile with `__SANITIZE_ADDRESS__` defined, the safe probe to exit zero with its completion marker, the deliberate test-only heap-boundary fault to exit 86 with the specific AddressSanitizer heap-buffer-overflow diagnostic and without completion, and all three existing CTests to pass without unexpected sanitizer diagnostics. A generic crash, missing DLL, timeout or empty result is a failure. The expected probe failure is explicitly recorded, not concealed as a successful process exit. This probe is separate from the application and never linked into its fixtures.

The report records the profile, runtime settings, binary/runtime hashes and individual results. Compiler/environment overrides and sanitizer dump/debugger overrides are cleared for child processes. ASan checks run before desktop journeys, so a later desktop failure does not erase their evidence. Overall qualification still fails if any required check fails.

This is existing-test memory-error instrumentation, not fuzzing or a memory-safety proof. Handwritten assembly is not instrumented; leak detection and the optional stack-use-after-return mode are not enabled. Unexecuted paths, external libraries and other build configurations are not qualified. T1/T2/T3 and their original acceptance gates remain incomplete.

Build settings follow [Microsoft's MSVC AddressSanitizer reference](https://learn.microsoft.com/en-us/cpp/sanitizers/asan-building).

## Optional Hypothesis property profile

Run `python -B scripts/qualify.py --properties`, or combine with `--asan`. Two additional steps install pinned, wheel-only dependencies into the checkout environment and run the bounded synthetic contract suite. The bootstrap Python must provide pip with its `--python` option. Existing default tests remain dependency-free. The property process has a five-minute timeout within the existing overall budget.

[Property acceptance criteria](property-qualification.md) define the three contracts, bounds, seeds and repeatability checks. A nonzero process exit, missing/short/malformed evidence, or mismatched repeat fingerprints fails qualification. The JSON report embeds the full property summary under the `properties` check. All 19 steps must pass when both optional profiles are requested. The deliberate ASan probe remains the only expected nonzero process exit.

These generated checks are explicitly a subset. The original fuzzing campaign remains incomplete and its completion flag stays false; that does not mean no generated Python examples ran in the optional property profile.

## Optional bounded libFuzzer pilot

Run `python -B scripts/qualify.py --libfuzzer --llvm-bin <LLVM-bin-directory>`; add `--asan --properties` for all 20 steps. The caller supplies LLVM; this runner does not download or install toolchains. The tested combination is LLVM 23.1.4, Visual Studio 2022 Build Tools, MSVC 14.44 and SDK 10.0.26100.0 on Windows x64. The pilot currently discovers that Build Tools layout; other installations need explicit adaptation.

The [pilot acceptance criteria](libfuzzer-pilot.md) fix bounds, controls and required coverage. Pilot logs, corpus and coverage data remain in the ignored qualification directory; the parent report embeds its evidence. LLVM's prebuilt fuzzer library requires matching disabled MSVC string/vector container annotations in this configuration. Compiler ASan remains enabled and is verified with the heap-error probe; this pilot does not claim those additional container-bound checks.

Full source coverage is measured by replaying the retained corpus through a separate instrumented parser driver. It is not coverage of every discarded mutation. The original campaign remains incomplete even when this pilot passes. Known harness/build failures are preserved separately in the milestone evidence.

## Deterministic relocation and parser-boundary pack

The optional `--libfuzzer --llvm-bin <directory>` profile also runs a fixed 88-case boundary pack twice under Clang ASan and source coverage, before the separate mutation runs. Each repetition has a 15-second outer limit and each input is at most 64 KiB. Exact expectations, repeatability and both outcomes of the selected relocation guards are required; missing evidence fails qualification. The combined profile still has 20 top-level checks. See [acceptance criteria and limits](parser-boundaries.md). Coverage for this pack is reported separately from retained fuzz-corpus coverage.

The pack includes 23 export-count and manifest-cardinality cases. See [their acceptance criteria](export-cardinality.md). Exact upper-limit positives use real tables and tail lookups, not only oversized header values.

## Optional bounded retention profile

Add `--retention` to run the [fixed retention acceptance cases](retention-acceptance.md).
The full command is `python -B scripts/qualify.py --asan --properties --libfuzzer
--llvm-bin <LLVM-bin-directory> --retention` (on one line). This adds one check,
for 21 top-level checks when all profiles are selected. Its existing five-minute
ceiling fits within the unchanged 30-minute qualification limit.

The 24 named cases run twice at the actual 500-sample, 8 MiB retention, and
16 MiB import limits. Decoder-valid histories verify whole-sample retention,
snapshot stability, JSON/JSONL conclusions and saved-case replay. Separate
padded internal fixtures exercise exact accounting boundaries; valid whitespace
padding exercises the import byte guard. Conservative retained-byte accounting
includes row and health reserves and is not a process memory measurement.

The report embeds per-case results and repeat fingerprints. Missing, failed,
duplicate, inconsistent or nonrepeatable evidence fails qualification. Each
attempt also retains an incrementally written report and saved synthetic cases
under an ignored `verification/qualification/retention-<id>` directory. On an
external timeout, a child case may remain `running`; the parent records failure
and does not treat remaining checks as completed. This profile does not finish
the original fuzz campaign, expand the collection target, or establish
long-duration/concurrent retention correctness.

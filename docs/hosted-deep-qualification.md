# Hosted deeper qualification acceptance

Criteria defined before this milestone's execution, 23 October 2026. Scope is the existing owned Surge fixtures and bounded qualification profile. Unfamiliar-tester acceptance remains pending; the original broader T1/T2/T3 fuzzing campaign remains incomplete.

1. Run the existing full 21-step profile on a clean committed Windows checkout with ASan, Hypothesis, the bounded libFuzzer parser pilot and fixed boundary pack, and retention enabled. Require the existing step/total/input/time/log/resource limits unchanged. Missing, skipped, timed-out or failed required checks cannot qualify.
2. Bootstrap the previously verified LLVM toolchain from its official source with a pinned archive digest. Record compiler/runtime/coverage versions and hashes; retain bootstrap failure evidence. Do not modify the system toolchain or bypass missing instrumentation.
3. Require safe/fault sanitizer controls, all native tests, bounded property results, positive and negative parser controls, measured target coverage and replay, and fixed retention cases. A command's zero exit alone is insufficient. Validate the generated evidence and each required profile flag and step.
4. Bind evidence to the tested commit and source manifest. Check clean Git state and source identity before/after; package portable reports, logs, source and dependent evidence with byte lengths and SHA-256 hashes. Download the hosted artifact and independently verify its contents and source identity.
5. Make deeper qualification a non-optional step of the already-required `test` job, with no continue-on-error or conditional bypass. Preserve `First-use release check` and its existing checks. Keep the draft PR unmerged and administrator enforcement off. Any aggregate job timeout adjustment allows toolchain preparation and the additional existing profile; it must not expand individual campaign limits.
6. Exercise an owned controlled command failure on a separate disposable probe branch. The required `test` job must fail, later work must remain unexecuted, and the always-upload step must retain partial reports, completed/failed/not_run states and logs. Retrieve and verify that artifact. Never merge the probe branch or treat its intentional failure as a release pass.
7. Preserve every unsuccessful attempt and distinguish environment, bootstrap, harness, application and deliberate-control failures. Do not automatically retry failed fuzz runs or reduce thresholds. Any corrective candidate is a separately recorded attempt.

Verification establishes one hosted Windows environment and the existing bounded profile. It does not establish unfamiliar-user comprehension, real native-dialog acceptance, broader platform compatibility, hostile-host trust, multi-hour endurance, or completion of the original fuzzing campaign. A saved required-check policy does not constitute an attempted blocked merge.

## Implementation and evidence

The required `test` job runs runner-contract tests, acquires LLVM, then calls
`scripts/check_deep_qualification.py` before the existing UI and compatibility
checks. The independent `First-use release check` is retained. The 60-minute job
ceiling includes bootstrap and both existing suites; qualification keeps its
1,800-second total limit and every original per-check and campaign budget.

`scripts/setup_qualification_llvm.ps1` downloads the official LLVM 23.1.4 portable
`.tar.xz` archive, pinned to SHA-256
`854bffcfc84528e0ee92490ff5c178920abd358a79c3e98f053e41e3e8e4c6d2`.
It uses standard-library extraction into a fresh external directory, verifies
official release metadata, and compares the four tools and three runtime/library
files against the previously verified `.tar.zst` toolchain. Bootstrap has its own
600-second outer limit. Compiler discovery uses Microsoft's installed-toolchain
locator so the existing parser pilot supports hosted Visual Studio editions.

The `deeper-qualification-<tested-sha>-<attempt>` artifact contains the source
package and manifest, qualification report and logs, dependent parser/property/
retention evidence, sanitizer artifacts, bootstrap provenance and a file manifest.
Verify an extracted bundle with
`python -B scripts/check_deep_qualification.py --verify <deep-artifacts-folder>`.
The verifier reads archived evidence; it does not execute archived binaries.

Only a disposable probe workflow substitutes
`scripts/probe_deep_qualification_failure.py` for the normal wrapper. It lets real
setup and native configuration complete, then substitutes a harmless owned
command that exits 73 for the native build. The other 18 checks must remain
`not_run`. A verified expected failure still exits nonzero. This probe establishes
ordinary supervised-command failure propagation, not cancellation, runner loss,
disk exhaustion or artifact-service availability.

The workflow retains uploaded evidence for 30 days. Local retrieved originals and
supplemental milestone results preserve the tested identities beyond that window.
Source identities distinguish pushed heads from PR merge checkouts. Failed
attempts are not deleted or reported as passes.

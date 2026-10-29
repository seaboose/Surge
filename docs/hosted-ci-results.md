# Hosted Windows qualification results — 2026-10-23

**Hosted candidate qualification: passed. Unfamiliar-tester acceptance: pending. Broader T1/T2/T3 fuzzing: unfinished.**

Candidate: `0200edcd34c6be047ff3aecd0fe23fdb08ec7e90`, branch `qualification/hosted-windows-20261023`, [draft PR #1](https://github.com/seaboose/Surge/pull/1). Nothing was merged and branch protection was not changed. The original development worktree and index were preserved; the candidate was committed in a separate checkout.

The candidate includes accumulated application changes and their qualification evidence (125 changed files), rather than a workflow-only patch. The milestone's narrow source change excludes scratch `work` directories from release packages, with a regression test. No hosted application failure required a fix and no limits were relaxed.

## Acceptance results

Criteria were committed before hosted execution in `docs/hosted-ci-acceptance.md`.

1. **Same committed candidate, both jobs: passed.** [Push run 40012255206](https://github.com/seaboose/Surge/actions/runs/40012255206), attempt 1: `test` and `First-use release check` succeeded. [PR run 40012280629](https://github.com/seaboose/Surge/actions/runs/40012280629), attempt 1: both jobs also succeeded. The PR actually checked out merge commit `a950e38fba3c8caba25b154ca8b85f664e096308`; its tree matches the candidate exactly.
2. **Artifact retrieval and evidence inspection: passed.** Both first-use ZIPs were downloaded. All 16 release steps passed in each report; clean Git state and unchanged source were recorded. Retrieved UI results were revalidated: replay 8, unapproved sample 5, approved sample 6, library 9, deletion 3, saved-case flow 10. These are check groups, not exhaustive security coverage. Human acceptance remains pending in both reports.
3. **Source and log identity: passed.** All 248 source entries in the push artifact match the committed Git tree, byte-for-byte after Git's configured Windows checkout line-ending conversions where applicable. The PR source manifest matches the push manifest exactly. Source archive/report fingerprints and all 16 step-log fingerprints in each artifact were checked. ZIP download hashes match GitHub's artifact digests.
4. **Failure handling: passed.** Disposable branch `qualification/hosted-failure-probe-20261023`, commit `85050823440a3ccc51844c24e45c56105878dc93`, [run 40012311078](https://github.com/seaboose/Surge/actions/runs/40012311078), attempt 1, contains one intentional assertion failure. The first-use job failed, its release step was skipped, and artifact upload succeeded. Downloaded log contains `SURGE_HOSTED_FAILURE_PROBE_20261023`, with 12 tests and exactly one failure. The broader test job also failed because it discovered that same deliberate test. The probe branch is retained for evidence and must not be merged.
5. **Attempt preservation and scope: passed, with the raw-log limits below.** All three hosted runs, their job logs, retrieved ZIPs, metadata, and verification results are retained locally. No hosted runs were erased or rerun over the evidence.

## Checks and environment

- Hosted Windows Server 2025, image `windows-2025-vs2026`, version `20261021.278.1`; Python 3.12.10, Node 24, pnpm 11.25.0.
- Local runner unit checks: 33 passed after rerunning outside the restricted temporary-directory sandbox. Hosted first-use unit checks: 11 passed.
- Push first-use release execution: 93.828 seconds, within unchanged limits, using initially empty task-local dependency caches and a newly extracted source package.
- Broader Python suite: 372 tests, initially 8 skipped because native fixtures were not built. All eight were explicitly matched to later successful results in the 12-test post-build native session/window suite. Do not report the first invocation as 372 executed passes.
- Native CTest: 3 passed. Desktop boundary/runtime suite: 10 passed, zero skipped. Hosted jobs also passed native live/stream and compatibility checks, published evaluation reproduction, UI journeys, accessibility/scaling, replay, formatting, and source hygiene.

## Artifact identity

- Push artifact ID `12525924731`; SHA-256 `335d0e6148434b54283b5763e33c1db983c29662f95aacedf55fbd7b3a7b1684`.
- PR artifact ID `12525849938`; SHA-256 `668478eabd0dc28cb678a8f78c582ed882ccfd76eaa6a8fd30ffa81ed4b12f10`.
- Failure artifact ID `12526089013`; SHA-256 `70aa889a9faaae569d0b78b05149d053f1b36c7502df87f07ebd785bfa9ec0af`.
- Push source ZIP SHA-256 `d5a990e67f8e9f0f1972e23ff86a87fa1f18f62605a9d9a1de18d0eb0d25e0ee`.
- Source manifest SHA-256 `8d45caaf3086804a083bb6b0dd7a25a714fcd1f6249fedbf0647227c868f1f3e`.

GitHub artifacts have 30-day retention (currently expire November 22, 2026); local copies preserve them beyond that window.

## Failed preparation and inspection attempts

These are separate from successful candidate CI and the intentional hosted failure probe:

- Initial sandboxed clone: networking initialization failure; isolated clone then succeeded outside that sandbox.
- Initial local unit invocation: 33 tests, 14 temporary-directory permission errors; 33 passed outside that sandbox. No assertions were weakened.
- Initial push: GitHub GH007 email privacy rejection. The unpublished commit was amended with the repository owner's GitHub no-reply identity; account privacy settings were unchanged. The rejected commit ID was retained locally.
- Initial supplemental artifact inspection: `KeyError: 'mode'` because saved-flow evidence uses a different valid schema. The inspection helper was corrected to handle that schema, then both artifacts passed. Product code and evidence were unchanged.

The first clone/unit/push/inspection failures are preserved as transcript output and explicit attempt summaries, not complete original on-disk raw logs. The successful local retry and all hosted job logs are preserved as files. The initial run-list snapshot also used insufficient JSON serialization depth; complete final per-run metadata replaced it as the authoritative record while retaining the initial snapshot.

## Remaining limitations

Unfamiliar-tester acceptance is still pending: automation cannot establish uncoached comprehension. Normal launch scripts and real native file-dialog interaction remain outside these UI wrappers. Hosted checks cover this Windows image and the owned sample, not a broad OS/hardware matrix or arbitrary protected processes.

This milestone did not rerun ASan, Hypothesis, the bounded libFuzzer pilot, retention qualification, or the full qualification command. Earlier evidence remains separate; the original broader fuzzing campaign is unfinished. The failure probe verifies assertion-failure propagation and artifact retention, not every infrastructure outage, cancellation, timeout, or mid-run crash. It failed before release execution, so it does not prove hosted partial-release-report recovery. Branch protection was not audited or configured, so a green workflow is not proof that merging requires these checks.

This results document and its summary evidence were produced after the immutable tested commit. They are supplemental records, not files claimed to be inside that tested source archive.

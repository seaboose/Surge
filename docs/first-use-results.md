# First-use acceptance — 23 October 2026

**Automated checks passed; independent first-use acceptance remains pending.** Criteria were fixed before execution in [first-use-acceptance.md](first-use-acceptance.md). This is a fresh application extraction/cache/profile test on the existing Windows host, not a fresh OS or an unfamiliar participant study.

## Changes made

Corrected the linked native/demo guides: Try Demo always uses v2, its exact build needs explicit approval, approval freezes per capture session, and saved files open through Case library. Removed references to the obsolete interface build selector and v1-first setup instructions. v1 remains available internally.

Added `desktop/first-use.test.cjs` with replay, unapproved and approved modes. Each creates an isolated profile and retains screenshots, assertions, failures and renderer-error observations. Ten existing JavaScript files were normalized from CRLF to LF after the source ZIP failed formatting; no executable logic changed. All 153 previously qualified code files remain identical after newline normalization to snapshot `d16eabad50b76cd6faeb08911e61b50c594318b5`.

## Tested candidate and environment

- Source archive SHA-256: `4b0c7a359e97c543e220c03d053cef2bd7adf701ee612b87776f3aa6ee30a358`.
- Manifest SHA-256: `02c7a0ed1b5bbf1858e8275a87c38eab4e136d97428af3a7140f818745f2d91e`.
- 243 source files, extracted into a new path containing spaces. Every extracted file matched the manifest before and after checks. No existing environment, dependencies/build, native build/captures/registry or user cases were carried in.
- Python 3.12.14, Node 24.19.0, pnpm 11.25.0; existing CMake/MSVC/Windows SDK. Python/Node/pnpm/CMake versions and OS are in the structured evidence; compiler/SDK identification is retained in the native configure log.
- Initially empty task-local pnpm and Electron caches. pnpm reported 21 downloaded packages and zero reused; Electron populated its own new cache. The host's pnpm supply-chain policy cache was reused. This is not absence of every possible system/network cache.
- Setup used the documented explicit-Python option and completed in **11.031 seconds**. Native configure/build took **3.312/12.547 seconds**. These are observed timings with prerequisites already installed, not promised install times or application benchmarks.

## Acceptance results

M1 — Passed. Exact package identity, file verification and absence of initial generated artifacts recorded.

M2 — Passed within isolated same-host scope. Documented setup succeeded using verified new package/Electron caches; a new desktop profile opened. Prerequisite installation, the normal launcher and another Windows installation remain untested.

M3 — Passed. Before native compilation, missing collector produced the actionable build message. All five published cases imported and opened with their declared visible verdicts: approved (4 normal), unapproved (4 review), changed code (1 review/3 normal), unreadable (1 unknown/3 normal), outside coverage (4 normal despite its documented blind spot). Original file hashes remained unchanged.

M4 — Passed. Native build and all three CTests passed. Before approval, live observations required review and no approved-match claim appeared. Explicit approval applied only to the extracted v2 build; subsequent complete observations had no findings and visible rows. Short captures stopped and opened the final snapshot. Baseline hash is retained in the report.

M5 — Passed for scripted workflows. Save/reopen preserved the evidence and explicitly excluded a live-integrity claim. Existing library, deletion and saved-flow journeys covered rename, export/import, cancellation, deletion, original preservation and restart. New first-use journeys recorded no uncaught renderer errors. A post-test process inspection found zero desktop/worker/sample processes tied to this extraction. This inspection does not claim absence of unrelated processes.

M6 — Passed. All **15 final runner steps** passed in **52.108 seconds of summed step execution**, with unchanged source and per-step timing/log hashes. Logs and screenshots remain in `work/first-use-3`, with complete prior attempts in `work/first-use-1` and `work/first-use-2`. Published structured evidence: [first-use-validation.json](../evidence/first-use-validation.json).

H1-H4 — **Pending. No unfamiliar tester participated.** Automated evidence does not complete these criteria.

## Preserved failed attempts

1. Initial setup/replay succeeded, but the cache-isolation criterion failed: unsupported environment settings left pnpm using the host store. Its step report alone says passed; the separately preserved cache assessment overrides that for M2. This attempt is not accepted as empty-cache evidence.
2. A fresh extraction with supported `PNPM_CONFIG_STORE_DIR` and `electron_config_cache` settings passed all functional steps. The additional formatting step failed for ten existing CRLF files. That overall report remains failed. Git had normalized these files in the earlier clean checkout; a raw source ZIP had not.
3. After only CRLF-to-LF normalization, a new archive, extraction and empty caches passed all 15 steps. Both source archive identities and the exact normalization hashes are retained. No time limit, expected outcome or formatting rule was relaxed.

Environment discovery found no running Docker service; the sandboxed WSL query was denied. No disposable Windows guest was established. A sandboxed process query was also denied; the later authorized read-only process inspection succeeded. These are environment limitations, not Surge correctness failures.

## What an unfamiliar tester must still do

Use the exact tested source package and [participant task sheet](first-use-tester.md), with only its README and linked guides. On an independent Windows environment, install prerequisites, run the normal Start-Surge.cmd launcher, use actual file dialogs, and complete the demo/case lifecycle without coaching. Observe for up to 45 minutes, recording time, wrong turns, assistance and failures. Preserve the first attempt before any assisted retry.

Ask neutral questions after use: what was measured; what no findings establishes; what unavailable evidence means; why outside-coverage changes may be missed; whether reopened evidence is live; what deletion removes. All six concepts must be substantively correct for H3. A developer, automated agent or simulated persona does not satisfy unfamiliar-user acceptance.

The desktop tests launch the real application through an isolated Electron entry wrapper. Native dialogs are substituted with known owned-fixture paths, and one legacy deletion test uses a bridge call to create an unrelated test case. These are useful automated checks, not a manual usability study. Renderer-error monitoring is explicit in the three new modes, not uniform across all reused tests.

## Limits and provenance

No new full 21-step qualification, ASan, Hypothesis/libFuzzer campaign, ten-minute performance measurement, long-duration run or complete CI matrix was executed in this milestone. Earlier results keep their original identity. Original T1/T2/T3 fuzzing remains incomplete. Local unsigned evidence remains unauthenticated against a hostile host; changes outside measured ranges or between samples can be missed.

The exact tested archive includes criteria and participant tasks. This report, structured evidence and README results link were added after testing and are not inside that immutable archive. No application code changed after the tests. No release was pushed or published.

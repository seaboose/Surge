# Combined opening and local case library results

23 October 2026. Implemented in the existing working tree. This milestone is separate from the earlier clean-checkout qualification and unfinished fuzzing campaign.

## Delivered behavior

- The opening combines cyan signal art with stacked Import evidence, Case library, and Try Demo actions. It uses only Surge and a concise purpose description. At narrow widths the decorative art is hidden and actions remain reachable by scrolling and keyboard.
- Save case (including Ctrl+S) asks for a name and creates a new, independent snapshot in the local library. Existing snapshots are never overwritten. Each contains the original embedded evidence, analysis settings, and results.
- Case library is available at startup and from every investigation view. It lists names and save dates and supports open, rename, delete, import, and export.
- Rename changes display metadata only. Delete asks for native confirmation and removes only the chosen managed snapshot. External evidence, portable case files, other cases, and the in-memory investigation remain unchanged.
- Import copies a portable case and verifies the managed copy before publishing it. Open recomputes and verifies through the existing engine. Invalid cases do not replace the workspace.
- Export case produces a portable file; existing destinations are not overwritten. Export case file in Findings exports the current investigation directly. Open case file in the library inspects an external case without adding it; Import case adds a managed copy.
- Managed cases are stored under Electron's per-user data directory, in `cases/<opaque UUID>/`. Display names do not become filesystem paths. The renderer cannot supply paths; external locations come from native dialogs. Linked managed files and invalid identifiers are rejected.

Recorded check summary and source hashes: [case-library-validation.json](../evidence/case-library-validation.json).

## Acceptance results

All seven criteria in [case-library-acceptance.md](case-library-acceptance.md) passed the checks performed. No claim is made about untested fault conditions.

1. Opening: dedicated short real-desktop check passed; checked keyboard focus, three actions, 720×540 layout, and screenshots. Final nine-check integration reran it successfully.
2. Save: focused check passed for distinct snapshots, invalid names, and failed-save publication. Real desktop saved a named case. Worker test verifies saving does not mutate the active workspace and rejects stale revisions.
3. Open/persistence: focused reopen and invalid-ID checks passed. Desktop restarted with the same isolated profile and reopened a saved case. Actual engine verification exercised.
4. Rename: focused and real-desktop checks passed; case bytes remained identical.
5. Delete: focused and real-desktop checks passed. Cancellation retained the case; confirmation deleted it while source fixture bytes, portable export, neighboring case, and active findings survived.
6. Import/export: focused and real-desktop checks passed for verified copies, byte-identical export, re-import, invalid import, failed export cleanup, and no-overwrite behavior.
7. Boundary: desktop tests rejected renderer-selected paths and traversal IDs; unit test rejected hard-linked managed evidence. These are selected defensive checks, not an exhaustive hostile-filesystem review.

## Completed checks

- Library storage: 6 tests passed. Short checks were run after save/open, rename, delete, and import/export implementation.
- Desktop boundary/runtime plus library storage: 10 tests passed.
- Dedicated opening check: passed.
- Library desktop integration: 9 checks passed, including desktop restart. Final artifacts: `verification/electron/case-library-EDmoTI/` (results and screenshots). Earlier successful runs remain in their own directories.
- Existing Python discovery suite: 321 tests passed in 66.647 seconds. This run started before the new library-specific test was added. The new worker test passed separately; this is not a claim that one 322-test run occurred.
- Existing desktop parity: 16 checks passed.
- Existing evaluation: 4 checks passed.
- Published demo replay: all 5 case fixtures passed.
- Existing owned-native desktop checks: passed automatic mapping, changed bytes, approved update, and unavailable evidence.
- Existing continuous collection journey: passed start, stable inspect, stop, export/reopen, restart, keyboard/text scaling, and shutdown checks.
- Existing accessibility journey: 24 display/text/zoom combinations and navigation/focus checks passed.
- Existing usability journey, stage 7: passed.
- Final worker-module regression: 15 tests passed, including the new library test.
- Final JavaScript/CSS formatting check passed.
- Renderer build passed. JavaScript/CSS formatting completed; Python formatting completed outside the sandbox.

Existing regression journeys now use Export case file when they are testing the portable-file workflow, and enter the Case library to open external files. New library saving is covered by its dedicated integration test; it is not substituted silently for the earlier portable-file checks.

## Preserved failed attempts

- Initial storage run: both save/open tests failed with Windows `EPERM` when renaming a staging directory beneath the sandbox temporary directory. The same tests passed outside the sandbox, without weakening the assertions or changing the implementation. Rename/delete checks subsequently used the same isolated, unsandboxed test environment.
- Initial renderer build was invoked from the workspace root and failed with `Could not resolve "src/main.jsx"`. Re-running from `Surge/desktop`, the build's expected working directory, succeeded.
- Two sandboxed Black formatter attempts produced no output and were interrupted (exit 1), including a single-worker attempt. The single-worker command completed outside the sandbox. They are not counted as successful checks.
- Two read-only searches used unsupported PowerShell/glob syntax; corrected searches succeeded. These were inspection errors, not test failures.

## Limits and next checks

This work used one Windows host, isolated test profiles, and existing installed dependencies/native builds. It did not repeat clean-checkout qualification, ASan, libFuzzer, Hypothesis, prolonged performance workloads, archived benchmark journeys, or the unfinished broader fuzzing campaign. The previous qualification's source fingerprint does not describe these new changes.

There is no multi-user sharing, cloud synchronization, search/paging, automatic migration of external saved files, overwrite/update-in-place, or undo after confirmed deletion. Save intentionally creates a new snapshot each time. Large-library performance and low-disk conditions have not been tested.

Publishing uses a staging directory and rename; metadata rename uses a temporary file. Power-loss durability and concurrent malicious filesystem modification have not been tested. Interrupted operations can leave hidden `.pending-*` or `.deleted-*` folders; incomplete deletion cleanup is reported. Deletion is ordinary local file removal, not secure erasure. The library is not a defense against a compromised local account or operating system.

## Why the demo is a separate program

Try Demo already leads to live collection: Surge launches its fixed, owned native program and observes configured ranges in that running process. The separate process supplies real process/build identity, fresh samples, and collection lifecycle behavior. A sample data file can demonstrate parsing, analysis, and navigation, but cannot demonstrate fresh process observations.

Recommended next UX step: offer Explore sample evidence for an immediate tour and Live demo capture for the existing owned-process collector. If only three opening actions are desired, retain Try Demo and let it offer those two choices. Do not advertise general Live capture until supported collection targets and their configuration are actually implemented. No collection scope was broadened in this milestone.

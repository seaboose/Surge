# Real Windows launcher acceptance

Criteria recorded before execution. This is a bounded startup/shutdown check of the unmodified `Start-Surge.cmd` → `Start-Surge.ps1` → Electron entry path. It supplements the existing UI journeys, which launch through test entry modules.

## Acceptance criteria

- **L1 — Isolated preconditions.** Use only this source checkout or an identified first-use extraction, with installed dependencies and a built renderer. Record source hashes. The ordinary `%APPDATA%/surge-desktop` profile must not exist, and no process may already use this extraction's Electron or Python executable. Refuse execution if either condition fails; never rename, replace, clear, or open an existing user profile. An ordinary developer workstation may therefore be unsuitable.
- **L2 — Real entry path.** Invoke the unchanged `Start-Surge.cmd` from its application directory. Its command must exit successfully. Deliberately inherit `ELECTRON_RUN_AS_NODE=1`; successful graphical startup establishes that the documented launcher clears this conflicting flag. Do not patch Electron, substitute an entry module, or enable a debugging port.
- **L3 — Bounded startup.** Within 30 seconds, observe exactly one main Electron process from the extraction, a visible top-level window titled `Surge — Development`, a renderer descendant, and the extraction's Python analysis worker. The exact title identifies the current ordinary source launch; product and test-session titles do not qualify. They must remain present for three seconds. The newly created ordinary profile must exist. These observations establish startup/liveness, not the correctness or readability of the rendered screen.
- **L4 — Owned cleanup.** Close only that process's verified window. Within 15 seconds the observed application processes must exit. Put the launcher and its descendants in a Windows job object before allowing launch, so error/timeout cleanup can terminate only test-owned descendants. Any forced cleanup fails graceful-shutdown acceptance.
- **L5 — Evidence preservation.** Keep a uniquely named report and launcher log for every success, refusal, or failure. Record the application source identity, observed processes/window, timing, and cleanup outcome. Source bytes must remain unchanged. Total execution is bounded to 90 seconds, apart from interpreter startup; the calling CI step supplies an additional outer timeout.

## Running

Run `python -B scripts/check_launcher.py --application-root <extracted-Surge-directory>` on a fresh Windows CI account after setup. The report is written under the invoking repository's `verification/qualification/launcher-<unique-id>/artifacts/` directory. The extracted source may contain spaces in its path. The runner intentionally refuses a workstation with an existing ordinary Surge profile.

The runner resolves the ordinary application-data folder with the Windows known-folder API; changing `APPDATA` is not treated as proof of isolation. It does not select files, use a live capture, alter a baseline, or touch third-party software. The only window action is closing its own identified application window. Its ordinary profile is retained for diagnosis rather than deleted.

## Local checks before hosted execution

On 23 October 2026, three runner contract tests passed: existing-profile refusal preserves original bytes and does not start a process; missing setup/unexpected application identity cannot pass preconditions; and readiness requires an owned window, worker, and renderer ancestry. The first unit attempt was denied access to sandbox temporary directories and remains preserved as `verification/qualification/launcher-unit-attempt-1.log`; the unchanged tests passed outside that restriction in `launcher-unit-attempt-2.log`.

A separate bounded Win32 primitive check assigned a sleeping helper to the job object and verified that closing the job ended it before its 30-second sleep completed. The owned-path process query also completed successfully (`launcher-win32-attempt-1.log`). This checks the cleanup primitive, not complete Electron shutdown.

The real local invocation correctly refused the existing ordinary Surge profile before launching anything. Its failed/precondition report is retained in `verification/qualification/launcher-d40f2268705b/artifacts/results.json` and `launcher-local-refusal-attempt-1.log`. Therefore real entry-path startup/shutdown is **not locally verified**; it requires the fresh hosted account. No user profile was moved, cleared, or opened. Black was unavailable in the bootstrap interpreter, so a Black formatting check was not completed; this is separate from the three passing functional contract tests.

## Remaining acceptance

Real native file-dialog navigation, save/overwrite/cancel behavior, accessibility of those dialogs, screen readability, and user comprehension remain untested by this smoke check. The existing automated case journeys substitute selected dialog results. H1–H4 unfamiliar-tester acceptance remains **pending** until an actual unfamiliar participant completes it; neither hosted CI nor this launcher check can satisfy it. The original broader T1/T2/T3 fuzzing campaign is also unaffected.

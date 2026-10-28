# Survive durable work checkpoint

## Current workflow coordination — October 26, 2026

The user explicitly disconnected this project from the separate Astra audit chat.
Do not send updates to that chat or resume its earlier reset-warning coordination.
Historical coordination statements below are superseded by this instruction.

## Standalone packaging checkpoint — October 26, 2026

The current game source supports a trusted external saved-data directory through
`SurvivePaths`. Developer mode retains the existing Saved location. The successful
editor rebuild is `Saved/Verification/build-20261026-151239-503-5df05a95`; all four
native checks passed at `engine-automation-20261026-151534-950-f5116170`.

The initial standalone Development build at
`Saved/Standalone/20261026T220109Z-f2154613` demonstrated packaging, but revealed
an unnecessary Development trace listener. It is not the final candidate. The
standalone package now targets Shipping with the supported study drivers retained
and runtime visual components replacing debug-only drawing. Final build and
acceptance receipts under the root verification folder identify the qualified
game manifest. Source, debug symbols, tests, editor and crash-reporter executables
are excluded from the distributable game folder.

Final Shipping game: `Saved/Standalone/20261026T221649Z-115c9419`, manifest SHA256
`3a52e5fbc1ca2856a5a5d9fecba222eed61174adfe3efd49881038ef7b2b3d5f`.
The 28 October standalone smoke passed a complete 60-second practice recording,
external saved data, immutable payload, package/Windows-only loaded modules and
no owned TCP/UDP endpoints at the two sampled times. Its receipt is
`Saved/Verification/standalone-20261028T163435Z-53886269/result.json`.

The combined builder accepts this attempt using `--survive-build`. The immutable
application payload and writable user data are separate. See root
`docs/standalone-demo.md` and `docs/runtime-release-scope.md`. Combined acceptance
evidence is under root `verification/survive-standalone-20261026`; only a passing
report for an exact ZIP qualifies that package. The earlier focused-layout and
editor-only checks below remain historical. Human and unfamiliar-user testing
remain deferred; automated verification trials are not human comparison data.

## Focused-layout checkpoint — October 26, 2026

Play, Record, Review, Explain and Export now show dedicated views while preserving
selection and unsaved report state. Review has a compact expandable summary,
resizable replay/evidence panes, overview/detail timeline ranges and counted
event clusters. Optional diagnostics and technical details expand on demand;
missing-data and source-integrity warnings remain visible. The learning map is
root `docs/code-map.md`; runtime/development package scope is documented in
`docs/runtime-release-scope.md`. No source/history was deleted.

Actual rendered-game UI automation completed both previously outstanding stop
checks: F10 stopped capture at 32.112 seconds and the HUD mouse button at 15.616
seconds. Both owned games continued to authentic 60-second completion and exited
normally. Exact partial prefixes stayed unchanged and Unknown. These were labelled
scripted practice controls, not human comparison data or unfamiliar-user testing.
Evidence: root `verification/survive-layout-20261026`; see its validation report
for final regression results. No game, detector, telemetry adapter or profile
changes were required for this layout iteration. The compiled module below remains
the current one.

## Prior five-step workflow checkpoint

The gameplay-to-report workflow now has a five-step navigation bar, separate game
and recorder clocks, a direct post-game review handoff, linked exact-event markers,
replay playback, session summaries, pinned evidence attachment and export readiness.
The game HUD's recorder status/control channel is separate from gameplay telemetry;
F10 stops the recorder only. See root `docs/survive-workflow.md` and
`verification/survive-flow-20261026T1513` for this iteration's validation evidence.
Native build and final validation identifiers are recorded in that evidence folder;
the older compiled-module identifiers below describe their historical checkpoints.

- Current compiled module: `Saved/Verification/build-20261026-092831-554-e64d493b`.
- All three native tests passed at `engine-automation-20261026-092937-633-0683d1ec`.
- Rendered scripted practice completed 60 seconds and retained 2,090 exact rows.
- An independently labelled headless control stopped recording at 5.216 seconds;
  the game continued another 54.784 seconds and completed normally. The partial
  prefix remained unchanged and Unknown. Native stop-file production and the real
  recorder protocol were tested; a physical F10/click pass was not completed
  because active desktop focus changed.

## Latest integration checkpoint - October 26, 2026, 13:22 UTC

The user authorized the Survive recording/study integration into Surge. Source
desktop is built and opens through the root `Start-Surge.cmd` → Survive sessions.
Human, Scripted, Mixed and speed-control trials use fixed owned-game launch paths.
Recording controls, linked timeline/replay/ratio graph/raw inspector, external
labels, saved verification and bounded comparison batches are implemented.

- Current compiled module: `Saved/Verification/build-20261026-061109-969-ec872022`.
  Final two native tests passed at `engine-automation-20261026-062029-248-ab36d8ec`.
- Root `verification/survive-live-20261026T124212Z` preserves: 534 Python tests
  run successfully (9 skips), 66 telemetry tests, 23 desktop safety/recovery
  tests, 19 controlled-renderer checks and 10 actual-service renderer checks.
- Root `verification/survive-engine-study-20261026T131211Z-a5ec6045/report.json`
  records four complete real-engine practice controls. Review counts: scripted
  practice 0, mixed headless 0, speed probe 94, scripted reference 0. Exact raw
  bytes, seq300 lookup and runtime session associations all passed.
- A rendered mixed practice also completed with 0 Review; desktop automation
  supplied a right-click after handoff (seq1383 at40.1603s). This is verification,
  not human baseline data. Its report and HUD image are in the root evidence folder.
- The first live trial exposed a Windows writer/read sharing conflict. Both game
  telemetry and study-journal appends now allow readers. The failed prefix and
  original failure report remain preserved, unavailable for clean comparisons.
- All nine earlier pilot streams still produce identical derived bytes and full
  Surge results; original files, detector rules and profile bytes are unchanged.
- Source recovery archives are separate from personal captures. Study data stays
  in Saved/Telemetry, Saved/SurgeRecordings, Saved/StudyActions and Saved/StudyTrials;
  those folders are excluded from source packaging. See the root collection and
  implementation-review documents for limits and the next human collection steps.

No human study or held-out accuracy claim has been produced. No freeze was made
on the user's behalf. Live findings remain Pending until the authentic run_end
and final adapter pass; local hashes verify consistency, not client attestation.
The Astra audit reports no disruptive work planned and will warn before resets.
Its existing package-review/process changes and backups were preserved. No git
commit, publication, system tuning or third-party game interaction was performed.

## Prior playable-prototype checkpoint - superseded by integration above

The user resumed work. Survive is now playable locally with `Play-Survive.cmd`
(practice Q 4s/E 12s) or `Play-Reference.cmd` (Q 16s/E 300s). Both use the compiled UE5.8.4
module. Source changes require a rebuild; do not infer the current build from
older failed attempts below.

- Current successful build: `Saved/Verification/build-20261026-033609-142-299e6d87`.
  It records module and source-manifest hashes. C++/UHT pass; the native run at
  `engine-automation-20261026-034435-051-2e3bd1e4` reports both Survive tests Success.
- Final Python suite: **66 tests pass**, retained in
  `Saved/Verification/offline-final-20261026-044713-128/python-tests.log`. Shared
  native math previously passed 227 assertions; unchanged math was not rerun.
- The nine-run, three-seed real automated development pilot is complete. Review:
  `telemetry/local/development-pilot-review-20261026T112755Z-88b998ed`. All nine
  raw/context/replay bundles validate and actual Surge cases reopen identically.
  Per seed: nominal 0 Review/45 Unknown; probe 94 Review/43 Unknown; fresh-restoration
  baseline 0 Review/45 Unknown. No unambiguous probe Review lies outside its logged
  control window. This is not held-out accuracy evidence; control windows include
  idle time and restoration starts a fresh process at 335.
- Reference profile review:
  `telemetry/local/reference-profile-review-20261026T112658Z-f440d796`. Two accepted
  dashes, one blink and five cooldown denials support implemented 16/300 behavior;
  exact thresholds and a 300-second blink regrant were not exercised.
- Rendered single-click/key review:
  `telemetry/local/rendered-input-review-20261026T101323Z-dbb35d38`. Root observed
  left/middle rejection and RMB/S/Q/E/R. S there followed arrival. Separate
  `input-probe-review-20261026T103748Z-9c2d227e` demonstrates engine-injected holding,
  S during motion, fresh-press resumption and Q clearing the held latch.
- Final focus review: `telemetry/local/final-focus-review-20261026T104839Z-e567dcfb`.
  Application/Slate deactivation clears held input while injected RMB is down;
  reactivation leaves it cleared. The full 20.115s observation completes, with no
  fresh press or automatic resumption. Physical sustained holding, fresh-press
  recovery after this reactivation and all input edge cases remain unproved.
- Current descriptive summary is v2, model `nominal-walk-v2`; see
  `docs/opportunity-model.md`. This corrects descriptive opportunity math without
  changing detector limits/features or profile bytes. Historical pilot analysis
  remains bound to its frozen inputs; do not silently overwrite older bundles.
  Reanalysis: `telemetry/local/opportunity-v2-reanalysis-20261026T115100Z-b6a76d5c/report.md`. All nine derived streams and
  actual Surge conclusions remain identical; original artifacts are untouched.
- Final completion/archive record: [Saved/Verification/completion-20261026T115303Z/result.json](Saved/Verification/completion-20261026T115303Z/result.json).
  It records the exact new source-only archive and completion checks. Future
  independent recovery ZIPs: `python scripts/save_source_archive.py`. Captures
  and reports remain under Saved and telemetry/local; the pilot frozen ZIP separately
  retains its original compiled module.

Continue to coordinate with the Astra audit in “Restore safe backup files” before
heavy work or disruptions. That chat agreed to warn before a reset/interruption
and wait for saved/stopped work. This task did not authorize Windows tuning,
installations, restarts or Riot-process interaction. The latest audit update reported no disruptive work planned and retained that
advance-warning agreement. Preserve originals, backups,
Surge core, hooks and CI; no commit/push/publication was performed here.

Use `docs/verification-2026-10-26.md` for retained evidence and historical failures.
Human studies, held-out seeds, synchronized client cue/input measurements, full
camera/map/FPS measurement and exact League comparison remain future work.

## Historical continuation notes - superseded

Everything below records earlier stages. Old pause instructions, missing-build
claims and test counts are historical; the current checkpoint above takes priority.

## RESUMED OCTOBER 26, 2026

The user explicitly resumed work, superseding the restart pause below. Coordinate
with the active Astra audit in “Restore safe backup files” before builds/heavy
tests; that chat has been asked to warn this chat before disruptive operations.
This chat does not authorize Windows tuning, restarts, installations or Riot
process interaction. Engine registration is still empty as of the resume check.
Registration alone is not a command-line build gate: see the actual attempt below.
Source edits can continue; retain frequent checkpoints and do not assume old
helper processes survived the reboot. The saved pause record remains historical.

Latest Oct26 milestone:

- NATIVE BUILD SUCCEEDED on the next continuation. Current checks can see the
  engine target source. A fresh attempt reached a real project V5/default-setting
  mismatch; both targets now use supported V7 + Unreal5_8 include order, without
  overriding engine/shared-build validation. Build exit0, UHT passed, all16 actions
  passed in98.63s; source fingerprints matched. Exact evidence:
  Saved/Verification/build-20261026-022447-431-8b95bc91. Earlier missing-rules notes
  below are historical and superseded. Native automation is currently being run;
  no gameplay/physical input success is claimed yet. Respect audit warnings.
- V3-only dash displacement/duration maxima and descriptive run-quality/command
  latency context are integrated. Full53-test Python suite passes;23 numeric
  source/profile settings plus terrain/ID still agree. Historical v1/v2 and
  profile bytes are unchanged. See docs/dash-evidence.md and quality-metrics.md.
  Primary design/protocol now describe the current335-based v3 project concisely;
  original placeholder-era documents are preserved as *-v2-history.md.
- Paired mobility/attack replay showcase is saved at telemetry/local/
  synthetic-mobility-showcase-20261026T091943Z-38d5f113: legal0 Review/58 Unknown,
  altered dash3 Review/52 Unknown, exact Surge case reopen matches,0 audit issues.
  These are authored coordinate fixtures, never Unreal capture. Prior090807 replay browser
  checks14 pass, owned browser closed; Saved/Verification/showcase-browser-20261026-0210.
- scripts/run-engine-checks.ps1 is ready for bounded native Automation/Smoke/
  SpeedProbe runs after a real build. Syntax and missing-module preflight guard
  passed; no editor launched. Finite request/capture guards are saved in C++ but
  remain uncompiled like the rest of the wrappers.
- Latest quality summary also includes accepted S stops and Q/E grants as a
  separate action-timing view; move-only command timing remains unchanged. Grants
  do not prove execution, a dodge or human reaction time. Denials/late actions are
  excluded and overlap/prior movement context is retained.
- Recovery source ZIPs under Saved/Verification/source-checkpoint-* are reopened
  byte-for-byte and hash-manifested. They preserve owned source/config/profile/
  tests/docs/licenses; external engine/media/captures and unrelated work are excluded.
- Actual installed UnrealBuildTool was run with a bounded project-only build,
  at most4 parallel actions, no engine changes or remote build executor. It failed
  before project C++: engine UE5Rules.dll cannot supply UnrealEditor target rules;
  Engine/Source/UnrealEditor.Target.cs is absent. Exact attempt, exit8 and logs:
  Saved/Verification/build-20261026-015422-241-20fad5f4. A prior restricted attempt
  failed on the normal UBT cache permission. Both owned process trees exited.
  No engine install/repair was attempted; do not work around the engine failure
  by overriding shared-build validation. Build runner now uses structural tool
  checks and records registration without making it a sufficient blocker.
- A shared engine-independent C++ math header now drives native pathfinding,
  dash distance/timing, relative projectile clearance and capture budget checks.
  Arena rendering and navigation use the same rectangle/extent constants.
  Portable tests/runner are authored under portable/ and scripts/check-portable.ps1.
  They subsequently compiled/ran after the audit explicitly cleared its quiet
  window:227 checks passed with MSVC C++17 /W4 /WX. See portable/README.md and
  Saved/Verification/portable-20261026-014304-942-0e8955d9 for exact evidence.
- Audit coordination update: its automated Practice Tool check stopped, but the
  game was confirmed closed and the resource window explicitly cleared. Small
  tests are permitted; no performance benchmarking was launched here. Continue
  honoring any later interruption/measurement warning from the coordinator.

- Offline replay exporter/template/tests are complete. The full portable suite
  passes33 tests; browser replay passed19 checks and closed owned helpers.
- Optional analyze_v3 --replay binds exact replay/source/profile bytes and
  exporter/template fingerprints in the final bundle manifest.
- Two explicitly synthetic examples are preserved under telemetry/local, plus
  Surge case exports that reopen with identical results. Nominal:1800 No finding;
  coordinate-speed change:450 Review/1350 No finding. No actual Unreal capture.
- Native capture-limit shutdown now preserves partial status and terminal byte
  reserve, with Recording/saved/failed/limit status visible in the HUD. Source
  fixes reviewed, not compiled or playtested.
- Official LucianE/LuxQ clips were located from Riot pages, downloaded, sampled
  and visually inspected. Supplementary observations are saved in
  docs/calibration/video-inspection-2026-10-26.md; numeric profiles unchanged.
- Active Astra audit has advanced to authorized reversible per-user settings.
  It excludes all Surge/Survive/toolchain/backup paths and will warn before
  disruptive changes or benchmark windows. No conflicting desktop UI, installer,
  Unreal build or long-running helper is active from this chat.
- Source/profile agreement remains23 numeric settings plus terrain flag/ID.
  First successful Unreal build/playtest remains pending installed engine rules;
  the real failed build attempt is not a source/runtime success claim.

Use docs/verification-2026-10-26.md for current checks. Historical pause notes and
older counts below are retained for provenance and are superseded by this section.

Updated October 25, 2026. User authorized sustained implementation while asleep.
Saved source files are the recovery boundary; do not depend on live processes.

## PAUSED FOR REQUESTED WINDOWS RESTART

The user explicitly requested saving/pausing this chat before a Microsoft Defender
Offline restart. Do not resume project work until the user explicitly resumes it.
No restart was initiated by this chat. All active workers were interrupted and
asked to save/close only their own helper processes.

Latest verified portable suite: **24 tests passed**. Source/profile agreement:
23 numeric settings, terrain flag and profile ID passed. Unreal remains unbuilt
and unplayed because engine registration/finalization was incomplete. No installer
or build was launched by this chat. No unsaved Unreal editor session exists here.

The offline v3 replay exporter under telemetry/ may be partially authored at the
pause boundary; inspect its files/tests before using. The latest calibrated inline
preview is complete and browser-checked, separate from Unreal. Additional Lucian
E/Lux Q video calibration was interrupted; only saved frame evidence counts.

Final worker pause confirmation: render_replay.py is saved (9705 bytes), but
replay-template.html and test_replay_export.py were not created. Exporter is
incomplete/untested. Extra Lucian/Lux video inspection had not started. Both
workers report no unsaved app state or known running helpers; prior headless
browsers closed normally. A final global process inventory could not be obtained
because CIM access is unavailable, so no unknown process was terminated.

On resumption: inspect the final worker pause notes, check engine setup state,
verify the replay exporter's saved work, run appropriate checks, then continue.
Do not assume old in-flight shell/browser/download jobs survived a restart.

## Current work

Latest durable milestone:

- Reference profiles saved in profiles/ with exact-source hashes and per-value
  confidence. Official W video frames were inspected; cue-to-flash0.75–0.90 s is
  a visual bound, not server/input timing.
- Source now has runtime arena/HUD/restart, direct server obstacle routing,
  separate41/65/50 radii, walk335, dash200–425@1350, Flash-style400, Lux-style
 1200/radius70/range1300, candidate circle250/.75. Practice/reference CDs separate.
- V3 writer/adapter/audit/bundle implemented. 22 synthetic Python checks passed;
  exact profile snapshots, explicit expected policy and gap/geometry checks tested.
- Calibrated browser concept passed movement/ability/control/replay checks and
  retains bounded60 Hz snapshots. It is not Unreal runtime evidence.
- Native automation and opt-in smoke/speed-probe source are authored but unrun.
- Engine is still unregistered with Pending install metadata; build wrapper
  scripts/build-local.ps1 refuses incomplete setup. No installer/reboot was run.

Read README.md and docs/telemetry-v3.md first. New offline v3 replay exporter is
being completed under telemetry/. Legacy bullets below describe the starting work.

- Researching a versioned Lucian movement/dash + Flash blink reference profile,
  Lux Q and Xerath W threat values; provenance/confidence must remain explicit.
- Unreal worker owns Source, Config, Content, scripts and project metadata.
- Main worker owns telemetry adapters, replay/analysis, checkpoint and docs.
- Preview worker will update concept behavior after the profile contract freezes.

## Safeguards

All work stays inside unreal/SurgeMovementLab or the existing thread preview.
Do not change Surge core, backups/_Recovery, hooks or CI; no push/merge/publish.
No Riot process/Vanguard interaction. No installations or reboot. Standard reviewed
builds are authorized if setup is complete. Keep failed attempts and logs.

## Verification status

Existing v1/v2 suite: 13 synthetic tests passed before this follow-up. Unreal
compilation and playtesting not yet verified. Setup status last read: UE5.8.4
finalizing, Visual Studio installed, restart requested. Confirm actual state before
building. New reference values and v3 schema must not be silently applied to v2.

## Next checkpoint

1. Freeze source-backed profile and explicit unit conversion.
2. Agree v3 extra fields with game writer; preserve v1/v2 replay.
3. Implement profile-based movement/radii/timing and bounded run controls.
4. Add replay/exposure/coverage metrics and external manifest/fingerprints.
5. Build and run owned-game checks if engine is ready; otherwise retain exact
   blockers and keep improving portable analysis/tests.

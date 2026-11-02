# Survive verification - October 26, 2026

This is a historical development report. Paths under `Saved/Verification/` and
`telemetry/local/` identify local receipts and captures, which are not included
in this public repository. These results have not been rerun for publication.

## Verified milestone at this snapshot

Survive is locally playable through `Play-Survive.cmd` or `Play-Reference.cmd`.
The UE5.8.4 C++/UHT build passes, both native tests report Success, and the final
Python regression run passes **66 tests**. Native shared math retains its earlier
227-assertion pass. These checks establish this prototype's behavior, not League
engine parity, human dodging or independent detection accuracy.

Current build: `Saved/Verification/build-20261026-033609-142-299e6d87`, with module
and source-manifest fingerprints. Current native automation:
`Saved/Verification/engine-automation-20261026-034435-051-2e3bd1e4` reports Success
for `Survive.Attacks.SeedIndependence` and `Survive.Movement.FixedArenaPaths`.
Source/profile agreement passes 23 numeric settings plus profile ID and terrain
policy; the current build's 25 recorded inputs and module remain unchanged.
Final Python log: `Saved/Verification/offline-final-20261026-044713-128/python-tests.log`.
The local final completion/archive record
(`Saved/Verification/completion-20261026T115303Z/result.json`)
retains the exact source-only archive path and completion checks. Captures/reports
remain separate; the historical pilot frozen ZIP includes its original module.

## Actual development pilot

The independent nine-run review
(`telemetry/local/development-pilot-review-20261026T112755Z-88b998ed/report.md`)
checks seeds 1337/2027/4242 across three fresh-process conditions. All raw/result/
invocation/profile/module/frozen-input identities bind; nine contexts, replay
bundles and actual Surge cases validate and reopen. Each run retains1800 samples.

| Condition | Runs | Review | Unknown | No finding |
| --- | ---: | ---: | ---: | ---: |
| Nominal baseline | 3 | 0 | 135 | 5415 |
| Controlled speed change | 3 | 282 | 129 | 5133 |
| Fresh restoration baseline | 3 | 0 | 135 | 5415 |

All geometry audits have 0 issues. No probe Review is unambiguously outside the
actual external action window with six-decimal timestamp rounding retained.
The windows contain 34.301s of eligible idle intervals across 45s of changed-speed
settings; these are not independently labeled positive intervals. Same-seed
shape/aim patterns, projectile origins and recorded random targets match, while
aimed coordinates/times can differ. Restoration means a fresh process at 335,
not demonstrated persistence from the preceding process. No held-out seeds ran.

The current descriptive summary is `survive-run-summary-v2`, opportunity model
`nominal-walk-v2`; [model documentation](opportunity-model.md) states its geometric
assumptions and deprecated aliases. This changes descriptive math, not detector
features or profile bytes. Older bundles and frozen pilot inputs remain intact.
The completed v2 reanalysis
(`telemetry/local/opportunity-v2-reanalysis-20261026T115100Z-b6a76d5c/report.md`)
checks all nine derived streams byte-for-byte and identical actual Surge
conclusions; 108 original artifacts remain unchanged. It makes 104 previously
boolean opportunity results explicitly unavailable outside the model domain.
Two new full baseline/probe bundles retain v2 summaries, replays and contexts.

## Input, focus and reference mode

The rendered input review
(`telemetry/local/rendered-input-review-20261026T101323Z-dbb35d38/report.md`)
retains automated desktop clicks/keys and two captures. Left/middle produced no
movement; RMB moved, Q/E executed and R created a new round. S was recorded after
arrival, so that first check did not prove stopping motion.

The engine-input probe
(`telemetry/local/input-probe-review-20261026T103748Z-9c2d227e/report.md`)
then demonstrates S during sampled movement, 41 stationary samples before a fresh
press, resumption and Q clearing held input. Injected hold commands averaged
9.23/9.00Hz, with 0.1000-0.1167s intervals. Engine-injected held keys are distinct
from automated desktop input and physical human holding. The first focus probe showed
natural key clearing but stale viewport focus; it ended before its requested 20s.

The final application-focus review
(`telemetry/local/final-focus-review-20261026T104839Z-e567dcfb/report.md`)
binds the corrected build. Deactivation at probe time 6.930683s records Slate
inactive, viewport still focused, and held 1-to-0 while RMB remains down.
Reactivation at 15.265047s keeps held 0; `focus_observation_finished` occurs at
20.115446s. No fresh press was supplied and no new commands resume. The earlier
accepted goal can finish independently of steering; this run does not prove
movement during inactive focus. Physical holding and all focus edge cases remain
unverified. A 0.416667s sample gap remains explicit rather than fabricated away.

The reference cooldown review
(`telemetry/local/reference-profile-review-20261026T112658Z-f440d796/report.md`)
verifies explicit profile/flag/context agreement: 0 Review/23 Unknown/1800 No finding,
with two dash grants, one blink and five cooldown denials consistent with 16/300.
Exact readiness boundaries and a 300-second blink regrant remain untested.

Observed Survive medians include walk 335, dash 1350 and projectile 1200 units/s;
blinks travel 400 at one simulation timestamp. The earlier 306-unit dash has an
intended 425-unit end payload and ends beside the radius 41-expanded obstacle;
its full projected endpoint enters the obstacle. This strongly supports an
obstacle stop, though raw events do not include a blocking-hit reason/normal.
Official data/video calibration remains provisional for exact League behavior.

## Historical milestones and failures - superseded

The remainder preserves the original progression, including old test counts,
failed build/editor attempts and statements made before real gameplay existed.
They do not describe the current build or invalidate the later retained evidence.

## Historical Python milestones

```text
python -B -m unittest discover -s unreal/SurgeMovementLab/telemetry -p "test_*.py" -v
Ran 53 tests - OK
```

This preserves the prior33 tests and adds nine dash timing/compatibility scenarios
and eight descriptive quality-metric tests. The exporter previously passed19
browser checks with no network requests or browser/CSP errors. Checks cover actual
sample interpolation, blink/gap/unsupported holds, event stepping, Play/Pause and
scrub, inert hostile text, exact visible hashes and340px layout. Owned browser
helpers closed normally. The local hash-bound browser report is retained as
`offline-replay-verification.json`.

The full50-test suite and source/profile agreement check were rerun after the
dash/quality integration. Source/profile agreement remains23 numeric settings,
terrain flag and profile ID. Native shared math was unchanged after its227-check
pass, so that compiler suite was not needlessly repeated.

Dash timing checks cover legal frame quantization, excess in-dash speed within
legal range, overlong duration, wall stops, gaps/state/tick changes, censoring,
partial runs and actual Surge import. Quality checks cover overlap, record-order
ties, already-moving context, denials/stops, missing commands and sparse/partial
timing. These remain synthetic evidence, not observed Unreal gameplay.

A further end-to-end showcase check brings the suite to51 tests. The new paired
artifact `telemetry/local/synthetic-mobility-showcase-20261026T090807Z-f5abe413`
contains60-second authored trajectories, five dashes, three blinks and six scripted
threat lifecycles. Legal:1806 No finding/58 Unknown/0 Review. Changed dash speed:
1803 No finding/52 Unknown/3 Review, all from in-dash displacement while total
range remains425. Both cases reopen identically through existing Surge and have
no geometry-audit issues; server clearance is explicitly unavailable throughout.
The external showcase receipt describes the controlled coordinate change.

The emitted paired replay passed14 additional browser checks, including explicit
synthetic labeling, profile/completion, dash/time inspection, narrow340px layout,
no page errors and no external requests. Both circle/dash screenshots were saved;
the circle view was visually inspected. Owned headless browser closed normally.
Local evidence: `Saved/Verification/showcase-browser-20261026-0210`.

Two further quality tests bring the latest suite to53: accepted dash/blink/stop
timing is retained separately from move-only command timing, denied/late actions
are excluded, and grants explicitly do not prove execution. The paired showcase
was regenerated with this additive summary at
`telemetry/local/synthetic-mobility-showcase-20261026T091943Z-38d5f113`; both source
hashes, verdict counts and exact Surge reopen matches are unchanged. Prior browser
evidence remains bound to the earlier090807 artifact; the template code is unchanged.

## Synthetic demonstration, explicitly not Unreal capture

Two new local bundles retain exact raw/derived evidence, profiles, summaries,
fingerprints and offline replay:

- `telemetry/local/synthetic-dodge-2026-10-26`:1806 raw rows,1800 derived intervals;
  1800 No finding,0 Review,0 Unknown, no geometry-audit issues.
- `telemetry/local/synthetic-speed-change-2026-10-26`:same base fixture with actual
  coordinate speed changed from335 to1200 during20–35 seconds, then restored;
  1350 No finding,450 Review,0 Unknown, no geometry-audit issues. Its action log
  remains external and never enters detector input.

Both cases were exported through Surge's existing `save_case`, reopened through
`open_case`, and their results matched. Exports/receipts are under
`telemetry/local/synthetic-cases-2026-10-26`. Source names explicitly say SYNTHETIC.
These validate integration/controlled mechanics, not real-world detection accuracy,
an independent evaluation or a successful Unreal playtest.

## Historical native source review before the build

Shared engine-independent code was added as `SurviveSim.h` and used by the actual
Unreal pathfinder, dash progression, relative projectile-clearance calculation and
capture-budget decisions. Rendered floor/walls/obstacles derive from the same
geometry constants as the pathfinder. Closed obstacle tangency is conservatively
blocked with the existing2-unit path-corner margin.

MSVC19.44 compiled the shared header/test program under C++17 with `/W4 /WX`. All227
checks passed, covering open/detour/reverse paths and invalid geometry, dash
boundaries/uneven timing, relative crossings/tangency/blink endpoint selection,
and exact byte/row reserve/overflow limits. These are227 assertions across a
bounded math suite, not227 Unreal gameplay scenarios or a performance benchmark.

Retained evidence:
`Saved/Verification/portable-20261026-014304-942-0e8955d9` contains invocation,
compiler/check logs, result, executable and exact source/header/runner snapshots.
Both exit codes are0; header SHA-256 before/after is
`ffcaaa6b8b9818568f4d3b6da97334d775eead2149fda6b6eb5e4e70ec1bc871`.
The runner uses only installed tools, unique output paths, bounded process-tree
timeouts and no cleanup/installation/engine execution.

Official Lucian E and Lux Q clips were downloaded from links verified in their
Riot champion pages, sampled and visually inspected. The
[video inspection supplement](calibration/video-inspection-2026-10-26.md) records
phase observations and uncertainty. No numeric profile changes were justified.

Capture shutdown now preserves `capture_limit` if the byte/row reserve is reached
while ending abilities/cancelling threats. The serialized row is checked against
the terminal byte reserve before writing. HUD reports Recording, Capture saved,
Capture limit reached or Capture failed. This is authored/reviewed source, not
executed native proof.

Read-only inspection of installed UE JSON policy showed double numbers formatted
with17 significant digits (`%.17g`), consistent with integer seq/tick fields for
the bounded counters. No adapter loosening was needed.

## Historical build progression

**Superseding result:** a fresh continuation can see the engine target source.
The next build reached a project V5/default-settings mismatch. Both project targets
were updated to supported V7/Unreal5_8 include order, with no shared-environment
override or engine repair. `build-20261026-022447-431-8b95bc91` passed exit0:
UHT generated16 project files, all16 compile/link/metadata actions passed, total
98.63 seconds. The runner's source/config fingerprints matched before/after.
Native automation and runtime checks are being performed separately; compilation
does not prove physical RMB input, rendering, collisions or gameplay capture.
Historical failures and source-review caveats below remain preserved.

The earlier Launcher-registration-only gate was too restrictive: installed managed
UHT, bundled .NET10, UnrealBuildTool and x64 engine import libraries are present.
The wrapper was revised to check those files, limit compilation to4 parallel
actions/600 seconds, forbid engine changes and preserve source fingerprints.
It invokes installed tools directly without an installer, repair or Launcher.

Actual attempts:

- `Saved/Verification/build-20261026-015404-836-9163495d`: UBT exit6, normal build
  cache under AppData was inaccessible in the restricted execution context.
- `Saved/Verification/build-20261026-015422-241-20fad5f4`: reviewed execution with
  cache access, UBT exit8 after44.15 seconds. It discovered installed MSVC/SDK and
  compiled the project's C# rules, then failed before UHT/project C++:
  `Couldn't find target rules file for target 'UnrealEditor' in rules assembly
  'UE5Rules'`. Engine/Source/UnrealEditor.Target.cs is absent as well.

Both owned process trees exited. No engine repair, installation, shared-build
validation override or reboot was attempted. LauncherInstalled.dat remains empty,
but that fact alone is not used to infer whether command-line compilation works.
Unreal C++/UHT, native automation, rendering, physical mouse input and gameplay
remain unverified. The direct NetUpdateFrequency write was updated to the current
SetNetUpdateFrequency API after local-header review; native validation is pending.
Finite-value guards also prevent a rejected invalid command from writing nonfinite
request coordinates and stop capture visibly rather than append nonfinite actual
geometry/timing. Local UE headers confirm ContainsNaN rejects both NaN/infinity;
these source changes remain uncompiled.

The new bounded `run-engine-checks.ps1` has Smoke/SpeedProbe/Automation modes,
exact module/log/capture fingerprints, a120-second maximum process-tree timeout,
and explicit automated-input provenance. Native automation requires exactly the
two successful Survive test results, not just exit0. Its queued automation Quit
syntax follows the locally installed Gauntlet implementation. PowerShell syntax
passed; a preflight attempt stopped at missing UnrealEditor-SurgeMovementLab.dll
with process_id null. No editor was launched. Evidence:
`Saved/Verification/engine-smoke-20261026-020532-948-fce26d0b`.
Surge core, native15-byte coverage, backups, hooks and CI were not modified.

Recovery ZIPs under `Saved/Verification/source-checkpoint-*` include isolated
source/config, profiles, tests, docs and licenses. Their manifests record exact
file/archive hashes and successful byte-for-byte reopening. They exclude Unreal,
external reference media, captures and unrelated files.

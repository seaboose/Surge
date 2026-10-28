# Survive

Survive is a playable local Unreal Engine 5.8.4 prototype: right-click movement,
skillshot dodging, a dash, a blink and inspectable movement data. Mechanics take
priority over art. The Unreal module/folder remains `SurgeMovementLab`.

## Play

For repeated labeled trials with live recording and analysis, open the repository
root's `Start-Surge.cmd` and choose **Survive sessions**. See the
[collection guide](../../docs/survive-study.md). Human/Scripted/Mixed conditions,
independent recording controls, saved replay and study comparisons are available.
The launchers below remain useful for standalone play.

Double-click [Play-Survive.cmd](Play-Survive.cmd) for practice cooldowns (Q 4s,
E 12s), or [Play-Reference.cmd](Play-Reference.cmd) for reference cooldowns
(Q 16s, E 300s). Reference E is therefore available once per 60-second round.
Both launch the existing compiled local module in a game window.

| Input | Behavior |
| --- | --- |
| RMB press / hold | Set a destination / steer toward the cursor |
| S | Stop walking and clear held steering |
| Q | Directional dash; clear the old path and held steering |
| E | Instant blink to a valid landing; clear the old path and held steering |
| R | Start a fresh round and capture |

Left/middle clicks do not move. Application deactivation clears held steering;
returning to the game requires a fresh RMB press to steer again. Releasing RMB
continues the last accepted destination. The hold target is 10Hz; observed
engine-injected command intervals were frame-quantized around 8.6-10Hz.

## Current mechanics

- Walk 335 units/s; separate path/hit/visual radii of 41/65/50.
- Lucian-inspired dash: requested range 200-425 at 1350 units/s; obstacles stop it.
- Flash-inspired blink: up to 400 units, with invalid landings rejected.
- Lux Q-inspired line: speed 1200, radius 70, range 1300, candidate warning 0.25s.
- Xerath W-inspired circle: radius 250, candidate warning 0.75s.
- One original arena, two obstacles, 60-second rounds, 70/30 line/circle mix and
  independent 50/50 aimed/random targeting. Aimed attacks commit at warning.

One chosen reference unit maps to one Unreal centimeter. Profiles use versioned
Riot static data, extracted spell data and inspected official clips; hit radius,
blink range and some timing semantics remain provisional. No full champion kit,
haste, refunds or exact League engine parity is claimed.
[Calibration evidence](docs/calibration/README.md) records the sources and limits.

## What has been checked

Unreal C++/UHT builds, both native automation tests and the final 66-test Python
suite pass. The shared C++ math also passed 227 assertions. Actual Survive observations include median walking,
dash and projectile speeds of 335/1350/1200 units/s and 400-unit blinks at one
simulation timestamp; these validate this prototype's behavior.

The [three-seed pilot](telemetry/local/development-pilot-review-20261026T112755Z-88b998ed/report.md)
contains nine real automated rounds and nine reopened Surge cases. Each seed has
0 baseline Reviews, 94 controlled-speed Reviews and 0 fresh-restoration Reviews.
No probe Review is unambiguously outside its actual control window. Idle time,
unsupported intervals and printed timestamp uncertainty are retained; this is a
development demonstration, not an accuracy study. Restoration uses a fresh process.

Rendered CUA clicks checked left/middle rejection and RMB/S/Q/E/R behavior. A
separate engine-injected hold probe checked steering, stopping during movement,
fresh-press resumption and Q clearing held movement. The
[final focus probe](telemetry/local/final-focus-review-20261026T104839Z-e567dcfb/report.md)
records application deactivation clearing the latch and a full observation through
reactivation without automatic resumption. Engine-injected keys, CUA window actions
and human input remain distinct; physical sustained holding was not established.

The [reference profile review](telemetry/local/reference-profile-review-20261026T112658Z-f440d796/report.md)
verifies two dash grants, one blink grant and five cooldown denials consistent with
16/300. Exact cooldown boundaries and the 300-second blink regrant remain untested.
[Verification and historical failures](docs/verification-2026-10-26.md) retain the
build, input and synthetic evidence separately.

## Build and data

After source changes, rebuild in PowerShell 7:

```powershell
pwsh -NoProfile -File scripts/build-local.ps1
```

The bounded build/check runners preserve unique logs and hashes; they do not
install, repair or restart the engine/system. The successful final build is
`Saved/Verification/build-20261026-033609-142-299e6d87`. Native automation is under
`Saved/Verification/engine-automation-20261026-034435-051-2e3bd1e4`.

Captures are `Saved/Telemetry/<GUID>.jsonl`: server-owned v3 events and 30Hz-target
samples, bounded to 60 simulation seconds, 10000 rows and 4MiB. Startup warmup,
restarts, cancellation, partial runs and capture failures remain explicit.

```powershell
<python> -B telemetry/analyze_v3.py Saved/Telemetry/<GUID>.jsonl telemetry/local/<new-run> --profile survive-lucian-practice-v1 --source-kind owned-unreal-capture --phase development --replay
```

Choose the reference profile explicitly for reference captures. New bundles retain
exact raw/profile bytes, derived `surge.jsonl`, summaries, policy and hashes; the
manifest is written last. Optional [runtime context](docs/runtime-context.md) binds
automated smoke captures to engine/module/source records. Other input provenance
stays in external sidecars. Missing input/camera/FPS context is unmeasured.

Import `surge.jsonl` with `telemetry/survive-policy.json` in existing Surge. The
rules check walking displacement, mobility range/cooldowns and supported dash
speed/duration maxima. Gaps and unsupported transitions yield Unknown; success at
dodging does not imply cheating. Descriptive exposure/action timing is not human
reaction time. [Summary v2](docs/opportunity-model.md) versions the nominal walking
opportunity math separately from detector limits. Local evidence is unsigned and
editable. The [v2 reanalysis](telemetry/local/opportunity-v2-reanalysis-20261026T115100Z-b6a76d5c/report.md) confirms
identical pilot detector bytes/conclusions while retaining the original artifacts.

## Scope and recovery

[CONTINUE-HERE](CONTINUE-HERE.md) preserves checkpoints and historical interruptions.
The [completion/archive record](Saved/Verification/completion-20261026T115303Z/result.json) identifies the
final source-only recovery ZIP. To save another independent source snapshot:

```powershell
python scripts/save_source_archive.py
```

Captures and reports remain in `Saved`/`telemetry/local`; the pilot frozen ZIP
separately retains the original module used by its runs.
[Design](docs/survive-design.md), [collection protocol](docs/experiment-protocol.md)
and [v3 contract](docs/telemetry-v3.md) describe current behavior and remaining work.
Human studies, held-out seeds, synchronized cue/input timing and exact League
comparison remain future work. No roster, accounts, multiplayer or elaborate art
is required for this milestone.

Surge core, backups, hooks and CI remain untouched; no commit/push/publication was
performed. The separate native-integrity demo still covers two ranges totaling
15 bytes. [MIT reuse](third_party/README.md) is documented; downloaded reference
clips are calibration evidence, not game art or redistributable assets.

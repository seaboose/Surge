# Survive

Survive is Surge's owned Unreal Engine 5.8.4 game: an original top-down arena
with right-click movement, skillshot dodging, dash, blink and recorded movement
evidence. Its module name remains `SurgeMovementLab`.

## Play and investigate

Open **Surge.exe** from the combined [Windows release](https://github.com/seaboose/Surge/releases),
or `Start-Surge.cmd` from a configured source checkout. Choose **Survive sessions**
to launch a 60-second trial, record it, review its timeline and export an evidence
report. See the [demonstration](../../docs/standalone-demo.md).

| Input | Behavior |
| --- | --- |
| Right-click / hold | Choose a destination / steer |
| S | Stop walking |
| Q | Directional dash |
| E | Blink to a valid landing |
| R | Start a fresh round |
| F10 | Stop recording while gameplay continues |

Practice and reference profiles have different ability cooldowns. Human, legal
Scripted, Mixed, and controlled-speed trials are separate conditions. Selecting
Human does not authenticate physical input; legal scripts can satisfy all current
movement rules. [Study collection](../../docs/survive-study.md) explains labels,
comparison groups and incomplete coverage.

## Build from source

Install Unreal Engine 5.8.4, a compatible Microsoft C++ toolchain, Windows SDK,
and PowerShell 7. From this folder:

```powershell
pwsh -NoProfile -File scripts/build-local.ps1
pwsh -NoProfile -File scripts/run-engine-checks.ps1 -Mode Automation
python -B -m unittest discover -s telemetry -p 'test_*.py'
```

Use `-EngineRoot <installation-folder>` when Unreal is outside its standard
installation location. The build/check runners preserve bounded, separate
attempts under `Saved/Verification`. They do not install or repair the engine.
After building, `Play-Survive.cmd` and `Play-Reference.cmd` launch their respective
profiles. [Runtime packaging](../../docs/runtime-release-scope.md) describes
building the cooked game and combined application.

## Evidence and scope

Development captures live in `Saved/Telemetry`; standalone recordings live in
the application's user-data directory. The v3 adapter derives constraints from
exact observations and reviewed profile values. Unsupported intervals remain
Unknown. Labels, trial conditions and action journals stay outside detection.

Profiles use cited static data and inspected reference clips, with explicit
provisional values. This is not exact League of Legends behavior, a human-input
classifier or a measured real-cheat detector. Local hashes establish consistency,
not authenticity. Native DLL coverage in Surge remains a separate 15-byte demo.

Read the [current design](docs/survive-design.md), [v3 telemetry contract](docs/telemetry-v3.md),
[experiment protocol](docs/experiment-protocol.md), and
[calibration sources](docs/calibration/README.md). Historical reports identify
their original snapshots; private local captures are excluded from this source
distribution. [Validation limits](../../docs/validation.md) remain explicit.
[Third-party attribution](third_party/README.md) is retained; reference clips are
not distributed as game assets.

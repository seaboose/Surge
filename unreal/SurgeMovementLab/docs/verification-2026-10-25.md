# Local verification — October 25, 2026

## Traditional point-and-click input follow-up

The browser preview passed explicit checks that left/middle/touch do not move,
RMB moves, held RMB redirects, release retains the last destination, S remains
stopped while the physical button stays held, Q/E cancel refreshes, and pointer
cancellation/focus loss clear the held input. No browser errors were recorded.

Unreal source now has RMB press/release and bounded held updates, focus/key-state
guards, S immediate walking stop and Q/E held-input cancellation. Movement has no
left-click binding. Relevant viewport APIs were inspected in local UE headers;
this is a static check, not a successful compile. The committed dash still finishes
after S. Ability constants/acceleration were not changed or newly calibrated.

The 13 synthetic contract checks passed again after the input/documentation update.
The new collection-plan JSON parses and explicitly identifies itself as planned,
with no runtime loader or completed study. All Unreal build/playtest limits remain.

## Survive follow-up

```text
python -B -m unittest discover -s unreal/SurgeMovementLab/telemetry -p "test_*.py" -v
Ran 13 tests — OK
```

Eight new synthetic checks extend the original five: legal mobility; blink wholly
between walking endpoints; actual excessive speed/range/short cooldown evidence;
hitch/partial capture; lifecycle/label/mutable-limit rejection; missing trajectory
head/tail coverage; current Surge engine compatibility; adapted calibration math.
Completed sessions with unsampled tails now retain Unknown coverage records.

The independent browser concept preview passed start/pause/resume, movement,
dash/blink, mix extremes and narrow-layout checks with zero browser errors.
It is a separate simulation, not an Unreal runtime or capture test.

Unreal source review corrected terminal-dash recording, terminal recursion,
blink collision across frame boundaries and configuration metadata consistency.
No Unreal build, UHT or playtest has run. No map/HUD/restart flow exists yet.

## Original walking-only checks

Executed with the existing bundled Python 3.12 runtime:

```text
python -B -m unittest discover -s unreal/SurgeMovementLab/telemetry -p test_contract.py -v
Ran 5 tests — OK
```

The tests exercise benign walk/acceleration/stop/redirect positions, a controlled
synthetic speed change, hitch and unsupported-mode coverage, malformed/label/
sequence/time rejection, and compatibility with the current Surge engine and
local policy. The engine returned `No finding`, `Review`, `Unknown` for the three
representative eligible/invalid/unavailable segments. No Surge core files were
edited by this implementation.

Evidence type: synthetic unit/compatibility tests only. No real Unreal telemetry
exists yet. Unreal compilation, UHT, project generation, asset loading, navmesh,
camera/input, physics, console actions, network replication, actual capture I/O
and controlled investigation are unverified. No installation was attempted here.

The source skeleton and policy require build/playtest review when the setup chat
finishes. Preserve failing attempts and update this record with actual engine
version and logs rather than replacing synthetic evidence with broader claims.

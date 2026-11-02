# Survive - current design

The local UE5.8.4 prototype is playable through `Play-Survive.cmd` (practice) or
`Play-Reference.cmd` (reference cooldowns). One character survives 60-second rounds
in an original arena with two obstacles, two threat shapes and two mobility tools.
Movement and usable data take priority over art.

Unreal build/UHT, two native checks and a nine-round, three-seed automated pilot
have executed successfully. Rendered CUA clicks and separate engine-injected
hold/focus probes support the input behavior below. These are development checks,
not human studies or exact League movement parity.
[Evidence](verification-2026-10-26.md) preserves current and historical results.

## Controls

| Input | Behavior |
| --- | --- |
| RMB press | Immediately replace the walking destination |
| RMB hold | Target 10Hz steering; release continues the last destination |
| S | Stop walking and clear held input |
| Q | Directional dash; clear path and held input |
| E | Instant blink to a valid landing; clear path and held input |
| R | End as restart and create a new round/capture |

Left/middle clicks do not move. Application deactivation clears the held latch;
reactivation does not restore it. S/Q/E require a fresh RMB press to resume
steering. Destination movement can continue toward a previously accepted goal
when no new steering arrives. The server controls movement and ability grants.

Engine-injected hold commands were observed at frame-quantized 0.1000-0.1167s
intervals. S during motion and Q clearing the latch were checked. The final focus
probe adds the application/Slate activation signal because viewport focus alone
stayed true. Physical mouse holding and all input edge cases remain unverified.

## Mechanics

| Mechanic | Current profile |
| --- | --- |
| Walk | 335 units/s, constant response |
| Radii | 41 path / 65 hit / 50 visual |
| Dash | Requested 200-425 range at 1350 units/s; obstacles stop travel |
| Blink | Up to 400 range, instant; invalid landings rejected |
| Lux Q-inspired line | 1200 speed, 70 radius, 1300 range, candidate 0.25s warning |
| Xerath W-inspired circle | 250 radius, candidate 0.75s warning |
| Cooldowns | Practice Q 4s / E 12s; reference Q 16s / E 300s |

The local coordinate scale is chosen, not a Riot physical-unit definition. Hit
radius, blink range and some cast/terrain semantics remain provisional.
[Calibration](calibration/README.md) preserves versions, conflicts and official
video observations. No complete kit, haste or cooldown refund is reproduced.
Observed Survive speeds and timing agree with this profile; that is not a direct
measurement of League. Exact 16-second readiness and a 300-second blink regrant
were not exercised by the 60-second reference check.

## Attack variation and data

Use 70% lines / 30% circles and independently 50% aimed / 50% random targets.
Aimed shots freeze the player's position at warning; random coordinates do not
track movement. Separate seeded streams preserve unrelated choices. Default seed
1337, 0.8s spawn spacing, eight origins and a 32-threat cap keep scope bounded.

The three-seed pilot reproduces shape/aim patterns, projectile emitters and
recorded random targets. Aimed coordinates and execution times still differ with
movement/ticks. Random misses are not automatically dodges. Centered circles may
need mobility: 315 units of escape exceed the ideal 251.25-unit walking budget.

V3 JSONL records 30Hz-target samples, command/ability/threat lifecycles, separate
simulation/monotonic clocks, geometry and available clearance. Limits are 60
simulation seconds, 10000 rows and 4MiB with terminal reserve. Partial runs,
restarts, cancellations and unsupported intervals remain visible.

Analysis selects a reviewed profile; raw data cannot select limits. Separate
constraints cover walking, mobility range/cooldowns and supported dash maxima.
Descriptive summaries retain exposure, overlap, cadence, clearance and accepted
action timing without calling it human reaction time. [Summary v2](opportunity-model.md)
keeps nominal walking opportunity budgets separate from observed delays and
detector limits. Offline replay uses recorded
paths and gaps. Hashes bind local bytes; they do not authenticate them.

## Next small steps

1. Collect separately labeled physical-player trials; keep engine-injected keys
   and CUA window operation distinct. Exercise fresh-press recovery, invalid
   landings and remaining input edge cases without expanding the game roster.
2. Freeze the new analysis version, build/profile/policy and camera/viewport
   before untouched held-out seeds. The completed pilot remains development data.
3. Measure synchronized visible cues, input receipt and capture overhead before
   making reaction-time or League-timing comparisons.
4. Report exposed opportunities and Unknown/rejected coverage by shape, targeting
   and movement mode. Keep failed attempts and all supported denominators.

No inventory, accounts, multiplayer, leaderboard or elaborate art is needed.
[Collection protocol](experiment-protocol.md) and [v3 contract](telemetry-v3.md)
describe current behavior. Earlier design revisions remain available in Git history.

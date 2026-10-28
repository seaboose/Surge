# Survive skeleton design and v2 contract

## Implementation follow-up

The current game now emits v3. [Current README](../README.md),
[versioned calibration](calibration/README.md) and [v3 contract](telemetry-v3.md)
supersede the earlier placeholder movement values and v2 runtime description below.
Historical v2 code/limits remain for old evidence. Runtime arena, direct obstacle
routing, separate radii, reference-based speeds, independent random streams,
restart/HUD and v3 timing/clearance context are authored. Native build/playtests
remain blocked on completing the engine installation; no real game capture exists.

Current candidate values are335walk,41path/65hit/50visual, dash200–425@1350,
blink400, Lux projectile1200/radius70/range1300, circle250/.75. Practice cooldowns
4/12 differ explicitly from16/300 reference. These values have individual evidence
confidence rather than a blanket exact-match claim. Audit exposure and ideal
walking escape geometry before interpreting hits as player reaction outcomes.

## Accepted plan update - October 25, 2026

The six data controls are requirements: paired seeds, exposed-threat scoring,
frozen difficulty presets, separate walking/dash/blink analysis, explicit capture
coverage and practice before scoring. The protocol and
[collection plan](collection-plan.json) make them concrete. These are collection
requirements, not claims that every analysis tool already exists.

Survive targets League's **traditional point-and-click** movement as closely as
the available evidence permits. Riot describes right-click destinations and
advance obstacle routing in its [official movement discussion](https://www.leagueoflegends.com/en-us/news/dev/dev-wasds-ranked-release/).
Exact walking physics and champion-specific ability parity remain unvalidated.

## Input and movement acceptance

- Desktop movement is **right mouse button only**. Left/middle clicks must neither
  issue a destination nor move the player. Touch is not a substitute in measured
  sessions. Q dash, E blink and S stop remain explicit Survive bindings.
- A right-click issues a destination immediately; a new destination replaces the
  old one. Holding RMB refreshes the cursor destination at a bounded 10 Hz in this
  lab. That cadence is our implementation choice, not a verified Riot rate.
- Releasing RMB stops refreshes but continues the last destination. S stops
  walking immediately and cancels refreshes. Q/E cancel refreshes and the old
  path; a new RMB press resumes walking. An already committed dash finishes.
- Release, focus loss and hidden-preview state must not leave a stuck movement
  input. Test left/right/middle separately and record the measured input scheme.
- Short redirects, 180-degree reversals, close destination arrival, obstacle
  corners and rapid S-stop/restart form the movement calibration course.

The Unreal source and concept preview implement RMB-only/held movement. Their
different cameras, scales and simulation loops are not numerically equivalent.
The server remains authoritative; a client sends destinations, not positions.
Fix camera pitch/zoom, locked-camera behavior and viewport size per measured
preset. Compare world-space destinations and movement angles; raw screen-pixel
mouse distances alone cannot be compared across different camera setups.

## League fidelity work before measured collection

| Priority | Match target | Current state and next check |
|---|---|---|
| 1 | Destination input and terrain routing | RMB/hold/nav paths authored; Unreal input and nav playtest pending |
| 2 | Walking response | 600 cm/s, acceleration/braking 2400 cm/s² are placeholders; calibrate time-to-speed, reversal, stop distance and short-click arrival |
| 3 | Geometry | Current capsule also supplies hit radius; separate pathing, gameplay-hit and visual/selection radii before profile calibration |
| 4 | One mobility reference | Freeze one Lucian-inspired dash profile and a Flash-style instant blink; do not combine incompatible champion exceptions |
| 5 | Speed/range scale | Choose a documented centimeter-to-reference-unit conversion; preserve dimensionless speed/radius and dash-range/radius relationships |
| 6 | Version and observation | Record source version/date and reproducible measurements; no unsupported claim of exact engine parity |

Riot distinguishes gameplay collision, pathfinding and selection radii in
[Patch 14.9](https://www.leagueoflegends.com/en-us/news/game-updates/patch-14-9-notes/).
That source establishes the distinction, not current values for a chosen champion.
Use one versioned reference profile; Riot's [Data Dragon documentation](https://developer.riotgames.com/docs/lol#data-dragon)
describes static data/versioning, not the movement engine. Verify actual available
fields before using them. Use permitted public footage or supplied recordings for
observations; do not attach to League processes or inspect Vanguard.

Current dash wall stopping, instant blink, cooldowns and post-ability path clearing
are Survive rules. Ezreal E is only a conceptual blink reference: this skeleton
does not reproduce its cast timing or damage. Exact turn response, command cadence,
destination clamping and ability resumption need observation. Tune the model and
detector constants together in development, then freeze/hash them before held-out
collection. Never raise limits from incoming evidence to suppress a finding.

## Small game, useful variation

One arena, one character, two mobility tools and two threat shapes. Lucian E is a
directional-dash reference; Ezreal E is a blink reference; Lux Q motivates straight
projectiles; Xerath W motivates delayed circles. Original basic geometry and lab
values omit full champion kits and damage systems.

Two independent choices produce the mix: shape (70% projectile, 30% circle) and
targeting (50% aimed, 50% random). Aimed attacks snapshot the player's position at
warning time. Random targets are independent uniform arena coordinates; they may
miss entirely or fall behind an obstacle. These are useful controls, not automatic
successful dodges. Committed targets never track the player. At most 32 threats
exist simultaneously. Projectiles stop at their first hit, world obstruction or
lifetime limit; circles resolve once at detonation.

A fixed seed reproduces random choices, not identical targeted coordinates for
different movement. Unreal schedules against actual simulation ticks, so hitches
can shift spawn times. Preserve actual events; do not claim identical schedules
across machines or the concept preview. The initial Unreal preset is frozen in
source. Different seeds/settings belong to different recorded conditions.

## Data contract

Authority-owned UTF-8 JSONL, schema `survive-v2`, one unified sequence per run.
Samples/events share a 10000-record/4 MiB budget and a 60-second target duration.
At most one sample per tick, target interval 1/30 s; no catch-up records. One
terminal row and 2 KiB are reserved. Synchronous I/O needs engine measurements
before calling this capture non-disruptive.

Every object has exactly these fields:

| Fields | Meaning |
|---|---|
| schema, session_id, seq | Version, fresh opaque GUID, contiguous zero-based sequence |
| elapsed_s, event | Server simulation elapsed time, lifecycle/gameplay event |
| x_cm, y_cm, z_cm | Player position at the event/sample time |
| movement_mode | walking / dash / blink / other / ended |
| related_id, detail | Activation/threat ID and ability or shape/targeting description |
| a, b, c, d | Event-specific numeric payload |
| source_x_cm, source_y_cm | Fixed threat launch origin; zero for non-threat events |
| velocity_x_cm_s, velocity_y_cm_s | Committed projectile velocity; zero for circles/non-threat events |

Payload conventions:

- `run_start`: seed, aimed fraction, target duration, contract version.
- `sample`: zeros. `command_request/grant`: target X/Y, zeros. Stop/denials carry
  descriptive detail, never a detector verdict.
- `ability_request/grant/start/end`: range, duration, cooldown, zero. Detail is
  dash or blink, with one activation ID. Denials include their reason. These
  payload limits are context, not policy inputs. Granted blink consumes cooldown
  even if its final teleport fails.
- `threat_warning/fire/hit/expired/blocked`: target X/Y, radius, projectile speed
  or circle warning delay. Detail is projectile_aimed/projectile_random/
  circle_aimed/circle_random. Source/velocity support trajectory analysis.
- `run_end`: reason, hit count, prior row/byte counts, actual elapsed time in d.
  Event elapsed_s is clamped at 60; d preserves terminal-tick overshoot.

The adapter bounds bytes/rows/line size and requires finite values, exact fields,
one session, contiguous sequence and nondecreasing event time. Samples must have
strictly increasing time. Missing run_end rejects conversion; partial terminal
records retain their reason and produce Unknown completion. Unsampled trajectory
heads/tails over 150 ms also produce Unknown, even when the run says completed.
A write failure can prevent the terminal record; preserve logs and do not score
the prefix as complete. Completion is not a claim of authenticity or full coverage.

No usernames, accounts, addresses, paths, ground-truth labels or expected verdicts
enter the stream. Local unsigned data can be edited. Validation and hashes do not
prove authenticity. New runs create new files; disk retention remains manual.

## Derived constraints

Output contains observed values, fixed allowed values, source sequence pairs,
units, coverage and a dimensionless constraint_ratio. Surge applies `> 1`:

- Walking: displacement / (600 cm/s × elapsed interval + 10 cm).
- Dash range: start/end displacement / (350 + 10 cm).
- Blink range: start/end displacement / (450 + 10 cm).
- Cooldown: fixed cooldown / (time between same-ability starts + 1 ms).

Walking intervals qualify only at 15–150 ms, both endpoints walking, no mobility
start/end between samples and no active mobility. Otherwise the ratio is null
and Surge reports Unknown. A blink entirely between walking samples is therefore
not a walking-speed finding. Mobility range uses linked actual start/end events.

The detector does not establish per-tick dash speed/duration, entire traveled path,
perfect collision, input authenticity or automated dodging. Displacement can
understate travel. Tampered logs can falsify modes/events. Any dash-duration rule
needs actual tested tick/hitch behavior before inclusion.

## Simple refinements for better evidence

1. **Paired seeds:** repeat a small frozen seed set; separate aimed/random results.
   Use new held-out seeds for final evaluation.
2. **Threat exposure:** determine whether a shot actually approached the player
   before counting a successful dodge. Keep all-shot/exposed-shot denominators.
3. **Clear geometry:** freeze radii, speed, delay and cooldown within a preset;
   change one parameter between trials. Keep build/map/config hashes in an
   external run manifest, not hidden detector inputs.
4. **Timing honesty:** server events are execution/receipt times. Client input and
   cue-display timestamps are a later addition; do not call server-spawn-to-move
   delay pure human reaction time.
5. **Coverage before scoring:** report actual sample intervals, terminal reason,
   Unknown/rejected counts and walking/dash/blink outcomes separately.
6. **Practice before scoring:** allow unscored learning, then fixed 60-second
   measured rounds. Avoid adaptive difficulty until base comparisons work.

Until a practice/record toggle exists, the skeleton still writes practice files;
mark them unscored in an external manifest and keep them out of evaluation.

## Further improvements, in order

1. **Replay and outcome audit:** preserve attack IDs, actual fire times, source,
   velocity and player path. Audit hits and minimum edge-to-edge clearance in a
   deterministic replay before drawing conclusions from dodge counts. A same-seed
   human rerun is not a deterministic replay because aimed targets depend on play.
2. **Independent randomness:** precompute random targets even for aimed attacks,
   or use separate random streams for shape/origin/target/timing. Changing the
   aimed fraction should not unintentionally change all later spawn choices.
3. **Opportunity-aware analysis:** at the warning, compare against a stationary
   continuation of the player's position and actual terrain/lifetime constraints.
   Report all attacks, initially threatening attacks, hits and near misses
   separately. This counterfactual is a geometric measure, not a verified reflex.
4. **Timing and performance:** add tick IDs, actual simulation delta, client input,
   client cue-display and server receipt/application times using separate clock
   domains and explicit synchronization uncertainty. Report frame stalls and
   capture overhead. Do not subtract unsynchronized clocks.
5. **Learning and repeatability:** counterbalance seed order across repetitions,
   retain a session/repetition index and offer consistent practice. If more people
   participate, use opaque external participant IDs and summarize by run/person;
   thousands of adjacent samples are not thousands of independent trials.

These are prioritized additions to the plan. New telemetry fields require a
versioned local contract/adapter update; do not silently add fields to strict v2.

These improve evidence without adding inventory, champion builds, accounts,
leaderboards, matchmaking, complex art or additional enemy AI.

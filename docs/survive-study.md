# Repeated Survive study sessions

The Survive workspace records one owned game round per trial. Choose a short
participant alias, a fixed profile, phase and seed. Start a trial, play the
60-second round, then repeat. The game exits after its round; each trial and
recording receives a new ID. Record two unscored practice rounds before collecting
development data. Physical human input is not attested by selecting Human.

## Start collecting your comparison set

1. Open `Surge.exe` in the standalone product (`Start-Surge.cmd` in development),
   then **Survive sessions**. Choose your alias and keep
   one profile for a comparison block. Practice and reference cooldowns are
   different experimental conditions.
2. Use **Human / Practice** for two warm-up rounds. Right-click to move or hold
   to refresh the destination; **S** stops, **Q** dashes and **E** blinks.
3. Begin **Human / Development** collection. A useful first pilot is 18–30
   rounds across three sittings, rotating seeds 1337, 2027 and 4242. This is a
   starting collection plan, not evidence that a false-positive rate is reliable.
4. Collect Scripted and Mixed rounds using the same seeds/profile. Rotate the
   order across blocks to reduce practice/fatigue effects. In Mixed, play normally
   whenever the HUD says your controls are active; make a fresh right-click after
   each scripted handoff.
5. Review each saved session. The shared time selection links the arena,
   movement-rule graph, events and exact source record. **Pause view** freezes
   inspection while recording continues. **Stop recording** preserves a partial
   observation and does not stop the game. Partial coverage remains Unknown.
6. Use **Refresh comparison** to verify saved sessions in bounded batches.
   Pending/rejected recordings remain visible. Only give an independent expected
   mechanical-violation assessment when you can justify it; leave uncertain
   sessions Unknown. Freeze the study only after development review is finished.

These automated verification runs do not populate your human baseline. Human
sessions require you to play. Repeated rounds from one person can be correlated;
report session counts, Unknown coverage and the collection conditions alongside
any rates. A zero observed false-positive count is not proof of a zero true rate.

The live rows are application telemetry from this owned game, not captured
League network packets. The stream records accepted commands and game state,
not physical mouse/keyboard input or when a threat first appeared on your screen.
It cannot support a precise human reaction-time claim without additional,
separately validated input/display timing instrumentation.

## Conditions

| Mode | Behavior |
| --- | --- |
| Human | No study automation. Normal right-click/S/Q/E controls are available. |
| Scripted | A fixed legal command sequence uses real game handlers. Normal movement/ability input is disabled while it owns control. |
| Mixed | Scripted control at 15–20s and 35–40s; normal controls outside those windows. A fresh right-click is needed after handoff. |
| Speed change control | Existing smoke driver with actual walk speed 1200 near 20–35s, restored to 335; a separate mechanical positive control. |

Scripted actions do not bypass cooldowns, movement rules or collision. They can
produce No finding because current rules detect mechanical violations, not all
automation. Mixed manual windows may be idle; a headless mixed trial is not a
human-plus-script trial. Script ownership boundaries stop the current destination;
a dash already in progress retains its ordinary game rules.

The game HUD names the study mode and indicates whether your controls or scripted
controls are active. A journal failure stops automation and appears in the HUD.
Developer verification can use constructor-only `StudyManager(headless=True)`;
it permits only non-human practice trials, marks manual input unavailable and
separates those trials from rendered desktop groups. Headless mixed means script
plus idle, and never contributes to false-positive or false-negative rates.

The schedule is fixed before observing findings. There is no threshold search,
evasion optimization, third-party process attachment or OS input injection.

## Recording and provenance

The recorder is armed before the owned game is launched. Trial manifests and
runtime action journals stay outside the 31-field game stream. The standalone data
root is `%APPDATA%/surge-desktop/Survive`; development uses
`unreal/SurgeMovementLab/Saved`. Within that root, the game writes
`StudyActions/<trial-id>.jsonl` with actual session ID, mode, elapsed game
time, window transitions and attempted scripted actions. A request does not by
itself prove the game accepted or executed it; raw grant/start/end records provide
that evidence. The study report verifies matching runtime identity and profile
bytes before attributing a recording to its trial.

`StudyTrials/<trial-id>` within the same data root contains the immutable trial intent, recording
association, process receipts and independent assessment revisions. Game captures
and recorder evidence retain their own storage and validation rules. Study paths
are fixed locally; the interface sends only IDs and bounded choices.

One owned process can run per manager. Trials have a 180-second wall-time limit
and 16 MiB engine-log limit. The watchdog terminates only its retained process
handle. Interrupted, unmatched and incomplete trials remain visible. The system
does not promise power-loss durability or source authenticity.

## Comparison and false positives

Reports group by participant, condition, phase, profile fingerprint and module
fingerprint and execution context. They show complete/unverified sessions, mechanical Review sessions,
Unknown coverage and interval counts. Adjacent interval records are correlated.

Selecting Human does not label every record clean; selecting Scripted does not
label it mechanically invalid. Add an independent expected-mechanical-violation
assessment (`yes`, `no` or `unknown`) only with a defensible reason. Revisions
are preserved and never enter detector inputs. Session-level false-positive and
false-negative rates use only explicitly labeled, complete, runtime-matched,
non-practice desktop sessions with eligible observations. Duplicate runtime
sessions cannot count as independent trials. Their denominators and excluded
sessions remain visible. These metrics concern the mechanical task, not cheating
or human-versus-automation accuracy.

The displayed confusion counts and rate pool all eligible groups, including
development and held-out sessions. Read the visible numerator, denominator,
exclusions and group context together. Do not present that aggregate as a
held-out performance estimate or as evidence about a wider player population.

Use the same seeds/profile for paired development comparisons, then freeze the
build, profiles and analysis before held-out collection. Development seeds are
1337/2027/4242. Seeds 9001/9007/9011 are reserved and rejected for practice or
development. Held-out trials require an immutable freeze and matching inputs;
later code/profile changes require a separately reviewed study rather than silently
replacing the old freeze.

## Developer command-line workflow

Run from the repository root with the configured Python environment:

```text
python scripts/survive_study.py start --mode human --participant player --seed 1337 --phase practice
python scripts/survive_study.py start --mode scripted --participant control --seed 1337
python scripts/survive_study.py start --mode mixed --participant player --seed 1337
python scripts/survive_study.py freeze
python scripts/survive_study.py list
python scripts/survive_study.py label <trial-id> --expected-mechanical-violation unknown --note "Awaiting independent review"
```

The local live recorder and compiled study-enabled Unreal module are required.
The command-line start keeps its manager alive until the finite game process
ends, finalizes its recorder and prints the retained identifiers. UI recording
Stop remains independent of game playback.

# Survive v3 evidence and replay audit

## Version and policy boundary

The current game source emits `survive-v3`; v1/v2 remain historical formats with
their original limits. Use `prepare_v3.py` or `analyze_v3.py` and explicitly select
the expected local profile. Incoming profile IDs cannot choose looser limits.
Never pass v3 through a historical adapter or silently change its schema.

The two reviewed local profiles are `survive-lucian-practice-v1` and
`survive-lucian-reference-v1`. They share movement/geometry, but cooldowns are
4/12 seconds for practice and 16/300 seconds for reference. Calibration status,
raw-value/display-range conflicts, source hashes and timing uncertainty are in
[the calibration record](calibration/README.md), not hidden detector features.

## Flat record fields

Every row retains the 19 v2 fields: schema, session_id, seq, elapsed_s, event,
x_cm, y_cm, z_cm, movement_mode, related_id, detail, a, b, c, d,
source_x_cm, source_y_cm, velocity_x_cm_s and velocity_y_cm_s.

Twelve v3 fields add timing, geometry and observed threat context:

| Field | Meaning |
|---|---|
| server_tick | Monotonically increasing unit tick counter; one sample per tick maximum |
| delta_s | Actual most recent server simulation tick delta |
| monotonic_s | Server platform elapsed time since capture start; a separate clock |
| profile_id | Recorded profile; must match explicit local analysis selection |
| path_radius_cm | Pathfinding clearance radius, 41 in the selected profile |
| hit_radius_cm | Projectile gameplay radius, provisional 65 |
| visual_radius_cm | Original visible-body radius, 50 |
| threat_x_cm, threat_y_cm | Actual threat position when its event is recorded |
| nearest_clearance_cm | Minimum observed edge-to-edge separation, when valid |
| clearance_valid | Whether the threat metric has actually been evaluated |
| baseline_threat | yes/no/unknown estimate for a stationary player at warning time |

`baseline_threat` is observed geometric context, not external ground truth. Neither
it nor server-provided limits can cause a movement detector finding. The current
selected projectile passes terrain, so its baseline is geometric; other future
profiles need explicit terrain behavior rather than assuming all missiles agree.

Limits remain 60 simulation seconds, at most 30 samples/s, 10000 total rows and
4 MiB. One terminal row/2 KiB are reserved. `threat_cancelled` distinguishes round
shutdown from hit, expiry or obstruction. An explicit R restart records terminal
reason `restart`, not a completed round. I/O failure can prevent even the terminal
record; missing completion rejects conversion and the server log remains relevant.

## What the detector checks

- Walking displacement against the fixed profile speed plus 5 cm tolerance.
- Linked dash/blink start-to-end displacement against fixed maximum range plus
  5 cm tolerance.
- Time between same-ability starts against the selected fixed cooldown, with a
  1 ms comparison allowance.
- Successive wholly in-dash sample displacement against1350 units/s plus5 units;
  matched dash duration against425/1350 seconds plus a bounded terminal tick/1ms.

Eligible walking intervals are 15–150 ms, both endpoints walking, and no mobility
transition/active ability. Missing heads/tails, hitches and mobility crossings
yield Unknown; they are never counted as clean. Dash timing additionally requires
supported in-dash samples/ticks and an uncensored matched end. Short wall-stopped
dashes remain valid; minimum actual travel and exact speed are not enforced.
[Dash evidence](dash-evidence.md) defines the conservative maximum-envelope rules.
The opt-in owned speed probe changes real walking speed to1200 at20–35 seconds,
then restores335; actions/expected outcomes remain external to raw detector input.

## Descriptive metrics and audit limits

`audit_v3.py` checks attack lifecycle and immutable target/source/velocity, requires
descriptors to match the selected profile, and separates shape/targeting outcomes.
It computes an independent geometric initial-exposure estimate without terrain,
records the server estimate separately, and distinguishes censored/cancelled shots.
It does not turn every random miss into a successful dodge.

Trajectory audits interpolate retained samples and actual ability events, never
resimulate player decisions. They avoid blink discontinuities and intervals over
150 ms. Timing allowance uses supported intervals within that threat's flight,
not an unrelated whole-run hitch. Partial coverage is unavailable for a clean
consistency result. Blocked terminals are clipped to recorded contact geometry.
This cannot establish every between-sample collision or prove authenticity.

For circles, minimum escape distance and the nominal walking budget
are reported. A centered 250-radius circle plus65 hit radius needs315 movement,
while335 ×.75 only permits251.25. Such a hit is not proof of slow human reaction;
mobility or a different starting position can be required. Centered aimed linear
shots receive a nominal budget for the best straight angled heading, with
explicit range/centering checks. This assumes no terrain, other threats, latency
or acceleration. Nominal delay and observed warning-to-fire delay are separate.
Summary v2 deprecates the old perpendicular field name; see
[the opportunity model](opportunity-model.md) for formulas and availability.

No pure human reaction time is reported. Client input/cue-display timestamps and
clock synchronization remain future work; server elapsed/platform clocks cannot
be subtracted from an arbitrary client clock to infer latency.

[Quality metrics](quality-metrics.md) add observed sample coverage, separate
monotonic cadence and simulation/monotonic ratios. Each threat also reports time
to the first later accepted move command, bounded by resolution/capture end,
with competing-threat counts and conservative prewarning displacement context.
Held steering and shared commands prevent causal or reaction-time attribution.
The separate action view includes accepted S stops and Q/E grants, retaining the
move-only measure. Authorization does not establish execution or a successful dodge.

## Durable evidence bundle

```powershell
<python> -B telemetry/analyze_v3.py Saved/Telemetry/<session>.jsonl telemetry/local/<new-run> --profile survive-lucian-practice-v1 --source-kind owned-unreal-capture --phase development --replay
```

Create the parent folder first. Output must be a new directory. The bundle retains
exact raw evidence, derived Surge JSONL, exact profile bytes, policy, summary and
a manifest with source/profile/adapter/output hashes. Manifest creation is last;
its absence identifies an interrupted bundle. Earlier runs are never overwritten.

`--replay` includes a standalone offline `replay.html` with Play/Pause, scrub and
event stepping. Raw/profile hashes, source-kind assertion and interpolation/gap
status remain visible. Blink discontinuities and unsupported/long gaps are held
instead of smoothly invented. Threats reconstruct from actual fire times and
committed trajectory parameters; their interpolation is explicitly labeled.
The optional arena outline is an illustration of current source geometry, not a
captured map fingerprint. Network access is blocked and embedded event text is
escaped. The bundle binds replay bytes and exporter/template hashes in its final
manifest. The viewer does not resimulate player decisions or establish exact
between-sample physics. Export one separately with `render_replay.py` if needed.

Manifest `profile_sha256` is the exact reviewed profile. Legacy `policy_sha256`
is an explicitly described alias for those movement-policy bytes;
`analysis_settings_sha256` separately identifies `policy.json` rule settings.

Source kind and phase are operator assertions, not authenticity checks. Engine,
build, map and camera fields remain explicitly unmeasured unless supplied in a
separate runtime/build record. Independent labels and action logs stay separate.
The derived JSONL uses the existing `survive-policy.json` settings in Surge, with
`constraint_ratio > 1`; no Surge core modification or live collector is required.

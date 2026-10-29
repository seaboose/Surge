# Optional smoke-run context

Saved unattended Unreal smoke records can be bound to an evidence bundle without
changing detector input. The helper reads `invocation.json`, `result.json`,
`capture-evidence.json`, `inputs-before.json`, `inputs-after.json` and the exact
`capture.jsonl` snapshot. It requires a successful Smoke/SpeedProbe result, matching
capture/session/profile/seed metadata, unchanged module/source/config fingerprints,
and the expected Entry map, automated driver, NullRHI and requested60FPS cap.

The caller selects the expected reviewed profile; the default remains
`survive-lucian-practice-v1`. Reference context requires an explicit
`--profile survive-lucian-reference-v1` and the exact retained invocation flag
`-SurviveReferenceCooldowns`. Practice requires that flag to be absent. Selected
profile, raw profile ID and retained flag must agree; raw evidence cannot select
movement or cooldown limits. Reference cooldowns are 16/300 seconds, practice 4/12.
When newer runner records include `expected_profile_id`, that fixed choice must
also agree. Older records without it remain supported.

```powershell
<python> -B telemetry/runtime_context.py Saved/Verification/<engine-smoke-run> telemetry/local/<new-runtime-context.json>
<python> -B telemetry/analyze_v3.py Saved/Verification/<engine-smoke-run>/capture.jsonl telemetry/local/<new-bundle> --profile survive-lucian-practice-v1 --source-kind owned-unreal-capture --phase development --replay --runtime-context telemetry/local/<new-runtime-context.json>
```

For a reference run, pass `--profile survive-lucian-reference-v1` to both commands.
Python callers can use `create_context(directory, profile_id=...)` or
`write_context(directory, output, profile_id=...)`. Context fields/schema and
profile bytes remain unchanged. The exact invocation-record hash binds its flag;
the resulting context separately binds the explicitly selected profile ID/hash.

The helper writes a new context file exclusively. Each runner record is limited
to128KiB, context to256KiB and capture to4MiB. The bundle validates the context
before creating output, preserves its exact bytes as `runtime-context.json`, and
hashes it in the final manifest. Context absence preserves existing bundle behavior.
The manifest exposes recorded engine version and the project module hash; the
hash identifies `UnrealEditor-SurgeMovementLab.dll`, rather than the whole build.

The context explicitly identifies automated game-command handlers and NullRHI.
Without context, `input_scheme` is unmeasured; `configured_input_scheme` records
the game's desktop RMB control configuration separately. A smoke context cannot
be attached to a bundle labeled `synthetic-fixture`.
Requested60FPS is not measured FPS. Map bytes, whole-build hash, camera/viewport,
rendering, cursor projection and human RMB input remain unverified. Source/config
fingerprints are recorded before and after the run; they are not proof that the
module was built from those sources. Five retained-record hashes permit comparison
with the original verification directory, which is not embedded in the bundle.

Local records remain unsigned and editable. Context does not establish authenticity
or infer operator-asserted source kind/phase; a contradictory synthetic source kind
is rejected. Context is never passed to movement
derivation, geometry summaries, replay model features or Surge detector input;
with/without-context derived evidence and conclusions are identical. Future visual
or human-input runs require their own context format instead of relabeling this
smoke-specific record.

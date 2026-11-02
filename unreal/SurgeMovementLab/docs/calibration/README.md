# League-reference calibration v1

Supplement: [official Lucian E and Lux Q video inspection](video-inspection-2026-10-26.md)
was completed October26. Clips/frames/hashes are retained; observations did not
justify changing the numeric profile or removing existing uncertainty labels.

Profiles saved October 25, 2026:

- `profiles/survive-lucian-practice-v1.json`: more mobility samples, dash 4 s and
  blink 12 s cooldowns. Explicitly a training preset.
- `profiles/survive-lucian-reference-v1.json`: rank-1 dash 16 s and Flash 300 s,
  without ability/summoner haste or passive refunds. Geometry still provisional.

Both select Lucian walking/dash and Flash-style blink, with Lux-Q-style projectiles
and Xerath-W-style circles. These are one coherent versioned *reference profile*,
not a recreation of all champion rules or proof of movement-engine parity.
One reference distance unit maps to one Unreal centimeter for a common internal
scale; this is a chosen conversion, not Riot's physical-unit definition.

## Selected values and evidence

| Parameter | Selected | Evidence and confidence |
|---|---:|---|
| Walking speed | 335 units/s | Official DataDragon16.21.1 and extracted Lucian root agree |
| Path radius | 41 units | Extracted named field40.6800003, rounded |
| Skillshot hit radius | 65 units | Provisional secondary value; inherited shared default not extracted |
| Visual radius | 50 units | Survive art/design choice, not a League measurement |
| Dash distance | 200–425 units | Extracted named MinDistance/MaxDistance; official effect array agrees |
| Dash speed | 1350 units/s | Extracted named DashSpeed; official effect array agrees |
| Dash maximum duration | 0.314815 s | Derived425/1350; shorter dash uses actual distance/speed |
| Dash reference cooldown | 16 s | Official rank-1 cooldown, corroborated by raw spell data |
| Flash range | 400 units | Provisional; official static range425 conflicts with secondary actual400 |
| Flash cast delay | 0 s | Selected instant-blink approximation; input-to-move delay unmeasured |
| Flash reference cooldown | 300 s | Official DataDragon SummonerFlash cooldown |
| Lux projectile speed | 1200 units/s | Extracted FixedSpeedMovement.mSpeed and missileSpeed |
| Lux collision radius | 70 units | Raw mMissileWidth70 interpreted as radius, diameter140; verify edges later |
| Lux travel range | 1300 units | Actual missile castRange1300; display override/static range1175 is separate |
| Lux flight lifetime | 1.083333 s | Derived1300/1200, excludes cast delay and world blocking |
| Lux terrain interaction | Pass through terrain | Selected fidelity mechanic; no decisive raw terrain flag or measured official wall-crossing example |
| Lux cast delay | 0.25 s | Provisional candidate; explicit cast time absent in downloaded spell |
| Xerath outer radius | 250 units | Raw castRadiusSecondary/targeter radius250; secondary gameplay275 not adopted |
| Xerath total warning | 0.75 s | Raw cast.25 plus named DamageDelay.5; script-order assumption, not exact measured timing |

Full per-value pointers, source URLs, hashes, differences and confidence labels
live in each JSON. Downloaded official/static and community-hosted extracted game
artifacts are in `profiles/evidence`; none was executed. CommunityDragon is a
community host of extracted implementation data, not an official Riot API or an
assurance that every named field directly equals its runtime effect.

Important ambiguities are preserved rather than silently resolved:

- Lucian E display range445 differs from named MaxDistance425. Use the named
  distance for movement, not the display field.
- Lux Q display1175, raw missile range1300 and secondary reported1300/1240 are
  different concepts. Source-bone offsets and script spawning may affect actual
  center travel; the current simplified missile starts at its declared origin.
- A raw field named width does not establish diameter. Here collision uses70 as
  radius; a later hitbox-edge test must verify that interpretation.
- Survive's Lux-style projectile ignores terrain. The extracted missile contains
  FixedSpeedMovement, CastOnHit and DestroyOnMovementComplete, without an explicit
  terrain-collision flag. Absence alone is not proof of runtime interaction, and
  no official wall-crossing clip was inspected. The profile records this selected
  fidelity behavior as provisional rather than claiming raw-code verification.
- Xerath raw radius250 differs from secondary reported gameplay275. The selected
  profile uses250 because it is directly present in the extraction, without
  inventing a25-unit allowance. Its .75 timing combines two raw components whose
  actual script/event order remains unobserved.
- Flash static425 is not presented as actual400. The selected400 stays provisional
  until shared spell data or a valid geometric measurement resolves it.

## Official video inspection actually performed

Located Riot's [Xerath W demonstration](https://lol.dyn.riotcdn.net/x/videos/champion-abilities/0101/ability_0101_W1.mp4)
through the [official champion page](https://www.leagueoflegends.com/en-us/champions/xerath/).
The downloaded clip is 4,884,196 bytes, 7.333333 seconds, 1056×720, SHA-256:
`5a29955cd2f52a820cb57411ebd3b98a1133e726b7f6797f7c808807dc65e38b`.
The clip has no patch version or authoritative input/server timestamps.

Installed Edge and bundled Playwright opened the local clip, sought selected
timeline times, and saved frames. Both coarse and detail contact sheets were
visually inspected. No ground warning ring was visible at 1.10 s; it was visible
at 1.20 s. No main impact flash was visible at 1.95 s; it was visible at 2.00 s.
This bounds the apparent ground-cue-to-main-flash interval to about 0.75–0.90 s,
including seek/frame uncertainty. It is a visual timing observation, not proof
of damage time, input latency, cast start, current-patch runtime or exact delay.
It is broadly consistent with a .75 s candidate plus tick/visual timing, but does
not resolve the actual script timing composition. No values were fabricated from
frames that were not inspected. The clip is calibration evidence only, not game
art or a distributed Survive asset.

Reproduction helper: `inspect-xerath-video.cjs`; its companion inspection page
opens only the downloaded clip. It needs the already-installed Edge and bundled
Playwright paths recorded in the helper. `profiles/evidence/video` holds metadata,
frames and contact sheets. Lucian E and Lux Q were subsequently inspected in the
October26 supplement linked above; neither inspection resolved all ambiguities.

## Next calibration gates

1. Verify both radii independently: path around a corner versus missile edge
   collision. Render the hit circle temporarily so the two tests are readable.
2. Log input receipt, accepted movement start, actual displacement and stop timing;
   test straight movement, 90° and 180° redirects without decorative rotation delays.
3. Compare traveled distance and phase timing for short/max dash and blink. Keep
   uncertainty in source-bone offsets and cast/telegraph onset explicit.
4. Keep one frozen preset per capture. Record profile ID/hash, map/build hashes,
   seed, actual attack events and timer resolution externally. A seed does not make
   aimed coordinates identical for different players.
5. Test normal dash/blink controls before controlled excess movement. Validation
   labels remain separate from detector input. Never transfer arbitrary numeric
   limits from telemetry payloads into detector policy.

Right-click destination planning around obstacles is directly supported by
[Riot's point-and-click description](https://www.leagueoflegends.com/en-us/news/dev/dev-wasds-ranked-release/).
Riot also documents separate collision/pathing/selection radii in
[Patch14.9](https://www.leagueoflegends.com/en-us/news/game-updates/patch-14-9-notes/).
Exact right-button hold cadence, turn-rate/acceleration physics, path planner,
network prediction and per-ability resume rules are not supplied by these sources.

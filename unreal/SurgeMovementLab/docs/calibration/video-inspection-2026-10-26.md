# Additional official ability-video inspection - October 26, 2026

These short headless inspection sessions used separate temporary profiles and
closed normally. No running game or game installation was involved.

Official champion-page HTML established the exact clip URLs. Bounded downloads,
clip metadata, timestamped frames, contact sheets and an exact-file hash record
are retained under `profiles/evidence/ability-video-2026-10-26`. These are private
calibration references, not assets copied into Survive or licensed for distribution.

| Clip | Official source | Retained bytes / duration / resolution |
|---|---|---|
| Lucian E | [Riot demonstration](https://lol.dyn.riotcdn.net/x/videos/champion-abilities/0236/ability_0236_E1.mp4) from [Lucian page](https://www.leagueoflegends.com/en-us/champions/lucian/) | 3945592 /5.933333 s /1056×720 |
| Lux Q | [Riot demonstration](https://lol.dyn.riotcdn.net/x/videos/champion-abilities/0099/ability_0099_Q1.mp4) from [Lux page](https://www.leagueoflegends.com/en-us/champions/lux/) | 2927945 /4.9 s /1056×720 |

Lucian clip SHA-256:
`bb1eef8e2f317fbbf99faf7e3559128bdfb662874612796117ca553a6bee1317`

Lux clip SHA-256:
`323c981fcd8b913ef5e482fa71a7acfc5f91cc43d9bd3b372c276e89be8f2faf`

## What was actually inspected

Headless installed Edge sought each local clip at0.25-second coarse intervals.
Contact sheets were visually inspected, then the first ability sequence was
sampled at approximately1/30-second steps. Detailed contact sheets and selected
full-resolution frames were inspected, not merely downloaded.

For Lucian, a standing/pre-dash frame remains at0.500 s; rapid displacement is
visible by0.533 s. Position settles around0.767–0.833 s, while recovery animation
continues. A conservative apparent movement interval is roughly0.20–0.333 s.
This is broadly compatible with the selected actual-distance/1350 model but does
not prove that the demonstrated dash traveled the maximum425 units. Shadow/body
pose and animation recovery make exact translation endpoints uncertain.

For Lux, the bright orb develops near the caster around0.200–0.300 s and is
clearly separate/traveling by0.367 s. The visible effect's onset is not necessarily
cast onset. This clip therefore does **not** independently establish the selected
0.25-second server cast delay. No missile speed, radius or range was derived from
uncalibrated screen pixels.

These clips have no patch version or authoritative input/server timestamps and
may be edited. Visual phase timing is evidence about the demonstration, not a
current-server physics measurement. The source-backed numeric profile remains
unchanged; unresolved timing/radius/Flash assumptions retain their earlier labels.
This supplement avoids changing profile bytes merely to append observations,
so existing evidence-bundle fingerprints continue to identify their exact profile.

## Reproduction and retained limitations

`fetch-ability-clips.py` verifies official-page clip references and applies page/
video size limits. It refuses an existing evidence directory. The reviewed
`inspect-ability-clips.cjs` opens local files only, aborts HTTP requests in the
inspection page, seeks frames, records reported seek positions and closes its
temporary browser in finally. Its arguments select one of the two known clips.

`inspection-findings.json` contains the observation statements, unchanged-profile
status and hashes for every retained page/clip/metadata/frame/contact-sheet file.
No gameplay code, detector thresholds or expected labels were inferred from
animation effects. A proper world-scale or input-to-motion study remains a
separate calibration gate after the owned Unreal runtime can be built and tested.

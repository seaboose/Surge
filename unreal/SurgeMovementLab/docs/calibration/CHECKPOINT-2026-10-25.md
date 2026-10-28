# Calibration checkpoint — October 25, 2026

Saved a reviewable provisional profile and seven hashed public-data snapshots.
Official DataDragon16.21.1 confirms Lucian335, dash cooldown16, Flash cooldown300.
Community-hosted extracted16.21 artifact names confirm dash min200/max425/speed1350,
Lux missile speed1200/radius-field70/range1300, Lucian pathing40.68, Xerath cast.25,
DamageDelay.5 and targeter outer250. Range/display and timing ambiguities remain
explicit in the profile. No runtime or video measurement is claimed.

Browsed official Riot champion page; located an official Xerath W clip. The basic
web reader cannot fetch the static JSON endpoints and ordinary shell DNS was
restricted; automatic review approved bounded public data downloads. No installs,
game process access, scripts from recovered folders, assets copied into the game,
hooks, CI, or core Surge changes were involved.

## Follow-up saved

Both practice and reference profiles now parse, and all eight retained artifact
hashes verify against `profiles/evidence/manifest.json`. An official unversioned
Xerath W clip was downloaded within a reviewed 20 MiB budget (actual 4.88 MB),
and timestamped frames were visually inspected. Apparent ground-cue-to-main-flash
timing is bounded approximately 0.75–0.90 s, with no input/server damage timestamp
claim. The final selected circle uses raw radius 250 and provisional total delay
0.75; Lux uses actual missile field range 1300, not display range 1175. See the
calibration README for ambiguity, method and next gates.

## Paused for Windows restart

User requested an immediate pause. Calibration work is paused until an explicit
resume. No restart, downloads, builds or additional research were started.

Last saved work: both versioned profile JSON files, the eight-artifact manifest,
official Xerath W clip/frame evidence, inspection helper/page, and calibration
README. The projectile terrain flag and its explicitly provisional confidence
were saved before the pause. Both profiles parsed at the last check; all eight
retained artifact hashes matched their manifest. Parent reported 24 synthetic
checks passing later; this calibration worker did not rerun that suite.

Incomplete next task: verify official Lucian E and Lux Q video URLs, then perform
bounded visual phase-timing inspection. No files or processes for that task were
created before the pause. Candidate URLs must still be verified from Riot pages;
no world distance/speed may be inferred from uncalibrated video pixels.

All earlier browser helpers exited after their explicit browser.close() cleanup.
This worker has no known active owned download/browser/helper process to stop.

# Survive analyst workflow review — October 26, 2026

**Assessment: 8/10 as a local movement-research lab.** The flow now supports
repeatable experiments and evidence review. It is not a production anti-cheat
system or a validated human-versus-script classifier.

## What is implemented

Start a finite trial, observe recording health, pin or pause the view, inspect one
shared moment across timeline/arena/constraint graph/raw record, then compare
saved sessions. Pause never stops collection. Recording Stop preserves a partial
observation; the game has its own lifetime. Interrupted/corrupt attempts stay
visible as Unknown. Live analysis stays Pending until a validated closed round.

Human, legal Scripted, timed Mixed and a controlled speed violation are distinct
conditions. Labels and actual automation-window journals remain outside detector
inputs. The game HUD identifies control ownership. Human baseline collection
still requires the user to play; no automated trial is labeled human evidence.

The rule graph shows observed/allowed displacement, including the rule's timing
allowance. Exact 31-field source records remain available beyond the first display
page. Arena paths and projectile positions are reconstructions, explicitly labeled;
accepted game commands are not physical mouse/key observations.

## Verification and fixes

| Check | Result |
| --- | --- |
| Portable Python suite | 534 run; 525 passed, 9 platform/optional skips |
| Existing Survive telemetry suite | 66 passed |
| Desktop boundary, startup and recovery suite | 23 passed |
| Actual React journey with controlled data | 19 passed |
| Actual renderer + real Python service + saved Unreal recording | 10 passed |
| Final Unreal build and native checks | Build passed; 2 native tests passed |
| Historical nine-run replay | Derived bytes and full conclusions identical; originals unchanged |

Four new headless **practice** trials passed through the actual game and live
recorder. Each completed 60 seconds, grew incrementally, retained exact source
bytes, reopened successfully, supplied exact raw record300 and matched its
runtime journal. The recorded outcomes were:

| Condition | Review intervals | Unknown intervals | No finding intervals |
| --- | ---: | ---: | ---: |
| Legal script, practice profile | 0 | 55 | 1807 |
| Mixed windows + idle, practice profile | 0 | 19 | 1801 |
| Controlled speed violation | 94 | 43 | 1711 |
| Legal script, reference profile | 0 | 31 | 1801 |

A fifth, rendered mixed practice completed with 0 Review / 20 Unknown / 1799
No finding. Its post-handoff right-click produced a recorded movement grant.
Those desktop inputs were automated verification, not a human sample. The manual
control HUD was visually inspected; the short scripted-status window was not
captured visually. Window transitions are present in the runtime journal.

The real-game test caught a Windows sharing conflict that synthetic tests missed:
a recorder read could collide with an exclusive append. Read-sharing flags fixed
the writer; all four rerun controls completed. The original failed prefix remains
retained. Review also fixed an omitted packaging dependency, finalization races,
hidden interrupted attempts, cleanup after failed trial association, and annotation
fields carrying over between selected trials. The first restricted desktop test
run hit Windows temporary-folder rename restrictions; the normal-permission rerun
passed all23 checks. Failed attempts remain in the evidence folders.

## Security and evidence quality

Renderer requests use fixed methods and bounded IDs/choices. They cannot supply
paths, executables, arbitrary commands, process IDs or detector thresholds. Capture
rejects linked/replaced/truncated sources, ambiguous new sessions, oversized or
nonfinite records and schema/sequence violations. Recording bytes, profiles,
policies and analysis inputs are verified before reuse. Comparison refreshes
perform at most four new full verifications, and show pending/rejected coverage.
Owned trial processes have finite time/log bounds and explicit cleanup.

These targeted tests found no remaining critical escape in the reviewed path.
They are not a comprehensive penetration test or proof of absence of defects.
Local unsigned data can be modified by the machine owner; hashes establish
consistency, not trustworthy client identity. Runtime captures and personal labels
are excluded from source packaging. Existing installed packages were not rebuilt
or distributed by this work.

## Professional interpretation and next priorities

The evidence-first flow is suitable for an analyst. A Review invites inspection;
No finding says only that the evaluated mechanical rules did not find a violation.
Legal scripts passing those rules is a demonstrated coverage limit. Public Riot
engineering also describes prevention and independent protective layers, rather
than a single movement score: [Fog of War design](https://www.riotgames.com/en/news/demolishing-wallhacks-valorants-fog-war)
and [Vanguard security architecture](https://www.riotgames.com/en/news/a-message-about-vanguard-from-our-security-privacy-teams).
This project has a deliberately narrower, owned-game scope.

1. Collect the human pilot using the [collection guide](survive-study.md), then
   inspect apparent false positives with raw context. Never treat Human as an
   automatic clean label or Scripted as an automatic mechanical violation.
2. Preserve the distinction between mechanical correctness and behavior. A later
   behavior model needs independently justified features, a frozen development
   protocol, unseen evaluation and uncertainty; do not tune to these controls.
3. If reaction time becomes a target, add separately validated physical-input and
   displayed-threat timing. Current event clocks cannot establish visual onset.
4. Improve session names with date/seed/condition, keep time controls visible
   while scrolling and add navigation through Unknown coverage. These are usability
   refinements, not prerequisites for the initial collection.

False-positive/negative summaries currently require explicitly assessed,
complete, runtime-matched, non-practice sessions with eligible observations.
Duplicate source sessions, headless verification, missing labels and incomplete
recordings cannot inflate those denominators. Repeated rounds from one player
are still correlated; small observed rates should not be generalized to League
players or a population. No human accuracy rate is established yet.

Detailed local evidence is retained in `verification/survive-live-20261026T124212Z`
and `verification/survive-engine-study-20261026T131211Z-a5ec6045`.

# Surge and Survive: standalone demonstration

Extract the entire combined Windows package into a new folder, then open
**Surge.exe**. Keep its `resources` folder beside it. Unreal Editor, Python and
Node are not required to run this package. The included game is a cooked Windows
Shipping build with explicitly supported controlled practice modes.

## A short demonstration

1. Choose **Survive sessions**. Enter an alias and leave **Phase** on **Practice**.
2. Choose **Scripted — legal game commands**, then **Play and record trial**.
   The game runs one 60-second round. Recording starts before gameplay.
3. Choose **Review this session**. Explain the distinction between a movement
   finding, missing evidence and a verified source. Legal automation can satisfy
   every movement rule; a clean result does not prove human input.
4. Repeat with **Controlled speed violation**. Open **Next review** and compare
   the measured movement with its allowance. The replay and raw record refer to
   the same recorded moment.
5. Choose **Add selection to investigation**, create a report with your alias,
   and write the question, observations, alternatives, conclusion and next steps.
   Cite **E1**, save a revision, then **Continue to export**.
6. Recheck the evidence and export the HTML report. It opens without Surge and
   contains the narrative, source-bound measurements and structured evidence.
7. For the failure case, start another practice round and **Stop recording** early.
   Show that gameplay continues and the saved prefix stays incomplete/Unknown.
   This demonstrates what the application cannot conclude from missing evidence.

Keep the report specific: what was measured, what the rule allowed, which
alternatives remain possible, and what this single recording supports. Use the
existing section tabs and citations; a second dashboard or a longer report is
not needed to demonstrate the evidence chain.

For actual play, select **Human — your play**. Right-click moves, S stops, Q dashes
and E blinks. F10 or the HUD button stops recording while the game continues.
Partial recordings stay incomplete/Unknown. **Pause view** pauses inspection only.
Keep automated demonstrations separate from any human comparison dataset.

## Saved work and updates

Ordinary Windows launches keep Survive data under
`%APPDATA%\surge-desktop\Survive`: telemetry, recordings, trials and investigations.
Surge's other saved cases remain under the same application profile. Exported
reports go to the location chosen in the save dialog.

Close Surge and finish any active game before replacing the application. Extract
the replacement into a separate folder; keep the user-data folder. Do not copy
old private recordings into the application payload. The source workspace's
existing development recordings remain in their original location; the standalone
package does not silently move or delete them.

If game files or analysis assets are missing or inconsistent, extract a fresh
complete copy. Packaged launches must not fall back to an installed Unreal editor
or a developer Python installation. Keep both the original package ZIP and its
matching manifest when preserving a demonstrated version.

## What this demonstration establishes

The project demonstrates a playable controlled environment, exact recording,
measurement-based review, provenance checks and reproducible reporting. It is
not a general anti-cheat product, authenticated human-input detector or measured
human false-positive benchmark. Local hashes establish consistency, not trust in
an unsigned client. The current candidate is unsigned.

See [workflow controls](survive-workflow.md) for timeline ranges, event clusters,
replay, resizable panels and report revisions. Development tests, build tools,
source recovery archives and private data are separate from this runtime package.

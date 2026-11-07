# Surge and Survive: standalone demonstration

The [browser preview](https://seaboose.github.io/Surge/) is a guided screenshot
tour. The steps below run the real Windows application and game. See the
validation results (separate validation kit) for the tested package.

Extract the entire combined Windows package into a new folder, then open
**Surge.exe**. Keep its `resources` folder beside it. Unreal Editor, Python and
Node are not required to run this package. The included game is a cooked Windows
Shipping build with explicitly supported controlled practice modes.

## Try a recording

1. Open **Try Demo → Survive**. Choose **Open example** for a short simulated recording.
2. To collect your own round, enter an alias in **Play & record**, choose a practice profile, and select **Play and record trial**.
3. In **Review**, select a timeline marker. The replay and evidence panel show that moment.
4. Select **Add selection to investigation**. Create or choose an investigation, cite the evidence, and save your notes.
5. Click **Attached as E1** in Review to open its card in Explain. **Back to replay** restores your time and zoom.
6. Open **Export**, recheck the evidence, and save the HTML report.

To compare movement, record one scripted legal round and one controlled speed round. An interrupted recording can leave intervals unassessed.

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

# Play & record, review, explain, export

In the standalone product, open `Surge.exe`; in the developer workspace, use
`Start-Surge.cmd`. Choose **Try Demo** → **Survive**. The four-step bar keeps
round setup and recording together, followed by review, investigation and export. Each step shows its own focused view. Changing steps preserves
the selected evidence and report draft; leaving Review stops replay playback.
Secondary settings, definitions and source details expand when needed.

1. **Play & record:** in **Round setup**, choose an alias, input condition, seed, phase and profile. **Play and
   record trial** arms recording before launching one 60-second game. Right-click
   moves; S stops movement, Q dashes and E blinks. Practice sessions are excluded
   from comparison rates. The launcher waits for the current owned game to exit
   before allowing another trial.
   Setup collapses when capture starts; reopen it to inspect your choices.
   The recording strip shows game elapsed time, recorder elapsed time,
   received records and receipt freshness. In the game, the HUD distinguishes
   telemetry being written from Surge receiving it. **F10** or the HUD's **Stop
   recording** button stops only the recorder. Gameplay continues and a partial
   recording remains partial/Unknown. A missing or stale heartbeat is unavailable,
   never a healthy fallback. **Inspect live recording** opens Review; **Pause view** pauses
   inspection, not recording. Recorder diagnostics are available on demand.
   Use **Recordings** to rename a saved round, open it, or record an existing or upcoming game source.
   The default name uses the session type and local recording date and time. Choose **Rename** to give it your own name.
   **Open example** loads an eight-second simulated recording. It supports the same evidence links and report workflow.
   Review and Explain unlock when a recording is loaded. Export also requires a report.
2. **Review:** when recording finishes, choose **Review this session**. Completion
   does not replace a paused view or a different saved session. A compact summary
   keeps duration, Review findings and Unknown observations visible. Expand it
   for hits, avoided initial threats, sampled coverage and metric definitions.
   Missing measurements are not displayed as zero.
3. **Explain:** select a timeline marker, graph interval or event row. Replay,
   selected time, measurements and exact raw evidence share that selection.
   **Add selection to investigation** pins the moment and attaches it to a clean
   open report in one click. If a report must be created or saved first, the pinned
   selection stays available without discarding notes or moving the replay.
   When the open investigation already includes this selection, Review and Explain show its evidence ID, for example **Attached as E2**.
   In Review, select **Attached as E2** to jump to that card in Explain. Choose **Back to replay** on the card to return to the same playhead position, evidence selection and zoom range.
   Choose **New investigation** or a saved title in the investigation picker. Review the attached evidence, then write and cite it.
   Report switching, authorship and revision history expand on demand.
4. **Export:** the readiness panel checks saved text, citations, current source
   verification, the question/conclusion and analyst review. **Recheck evidence**
   preserves unsaved notes. Drafts and incomplete investigations can still be
   exported with visible warnings; unsaved changes and unknown citation IDs must
   be addressed first. Export rechecks sources and writes a new HTML file without
   overwriting an existing report. **Continue to export** opens a focused preview
   and readiness view; **Edit report** returns to the preserved writing state.

## A focused review layout

Replay and selected evidence sit together. Drag their divider, or focus it and
use Left/Right, to change the available space. Home/End select the limits;
**Reset review layout** restores the default split. Narrow windows stack the panes.
Resizing never changes the selected moment or evidence.

The inspector shows the assessment, observed/allowed values, coverage, event and
time first. Field help explains the value and its limits. Identifiers, source details and raw JSON expand individually.
In **Replay tools**, change the camera, enlarge the map or switch colors. Mark a location or the current player position. These personal map notes stay on this device and reopen the linked moment. For a portable citation use **Add selection to investigation**.
**Timeline** opens first. Choose **Movement** or **Event records** to switch views, or use **Show together** to inspect the same selection in several views.
**Compare recordings** opens a second saved recording alongside the current summary. Study comparison and labels are available there.

## Time and visual meaning

| Display | Meaning |
| --- | --- |
| Game elapsed / replay time | Recorded simulation time in seconds. |
| Recorder elapsed | Time the recorder has been running, including game startup. |
| Last receipt age | Time since source bytes were received; not network latency or reaction time. |
| Sampled coverage | Fraction of game time supported by sampled position intervals. Near-100% values remain visibly below 100%. |
| Avoided initial threats | Initially threatening geometry that expired without a hit. This excludes terrain and does not establish that a particular input caused a dodge. |
| Amber Review | A measurement needs investigation; not an automatic cheating verdict. |
| Grey Unknown / missing data | Evidence is unavailable or unsupported; not a clean result. |
| Cyan verified | Source consistency was checked; not authenticated human input. |

Click or drag the full-round timeline to seek. Seeking pauses replay and leaves
the arena and inspector at the same moment. Arrow keys move 0.1 s; Shift+arrow
moves 1 s. Home/End jump to the ends. Open **Time & zoom** for an exact time or
viewing range. **Zoom range** changes dragging to range selection; close the tools
to seek again. **Follow selected moment** restores the moving window.
Changing the viewed range does not change the selected evidence or replay time.

Three lanes distinguish Review (amber diamond), Coverage (hollow square),
and recorded Events (muted dot). **Filter events** narrows the display by kind. Nearby markers become counted clusters: open one to choose its exact
event. Single markers and listed events support Enter/Space. Grey spans mark gaps
greater than 150 ms between recorded positions, including gaps crossing the viewed
range. The overview's missing-data indicators stay visible when event filters are
off. Bounded display omissions have an explicit warning and are not called gaps.

**Play replay** uses 0.5×, 1× or 2× recorded game-time progression. Pausing,
selecting a marker or hiding the window stops replay progression. Live recording
continues independently. Raw-record inspection resumes when playback is paused
to avoid queuing a request for every animation frame. Positions are not invented
across sample gaps or blinks; reconstructed projectile flight remains labelled.

The recorder/HUD status channel is local and unsigned, tied to the owned trial
and its recording. It can request only recorder stop. It is separate from the
31-field telemetry stream, detector inputs and study labels. Closing the owned
game allows a short final drain; an incomplete source cannot become a complete
round merely because its process exited.

Use [study guidance](survive-study.md) for repeated collection and independent
labels, and [investigation guidance](survive-investigations.md) for source/revision
integrity. Human comparison data still requires actual play and independent
review; automated verification sessions are not a human baseline.

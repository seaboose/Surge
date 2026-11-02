# Evidence-linked investigations

Open `Surge.exe` in the standalone product (`Start-Surge.cmd` in development) →
**Survive sessions**. Open a finalized saved recording,
select an event or movement-rule interval, and choose **Add selection to investigation**. Create an
investigation with a title and your local author label, then attach the selected
evidence. Live recording remains independent while you inspect saved evidence.

The replay's **Add selection to investigation** action attaches immediately to a
clean open report. Otherwise it pins the selected moment while you choose/create
a report or finish unsaved edits. Moving the replay does not change that pinned
request. Duplicate selections do not create additional revisions.

Write the question, observations, hypotheses/alternatives, conclusion/limitations
and next steps. Insert references such as `[E1]` using the evidence cards. Reading
the narrative makes those references navigable: a verified reference restores its
recording, exact record, game time and selected movement rule in the replay.

Save a revision with a short explanation of what changed. Drafts and Reviewed
revisions are separate from detector outcomes. Reviewed requires evidence that
currently verifies and a written conclusion; it does not mean the player was
legitimate or the recording was complete. An incomplete recording can still be
reviewed as incomplete. Attaching new evidence returns the investigation to Draft.

## Evidence and history

Evidence facts come from the recording service, never from editable narrative
fields. Each card retains the exact selected record, interval endpoints and rule
when applicable, session/profile identifiers, recording completeness and fingerprints
of the source, profile, policy and analysis inputs. Analyst prose cannot change
recorded measurements, study labels, policies or detector findings.

Opening a report checks its revision chain and source bindings. Missing, changed
or incompatible source data produces a warning; the original snapshot remains
readable, and replay navigation is blocked when it cannot be verified. References
never silently update to new evidence. Navigation returns the verified replay and
selected evidence together, avoiding a different version being loaded between calls.

Every save creates a new revision. Earlier revisions remain read-only and show
their author label, timestamp and change reason. A stale save from another window
is rejected while your typed text remains available. Unsaved edits trigger a
discard/keep-editing choice before switching reports or leaving the workspace.
Author labels are local assertions, not authenticated accounts. Local hashes
check consistency; they do not make evidence tamper-proof against the machine owner.

## Portable reports

Save changes, then export the selected revision to a **new HTML file** through
the desktop save dialog. Existing destination files are never overwritten. The
report contains analyst prose, navigable evidence references, measured facts,
an interval endpoint diagram where available, revision history through the selected
revision, verification warnings and an expandable structured JSON appendix.
HTML is self-contained, escaped and has no scripts or external resources.

The **Report readiness** panel checks saved edits, source verification, citations,
the question/conclusion and analyst review. Missing citations or a draft status
remain visible warnings; unknown citation IDs and unsaved edits block export.
**Recheck evidence** refreshes source health without discarding typed notes.
Export performs a fresh verification before opening the native save dialog.

The export preserves selected snapshots, not the entire original capture. Repeating
the complete analysis requires the referenced original recording and analysis
version. Verification reflects export time; this static file does not monitor
later source changes. Review the selected evidence before sharing a report.

## Operational boundaries

- Standalone investigations are stored at
  `%APPDATA%/surge-desktop/Survive/Investigations/<id>/<revision>.json`.
  Development uses `unreal/SurgeMovementLab/Saved/Investigations/<id>/<revision>.json`.
- Revisions are published only after complete staged bytes have been flushed,
  using an exclusive operation that cannot replace an existing revision.
- The supported bounds are 32 evidence cards from eight recordings, 256 revisions,
  384 KiB per revision, 16 MiB of history and 256 investigations. Limit errors preserve
  previous data; create a separate investigation when needed.
- Unsupported safe-publication filesystems are rejected rather than falling back
  to overwriting. Interrupted attempts remain visible when opening/listing reports.
- Recording, report editing and legacy Surge cases keep separate state. No game
  rebuild, remote service, AI credentials or installation is required for this feature.
- This is a local investigation workflow with portable handoff, not simultaneous
  online document collaboration. It does not generate AI-written conclusions.

Useful demonstration: select a controlled speed finding, attach it as E1, explain
what exceeded the allowance and what remains unknown, save, follow `[E1]` back to
the exact interval, inspect an earlier revision, and export the report.

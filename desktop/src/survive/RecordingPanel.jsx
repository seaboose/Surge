import React from "react";
import { number, pretty } from "./replay-model.mjs";

export default function RecordingPanel({
  active,
  running,
  hasRecording,
  hidden,
  onNavigate,
}) {
  const health = active?.health || {};
  return (
    <section
      className="survive-panel survive-record-view"
      aria-label="Record workspace"
      hidden={hidden}
    >
      <h2>Recording</h2>
      <p>
        {running
          ? "Play the round. Your recording continues while you inspect other views."
          : "Start a round in Play, or review a saved recording."}
      </p>
      <div className="survive-record-progress">
        <progress
          aria-label="Round progress"
          max="60"
          value={Math.min(60, active?.source_elapsed_s || 0)}
        />
        <span>{number(active?.source_elapsed_s || 0, 1)} / 60 s game time</span>
      </div>
      <div className="survive-controls">
        <button disabled={!hasRecording} onClick={() => onNavigate("review")}>
          Inspect live recording
        </button>
        <button onClick={() => onNavigate("play")}>Session setup</button>
      </div>
      <details>
        <summary>Recording diagnostics</summary>
        <div className="survive-health" aria-label="Recording health">
          <strong>{active ? pretty(active.state) : "Recorder idle"}</strong>
          <span>{active?.records || 0} recorded rows</span>
          <span>{active?.bytes || 0} bytes</span>
          <span>
            Known sequence gaps: {health.sequence_gaps ?? "unmeasured"}
          </span>
          <span>Parse errors: {health.parse_errors ?? "unmeasured"}</span>
          <span>Last receipt age: {number(health.stale_s, 1)} s</span>
          {health.pending_bytes > 0 && (
            <span>{health.pending_bytes} bytes await a complete line</span>
          )}
        </div>
      </details>
    </section>
  );
}

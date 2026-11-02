import React, { useContext } from "react";
import { Context } from "./context.jsx";
import { Button } from "./controls.jsx";

export default function Welcome({ onSurvive, onLibrary, onCapture }) {
  const { busy, run, captureVisible } = useContext(Context);
  return (
    <section className="surge-opening" aria-label="Welcome to Surge">
      <div className="opening-identity">
        <h1>Surge</h1>
        <p>
          A security investigation tool for analyzing telemetry, reviewing
          code-integrity observations, and preserving evidence.
        </p>
        <svg className="signal-art" viewBox="0 0 460 460" aria-hidden="true">
          <g fill="none" stroke="currentColor">
            <circle cx="230" cy="230" r="176" opacity=".2" />
            <circle
              cx="230"
              cy="230"
              r="138"
              opacity=".32"
              strokeDasharray="2 12"
            />
            <path d="M230 30v45m0 310v45M30 230h45m310 0h45" opacity=".5" />
            <path d="M54 230h78l28-45 34 86 39-111 30 70h143" strokeWidth="3" />
            <circle
              cx="230"
              cy="230"
              r="201"
              opacity=".18"
              strokeDasharray="60 24 4 24"
            />
          </g>
        </svg>
      </div>
      <div className="opening-actions">
        <Button
          aria-label="Survive sessions"
          className="opening-action"
          disabled={busy}
          onClick={onSurvive}
        >
          <span className="opening-icon" aria-hidden="true">
            ◇
          </span>
          <strong>Survive sessions</strong>
          <span>
            Record gameplay and inspect movement, abilities and skillshots.
          </span>
          <b aria-hidden="true">→</b>
        </Button>
        <Button
          aria-label="Import evidence"
          className="opening-action"
          disabled={busy}
          onClick={() => run("import", { role: "current" })}
        >
          <span className="opening-icon" aria-hidden="true">
            ↓
          </span>
          <strong>Import evidence</strong>
          <span>Start an investigation from a local data file.</span>
          <span>(CSV, JSON, JSONL, NDJSON)</span>
          <b aria-hidden="true">→</b>
        </Button>
        <Button
          aria-label="Case library"
          className="opening-action"
          disabled={busy}
          onClick={onLibrary}
        >
          <span className="opening-icon" aria-hidden="true">
            ▱
          </span>
          <strong>Case library</strong>
          <span>Browse, reopen, and manage saved investigations.</span>
          <b aria-hidden="true">→</b>
        </Button>
        <Button
          aria-label="Try Demo"
          className="opening-action"
          disabled={busy || captureVisible}
          onClick={onCapture}
        >
          <span className="opening-icon" aria-hidden="true">
            ▷
          </span>
          <strong>Try Demo</strong>
          <span>
            See live capture in action: run the included sample app, collect its
            code-range observations in Surge, and inspect the results.
          </span>
          <b aria-hidden="true">→</b>
        </Button>
      </div>
    </section>
  );
}

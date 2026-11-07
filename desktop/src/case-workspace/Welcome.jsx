import React, { useContext } from "react";
import { Context, useData } from "./context.jsx";
import { Button } from "./controls.jsx";
import { PacketScene } from "./Optical.jsx";

function ActionIcon({ capture = false }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className="landing-action-icon"
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {capture ? (
        <path d="M2 22H8V10H14V22H20V10H26V22H30" />
      ) : (
        <>
          <path d="M8 3H19L25 9V29H8Z" />
          <path d="M19 3V10H25M12 16H21M12 21H21" />
        </>
      )}
    </svg>
  );
}
function CornerMarks() {
  return (
    <span className="landing-corners" aria-hidden="true">
      <i className="reticle reticle-tl" />
      <i className="reticle reticle-tr" />
      <i className="reticle reticle-bl" />
      <i className="reticle reticle-br" />
    </span>
  );
}
export default function Welcome({ onLibrary, onCapture, libraryRefresh = 0 }) {
  const { busy, working, run } = useContext(Context);
  const [library, libraryError] = useData(
    "library_list",
    {},
    true,
    libraryRefresh,
  );
  const recent = [...(library?.entries || [])].sort(
    (a, b) => b.created.localeCompare(a.created) || a.id.localeCompare(b.id),
  )[0];
  const disabled = busy || working;
  const openRecent = () => run("library_open", { id: recent.id });
  return (
    <section
      className="surge-opening luminous-opening landing-flow"
      aria-label="Welcome to Surge"
    >
      <div className="packet-hero">
        <PacketScene />
        <div className="packet-actions">
          <Button
            aria-label="Open evidence"
            className="packet-action landing-open"
            disabled={disabled}
            onClick={() => run("import", { role: "current" })}
          >
            <CornerMarks />
            <ActionIcon />
            <span className="landing-action-copy">
              <strong>Open evidence</strong>
              <span>Import a file</span>
            </span>
          </Button>
          <Button
            aria-label="Start capture"
            className="packet-action landing-capture"
            disabled={disabled}
            onClick={onCapture}
          >
            <CornerMarks />
            <ActionIcon capture />
            <span className="landing-action-copy">
              <strong>Start capture</strong>
              <span>Choose a source</span>
            </span>
          </Button>
        </div>
      </div>
      <section className="landing-recent" aria-label="Recent cases">
        <svg
          className="landing-history-icon"
          viewBox="0 0 24 24"
          aria-hidden="true"
          focusable="false"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 6V12L17 15" />
        </svg>
        <div className="landing-recent-summary">
          <h2>Recent cases</h2>
          {libraryError && <p role="alert">{libraryError}</p>}
          {!library && !libraryError && <p role="status">Loading cases…</p>}
          {library && !recent && <p>No saved cases yet.</p>}
          {recent && (
            <Button
              className="landing-recent-case"
              aria-label={recent.name}
              disabled={disabled}
              onClick={openRecent}
            >
              {recent.name}
            </Button>
          )}
          {library?.unavailable > 0 && (
            <p role="alert">
              {library.unavailable} saved{" "}
              {library.unavailable === 1 ? "case is" : "cases are"} unavailable.
            </p>
          )}
        </div>
        <div className="landing-recent-actions">
          {recent && (
            <Button
              className="landing-open-case"
              disabled={disabled}
              onClick={openRecent}
            >
              Resume <span aria-hidden="true">→</span>
            </Button>
          )}
          <Button
            className="landing-all-cases"
            disabled={disabled}
            onClick={onLibrary}
          >
            All cases <span aria-hidden="true">→</span>
          </Button>
        </div>
      </section>
    </section>
  );
}

import React from "react";
import { Info } from "../Info.jsx";

export default function InvestigationReadiness({
  readiness,
  ready,
  dirty,
  busy,
  checkedUtc,
  onRecheck,
}) {
  return (
    <section className="investigation-readiness" aria-label="Report readiness">
      <div className="investigation-readiness-heading">
        <div className="report-heading">
          <h3>Report readiness</h3>
          <Info label="Report readiness">
            Check the saved revision, source links, citations, and analyst
            review. Recheck evidence updates the source checks for this
            revision.
          </Info>
        </div>
        <span
          className={`investigation-state ${ready ? "is-verified" : "is-unknown"}`}
        >
          {dirty
            ? "Save changes first"
            : ready
              ? "Ready for handoff"
              : "Draft export available"}
        </span>
        <button disabled={busy} onClick={onRecheck}>
          Recheck evidence
        </button>
      </div>
      <ul>
        {readiness.map((item) => (
          <li key={item.label} data-ready={item.pass}>
            <span
              className={`investigation-state ${item.pass ? "is-verified" : "is-unknown"}`}
            >
              {item.pass ? "Ready" : "Check"}
            </span>
            <div>
              <strong>{item.label}</strong>
              {item.pass ? (
                <details>
                  <summary>Details</summary>
                  <p>{item.detail}</p>
                  {item.label === "Evidence sources" && (
                    <small>Checked {checkedUtc || "Unavailable"}.</small>
                  )}
                </details>
              ) : (
                <p>{item.detail}</p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

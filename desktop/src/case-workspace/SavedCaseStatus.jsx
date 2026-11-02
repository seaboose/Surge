import React, { useContext } from "react";
import { Context } from "./context.jsx";
import { Button } from "./controls.jsx";

export default function SavedCaseStatus({ openedCase, onShowCapture }) {
  const { state, capture, captureVisible, working } = useContext(Context);
  return (
    <section className="saved-case-context" aria-label="Saved case">
      <strong>
        {openedCase.modified ? "Working from saved case" : "Viewing saved case"}
        : {openedCase.name}
      </strong>
      {(openedCase.modified || state.case_file?.modified) && (
        <span>
          Workspace settings have changed. The saved copy is unchanged.
        </span>
      )}
      {!state.saved_result && !openedCase.modified && (
        <span>Saved evidence only · no live check.</span>
      )}
      {state.saved_result && (
        <div
          className="saved-observations"
          role="region"
          aria-label="Saved observations"
        >
          <strong>
            {state.saved_result.expected
              ? `Saved observations: all ${state.saved_result.ranges} configured ranges matched the recorded approved baseline.`
              : `Saved observations: expected match not established · ${state.saved_result.review} need review · ${state.saved_result.unknown} unknown.`}
          </strong>
          <span>
            Saved evidence only · recorded build and configured ranges · no live
            check.
          </span>
        </div>
      )}
      {capture?.state === "running" && (
        <div className="actions">
          <span>
            {capture.state === "running"
              ? "Live demo capture is running separately."
              : "The previous demo capture is separate from this case."}
          </span>
          {!captureVisible && (
            <Button disabled={working} onClick={onShowCapture}>
              View demo capture
            </Button>
          )}
        </div>
      )}
      {capture && capture.state !== "running" && !captureVisible && (
        <details>
          <summary>Previous demo capture</summary>
          <p>This stopped capture is separate from the saved case.</p>
          <Button disabled={working} onClick={onShowCapture}>
            View demo capture
          </Button>
        </details>
      )}
    </section>
  );
}

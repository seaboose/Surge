import React, { useContext } from "react";
import { Context } from "./context.jsx";
import { Button, ExportOptions } from "./controls.jsx";

function SnapshotStatus({ snapshot, capture, hasEvidence }) {
  const sameSession =
    !!snapshot?.session_id && snapshot.session_id === capture?.session_id;
  const newer =
    sameSession &&
    Number.isInteger(capture?.final_sequence) &&
    Number.isInteger(snapshot.final_sequence) &&
    capture.final_sequence > snapshot.final_sequence;
  let relation = "";
  if (snapshot && capture?.error)
    relation = "Live status needs attention; the viewed snapshot is unchanged.";
  else if (snapshot?.session_id && capture?.session_id && !sameSession)
    relation =
      "Snapshot is from an earlier collection. Inspect snapshot to view this collection.";
  else if (snapshot && capture?.state === "running" && !capture.session_id)
    relation = "Collection is starting; the viewed snapshot is unchanged.";
  else if (snapshot?.final_sequence === null && capture?.records > 0)
    relation =
      "Collection has observations available. Inspect snapshot to view them.";
  else if (newer)
    relation =
      "Newer samples available. Inspect snapshot to update the viewed evidence.";
  else if (snapshot && sameSession)
    relation =
      "The viewed snapshot is fixed; collection never updates it automatically.";
  return (
    <div className="snapshot-status" aria-label="Viewed evidence">
      {snapshot ? (
        <>
          <strong>
            Viewing snapshot
            {snapshot.final_sequence === null
              ? " · no observations available"
              : ` · through sample ${snapshot.final_sequence}`}
          </strong>
          <span>
            {snapshot.samples} retained samples · {snapshot.records} observation
            records
            {snapshot.captured_at
              ? ` · Last observation: ${snapshot.captured_at}`
              : ""}
          </span>
          <span>{relation}</span>
        </>
      ) : (
        <span>
          {hasEvidence
            ? "Viewing imported evidence. Collection is separate until you inspect a snapshot or stop collection."
            : "No snapshot inspected yet. Start collection, then inspect a snapshot."}
        </span>
      )}
    </div>
  );
}

export default function CollectionPanel({
  openedCase,
  savedNotice,
  page,
  inspectedCurrentCapture,
  finalSnapshotOpen,
  onClose,
}) {
  const { state, run, capture, working } = useContext(Context);
  const captureReadiness = capture?.error
    ? "Collection needs attention. Review the reported issue."
    : capture?.samples > 0 && capture?.records > 0
      ? "Observations available—you can inspect now."
      : "Waiting for the first sample. You can stop collection at any time.";
  return (
    <section className="capture-controls" aria-label="Demo app collection">
      <div className="actions">
        <Button
          disabled={working || capture?.state === "running"}
          onClick={onClose}
          title={
            capture?.state === "running"
              ? "Stop collection before leaving the demo"
              : state.current
                ? "Hide controls and keep the investigation open"
                : "Return to the opening screen"
          }
        >
          {state.current ? "Hide demo controls" : "Back to start"}
        </Button>
        <h2>Try Demo</h2>
      </div>
      {!state.inspected_capture && (
        <p>
          The sample app runs separately by design, giving Surge a real process
          to observe.
        </p>
      )}
      <p className="demo-next" role="status">
        {openedCase
          ? "Saved case remains open below. Inspect snapshot or Stop collection will replace it with captured evidence; the saved copy stays unchanged."
          : savedNotice?.revision === state.revision
            ? "You can continue reviewing or start another capture."
            : capture?.state === "running"
              ? state.inspected_capture?.session_id === capture.session_id
                ? "Review the snapshot below. Choose Stop collection for the final snapshot, then save the case."
                : captureReadiness
              : capture?.has_evidence
                ? finalSnapshotOpen
                  ? "Collection stopped. The final snapshot is open and ready to save."
                  : "Inspect the available evidence before saving a case."
                : "Start collection to observe the included sample app."}
      </p>
      {capture?.state === "running" &&
        !inspectedCurrentCapture &&
        !openedCase && (
          <small>
            Inspect while collecting, or stop to review the final snapshot.
          </small>
        )}
      <div className="actions">
        <Button
          className={
            (!state.current || page !== "Data") &&
            !(
              state.inspected_capture?.session_id === capture?.session_id &&
              state.summary &&
              capture?.state === "stopped"
            ) &&
            capture?.state !== "running"
              ? "primary"
              : undefined
          }
          disabled={working || capture?.state === "running"}
          onClick={() => run("native_start", { build: "v2" })}
        >
          {capture ? "Start another capture" : "Start collection"}
        </Button>
        <Button
          className={
            (!state.current || page !== "Data") &&
            capture?.has_evidence &&
            !finalSnapshotOpen &&
            (!inspectedCurrentCapture || capture?.state !== "running")
              ? "primary"
              : undefined
          }
          disabled={working || !capture?.has_evidence || finalSnapshotOpen}
          title={
            finalSnapshotOpen
              ? "The final captured evidence is already open"
              : undefined
          }
          onClick={() => run("native_snapshot")}
        >
          {inspectedCurrentCapture && capture?.state === "running"
            ? "Inspect newer snapshot"
            : "Inspect snapshot"}
        </Button>
        <Button
          className={
            inspectedCurrentCapture && capture?.state === "running"
              ? "primary"
              : undefined
          }
          disabled={working || capture?.state !== "running"}
          onClick={() => run("native_stop")}
        >
          Stop collection
        </Button>
        {!state.summary && (
          <ExportOptions
            items={[
              {
                label: "Export captured records",
                disabled: working || !capture?.has_evidence,
                run: () => run("native_export"),
                description:
                  "Save the retained collection window as JSONL, without an investigation.",
              },
            ]}
          />
        )}
      </div>
      <div className="capture-status">
        <span role="status">
          Demo app ·{" "}
          {capture?.state === "running"
            ? "Collecting"
            : capture?.state === "failed"
              ? "Collection failed"
              : capture
                ? "Stopped"
                : "Ready"}
        </span>
        {capture && (
          <span>
            {capture.samples.toLocaleString()} samples ·{" "}
            {capture.records.toLocaleString()} retained records
          </span>
        )}
      </div>
      {capture?.error && <p role="alert">{capture.error}</p>}
      {state.demo_result && (
        <div
          className="snapshot-status"
          role="region"
          aria-label="Demo snapshot result"
        >
          <strong>
            {state.demo_result.expected
              ? `Expected demo result: all ${state.demo_result.ranges} configured ranges match the approved baseline.`
              : `Expected match not established: ${state.demo_result.review} need review · ${state.demo_result.unknown} unknown. Inspect the observations below.`}
          </strong>
          <span>
            Inspected snapshot only ·{" "}
            {state.inspected_capture?.session_id !== capture?.session_id
              ? "from an earlier collection"
              : "normal observations are included"}
          </span>
        </div>
      )}
      <details className="demo-guide">
        <summary>About this demo and its results</summary>
        {state.inspected_capture && (
          <p>
            The sample app runs separately by design, giving Surge a real
            process to observe.
          </p>
        )}
        <p>
          Start collection gathers fresh observations. Inspect snapshot analyzes
          a fixed set while collection continues. Stop collection opens the
          final snapshot, ready to save; no second inspection is needed.
        </p>
        <p>
          No finding means no issue was detected in the checked evidence. Review
          flags a change or another rule match, such as an unapproved build.
          Unknown means evidence is missing or incomplete.
        </p>
        <p>
          For the unchanged, approved sample, No finding is the expected result.
          Only configured code ranges are checked; this does not prove the whole
          app is safe or that a flagged observation is malicious.
        </p>
        <p>
          Save case keeps the inspected evidence, settings, and results in your
          library. Export captured records saves the collection window as JSONL.
        </p>
      </details>
      <details className="demo-collection-details">
        <summary>Collection details</summary>
        <SnapshotStatus
          snapshot={state.inspected_capture}
          capture={capture}
          hasEvidence={!!state.current}
        />
        {capture && (
          <p>
            {(capture.elapsed_ms / 1000).toFixed(1)} s elapsed ·{" "}
            {capture.dropped_samples.toLocaleString()} missing samples ·{" "}
            {capture.evicted_samples.toLocaleString()} earlier samples removed
          </p>
        )}
        <small>
          Retains up to {capture?.limit_samples || 500} samples, subject to the
          evidence size limit · Stops after 10 minutes
        </small>
      </details>
    </section>
  );
}

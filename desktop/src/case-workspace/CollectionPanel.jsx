import React, { useContext } from "react";
import { Context } from "./context.jsx";
import { Button, ExportOptions } from "./controls.jsx";

function SnapshotStatus({ snapshot, capture, hasEvidence, finalSnapshotOpen }) {
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
    <div className="capture-snapshot-copy">
      {snapshot ? (
        <>
          <strong>
            {finalSnapshotOpen ? "Final snapshot" : "Viewing snapshot"}
            {snapshot.final_sequence === null
              ? " · no observations available"
              : ` · through sample ${snapshot.final_sequence}`}
          </strong>
          <span>
            {snapshot.samples} retained samples · {snapshot.records} observation
            records
          </span>
          {relation && <span>{relation}</span>}
        </>
      ) : (
        <>
          <strong>
            {hasEvidence ? "Imported evidence open." : "No snapshot open."}
          </strong>
          <span>
            {hasEvidence
              ? "Collection stays separate until you inspect a snapshot or stop collection."
              : capture?.state === "running"
                ? "Inspection opens a fixed copy. New samples stay separate."
                : "Start collection, then inspect a snapshot or stop to review."}
          </span>
        </>
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
  demoMode = false,
  onSources,
}) {
  const { state, run, capture, working } = useContext(Context);
  const running = capture?.state === "running";
  const observationsReady = capture?.samples > 0 && capture?.records > 0;
  const status = running
    ? "Collecting"
    : capture?.state === "failed"
      ? "Collection failed"
      : capture
        ? "Stopped"
        : "Ready";
  const heading =
    capture?.error || capture?.state === "failed"
      ? "Collection needs attention."
      : running
        ? observationsReady
          ? inspectedCurrentCapture
            ? "Collection continues."
            : "Observations ready."
          : "Waiting for the first sample."
        : finalSnapshotOpen
          ? "Final snapshot open."
          : capture?.has_evidence
            ? "Captured evidence available."
            : "Ready to collect.";
  const guidance = openedCase
    ? "Saved case remains open below. Inspect snapshot or Stop collection will replace it with captured evidence; the saved copy stays unchanged."
    : savedNotice?.revision === state.revision
      ? "You can continue reviewing or start another capture."
      : capture?.error
        ? "Review the reported issue. The viewed evidence is unchanged."
        : running
          ? inspectedCurrentCapture
            ? "Your viewed snapshot stays fixed. Stop collection opens the final snapshot."
            : observationsReady
              ? "Inspect a snapshot while collection continues."
              : "You can stop collection at any time."
          : capture?.has_evidence
            ? finalSnapshotOpen
              ? "The final snapshot is open and ready to save."
              : "Inspect the available evidence before saving a case."
            : "Start collection to observe the controlled process.";
  return (
    <section className="capture-controls" aria-label="Capture controls">
      <div className="capture-heading">
        <div>
          <h2>{demoMode ? "Code integrity" : "Owned process"}</h2>
          <p>Code integrity · approved baseline</p>
        </div>
        <div className="actions">
          {state.current && (
            <Button
              disabled={working || running}
              onClick={onClose}
              title="Hide capture controls; keep the evidence open"
            >
              Hide capture controls
            </Button>
          )}
          {onSources && (
            <Button disabled={working} onClick={onSources}>
              Sources
            </Button>
          )}
        </div>
      </div>
      <div
        className="capture-live-panel"
        data-state={capture?.error ? "attention" : status.toLowerCase()}
      >
        <div className="capture-live-main">
          <div className="capture-live-copy">
            <span className="capture-state" role="status">
              Live capture · {status}
            </span>
            <h3>{heading}</h3>
            <p className="capture-guidance">{guidance}</p>
          </div>
          <div className="actions capture-live-actions">
            {!running && (
              <Button
                className={
                  (!state.current || page !== "Data") &&
                  !finalSnapshotOpen &&
                  !capture?.has_evidence
                    ? "primary"
                    : undefined
                }
                disabled={working}
                onClick={() => run("native_start", { build: "v2" })}
              >
                {capture ? "Start another capture" : "Start collection"}
              </Button>
            )}
            {(running || (capture?.has_evidence && !finalSnapshotOpen)) && (
              <Button
                className={
                  (!state.current || page !== "Data") &&
                  capture?.has_evidence &&
                  (!inspectedCurrentCapture || !running)
                    ? "primary"
                    : undefined
                }
                disabled={
                  working || !capture?.has_evidence || finalSnapshotOpen
                }
                onClick={() => run("native_snapshot")}
              >
                {inspectedCurrentCapture && running
                  ? "Inspect newer snapshot"
                  : "Inspect snapshot"}
              </Button>
            )}
            {running && (
              <Button
                className={inspectedCurrentCapture ? "primary" : undefined}
                disabled={working}
                onClick={() => run("native_stop")}
              >
                Stop collection
              </Button>
            )}
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
        </div>
        {capture && (
          <div className="capture-live-meta">
            <span>
              {capture.samples.toLocaleString()} samples ·{" "}
              {capture.records.toLocaleString()} retained records
            </span>
            <span>
              {capture.dropped_samples.toLocaleString()} missing samples
            </span>
          </div>
        )}
        {capture?.error && (
          <p className="capture-error" role="alert">
            {capture.error}
          </p>
        )}
      </div>
      <div
        className="capture-viewed"
        role="region"
        aria-label="Viewed evidence"
      >
        <span className="capture-viewed-label">Viewed evidence</span>
        <div>
          <SnapshotStatus
            snapshot={state.inspected_capture}
            capture={capture}
            hasEvidence={!!state.current}
            finalSnapshotOpen={finalSnapshotOpen}
          />
          {state.demo_result && (
            <div
              className="capture-snapshot-result"
              role="region"
              aria-label={demoMode ? "Demo snapshot result" : "Snapshot result"}
            >
              <strong>
                {state.demo_result.expected
                  ? `${demoMode ? "Expected demo result: all" : "All"} ${state.demo_result.ranges} configured ranges match the approved baseline.`
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
        </div>
      </div>
      <details className="capture-disclosure">
        <summary>
          {demoMode ? "About this demo and its results" : "About this source"}
        </summary>
        <p>
          This built-in workflow captures observations from a controlled process
          launched by Surge.
        </p>
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
          For the unchanged, approved baseline, No finding is the expected
          result. Only configured code ranges are checked; this does not prove
          the whole app is safe or that a flagged observation is malicious.
        </p>
        <p>
          Save case keeps the inspected evidence, settings, and results in your
          library. Export captured records saves the collection window as JSONL.
        </p>
      </details>
      {demoMode && (
        <details className="capture-disclosure capture-roadmap">
          <summary>What I’m building next</summary>
          <p>
            I’m using Surge to learn how to make detection evidence clearer,
            test its limits, and handle gaps honestly.
          </p>
          <p>
            Next: selectable live scenarios. These are development targets, not
            available controls.
          </p>
          <ul>
            <li>
              <strong>Changed code:</strong> capture a controlled change and
              inspect the resulting review.
            </li>
            <li>
              <strong>Missing evidence:</strong> show Unknown and recovery when
              a range cannot be read.
            </li>
            <li>
              <strong>Outside coverage:</strong> show a change the configured
              ranges do not observe.
            </li>
          </ul>
          <p>
            Selected scenarios will describe the setup. Captured evidence will
            determine the result.
          </p>
        </details>
      )}
      <details className="capture-disclosure">
        <summary>Collection details</summary>
        {state.inspected_capture?.captured_at && (
          <p>
            Viewed snapshot · last observation:{" "}
            {state.inspected_capture.captured_at}
          </p>
        )}
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
      <div className="capture-limits">
        <span>Current live scenario: approved baseline.</span>
        <span>Home keeps collection running.</span>
      </div>
    </section>
  );
}

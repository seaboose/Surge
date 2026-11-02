import React from "react";
import { PROFILE, number, pretty } from "./replay-model.mjs";

export default function Inspector({
  record,
  rawRecord,
  rawError,
  constraint,
  capture,
  metadata,
  final,
}) {
  const status = !final
    ? capture?.analysis_state === "unavailable"
      ? "Unknown — incomplete evidence"
      : "Pending"
    : constraint?.status || "No linked constraint";
  return (
    <section
      className="survive-panel survive-inspector"
      aria-label="Selected evidence"
    >
      <h3>Selected evidence</h3>
      <strong
        className={`survive-assessment ${status === "Review" ? "is-review" : ""}`}
      >
        {status}
      </strong>
      {constraint ? (
        <dl>
          <dt>Rule</dt>
          <dd>{pretty(constraint.constraint)}</dd>
          <dt>Observed</dt>
          <dd>
            {number(constraint.observed)} {constraint.unit}
          </dd>
          <dt>Allowed</dt>
          <dd>
            {number(constraint.allowed)} {constraint.unit}
          </dd>
          <dt>Ratio</dt>
          <dd>{number(constraint.constraint_ratio)}×</dd>
          <dt>Coverage</dt>
          <dd>{constraint.coverage || "Unavailable"}</dd>
          <dt>Source records</dt>
          <dd>
            {constraint.start_seq}–{constraint.end_seq}
          </dd>
        </dl>
      ) : (
        <p>
          {final
            ? "This event has no selected movement constraint. Use a graph point or Next review to inspect one."
            : capture?.analysis_state === "unavailable"
              ? "This recording cannot support complete-run assessment. Its retained observations and completion reason remain inspectable."
              : "Records remain available while the game runs. Conclusions are pending until complete-run validation."}
        </p>
      )}
      {record && (
        <dl>
          <dt>Event</dt>
          <dd>
            {pretty(record.event)} · {record.detail || "—"}
          </dd>
          <dt>Game time</dt>
          <dd>{number(record.elapsed_s, 6)} s</dd>
        </dl>
      )}
      {record && (
        <details>
          <summary>Record identifiers</summary>
          <dl>
            <dt>Sequence / tick</dt>
            <dd>
              {record.seq} / {record.server_tick}
            </dd>
            <dt>Related ID</dt>
            <dd>{record.related_id || "—"}</dd>
            <dt>Mode</dt>
            <dd>{record.movement_mode}</dd>
          </dl>
        </details>
      )}
      <details>
        <summary>Source and policy</summary>
        <dl>
          <dt>Source session</dt>
          <dd>{capture?.session_id || "Awaiting source"}</dd>
          <dt>Profile</dt>
          <dd>{capture?.profile_id || PROFILE}</dd>
          <dt>Authenticity</dt>
          <dd>Local unsigned evidence; not attested</dd>
          <dt>Acquisition</dt>
          <dd>{pretty(capture?.provenance || "unavailable")}</dd>
        </dl>
        {metadata && <pre>{JSON.stringify(metadata, null, 2)}</pre>}
      </details>
      {record && (
        <details>
          <summary>Raw source record</summary>
          {rawRecord ? (
            <pre>{JSON.stringify(rawRecord, null, 2)}</pre>
          ) : (
            <p>{rawError || "Loading exact source record…"}</p>
          )}
        </details>
      )}
      <details>
        <summary>What does this assessment mean?</summary>
        <p>
          Review requests investigation. No finding does not establish
          legitimate play. Commands show game acceptance, not physical input.
          Unknown means evidence is unsupported or incomplete.
        </p>
      </details>
    </section>
  );
}

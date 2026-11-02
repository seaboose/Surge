import React from "react";
import {
  SECTIONS,
  formatEvidenceNumber as number,
} from "./investigation-model.mjs";

function CitationText({ text, evidence, verification, navigate, disabled }) {
  return String(text || "")
    .split(/(\[E[1-9][0-9]*\])/g)
    .map((part, index) => {
      if (!/^\[E[1-9][0-9]*\]$/.test(part)) return part;
      const id = part.slice(1, -1);
      return (
        <button
          key={`${id}-${index}`}
          className="investigation-citation"
          disabled={
            disabled ||
            !evidence.some((item) => item.evidence_id === id) ||
            !verification?.items?.some(
              (item) => item.evidence_id === id && item.state === "verified",
            )
          }
          onClick={() => navigate(id)}
          aria-label={`Open evidence ${id}`}
        >
          {part}
        </button>
      );
    });
}

export function NarrativePreview({
  sections,
  evidence,
  verification,
  navigate,
  disabled,
}) {
  return (
    <div className="investigation-preview">
      {SECTIONS.map(([key, label]) => (
        <section key={key} className="investigation-prose">
          <h4>{label}</h4>
          <div>
            <CitationText
              text={sections[key] || "Not recorded."}
              evidence={evidence}
              verification={verification}
              navigate={navigate}
              disabled={disabled}
            />
          </div>
        </section>
      ))}
    </div>
  );
}

export function EvidenceCard({
  item,
  compact = false,
  verification,
  busy,
  historical,
  navigate,
  cite,
}) {
  const check = verification?.items?.find(
    (entry) => entry.evidence_id === item.evidence_id,
  );
  return (
    <article
      key={item.evidence_id}
      className="investigation-card"
      aria-label={`Evidence ${item.evidence_id}`}
    >
      <div className="investigation-card-heading">
        <strong>{item.evidence_id}</strong>
        <span>
          {number(item.time_s)} s · record {item.seq}
        </span>
        <span
          className={`investigation-state ${check?.state === "verified" ? "is-verified" : "is-unknown"}`}
        >
          {check?.state || "Unavailable"}
        </span>
      </div>
      {item.constraint ? (
        <div className="investigation-measurement">
          <span
            className={`investigation-state ${item.constraint.status === "Review" ? "is-review" : item.constraint.status === "Unknown" ? "is-unknown" : "is-verified"}`}
          >
            {item.constraint.status}
          </span>
          <span>
            {number(item.constraint.observed)} /{" "}
            {number(item.constraint.allowed)} {item.constraint.unit}
          </span>
          <small>Observed / allowed</small>
        </div>
      ) : (
        <p>
          {item.raw_record?.event || "Unavailable"} ·{" "}
          {item.capture?.completion || "Partial / unavailable"}
        </p>
      )}
      {check?.state !== "verified" && (
        <p className="investigation-source-issue">
          {check?.message || "Source verification is unavailable."}
        </p>
      )}
      {!compact && (
        <div className="survive-controls">
          <button
            disabled={busy || check?.state !== "verified"}
            onClick={() => navigate(item.evidence_id)}
          >
            Open {item.evidence_id} in replay
          </button>
          <button
            disabled={busy || historical}
            onClick={() => cite(item.evidence_id)}
          >
            Cite {item.evidence_id} in observations
          </button>
        </div>
      )}
      <details>
        <summary>Source, pinned fingerprints and raw records</summary>
        <dl>
          <dt>Game time / record</dt>
          <dd>
            {number(item.time_s)} s / {item.seq}
          </dd>
          <dt>Event</dt>
          <dd>{item.raw_record?.event || "Unavailable"}</dd>
          <dt>Profile</dt>
          <dd>{item.capture?.profile_id || "Unavailable"}</dd>
          <dt>Completion</dt>
          <dd>{item.capture?.completion || "Partial / unavailable"}</dd>
          {item.constraint && (
            <>
              <dt>Rule / result</dt>
              <dd>
                {item.constraint.constraint} · {item.constraint.status}
              </dd>
              <dt>Interval</dt>
              <dd>
                {item.constraint.start_seq}–{item.constraint.end_seq}
              </dd>
            </>
          )}
        </dl>
        <p>
          Recording: {item.recording_id}
          <br />
          Session: {item.session_id}
          <br />
          Attached by {item.added_by} at {item.added_utc}
        </p>
        <pre>
          {JSON.stringify(
            {
              fingerprints: item.fingerprints,
              interval_start_record: item.interval_start_record,
              raw_record: item.raw_record,
              constraint: item.constraint,
            },
            null,
            2,
          )}
        </pre>
      </details>
    </article>
  );
}

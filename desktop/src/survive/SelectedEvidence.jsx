import React from "react";
import { PROFILE, number, pretty } from "./replay-model.mjs";
import { Info } from "../Info.jsx";

function Field({ name, help, children }) {
  return (
    <>
      <dt>
        {name} <Info label={name}>{help}</Info>
      </dt>
      <dd>{children}</dd>
    </>
  );
}

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
    : constraint?.status || "Recorded event";
  return (
    <section
      className="survive-panel survive-inspector"
      aria-label="Selected evidence"
    >
      <div className="survive-field-heading">
        <h3>Selected evidence</h3>
        <Info label="Selected evidence">
          Shows the source record at the replay cursor and any linked movement
          interval. Select a chart point or a sequence number to inspect an
          exact record.
        </Info>
      </div>
      <div className="survive-field-heading">
        <strong
          className={`survive-assessment ${status === "Review" ? "is-review" : ""}`}
        >
          {status}
        </strong>
        <Info label="Assessment">
          {{
            Review:
              "The measurement exceeded a rule allowance. Inspect the interval and its coverage before drawing a conclusion.",
            Unknown:
              "The rule could not assess this interval. Coverage identifies the missing or unsupported observation.",
            "No finding":
              "The rule found no supported exceedance in this interval. Its conclusion applies only to this measurement.",
            Pending:
              "The recorder has captured this event. Final assessments become available after a complete round is validated.",
            "Recorded event":
              "This event provides gameplay context. No movement assessment is linked to its sequence.",
          }[status] ||
            "This recording has incomplete evidence. Its retained records and completion reason remain available."}
        </Info>
      </div>
      {constraint ? (
        <dl>
          <Field
            name="Rule"
            help="The movement constraint evaluated for this interval."
          >
            {pretty(constraint.constraint)}
          </Field>
          <Field
            name="Observed"
            help="The quantity measured from the source records, in the unit shown."
          >
            {number(constraint.observed)} {constraint.unit}
          </Field>
          <Field
            name="Allowed"
            help="The rule allowance for this interval, with applicable tolerance."
          >
            {number(constraint.allowed)} {constraint.unit}
          </Field>
          <Field
            name="Ratio"
            help="Observed divided by allowed. A value of 1× reaches the allowance."
          >
            {number(constraint.constraint_ratio)}×
          </Field>
          <Field
            name="Coverage"
            help="Whether the interval satisfied the rule’s evidence requirements. Missing or unsupported evidence can leave the result unknown."
          >
            {constraint.coverage || "Unavailable"}
          </Field>
          <Field
            name="Source records"
            help="Sequence numbers of the records that bound this measurement. The chart selects its ending record."
          >
            {constraint.start_seq}–{constraint.end_seq}
          </Field>
        </dl>
      ) : (
        <p>
          {final
            ? "Context only. No movement assessment is linked to this event."
            : capture?.analysis_state === "unavailable"
              ? "This recording cannot support complete-run assessment. Its retained observations and completion reason remain inspectable."
              : "Records remain available while the game runs. Conclusions are pending until complete-run validation."}
        </p>
      )}
      {record && (
        <dl>
          <Field
            name="Event"
            help="What the game recorded at this sequence. Command events describe game-side handling and cannot identify physical input."
          >
            {pretty(record.event)} · {record.detail || "—"}
          </Field>
          <Field
            name="Game time"
            help="Elapsed simulation time of this exact record. Nearby records can share a time and have different sequences."
          >
            {number(record.elapsed_s, 6)} s
          </Field>
        </dl>
      )}
      {record && (
        <details>
          <summary>
            <span>Record identifiers</span>{" "}
            <Info label="Record identifiers">
              Trace this event to its source sequence, simulation tick and
              related gameplay object.
            </Info>
          </summary>
          <dl>
            <Field
              name="Sequence / tick"
              help="Sequence identifies the record inside this session. Tick identifies the simulation update that produced it."
            >
              {record.seq} / {record.server_tick}
            </Field>
            <Field
              name="Related ID"
              help="Links this record to the gameplay object or action identified by the source."
            >
              {record.related_id || "—"}
            </Field>
            <Field
              name="Mode"
              help="Movement mode reported by the source at this moment."
            >
              {record.movement_mode}
            </Field>
          </dl>
        </details>
      )}
      <details>
        <summary>
          <span>Source and policy</span>{" "}
          <Info label="Source and policy">
            Shows where this recording came from and which profile applies to
            its measurements.
          </Info>
        </summary>
        <dl>
          <Field
            name="Source session"
            help="The game session identifier carried by the source records."
          >
            {capture?.session_id || "Awaiting source"}
          </Field>
          <Field
            name="Profile"
            help="Identifies the collection and movement policy used to interpret this recording."
          >
            {capture?.profile_id || PROFILE}
          </Field>
          <Field
            name="Authenticity"
            help="These local records have no signature attesting who produced them."
          >
            Local unsigned evidence; not attested
          </Field>
          <Field name="Acquisition" help="How Surge obtained these records.">
            {pretty(capture?.provenance || "unavailable")}
          </Field>
        </dl>
        {metadata && <pre>{JSON.stringify(metadata, null, 2)}</pre>}
      </details>
      {record && (
        <details>
          <summary>
            <span>Raw source record</span>{" "}
            <Info label="Raw source record">
              Opens the source fields for this exact sequence. Pause replay to
              read them.
            </Info>
          </summary>
          {rawRecord ? (
            <pre>{JSON.stringify(rawRecord, null, 2)}</pre>
          ) : (
            <p>{rawError || "Loading exact source record…"}</p>
          )}
        </details>
      )}
    </section>
  );
}

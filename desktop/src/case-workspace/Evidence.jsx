import React, { useContext } from "react";
import { Context, useData } from "./context.jsx";

export default function Evidence({ row, active }) {
  const { state: s } = useContext(Context);
  const [data, error] = useData(
    "evidence",
    { revision: s.revision, row },
    active,
  );
  return (
    <div
      className="evidence scroll"
      tabIndex="0"
      role="region"
      aria-label="Record evidence"
      aria-busy={active && !data && !error}
    >
      {active && !data && !error && <p role="status">Loading record {row}…</p>}
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          {data.explanation && (
            <p className="record-explanation">{data.explanation}</p>
          )}
          {!data.groups.length && (
            <p>
              {data.gaps.length
                ? "Cannot fully assess this record."
                : "No configured condition matched."}
            </p>
          )}
          {data.groups.map((g) => (
            <div className="evidence-group" key={g.field}>
              <pre className="observed">
                {g.field}: {g.value}
              </pre>
              {g.lines.map((l, i) => (
                <div key={i}>
                  <p className="condition">{l.text}</p>
                  {l.details && (
                    <details>
                      <summary>Details</summary>
                      <p>{l.details}</p>
                    </details>
                  )}
                </div>
              ))}
            </div>
          ))}
          {data.numeric && (
            <p className="muted">A reference median is not a safe limit.</p>
          )}
          {data.reference_group && (
            <p className="muted">
              Reference group:{" "}
              {data.reference_group.fields
                .map(
                  (f, i) =>
                    `${f} = ${JSON.stringify(data.reference_group.values[i])}`,
                )
                .join(" · ")}
              <br />
              {data.reference_group.mode} ·{" "}
              {data.reference_group.reference_rows} reference records
            </p>
          )}
          {data.gaps.map((g, i) => (
            <p key={i} className="warning">
              Check: {g}
            </p>
          ))}
          <p>
            {data.status} · Priority: {data.priority || "None"}
          </p>
          <pre>
            Record: {row} · ID: {data.event_id}
            {"\n"}Session: {data.session}
            {"\n"}Time: {data.time}
          </pre>
          {data.context.map((c) => (
            <p key={c.role}>
              {c.role}: <code>{c.value}</code> · from {c.field}
            </p>
          ))}
          <p className="muted">
            Source: {data.source.name}
            <br />
            SHA-256: {data.source.sha256.slice(0, 12)}… · source record {row}
          </p>
          {data.reference && (
            <details>
              <summary>Reference</summary>
              <p>{data.reference.name}</p>
              <pre>SHA-256: {data.reference.sha256}</pre>
            </details>
          )}
          <details>
            <summary>Source values</summary>
            <pre>SHA-256: {data.source.sha256}</pre>
            {data.values.map((v) => (
              <div className="field-value" key={v.field}>
                <span className="field-name">{v.field}</span>
                <pre>{v.value}</pre>
              </div>
            ))}
          </details>
        </>
      )}
    </div>
  );
}

import React, { useContext, useEffect, useRef } from "react";
import { Context, useData } from "./context.jsx";

function EvidenceGroups({ groups }) {
  return groups.map((group) => (
    <div className="evidence-group" key={group.field}>
      <pre className="observed">
        {group.field}: {group.value}
      </pre>
      {group.lines.map((line, index) => (
        <div key={index}>
          <p className="condition">{line.text}</p>
          {line.details && (
            <details>
              <summary>Details</summary>
              <p>{line.details}</p>
            </details>
          )}
        </div>
      ))}
    </div>
  ));
}

// Display strings without coercing exact numeric source values into JS numbers.
function sourceText(value) {
  if (value === undefined || value === "null") return "Unavailable";
  if (value.startsWith('"')) {
    try {
      const parsed = JSON.parse(value);
      if (typeof parsed === "string") return parsed;
    } catch {}
  }
  return value;
}

function bytePairs(value) {
  const text = sourceText(value);
  return /^(?:[0-9a-f]{2})+$/i.test(text)
    ? { length: text.length / 2, shown: text.slice(0, 64).match(/.{2}/g) }
    : null;
}

function ByteSequence({ label, bytes, comparison }) {
  const shown = bytes?.shown;
  return (
    <div>
      <span>
        {label}
        {bytes?.length > 32 ? " · first 32 bytes" : ""}
      </span>
      <code>
        {shown
          ? shown.map((byte, index) => (
              <React.Fragment key={index}>
                {index > 0 && " "}
                {comparison &&
                byte.toLowerCase() !==
                  comparison.shown[index]?.toLowerCase() ? (
                  <mark>{byte}</mark>
                ) : (
                  byte
                )}
              </React.Fragment>
            ))
          : "Unavailable"}
      </code>
    </div>
  );
}

function EvidenceNotices({ data }) {
  return (
    <>
      {data.explanation && (
        <p className="record-explanation">{data.explanation}</p>
      )}
      {data.gaps.map((gap, index) => (
        <p key={index} className="warning">
          Check: {gap}
        </p>
      ))}
    </>
  );
}

function NativeSummary({ values, data }) {
  const read = (name) => sourceText(values.get(name));
  const observed = bytePairs(values.get("observed_hex"));
  const reference = bytePairs(values.get("reference_hex"));
  const approved = values.get("baseline_approved") === "true";
  const protection = values.get("protection_matches");
  return (
    <>
      <h3 className="evidence-title">{data.reason || data.status}</h3>
      <EvidenceNotices data={data} />
      {values.has("range_name") && (
        <>
          <dl className="evidence-facts">
            <dt>Range</dt>
            <dd>{read("range_name")}</dd>
            {values.has("stream_sequence") && (
              <>
                <dt>Sample</dt>
                <dd>{read("stream_sequence")}</dd>
              </>
            )}
            <dt>Bytes read</dt>
            <dd>
              {observed
                ? `${observed.length} / ${read("range_size")}`
                : "Unavailable"}
            </dd>
            <dt>Protection</dt>
            <dd>
              {protection === "true"
                ? "Matches reference"
                : protection === "false"
                  ? "Changed"
                  : "Unavailable"}
            </dd>
          </dl>
          <div className="evidence-bytes">
            <ByteSequence
              label="Observed"
              bytes={observed}
              comparison={reference}
            />
            <ByteSequence
              label={approved ? "Approved reference" : "Recorded reference"}
              bytes={reference}
              comparison={observed}
            />
          </div>
        </>
      )}
    </>
  );
}

export default function Evidence({ row, active }) {
  const { state: s } = useContext(Context);
  const scroller = useRef();
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = 0;
  }, [row]);
  const [data, error] = useData(
    "evidence",
    { revision: s.revision, row },
    active,
  );
  const values = new Map(
    data?.values.map((value) => [value.field, value.value]),
  );
  const native =
    sourceText(values.get("schema")) === "surge-native-integrity-v1";
  return (
    <div
      ref={scroller}
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
          <p className="evidence-status" data-result={data.status}>
            {data.status} · Priority: {data.priority || "None"}
          </p>
          {native ? (
            <NativeSummary values={values} data={data} />
          ) : (
            <EvidenceNotices data={data} />
          )}
          {!data.groups.length && (
            <p>
              {data.gaps.length
                ? "Cannot fully assess this record."
                : "No configured condition matched."}
            </p>
          )}
          {native ? (
            <details className="evidence-analysis">
              <summary>Analysis details</summary>
              <EvidenceGroups groups={data.groups} />
            </details>
          ) : (
            <EvidenceGroups groups={data.groups} />
          )}
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
          <details className="evidence-identifiers">
            <summary>Record details</summary>
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
          </details>
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
          {native && (
            <p className="evidence-scope">
              Only declared ranges are checked. A result does not prove the
              whole process is safe or establish malicious behavior.
            </p>
          )}
        </>
      )}
    </div>
  );
}

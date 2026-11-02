import React, { useContext } from "react";
import { Context, useData } from "./context.jsx";

export default function Details({ active }) {
  const { state: s } = useContext(Context),
    [data, error] = useData("details", { revision: s.revision }, active);
  return (
    <div className="details scroll">
      <p className="view-help">
        Source fingerprints, analysis settings and evidence provenance. Select a
        record in Results to inspect its individual evidence.
      </p>
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          <p>Data: {data.source.name}</p>
          <pre>SHA-256: {data.source.sha256}</pre>
          <p>Reference: {data.reference?.name || "None"}</p>
          {data.reference && <pre>SHA-256: {data.reference.sha256}</pre>}
          <p>
            {Object.entries(data.summary)
              .map(
                ([k, v]) =>
                  `${{ total: "Records", Review: "Need review", Unknown: "Unknown", "No finding": "No finding", rows_with_gaps: "Records with gaps" }[k] || k}: ${v}`,
              )
              .join(" · ")}
          </p>
          <details>
            <summary>Analysis settings</summary>
            <pre>{data.settings}</pre>
          </details>
          <details>
            <summary>Numeric reference profiles</summary>
            <pre>{data.profiles}</pre>
          </details>
          <p>
            Constant references use 1% of the absolute median as scale, with a
            1e-9 minimum.
          </p>
          <p>
            Deviation = distance from the median / scale. The threshold sets
            when to flag it.
          </p>
          <p>
            Imported records are unverified claims. Fingerprints do not prove
            who collected them.
          </p>
          <p>
            Engine: {data.engine}. {data.meaning}
          </p>
        </>
      )}
    </div>
  );
}

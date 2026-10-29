import React, { useState, useRef, useContext } from "react";
import { Context, useData } from "./context.jsx";
import { Button, rowKey, Select, Pager } from "./controls.jsx";

export default function Compare({ active }) {
  const { state: s, run } = useContext(Context),
    [refresh, setRefresh] = useState(0),
    [changePage, setChangePage] = useState(0);
  const [row, setRow] = useState(null),
    [changed, setChanged] = useState(false);
  const [kind, setKind] = useState("All"),
    [showRecords, setShowRecords] = useState(false);
  const [data, error] = useData(
    "comparison",
    { revision: s.revision, row, changes_only: changed },
    active,
    `${refresh}:${s.case_file?.sha256 || ""}`,
  );
  const choices = useRef(null);
  if (data) choices.current = data;
  const affected = (choices.current?.changes || []).filter(
    ([, reason]) => kind === "All" || reason.split(", ").includes(kind),
  );
  const pageRecords = affected.slice(changePage * 100, (changePage + 1) * 100);
  function follow(filter) {
    setKind(filter);
    setShowRecords(true);
    setRow(null);
    setChangePage(0);
  }
  return (
    <div className="column full">
      <p className="view-help">
        Compare this investigation with a saved case. Choose a case to review
        differences in settings and conclusions; matching sources are needed for
        record comparisons.
      </p>
      <div className="actions">
        <Button
          onClick={() =>
            run("compare", {}, (v) => {
              choices.current = v;
              setRow(null);
              setKind("All");
              setShowRecords(false);
              setChangePage(0);
              setRefresh((n) => n + 1);
            })
          }
        >
          Choose case
        </Button>
        <Button
          disabled={!choices.current?.sources}
          className={row === null && !showRecords ? "active" : ""}
          onClick={() => {
            setRow(null);
            setShowRecords(false);
          }}
        >
          Settings
        </Button>
        <Select
          label="Changed records"
          value={row ?? ""}
          options={[
            { value: "", label: "Select record" },
            ...pageRecords.map(([r, reason]) => ({
              value: r,
              label: `${r} · ${reason}`,
            })),
          ]}
          disabled={!affected.length}
          onChange={(v) => setRow(v ? Number(v) : null)}
        />
        {row === null && (
          <label>
            <input
              type="checkbox"
              checked={changed}
              onChange={(e) => setChanged(e.target.checked)}
            />
            Changes only
          </label>
        )}
      </div>
      {choices.current?.paired && (
        <div className="actions" aria-label="Comparison changes">
          {[
            ["Result", "outcome"],
            ["Priority", "priority"],
            ["Reasons", "reason"],
          ].map(([filter, label]) => {
            const count = choices.current.counts?.[filter] || 0;
            return (
              <Button
                key={filter}
                disabled={!count}
                className={showRecords && kind === filter ? "active" : ""}
                onClick={() => follow(filter)}
              >
                {count} changed{" "}
                {count === 1
                  ? label
                  : label === "priority"
                    ? "priorities"
                    : label + "s"}
              </Button>
            );
          })}
          <Button
            disabled={!choices.current.changes.length}
            className={showRecords && kind === "All" ? "active" : ""}
            onClick={() => follow("All")}
          >
            {choices.current.changes.length} changed{" "}
            {choices.current.changes.length === 1 ? "record" : "records"}
          </Button>
        </div>
      )}
      {affected.length > 100 && (
        <Pager
          page={changePage}
          total={affected.length}
          onChange={(n) => {
            setChangePage(n);
            setRow(null);
          }}
        />
      )}
      {showRecords && (
        <>
          <small>
            {affected.length} affected{" "}
            {affected.length === 1 ? "record" : "records"} ·{" "}
            {kind === "All" ? "All changes" : kind}
          </small>
          <div className="scroll changed-records">
            <table aria-label="Affected records">
              <thead>
                <tr>
                  <th>Record</th>
                  <th>Changed</th>
                </tr>
              </thead>
              <tbody>
                {pageRecords.map(([n, reason], i) => (
                  <tr
                    key={n}
                    tabIndex={row === n || (!row && i === 0) ? 0 : -1}
                    aria-selected={row === n}
                    className={row === n ? "selected" : ""}
                    onClick={() => setRow(n)}
                    onKeyDown={(e) =>
                      rowKey(
                        e,
                        pageRecords.map(([row]) => ({ row })),
                        n,
                        setRow,
                      )
                    }
                  >
                    <td>{n}</td>
                    <td>{reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="muted" role={error ? "alert" : undefined}>
        {error ||
          (data
            ? data.paired
              ? "Same incoming evidence · select a record to compare its decisions."
              : data.note
            : "Loading comparison…")}
      </p>
      {data?.sources && (
        <div className="comparison-sources">
          {["Current", "Previous"].map((label, i) => (
            <ComparisonSource
              key={label}
              label={label}
              file={i === 0 ? s.case_file : data.cases?.[i]}
              source={data.provenance?.[i]}
              fallback={data.sources[i]}
            />
          ))}
        </div>
      )}
      <div className="scroll grow">
        <table className="comparison" aria-label="Comparison">
          <thead>
            <tr>
              <th>Field</th>
              <th>Current</th>
              <th>Previous</th>
              <th>Change</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows.map((r, i) => (
              <tr key={i} className={r.changed ? "changed" : ""}>
                <td>{r.label}</td>
                <td>{r.current}</td>
                <td>{r.previous}</td>
                <td>{r.changed ? "Changed" : "Same"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ComparisonSource({ label, file, source, fallback }) {
  return (
    <div className="comparison-source">
      <p>
        {label} · {file?.name || "Unsaved case"}
        {file?.modified ? " · unsaved changes" : ""}
      </p>
      <small>
        {source
          ? `Data: ${source.data.name} · SHA-256 ${source.data.sha256.slice(0, 12)}…`
          : fallback}
      </small>
      <details>
        <summary>{label} source</summary>
        {file ? (
          <>
            <pre>
              Case: {file.path}
              {"\n"}SHA-256: {file.sha256}
            </pre>
            {file.modified && (
              <p>
                This fingerprint identifies the loaded file before your changes.
              </p>
            )}
          </>
        ) : (
          <p>Case has not been saved.</p>
        )}
        {source && (
          <>
            <pre>
              Data: {source.data.name}
              {"\n"}Path:{" "}
              {source.paths.current ||
                "Embedded in case; original path not stored"}
              {"\n"}SHA-256: {source.data.sha256}
            </pre>
            {source.reference ? (
              <pre>
                Reference: {source.reference.name}
                {"\n"}Path:{" "}
                {source.paths.reference ||
                  "Embedded in case; original path not stored"}
                {"\n"}SHA-256: {source.reference.sha256}
              </pre>
            ) : (
              <p>Reference: None</p>
            )}
          </>
        )}
      </details>
    </div>
  );
}

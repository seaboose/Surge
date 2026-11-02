import React, { useState, useContext } from "react";
import { Context, useData } from "./context.jsx";
import {
  Button,
  InfoBubble,
  rowKey,
  Select,
  Pager,
  Split,
} from "./controls.jsx";
import Evidence from "./Evidence.jsx";

export default function Evaluate({ active }) {
  const { state: s, run } = useContext(Context);
  const [outcome, setOutcome] = useState("All"),
    [group, setGroup] = useState(""),
    [page, setPage] = useState(0),
    [row, setRow] = useState(null);
  const [data, error] = useData(
    "evaluation",
    { revision: s.revision, outcome, group, page },
    active,
  );
  const rate = (r) => {
    if (r.value === null) return "Not available";
    const percent = r.value * 100;
    // Do not round a small nonzero miss rate to zero, or imperfect recall to 100%.
    const digits =
      (percent > 0 && percent < 0.1) || (percent > 99.9 && percent < 100)
        ? 2
        : 1;
    return `${percent.toFixed(digits)}% (${r.numerator}/${r.denominator})`;
  };
  function filter(value) {
    setOutcome(value);
    setPage(0);
    setRow(null);
  }
  const selected = data?.rows?.find((r) => r.row === row);
  const left = (
    <div className="column full evaluation">
      <p className="view-help">
        Measure detection performance using independently assigned labels.
        Import labels for the analyzed evidence below.
      </p>
      <div className="actions">
        <Button onClick={() => run("labels_load")}>Import labels</Button>
        <Button onClick={() => run("labels_template")}>
          Save label template
        </Button>
        <Button disabled={!s.labels} onClick={() => run("evaluation_save")}>
          Save evaluation
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
      {!s.labels && (
        <div className="scroll grow">
          <ol className="evaluation-steps">
            <li>Save a label template for this evidence.</li>
            <li>
              Ask a reviewer to label it from independent evidence, without
              seeing Surge's decisions.
            </li>
            <li>
              Import the completed JSON file to review detection performance.
            </li>
          </ol>
          <span>Labeling guidance</span>
          <InfoBubble label="Labeling guidance">
            Use legitimate or target for truth, a short group such as
            “legitimate update”, and a note explaining the label. Leave unknown
            truth as null.
            <br />
            <br />
            Record the author, method, reference/test partition, purpose, and
            independence from the detector. Use untouched sessions, users or
            time periods where appropriate. Current data is the test source;
            reference data sets the numeric profile. Labels never enter
            detection.
          </InfoBubble>
          <p>
            Keep labels outside the source data and reference. Do not map answer
            fields into rules or numeric signals.
          </p>
          <p>
            Labels are separate from the case. Keep the case, labels and
            evaluation together; import labels again after reopening a case.
          </p>
          <small>
            Independent annotation and representative data are needed before
            claiming real detection accuracy.
          </small>
        </div>
      )}
      {data?.available && (
        <>
          <small>
            {data.summary.labeled} / {data.summary.total} labeled ·{" "}
            {data.summary.legitimate} legitimate · {data.summary.targets}{" "}
            targets
          </small>
          <div className="actions" aria-label="Evaluation counts">
            <Button
              className={outcome === "All" ? "active" : ""}
              onClick={() => filter("All")}
            >
              All · {data.summary.total}
            </Button>
            {Object.entries(data.summary.counts).map(([key, count]) => (
              <Button
                key={key}
                className={outcome === key ? "active" : ""}
                onClick={() => filter(key)}
              >
                {key} · {count}
              </Button>
            ))}
          </div>
          <small>Rates · all labeled records, before view filters</small>
          <div className="evaluation-rates">
            <span>
              False positives: {rate(data.summary.rates.false_positive)}
            </span>
            <span>Missed: {rate(data.summary.rates.missed)}</span>
            <span>Precision: {rate(data.summary.rates.precision)}</span>
            <span>Recall: {rate(data.summary.rates.recall)}</span>
          </div>
          <small>
            Missed includes {data.summary.unresolved_targets} unassessable
            targets. Unresolved means legitimate labels with missing evidence.
            Rates use labeled records only.
          </small>
          <div className="actions">
            <Select
              label="Group"
              value={group}
              options={[
                { value: "", label: "All groups" },
                ...data.groups.map((g) => ({ value: g.group, label: g.group })),
              ]}
              onChange={(v) => {
                setGroup(v || "");
                setPage(0);
                setRow(null);
              }}
            />
            <Button
              onClick={() => {
                filter("All");
                setGroup("");
              }}
            >
              Clear filters
            </Button>
          </div>
          <details className="evaluation-details">
            <summary>Groups and provenance</summary>
            <p>
              {data.provenance.purpose} · Independence:{" "}
              {data.provenance.independent_of_detector
                ? "declared by label author"
                : "not declared"}
            </p>
            <pre>
              Author: {data.provenance.author}
              {"\n"}Method: {data.provenance.method}
              {"\n"}Partition: {data.provenance.partition}
            </pre>
            <table aria-label="Label groups">
              <thead>
                <tr>
                  <th>Group</th>
                  <th>False positives</th>
                  <th>Missed</th>
                </tr>
              </thead>
              <tbody>
                {data.groups.map((g) => (
                  <tr key={g.group}>
                    <td>{g.group}</td>
                    <td>{rate(g.rates.false_positive)}</td>
                    <td>{rate(g.rates.missed)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.warnings.map((w) => (
              <p key={w} className="warning">
                {w}
              </p>
            ))}
            <pre>
              Test: {data.source.name}
              {"\n"}SHA-256: {data.source.sha256}
              {"\n"}Reference: {data.reference?.name || "None"}
              {"\n"}SHA-256: {data.reference?.sha256 || "None"}
              {"\n"}Labels: {data.labels.name}
              {"\n"}SHA-256: {data.labels.sha256}
              {"\n"}Settings SHA-256: {data.settings_sha256}
            </pre>
            <p>{data.definitions.rates}</p>
          </details>
          <small className="warning">
            {data.provenance.purpose} labels · independence{" "}
            {data.provenance.independent_of_detector
              ? "declared, not verified"
              : "not declared"}
            . {data.warnings.length} notes in Groups and provenance.
          </small>
          <small>
            {data.total} records · {outcome} · {group || "All groups"}
          </small>
          <div className="scroll grow">
            <table aria-label="Evaluation records">
              <thead>
                <tr>
                  <th>Record</th>
                  <th>Label</th>
                  <th>Result</th>
                  <th>Group</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr
                    key={r.row}
                    tabIndex={row === r.row || (!row && i === 0) ? 0 : -1}
                    aria-selected={row === r.row}
                    className={row === r.row ? "selected" : ""}
                    onClick={() => setRow(r.row)}
                    onKeyDown={(e) => rowKey(e, data.rows, r.row, setRow)}
                  >
                    <td>{r.row}</td>
                    <td>{r.truth || "Unlabeled"}</td>
                    <td>
                      {r.outcome}
                      {r.gaps ? " · gaps" : ""}
                    </td>
                    <td>{r.group || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={data.page}
            total={data.total}
            onChange={(n) => {
              setPage(n);
              setRow(null);
            }}
          />
        </>
      )}
    </div>
  );
  return (
    <Split
      name="surge.evaluation.split"
      left={left}
      right={
        selected ? (
          <div className="column full">
            <div className="evaluation-label">
              <p>
                Record {row} · Label: {selected.truth || "Unlabeled"} ·{" "}
                {selected.outcome}
              </p>
              <p>{selected.note || "No independent label supplied."}</p>
            </div>
            <div className="grow">
              <Evidence row={row} active={active} />
            </div>
          </div>
        ) : (
          <p>
            Select a record to compare its label with the detection evidence.
          </p>
        )
      }
    />
  );
}

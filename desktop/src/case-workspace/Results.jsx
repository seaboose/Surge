import React, { useState, useEffect, useRef, useContext } from "react";
import { Context, request, useData, useDebounce } from "./context.jsx";
import {
  Button,
  InfoBubble,
  ExportOptions,
  rowKey,
  Select,
  Pager,
  Split,
} from "./controls.jsx";
import Evidence from "./Evidence.jsx";

export default function Results({ active }) {
  const {
    state: s,
    run,
    setError,
    capture,
    captureVisible,
    working,
    demoReadyToSave,
    saveActionLabel,
    savedInLibrary,
  } = useContext(Context);
  const [query, setQuery] = useState(""),
    [minimum, setMinimum] = useState("All"),
    [hide, setHide] = useState(
      () =>
        !s.inspected_capture &&
        !(s.case_file && s.summary.Review === 0 && s.summary.Unknown === 0),
    );
  const [page, setPage] = useState(0),
    [row, setRow] = useState(null),
    [reveal, setReveal] = useState(null);
  const needle = useDebounce(query);
  const [data, error] = useData(
    "findings",
    {
      revision: s.revision,
      query: needle,
      minimum,
      hide,
      page,
      reveal,
      locate: reveal,
    },
    active,
  );
  const chartVisible = useRef(false);
  if (data)
    chartVisible.current =
      s.numeric_evidence &&
      (!data.rows.length ||
        !row ||
        row === reveal ||
        data.rows.some((r) => r.row === row && r.numeric_evidence));
  const searchRef = useRef();
  useEffect(() => {
    const handler = (e) => {
      if (active && (e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [active]);
  useEffect(() => {
    setPage(0);
    setReveal(null);
  }, [needle, minimum, hide]);
  useEffect(() => {
    if (data && !data.rows.some((r) => r.row === row))
      setRow(data.rows[0]?.row ?? null);
  }, [data]);
  function choose(n) {
    setReveal(n);
    setRow(n);
  }
  const left = (
    <div className="column full">
      {savedInLibrary && <small>Saved in library</small>}
      {s.observation_counts && (
        <div role="region" aria-label="Observation counts">
          <small>
            Viewed evidence: {s.observation_counts.samples} retained samples ·{" "}
            {s.observation_counts.observations} range observations
            {s.observation_counts.notices > 0
              ? ` · ${s.observation_counts.notices} collection notices`
              : ""}
            .
          </small>
          <InfoBubble label="About sample counts">
            {s.observation_counts.ranges_per_sample !== null
              ? `Each retained sample contains ${s.observation_counts.ranges_per_sample} range observations.`
              : "The number of range observations varies by sample."}{" "}
            Counts describe the evidence currently open. A live collection may
            contain newer samples.
          </InfoBubble>
        </div>
      )}
      <div className="actions">
        <Button
          title="Save the inspected evidence, settings and results"
          className={demoReadyToSave ? "primary" : undefined}
          onClick={() => run("save")}
        >
          {saveActionLabel}
        </Button>
        <ExportOptions
          items={[
            {
              label: "Export case file",
              disabled: working,
              run: () => run("export_case"),
              description:
                "Save a portable copy of the inspected evidence, settings, and results.",
            },
            {
              label: "Export alerts",
              disabled: working,
              run: () => run("alerts", { minimum }),
              description:
                "Export findings using the selected priority; normal observations are excluded.",
            },
            ...(captureVisible
              ? [
                  {
                    label: "Export captured records",
                    disabled: working || !capture?.has_evidence,
                    run: () => run("native_export"),
                    description:
                      "Export the retained collection window as JSONL. It may be newer than the inspected snapshot.",
                  },
                ]
              : []),
          ]}
        />
      </div>
      <div className="actions">
        <input
          ref={searchRef}
          className="grow"
          aria-label="Search records"
          placeholder="Record ID, session, user, rule"
          maxLength={4096}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setQuery("");
          }}
        />
        <Button onClick={() => setQuery("")}>Clear</Button>
      </div>
      <div className="actions">
        <Select
          label="Priority"
          value={minimum}
          options={["All", "Notice", "Warning", "Error", "Critical"]}
          onChange={setMinimum}
        />
        <label>
          <input
            type="checkbox"
            checked={hide}
            onChange={(e) => setHide(e.target.checked)}
          />
          Findings only
        </label>
      </div>
      <small>
        {data?.total ?? "…"} shown / {s.summary.total} · {s.summary.Review} need
        review · {s.summary.Unknown} unknown
      </small>
      <details className="result-guide">
        <summary>What the results mean</summary>
        <p>
          No finding: no issue detected in checked evidence; this does not prove
          whole-process integrity. Review: evidence needs investigation.
          Unknown: evidence is missing or inconclusive.
        </p>
        <p>Priority keeps gaps visible. Exports use priority.</p>
        <p>
          Search and Findings only filter the displayed records. Clear the
          filters to show all observations.
        </p>
      </details>
      {(query || minimum !== "All" || hide) && (
        <small aria-label="Active filters">
          {[
            query ? `Search: ${query}` : null,
            minimum !== "All" ? `Priority: ${minimum}+` : null,
            hide ? "Findings only" : null,
          ]
            .filter(Boolean)
            .join(" · ") || "All records · no filters"}
        </small>
      )}
      {data?.hidden_gaps > 0 && (
        <small className="warning">
          {data.hidden_gaps} records with gaps hidden by search. Clear to see
          them.
        </small>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="scroll grow">
        <table className="results-table" aria-label="Results">
          {(s.inspected_capture || s.saved_result) && (
            <caption>Observations</caption>
          )}
          <thead>
            <tr>
              <th>Record</th>
              <th>Priority</th>
              <th>Result</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows.map((r, i) => (
              <tr
                key={r.row}
                className={row === r.row ? "selected" : ""}
                tabIndex={row === r.row || (!row && i === 0) ? 0 : -1}
                aria-selected={row === r.row}
                onClick={() => {
                  setReveal(null);
                  setRow(r.row);
                }}
                onKeyDown={(e) =>
                  rowKey(e, data.rows, r.row, (n) => {
                    setReveal(null);
                    setRow(n);
                  })
                }
              >
                <td>{r.row}</td>
                <td
                  className={
                    ["Critical", "Error"].includes(r.priority) ? "danger" : ""
                  }
                >
                  {r.priority || "—"}
                </td>
                <td>{r.status}</td>
                <td>{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && !data.total && (
        <div>
          <p>
            No records match these filters. This does not establish that the
            data is safe.
          </p>
          {(query || minimum !== "All" || hide) && (
            <Button
              onClick={() => {
                setQuery("");
                setMinimum("All");
                setHide(false);
                setPage(0);
                setReveal(null);
              }}
            >
              Show all observations
            </Button>
          )}
        </div>
      )}
      {data && (
        <Pager
          page={data.page}
          total={data.total}
          onChange={(n) => {
            setReveal(null);
            setPage(n);
          }}
        />
      )}
      {chartVisible.current && (
        <Chart
          row={row}
          select={choose}
          outside={row === reveal && data?.outside}
          active={active}
        />
      )}
      {data?.outside && (
        <Button onClick={() => setReveal(null)}>Return to filters</Button>
      )}
    </div>
  );
  return (
    <Split
      name="surge.findings.split"
      left={left}
      right={
        row ? (
          <Evidence row={row} active={active} />
        ) : (
          <p>Select a record to inspect evidence.</p>
        )
      }
    />
  );
}

function Chart({ row, select, outside, active }) {
  const { state: s, setError } = useContext(Context);
  const host = useRef(),
    [width, setWidth] = useState(0);
  const measured = useRef(width);
  useEffect(() => {
    if (!active) return;
    let timer;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) {
        measured.current = Math.max(
          180,
          Math.min(2400, Math.round(entry.contentRect.width)),
        );
        clearTimeout(timer);
        timer = setTimeout(() => setWidth(measured.current), 120);
      }
    });
    observer.observe(host.current);
    return () => {
      observer.disconnect();
      clearTimeout(timer);
    };
  }, [active]);
  const [data, error] = useData(
    "chart",
    { revision: s.revision, width, row },
    active && width > 0,
  );
  const lastPlot = useRef(null);
  if (data) lastPlot.current = { width, data };
  const plot = data || lastPlot.current?.data;
  const plotWidth = data ? width : lastPlot.current?.width || width || 600;
  function selectNearest(event) {
    // Expanded SVG hit areas can overlap. Resolve the displayed geometry at
    // the pointer, rather than trusting whichever neighboring group is on top.
    if (!event.target.closest("g")) return;
    const matrix = event.currentTarget.getScreenCTM();
    if (!matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(
      matrix.inverse(),
    );
    const candidates = (plot?.points || []).map((p) => ({ ...p, stem: true }));
    if (data?.selected && !candidates.some((p) => p.row === data.selected.row))
      candidates.push({ ...data.selected, stem: false });
    let nearest;
    for (const p of candidates) {
      const low = p.stem ? Math.min(p.y, 82) : p.y;
      const high = p.stem ? Math.max(p.y, 82) : p.y;
      const distance = Math.hypot(
        point.x - p.x,
        point.y - Math.max(low, Math.min(high, point.y)),
      );
      const endpoint = Math.hypot(point.x - p.x, point.y - p.y);
      if (
        !nearest ||
        distance < nearest.distance ||
        (distance === nearest.distance && endpoint < nearest.endpoint)
      )
        nearest = { row: p.row, distance, endpoint };
    }
    if (nearest) select(nearest.row);
  }
  async function step(direction) {
    try {
      const v = await request("chart_step", {
        revision: s.revision,
        row: row || 0,
        step: direction,
      });
      if (v.row) select(v.row);
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <div
      ref={host}
      className="chart"
      tabIndex="0"
      role="group"
      aria-label="Numeric chart"
      onKeyDown={(e) => {
        if (["ArrowLeft", "ArrowRight"].includes(e.key)) {
          e.preventDefault();
          step(e.key === "ArrowLeft" ? -1 : 1);
        }
      }}
    >
      <small>Max deviation / threshold · capped at 2×</small>
      <svg
        width="100%"
        height="104"
        viewBox={`0 0 ${plotWidth} 104`}
        aria-label="All records in source order"
        onClick={selectNearest}
      >
        <line
          x1="58"
          x2={plotWidth - 18}
          y1="54"
          y2="54"
          className="threshold"
        />
        <text x="10" y="29">
          2×
        </text>
        <text x="10" y="57">
          1×
        </text>
        <text x="10" y="85">
          0
        </text>
        {plot?.points.map((p) => (
          <g
            key={p.row}
            className={p.score >= plot.threshold ? "peak" : ""}
            data-row={p.row}
          >
            <title>
              Record {p.row} · {p.field} · deviation {p.score} · peak of{" "}
              {p.count}
            </title>
            <line x1={p.x} x2={p.x} y1="82" y2={p.y} />
            <circle cx={p.x} cy={p.y} r="2.5" />
            <line x1={p.x} x2={p.x} y1="82" y2={p.y} className="hit-target" />
          </g>
        ))}
        {data?.selected && (
          <g className="selected-marker">
            <circle
              cx={data.selected.x}
              cy={data.selected.y}
              r="5"
              className="selected-point"
            />
            <circle
              cx={data.selected.x}
              cy={data.selected.y}
              r="6"
              className="selected-hit"
            />
          </g>
        )}
      </svg>
      {error && <p role="alert">{error}</p>}
      <div className="chart-readout">
        {data?.selected ? (
          <>
            Record {data.selected.row}
            {outside ? " · outside filters" : ""} · {data.selected.field}:{" "}
            {data.selected.value}
            <br />
            Deviation: {data.selected.score}
          </>
        ) : (
          "Click a point to inspect its exact value."
        )}
      </div>
      <small>All records in source order · click / ← →</small>
    </div>
  );
}

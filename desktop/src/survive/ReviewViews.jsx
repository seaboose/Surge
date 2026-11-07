import React, { useId, useMemo, useRef, useState } from "react";
import { Info } from "../Info.jsx";
import { number, pretty } from "./replay-model.mjs";

const views = [
  ["timeline", "Timeline"],
  ["movement", "Movement"],
  ["records", "Event records"],
];

export function ViewPicker({ visible, setVisible, together, setTogether }) {
  function choose(key) {
    if (!together) return setVisible([key]);
    if (!visible.includes(key)) return setVisible([...visible, key]);
    if (visible.length > 1) setVisible(visible.filter((item) => item !== key));
  }
  return (
    <div
      className="survive-view-picker"
      role="group"
      aria-label="Evidence views"
    >
      {views.map(([key, label]) => (
        <button
          type="button"
          key={key}
          aria-pressed={visible.includes(key)}
          onClick={() => choose(key)}
        >
          {label}
        </button>
      ))}
      <label>
        <input
          type="checkbox"
          checked={together}
          onChange={(e) => {
            setTogether(e.target.checked);
            if (!e.target.checked) setVisible([visible[0]]);
          }}
        />{" "}
        Show together
      </label>
      <Info label="Evidence views">
        Choose a view, or enable Show together to keep several open. Every view
        shares the replay time and selected evidence.
      </Info>
    </div>
  );
}

// Display the same description for pointer hover and keyboard focus without
// adding a tab stop for every pixel of a continuous chart.
export function usePlotHint() {
  const container = useRef(null);
  const [hint, setHint] = useState(null);
  const id = useId();
  function show(event, text, anchor = event.currentTarget) {
    if (!container.current) return;
    const bounds = container.current.getBoundingClientRect();
    const target = anchor.getBoundingClientRect();
    const px = Number.isFinite(event.clientX)
      ? event.clientX
      : target.left + target.width / 2;
    const py = Number.isFinite(event.clientY) ? event.clientY : target.bottom;
    const left = Math.max(
      0,
      Math.min(px - bounds.left, bounds.width - Math.min(290, bounds.width)),
    );
    const top =
      py + 85 <= window.innerHeight
        ? py - bounds.top + 12
        : py - bounds.top - 75;
    setHint({ text, left, top: Math.max(0, top) });
  }
  function dismiss() {
    setHint(null);
  }
  const bindings = (text) => ({
    onPointerEnter: (e) => show(e, text),
    onPointerLeave: dismiss,
    onFocus: (e) => show(e, text),
    onBlur: dismiss,
    onKeyUp: (e) => {
      if (e.key === "Escape") dismiss();
    },
  });
  return {
    container,
    show,
    dismiss,
    bindings,
    id,
    bubble: hint && (
      <div
        id={id}
        role="tooltip"
        className="survive-plot-hint"
        style={{ left: hint.left, top: hint.top }}
      >
        {hint.text}
      </div>
    ),
  };
}

const pageSize = 30;

export function EventRecords({
  rows,
  domain,
  record,
  constraints,
  choose,
  final,
  analysisState,
}) {
  const [samples, setSamples] = useState(false);
  const [pageOverride, setPageOverride] = useState(null);
  const bySequence = useMemo(
    () => new Map(constraints.map((r) => [r.end_seq, r])),
    [constraints],
  );
  const windowRows = useMemo(
    () =>
      rows.filter(
        (r) =>
          r.elapsed_s >= domain[0] &&
          r.elapsed_s <= domain[1] &&
          (samples || r.event !== "sample"),
      ),
    [rows, samples, domain[0], domain[1]],
  );
  // Include the selected position sample in its original sequence without
  // rebuilding the full record list for every tick of playback.
  const extra =
    !samples &&
    record?.event === "sample" &&
    record.elapsed_s >= domain[0] &&
    record.elapsed_s <= domain[1];
  let first = 0,
    end = windowRows.length;
  while (first < end) {
    const middle = (first + end) >> 1;
    if (windowRows[middle].seq < record?.seq) first = middle + 1;
    else end = middle;
  }
  const selectedIndex =
    extra || windowRows[first]?.seq === record?.seq ? first : -1;
  const count = windowRows.length + (extra ? 1 : 0);
  const lastPage = Math.max(0, Math.ceil(count / pageSize) - 1);
  const scope = [domain[0], domain[1], samples, record?.seq].join("/");
  const page =
    pageOverride?.scope === scope
      ? Math.min(pageOverride.page, lastPage)
      : Math.max(0, Math.floor(selectedIndex / pageSize));
  const setPage = (next) => setPageOverride({ scope, page: next });
  const pageRows = [];
  for (
    let i = page * pageSize;
    i < Math.min(count, (page + 1) * pageSize);
    i++
  ) {
    pageRows.push(
      extra && i === first
        ? record
        : windowRows[extra && i > first ? i - 1 : i],
    );
  }
  return (
    <section className="survive-linked-records" aria-label="Related events">
      <div className="survive-controls">
        <h3>Event records</h3>
        <Info label="Event records">
          Each row is one source record inside the visible time window. Select
          its sequence number to open that moment in replay and Selected
          evidence.
        </Info>
        <label>
          <input
            type="checkbox"
            checked={samples}
            onChange={(e) => {
              setSamples(e.target.checked);
              setPageOverride(null);
            }}
          />{" "}
          Include position samples
        </label>
      </div>
      <div className="survive-table-wrap">
        <table>
          <thead>
            <tr>
              {[
                "Sequence",
                "Game time",
                "Event",
                "Detail / related ID",
                "Assessment",
              ].map((name) => (
                <th scope="col" key={name}>
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((r) => {
              const status = bySequence.get(r.seq)?.status;
              return (
                <tr
                  key={r.seq}
                  className={record?.seq === r.seq ? "survive-selected" : ""}
                  onClick={() => choose(r)}
                >
                  <td>
                    <button
                      className="survive-sequence"
                      aria-label={`Inspect record ${r.seq}`}
                      aria-current={r.seq === record?.seq ? "true" : undefined}
                    >
                      {r.seq}
                    </button>
                  </td>
                  <td>{number(r.elapsed_s, 3)} s</td>
                  <td>{pretty(r.event)}</td>
                  <td>
                    {pretty(r.detail)}
                    {r.related_id ? ` · ${r.related_id}` : ""}
                  </td>
                  <td>
                    {final
                      ? status || "Recorded event"
                      : analysisState === "unavailable"
                        ? "Unknown"
                        : "Pending"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {count ? (
        <div className="survive-timeline-actions">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>
            Previous events
          </button>
          <span>
            Page {page + 1} of {lastPage + 1} · {count} records
          </span>
          <button disabled={page >= lastPage} onClick={() => setPage(page + 1)}>
            Next events
          </button>
        </div>
      ) : (
        <p>No matching records in this time window.</p>
      )}
    </section>
  );
}

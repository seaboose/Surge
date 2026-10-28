import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  MARKER_FILTERS,
  recordingPresentation,
  sessionSummary,
  timelineMarkers,
  TIMELINE_LANES,
  clampTimelineRange,
  zoomTimelineRange,
  markerOverlapsRange,
  clusterTimelineMarkers,
  timelineOverview,
} from "./survive-flow.mjs";
import "./timeline-detail.css";

const format = (n, digits = 1) =>
  Number.isFinite(n) ? n.toFixed(digits) : "Unavailable";

export function useChartWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(220, entry.contentRect.width)),
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export function WorkflowBar({ stage, onNavigate, hasRecording, hasReport }) {
  return (
    <nav className="survive-workflow" aria-label="Session workflow">
      {["Play", "Record", "Review", "Explain", "Export"].map((name, i) => (
        <button
          key={name}
          aria-current={stage === name.toLowerCase() ? "step" : undefined}
          disabled={
            (name === "Review" && !hasRecording) ||
            (name === "Export" && !hasReport)
          }
          onClick={() => onNavigate(name.toLowerCase())}
        >
          <span>{i + 1}</span> {name}
        </button>
      ))}
    </nav>
  );
}

export function RecordingStrip({
  capture,
  updatedAt,
  requestFailed,
  busy,
  onStop,
  trialRunning,
}) {
  const [now, setNow] = useState(performance.now());
  const active = ["waiting", "recording"].includes(capture?.state);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(performance.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  const age = updatedAt ? Math.max(0, (now - updatedAt) / 1000) : 0;
  const state = recordingPresentation(capture, age, requestFailed);
  return (
    <section
      className={`survive-record-strip tone-${state.tone}`}
      aria-label="Recording status"
    >
      <div>
        <strong>
          <span className="survive-state-dot" />
          {state.label}
        </strong>
        <div className="survive-clock-labels">
          <span>
            Game elapsed <b>{format(capture?.source_elapsed_s)} s</b>
          </span>
          <span>{capture?.records ?? 0} received records</span>
          {active && (
            <span>
              {capture?.records > 0
                ? `Last receipt ${format((capture?.health?.stale_s ?? 0) + age)} s ago`
                : "Awaiting first receipt"}
            </span>
          )}
        </div>
        <details className="survive-inline-help">
          <summary>Recording details</summary>
          <dl>
            <dt>Recorder elapsed</dt>
            <dd>{format(capture?.elapsed_s)} s, including startup</dd>
            <dt>Receipt age</dt>
            <dd>
              Time since received game data; not input or network latency.
            </dd>
            <dt>Recording health</dt>
            <dd>
              {capture?.health?.sequence_gaps ?? "Unmeasured"} sequence gaps ·{" "}
              {capture?.health?.parse_errors ?? "Unmeasured"} parse errors
            </dd>
          </dl>
        </details>
        {trialRunning && !active && (
          <small>
            The game is still running. Start the next round after it exits.
          </small>
        )}
      </div>
      <button disabled={busy || !active} onClick={onStop}>
        Stop recording
      </button>
    </section>
  );
}

export function SessionSummary({ snapshot }) {
  const s = sessionSummary(snapshot);
  const pending = snapshot?.capture?.analysis_state !== "complete";
  return (
    <section
      className="survive-panel survive-session-summary"
      aria-label="Session summary"
    >
      <div className="survive-summary-title">
        <h2>Session summary</h2>
        <span
          className={`survive-status-badge ${pending ? "tone-unknown" : "tone-verified"}`}
        >
          {pending ? "Partial / pending assessment" : "Analysis complete"} ·{" "}
          {s.completion}
        </span>
      </div>
      <dl className="survive-summary-metrics">
        {[
          ["Game duration", `${format(s.duration)} s`],
          ["Hits", s.hits ?? "Unavailable"],
          ["Avoided initial threats", s.avoided ?? "Unavailable"],
          [
            "Sampled coverage",
            Number.isFinite(s.coverage)
              ? s.coverage === 100
                ? "100%"
                : s.coverage > 99.99
                  ? ">99.99% (<100%)"
                  : s.coverage > 0 && s.coverage < 0.01
                    ? "<0.01%"
                    : `${format(s.coverage, 2)}%`
              : "Unavailable",
          ],
          ["Review findings", s.reviews ?? "Pending"],
          ["Unknown observations", s.unknown ?? "Pending"],
        ].map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <details className="survive-inline-help">
        <summary>What do these numbers mean?</summary>
        <p>
          Avoided initial threats: initially threatening geometry that expired
          without a hit; excludes terrain and causal attribution. Sampled
          coverage describes recorded position intervals, not a clean-play
          verdict. Pending or missing measurements are not zero.
        </p>
      </details>
    </section>
  );
}

export function MarkerTimeline({
  events,
  constraints,
  points,
  domain,
  duration,
  time,
  selectTime,
  chooseRecord,
  chooseConstraint,
  truncated,
  onDomainChange,
  recordingId,
}) {
  const [ref, width] = useChartWidth();
  const [filters, setFilters] = useState(
    Object.fromEntries(Object.keys(MARKER_FILTERS).map((k) => [k, true])),
  );
  const [expanded, setExpanded] = useState(null);
  const [listPage, setListPage] = useState(0);
  const [drag, setDrag] = useState(null);
  const gesture = useRef(null);
  const source =
    recordingId || events[0]?.session_id || constraints[0]?.session_id;
  useEffect(() => {
    setExpanded(null);
    setListPage(0);
    setDrag(null);
    setRangeDraft(null);
    gesture.current = null;
  }, [source]);
  const markers = useMemo(
    () => timelineMarkers(events, constraints, points, truncated),
    [events, constraints, points, truncated],
  );
  const total = Math.max(
    0.001,
    Number.isFinite(duration) ? duration : domain[1],
    markers.at(-1)?.time || 0,
  );
  const range = clampTimelineRange(domain, total);
  const enabled = useMemo(
    () =>
      markers.filter((r) => r.category === "capture" || filters[r.category]),
    [markers, filters],
  );
  const visible = useMemo(
    () => enabled.filter((r) => markerOverlapsRange(r, range)),
    [enabled, range[0], range[1]],
  );
  const unknownCount = useMemo(
    () => markers.filter((r) => r.category === "gaps").length,
    [markers],
  );
  const left = width < 400 ? 68 : 86,
    right = width - 12,
    plotWidth = Math.max(1, right - left);
  const x = (t) => left + ((t - range[0]) / (range[1] - range[0])) * plotWidth;
  const overviewX = (t) => 10 + (t / total) * (width - 20);
  const groups = useMemo(
    () => clusterTimelineMarkers(visible, range, plotWidth),
    [visible, range[0], range[1], plotWidth],
  );
  const buckets = useMemo(
    () => timelineOverview(markers, total),
    [markers, total],
  );
  const highest = Math.max(1, ...buckets.map((b) => b.count));
  const changeRange = (value) =>
    onDomainChange?.(value === null ? null : clampTimelineRange(value, total));
  const activate = (marker) =>
    marker.constraint
      ? chooseConstraint(marker.constraint)
      : chooseRecord(marker.row);
  const showGroup = (group) => {
    if (group.items.length === 1) activate(group.items[0]);
    else {
      setExpanded(group.items);
      setListPage(0);
    }
  };
  const coordinate = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return Math.max(
      0,
      Math.min(
        total,
        ((event.clientX - bounds.left - 10) / (bounds.width - 20)) * total,
      ),
    );
  };
  function beginRange(event) {
    if (!onDomainChange || event.button !== 0) return;
    const start = coordinate(event);
    gesture.current = { start, pointer: event.pointerId };
    setDrag([start, start]);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }
  function moveRange(event) {
    if (gesture.current?.pointer !== event.pointerId) return;
    setDrag([gesture.current.start, coordinate(event)]);
  }
  function finishRange(event) {
    if (gesture.current?.pointer !== event.pointerId) return;
    const { start } = gesture.current,
      end = coordinate(event);
    gesture.current = null;
    setDrag(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    // A click recenters the current window. A drag selects a new bounded window.
    const threshold = (total * 4) / Math.max(1, width - 20);
    const span = range[1] - range[0],
      first = Math.max(0, Math.min(total - span, end - span / 2));
    changeRange(
      Math.abs(end - start) <= threshold ? [first, first + span] : [start, end],
    );
  }
  const shownRange = drag ? clampTimelineRange(drag, total) : range;
  const visibleList = expanded || visible;
  const maxPage = Math.max(0, Math.ceil(visibleList.length / 30) - 1),
    boundedPage = Math.min(listPage, maxPage);
  const [rangeDraft, setRangeDraft] = useState(null);
  function applyRange(event) {
    event.preventDefault();
    const values = rangeDraft || range.map(String);
    if (values.every((v) => v.trim() !== "" && Number.isFinite(Number(v))))
      changeRange(values.map(Number));
    setRangeDraft(null);
  }
  return (
    <section
      className="survive-panel survive-timeline-detail"
      aria-label="Shared event timeline"
    >
      <div className="survive-timeline-heading">
        <h3>Timeline</h3>
        <span>
          {format(range[0], 2)}–{format(range[1], 2)} s of {format(total, 1)} s
        </span>
      </div>
      <div ref={ref} className="survive-timeline-canvas">
        <svg
          width="100%"
          height="62"
          viewBox={`0 0 ${width} 62`}
          role="img"
          aria-label="Whole-round timeline overview"
          className="survive-timeline-overview"
          onPointerDown={beginRange}
          onPointerMove={moveRange}
          onPointerUp={finishRange}
          onPointerCancel={() => {
            gesture.current = null;
            setDrag(null);
          }}
        >
          <title>
            Drag to zoom into a time range. All recorded markers remain
            represented, including hidden filter categories.
          </title>
          {buckets.map((b, i) => (
            <g key={i} pointerEvents="none">
              <rect
                x={overviewX(b.start)}
                y={35 - (27 * b.count) / highest}
                width={Math.max(1, (width - 20) / buckets.length - 1)}
                height={Math.max(1, (27 * b.count) / highest)}
                className="survive-overview-bin"
              />
              {b.reviews > 0 && (
                <rect
                  x={overviewX(b.start)}
                  y="37"
                  width={Math.max(1, (width - 20) / buckets.length - 1)}
                  height="4"
                  className="survive-overview-review"
                />
              )}
              {b.unknown > 0 && (
                <rect
                  x={overviewX(b.start)}
                  y="43"
                  width={Math.max(1, (width - 20) / buckets.length - 1)}
                  height="4"
                  className="survive-overview-unknown"
                />
              )}
              <title>
                {format(b.start, 2)}–{format(b.end, 2)} s: {b.count} markers;{" "}
                {b.reviews} Review; {b.unknown} missing/unsupported
              </title>
            </g>
          ))}
          {markers
            .filter((r) => Number.isFinite(r.start))
            .map((r) => (
              <rect
                key={`overview-${r.id}`}
                x={overviewX(r.start)}
                y="43"
                width={Math.max(1, overviewX(r.time) - overviewX(r.start))}
                height="4"
                className="survive-overview-unknown"
                pointerEvents="none"
              />
            ))}
          <rect
            x={overviewX(shownRange[0])}
            y="3"
            width={Math.max(
              2,
              overviewX(shownRange[1]) - overviewX(shownRange[0]),
            )}
            height="46"
            className="survive-overview-window"
            pointerEvents="none"
          />
          <line
            x1={overviewX(time)}
            x2={overviewX(time)}
            y1="3"
            y2="49"
            className="survive-playhead"
            pointerEvents="none"
          />
          <text x="10" y="60">
            0 s
          </text>
          <text x={width - 10} y="60" textAnchor="end">
            {format(total)} s
          </text>
        </svg>
        <div className="survive-timeline-actions">
          <span>Drag the overview to zoom.</span>
          <button
            disabled={
              !onDomainChange ||
              range[1] - range[0] <= Math.min(0.25, total) + 0.001
            }
            aria-label="Zoom in timeline"
            onClick={() =>
              changeRange(zoomTimelineRange(range, 0.5, total, time))
            }
          >
            Zoom in
          </button>
          <button
            disabled={!onDomainChange || range[1] - range[0] >= total - 0.001}
            aria-label="Zoom out timeline"
            onClick={() =>
              changeRange(zoomTimelineRange(range, 2, total, time))
            }
          >
            Zoom out
          </button>
          <button disabled={!onDomainChange} onClick={() => changeRange(null)}>
            Follow selected moment
          </button>
          <details className="survive-range-settings">
            <summary>Set range</summary>
            <form onSubmit={applyRange}>
              <label>
                From{" "}
                <input
                  aria-label="Timeline range start"
                  type="number"
                  min="0"
                  max={total}
                  step="0.001"
                  value={rangeDraft?.[0] ?? format(range[0], 3)}
                  onChange={(e) =>
                    setRangeDraft([
                      e.target.value,
                      rangeDraft?.[1] ?? format(range[1], 3),
                    ])
                  }
                />
              </label>
              <label>
                To{" "}
                <input
                  aria-label="Timeline range end"
                  type="number"
                  min="0"
                  max={total}
                  step="0.001"
                  value={rangeDraft?.[1] ?? format(range[1], 3)}
                  onChange={(e) =>
                    setRangeDraft([
                      rangeDraft?.[0] ?? format(range[0], 3),
                      e.target.value,
                    ])
                  }
                />
              </label>
              <button type="submit" disabled={!onDomainChange}>
                Apply range
              </button>
            </form>
          </details>
        </div>
        <svg
          width="100%"
          height="187"
          viewBox={`0 0 ${width} 187`}
          aria-label="Linked events, findings and missing observations on the same game-time axis"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            selectTime(
              range[0] +
                Math.max(
                  0,
                  Math.min(1, (e.clientX - rect.left - left) / plotWidth),
                ) *
                  (range[1] - range[0]),
            );
          }}
        >
          {TIMELINE_LANES.map((label, i) => (
            <g key={label}>
              <text x="0" y={22 + i * 25}>
                {label}
              </text>
              <line
                x1={left}
                x2={right}
                y1={18 + i * 25}
                y2={18 + i * 25}
                className="survive-gridline"
              />
            </g>
          ))}
          {visible
            .filter((r) => Number.isFinite(r.start))
            .map((r) => (
              <rect
                key={`shade-${r.id}`}
                x={x(Math.max(range[0], r.start))}
                y="4"
                width={Math.max(
                  1,
                  x(Math.min(range[1], r.time)) -
                    x(Math.max(range[0], r.start)),
                )}
                height="151"
                className="survive-gap"
                pointerEvents="none"
              />
            ))}
          {time >= range[0] && time <= range[1] && (
            <line
              x1={x(time)}
              x2={x(time)}
              y1="4"
              y2="155"
              className="survive-playhead"
              pointerEvents="none"
            />
          )}
          {groups.map((group) => {
            const one = group.items.length === 1,
              r = group.items[0];
            const label = one
              ? `Timeline ${r.label} · record ${r.seq}`
              : `Timeline cluster · ${group.items.length} events · ${TIMELINE_LANES[group.lane]} · ${format(group.items[0].time, 3)}–${format(group.items.at(-1).time, 3)} s`;
            return (
              <g
                key={group.id}
                role="button"
                tabIndex="0"
                className={`survive-marker category-${group.category}`}
                aria-label={label}
                onClick={(e) => {
                  e.stopPropagation();
                  showGroup(group);
                }}
                onKeyDown={(e) => {
                  if (["Enter", " "].includes(e.key)) {
                    e.preventDefault();
                    e.stopPropagation();
                    showGroup(group);
                  }
                }}
              >
                <title>{label}</title>
                {one ? (
                  <>
                    <circle
                      cx={x(group.time)}
                      cy={18 + group.lane * 25}
                      r="8"
                      fill="transparent"
                      stroke="none"
                    />
                    {r.category === "gaps" ? (
                      <rect
                        x={x(group.time) - 3}
                        y={14 + group.lane * 25}
                        width="6"
                        height="8"
                      />
                    ) : (
                      <circle
                        cx={x(group.time)}
                        cy={18 + group.lane * 25}
                        r={r.category === "findings" ? 4.5 : 3.5}
                      />
                    )}
                  </>
                ) : (
                  <>
                    <rect
                      x={x(group.time) - 13}
                      y={10 + group.lane * 25}
                      width="26"
                      height="16"
                      rx="5"
                    />
                    <text
                      className="survive-cluster-count"
                      x={x(group.time)}
                      y={22 + group.lane * 25}
                      textAnchor="middle"
                    >
                      {group.items.length}
                    </text>
                  </>
                )}
              </g>
            );
          })}
          {[0, 1, 2, 3].map((i) => (
            <text
              key={i}
              x={x(range[0] + (i / 3) * (range[1] - range[0]))}
              y="179"
              textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}
            >
              {format(range[0] + (i / 3) * (range[1] - range[0]), 2)} s
            </text>
          ))}
        </svg>
      </div>
      <div className="survive-timeline-footer">
        <span>
          {visible.length} in range · {markers.length - enabled.length} filtered
          · {unknownCount} missing/unsupported markers{" "}
          {truncated ? "in display" : "in round"}
        </span>
        <button
          onClick={() => {
            setExpanded(expanded ? null : visible);
            setListPage(0);
          }}
        >
          {expanded ? "Close event list" : "List events in range"}
        </button>
        <details>
          <summary>Filter events</summary>
          <div className="survive-marker-filters" aria-label="Timeline filters">
            {Object.entries(MARKER_FILTERS).map(([key, label]) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={filters[key]}
                  onChange={(e) => {
                    setFilters({ ...filters, [key]: e.target.checked });
                    setExpanded(null);
                    setListPage(0);
                  }}
                />
                <span className={`survive-marker-key category-${key}`} />
                {label}
              </label>
            ))}
          </div>
        </details>
        <details className="survive-inline-help">
          <summary>Reading the timeline</summary>
          <p>
            Counted markers group nearby events; select one to choose an exact
            record. Amber is Review; grey is missing or unsupported evidence.
            Zoom and filters change only the display, never evidence or selected
            time.{" "}
            {truncated
              ? "This display omits some items; gaps are not inferred from omitted positions."
              : "Shaded spans exceed 150 ms between recorded positions."}
          </p>
        </details>
      </div>
      {truncated && (
        <p className="survive-timeline-limited">
          Limited display: some recorded items are omitted. Counts describe the
          visible projection; omitted positions are not treated as source gaps.
        </p>
      )}
      {expanded && (
        <section
          className="survive-cluster-list"
          aria-label="Timeline event list"
        >
          <div className="survive-timeline-heading">
            <h4>Choose an exact event</h4>
            <span>
              {visibleList.length} events · page {boundedPage + 1} of{" "}
              {maxPage + 1}
            </span>
          </div>
          <div className="survive-cluster-rows">
            {visibleList
              .slice(boundedPage * 30, boundedPage * 30 + 30)
              .map((r) => (
                <button
                  key={r.id}
                  aria-label={`Timeline ${r.label} · record ${r.seq}`}
                  onClick={() => activate(r)}
                >
                  <span>{format(r.time, 3)} s</span>
                  <span className={`category-${r.category}`}>{r.label}</span>
                  <span>Record {r.seq}</span>
                </button>
              ))}
          </div>
          <div className="survive-timeline-actions">
            <button
              disabled={boundedPage === 0}
              onClick={() => setListPage(boundedPage - 1)}
            >
              Previous timeline events
            </button>
            <button
              disabled={boundedPage >= maxPage}
              onClick={() => setListPage(boundedPage + 1)}
            >
              Next timeline events
            </button>
            <button
              onClick={() => {
                setExpanded(null);
                setListPage(0);
              }}
            >
              Close event list
            </button>
          </div>
        </section>
      )}
    </section>
  );
}

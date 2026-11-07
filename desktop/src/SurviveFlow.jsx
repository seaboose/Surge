import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { Info } from "./Info.jsx";
import ConstraintChart from "./survive/ConstraintChart.jsx";
import {
  ViewPicker,
  EventRecords,
  usePlotHint,
} from "./survive/ReviewViews.jsx";
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
      {[
        ["play", "Play & record"],
        ["review", "Review"],
        ["explain", "Explain"],
        ["export", "Export"],
      ].map(([value, name], i) => (
        <button
          key={name}
          aria-current={stage === value ? "step" : undefined}
          disabled={
            (value !== "play" && !hasRecording) ||
            (value === "export" && !hasReport)
          }
          onClick={() => onNavigate(value)}
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
          <summary>
            Recording details{" "}
            <Info label="Recording details">
              Compare game time with recorder time and check how recently data
              arrived.
            </Info>
          </summary>
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
        <div className="survive-field-heading">
          <h2>Session summary</h2>
          <Info label="Session summary">
            Results for the selected recording. Counts become available when the
            round and its analysis are complete.
          </Info>
        </div>
        <span
          className={`survive-status-badge ${pending ? "tone-unknown" : "tone-verified"}`}
        >
          {pending ? "Partial / pending assessment" : "Analysis complete"} ·{" "}
          {s.completion}
        </span>
      </div>
      <dl className="survive-summary-metrics">
        {[
          [
            "Game duration",
            `${format(s.duration)} s`,
            "Elapsed simulation time observed in this recording.",
          ],
          [
            "Hits",
            s.hits ?? "Unavailable",
            "Number of recorded threats with a hit outcome.",
          ],
          [
            "Avoided initial threats",
            s.avoided ?? "Unavailable",
            "Initially threatening geometry that expired without a hit. This measure excludes terrain and does not establish why a threat missed.",
          ],
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
            "Share of sampled position intervals supported by the coverage calculation.",
          ],
          [
            "Review findings",
            s.reviews ?? "Pending",
            "Rule observations that need investigation. Select a Review marker to inspect the source records.",
          ],
          [
            "Unknown observations",
            s.unknown ?? "Pending",
            "Rule observations with insufficient or unsupported evidence. Inspect Coverage to see where assessment was limited.",
          ],
        ].map(([key, value, help]) => (
          <div key={key}>
            <dt>
              {key} <Info label={key}>{help}</Info>
            </dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

const filterHelp = {
  findings:
    "Amber diamonds mark rule observations that need investigation. Select one to see the measured interval.",
  gaps: "Hollow squares mark unsupported observations or gaps of more than 150 ms between recorded positions. Shading spans the missing time.",
  hits: "Show recorded threat impacts on the Events lane. A hit provides gameplay context.",
  dashes: "Show recorded starts and ends of dash abilities.",
  blinks: "Show recorded starts and ends of blink abilities.",
  commands:
    "Show game-side command events. They describe command handling rather than physical input.",
  threats:
    "Show threat events such as spawns and expiry. Impacts have their own Hits filter.",
};
const laneHelp = [
  "Needs review. A rule flagged a movement interval for investigation.",
  "Cannot assess. The rule lacks usable evidence, or part of the position trail is missing.",
  "Recorded events. These describe what happened in the game.",
];
function markerDescription(marker) {
  const when = Number.isFinite(marker.start)
    ? `${format(marker.start, 3)}–${format(marker.time, 3)} s`
    : `${format(marker.time, 3)} s`;
  const meaning =
    marker.category === "findings"
      ? "Movement needs review."
      : marker.category === "gaps"
        ? "Coverage is limited."
        : "Recorded gameplay event.";
  return `${marker.label} · ${when}. ${meaning} Select to inspect record ${marker.seq} in Selected evidence.`;
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
  controls,
  rows,
  selectedRecord,
  selectedConstraint,
  final,
  analysisState,
}) {
  const [ref, width] = useChartWidth();
  const hint = usePlotHint();
  const [views, setViews] = useState(["timeline"]);
  const [together, setTogether] = useState(false);
  const showTimeline = views.includes("timeline");
  const showMovement = views.includes("movement");
  const [filters, setFilters] = useState(
    Object.fromEntries(Object.keys(MARKER_FILTERS).map((k) => [k, true])),
  );
  const [expanded, setExpanded] = useState(null);
  const [listPage, setListPage] = useState(0);
  const [drag, setDrag] = useState(null);
  const [zoomMode, setZoomMode] = useState(false);
  const [seekDraft, setSeekDraft] = useState("");
  const seekHelpId = useId();
  const gesture = useRef(null);
  const source =
    recordingId || events[0]?.session_id || constraints[0]?.session_id;
  useEffect(() => {
    setExpanded(null);
    setListPage(0);
    setDrag(null);
    setRangeDraft(null);
    setSeekDraft("");
    setZoomMode(false);
    setViews(["timeline"]);
    setTogether(false);
    hint.dismiss();
    cancelGesture();
    return cancelGesture;
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
    () =>
      enabled.filter(
        (r) =>
          markerOverlapsRange(r, range) &&
          (showTimeline ||
            (r.category !== "findings" && r.category !== "gaps")),
      ),
    [enabled, range[0], range[1], showTimeline],
  );
  const unknownCount = useMemo(
    () => markers.filter((r) => r.category === "gaps").length,
    [markers],
  );
  const left = width < 400 ? 76 : 86,
    right = width - 12,
    plotWidth = Math.max(1, right - left);
  const laneStep = 27,
    laneTop = 18,
    plotBottom =
      laneTop + (showTimeline ? TIMELINE_LANES.length - 1 : 0) * laneStep + 12,
    detailHeight = plotBottom + 30;
  const laneY = (i) => laneTop + (showTimeline ? i : 0) * laneStep;
  const x = (t) => left + ((t - range[0]) / (range[1] - range[0])) * plotWidth;
  const overviewX = (t) => 10 + (t / total) * (width - 20);
  const groups = useMemo(
    () => clusterTimelineMarkers(visible, range, plotWidth),
    [visible, range[0], range[1], plotWidth],
  );
  const selectedGroups = useMemo(() => {
    const recordGroups = new Map();
    const ruleGroups = new Map();
    for (const group of groups)
      for (const item of group.items) {
        if (item.constraint) ruleGroups.set(item.constraint.event_id, group);
        else if (item.row) recordGroups.set(`${group.lane}:${item.seq}`, group);
      }
    return { recordGroups, ruleGroups };
  }, [groups]);
  const roundGaps = useMemo(
    () => markers.filter((r) => Number.isFinite(r.start)),
    [markers],
  );
  const rangeGaps = useMemo(
    () => visible.filter((r) => Number.isFinite(r.start)),
    [visible],
  );
  const buckets = useMemo(
    () => timelineOverview(markers, total),
    [markers, total],
  );
  const highest = Math.max(1, ...buckets.map((b) => b.count));
  function bucketDescription(value) {
    const index = Math.max(
      0,
      Math.min(
        buckets.length - 1,
        Math.floor((value / total) * buckets.length),
      ),
    );
    const b = buckets[index];
    return `${format(b.start, 2)}–${format(b.end, 2)} s · ${b.count} markers, ${b.reviews} needing review, ${b.unknown} coverage limits. Select here to move the replay cursor.`;
  }
  function overviewHover(e) {
    if (gesture.current) return;
    const value = coordinate(
      e.clientX,
      e.currentTarget.getBoundingClientRect(),
      total,
      width,
    );
    const text = e.target.dataset.hint || bucketDescription(value);
    hint.show(e, text);
  }
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
  const coordinate = (clientX, bounds, limit, chartWidth) => {
    const chartX =
      ((clientX - bounds.left) / Math.max(1, bounds.width)) * chartWidth;
    return Math.max(
      0,
      Math.min(limit, ((chartX - 10) / Math.max(1, chartWidth - 20)) * limit),
    );
  };
  function seek(value) {
    if (value <= 0) return selectTime(0);
    if (value >= total) return selectTime(total);
    selectTime(Math.min(total, Math.round(value * 1000) / 1000));
  }
  function cancelGesture() {
    const current = gesture.current;
    gesture.current = null;
    setDrag(null);
    if (current?.node.hasPointerCapture(current.pointer))
      current.node.releasePointerCapture(current.pointer);
  }
  function cancelPointer(event) {
    if (gesture.current?.pointer === event.pointerId) cancelGesture();
  }
  function beginGesture(event) {
    if (gesture.current || event.button !== 0 || (zoomMode && !onDomainChange))
      return;
    hint.dismiss();
    const bounds = event.currentTarget.getBoundingClientRect();
    const start = coordinate(event.clientX, bounds, total, width);
    gesture.current = {
      start,
      pointer: event.pointerId,
      node: event.currentTarget,
      bounds,
      total,
      width,
      range,
      zoom: zoomMode,
    };
    if (zoomMode) setDrag([start, start]);
    else seek(start);
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }
  function moveGesture(event) {
    const current = gesture.current;
    if (current?.pointer !== event.pointerId) return;
    const end = coordinate(
      event.clientX,
      current.bounds,
      current.total,
      current.width,
    );
    if (current.zoom) setDrag([current.start, end]);
    else seek(end);
  }
  function finishGesture(event) {
    const current = gesture.current;
    if (current?.pointer !== event.pointerId) return;
    const end = coordinate(
      event.clientX,
      current.bounds,
      current.total,
      current.width,
    );
    cancelGesture();
    if (!current.zoom) {
      seek(end);
      return;
    }
    // Range mode changes only the viewing window; it never changes evidence selection.
    const threshold = (current.total * 4) / Math.max(1, current.width - 20);
    const span = current.range[1] - current.range[0];
    const first = Math.max(0, Math.min(current.total - span, end - span / 2));
    changeRange(
      Math.abs(end - current.start) <= threshold
        ? [first, first + span]
        : [current.start, end],
    );
  }
  function seekByKeyboard(event) {
    const step = event.shiftKey ? 1 : 0.1;
    const values = {
      ArrowLeft: time - step,
      ArrowDown: time - step,
      ArrowRight: time + step,
      ArrowUp: time + step,
      PageDown: time - 10,
      PageUp: time + 10,
      Home: 0,
      End: total,
    };
    if (event.key === "Escape") hint.dismiss();
    if (!(event.key in values)) return;
    event.preventDefault();
    cancelGesture();
    seek(values[event.key]);
    hint.show(event, bucketDescription(values[event.key]));
  }
  function applySeek(event) {
    event.preventDefault();
    if (seekDraft.trim() !== "" && Number.isFinite(Number(seekDraft)))
      seek(Number(seekDraft));
    setSeekDraft("");
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
        <div className="survive-field-heading">
          <h3>Timeline</h3>
          <Info label="Timeline">
            The overview shows activity across the full round. Click or drag it
            to seek. The views below show the chosen time window and share one
            evidence selection.
          </Info>
        </div>
        <span>
          {format(range[0], 2)}–{format(range[1], 2)} s of {format(total, 1)} s
        </span>
      </div>
      {controls}
      <div ref={ref} className="survive-timeline-canvas">
        <div ref={hint.container} className="survive-chart-with-hint">
          <svg
            width="100%"
            height="62"
            viewBox={`0 0 ${width} 62`}
            role="slider"
            tabIndex="0"
            aria-label="Game time"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={Math.min(total, Math.max(0, time))}
            aria-valuetext={`${format(time, 3)} of ${format(total, 1)} seconds`}
            aria-describedby={seekHelpId}
            aria-orientation="horizontal"
            data-zoom-mode={zoomMode}
            className="survive-timeline-overview"
            onPointerDown={beginGesture}
            onPointerMove={(e) => {
              if (gesture.current) moveGesture(e);
              else overviewHover(e);
            }}
            onPointerLeave={hint.dismiss}
            onFocus={(e) => hint.show(e, bucketDescription(time))}
            onBlur={hint.dismiss}
            onPointerUp={finishGesture}
            onPointerCancel={cancelPointer}
            onLostPointerCapture={cancelPointer}
            onKeyDown={seekByKeyboard}
          >
            <title>
              {zoomMode
                ? "Drag to choose a zoom range. Arrow keys still seek playback."
                : "Click or drag to seek. Arrow keys move 0.1 seconds; Shift moves 1 second. Home and End jump to the boundaries."}
            </title>
            {buckets.map((b, i) => (
              <g key={i}>
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
                    data-hint={`${format(b.start, 2)}–${format(b.end, 2)} s · ${b.reviews} observations need review. Select an amber diamond below to inspect one.`}
                  />
                )}
                {b.unknown > 0 && (
                  <rect
                    x={overviewX(b.start)}
                    y="43"
                    width={Math.max(1, (width - 20) / buckets.length - 1)}
                    height="4"
                    className="survive-overview-unknown"
                    data-hint={`${format(b.start, 2)}–${format(b.end, 2)} s · ${b.unknown} coverage limits. Select a hollow square below to inspect its evidence.`}
                  />
                )}
                <title>
                  {format(b.start, 2)}–{format(b.end, 2)} s: {b.count} markers;{" "}
                  {b.reviews} Review; {b.unknown} missing/unsupported
                </title>
              </g>
            ))}
            {roundGaps.map((r) => (
              <rect
                key={`overview-${r.id}`}
                x={overviewX(r.start)}
                y="43"
                width={Math.max(1, overviewX(r.time) - overviewX(r.start))}
                height="4"
                className="survive-overview-unknown"
                data-hint={markerDescription(r)}
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
              pointerEvents="stroke"
              data-hint={`Visible window · ${format(shownRange[0], 2)}–${format(shownRange[1], 2)} s. Time & zoom changes this range.`}
            />
            <line
              x1={overviewX(time)}
              x2={overviewX(time)}
              y1="3"
              y2="49"
              className="survive-playhead"
              pointerEvents="stroke"
              data-hint={`Replay cursor · ${format(time, 3)} s. Replay and Selected evidence follow this time.`}
            />
            <path
              d={`M ${overviewX(time) - 5} 2 H ${overviewX(time) + 5} L ${overviewX(time)} 9 Z`}
              className="survive-seek-head"
              data-hint={`Replay cursor · ${format(time, 3)} s. Drag to seek.`}
            />
            <text x="10" y="60">
              0 s
            </text>
            <text x={width - 10} y="60" textAnchor="end">
              {format(total)} s
            </text>
          </svg>
          <div className="survive-timeline-actions">
            <span id={seekHelpId}>
              {zoomMode
                ? "Drag to choose a zoom range"
                : "Click or drag to seek"}
            </span>
            <details
              className="survive-range-settings"
              onToggle={(event) => {
                if (!event.currentTarget.open) {
                  cancelGesture();
                  setZoomMode(false);
                }
              }}
            >
              <summary>Time &amp; zoom</summary>
              <div className="survive-timeline-actions">
                <button
                  disabled={!onDomainChange}
                  aria-pressed={zoomMode}
                  onClick={() => {
                    cancelGesture();
                    setZoomMode((value) => !value);
                  }}
                >
                  Zoom range
                </button>
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
                  disabled={
                    !onDomainChange || range[1] - range[0] >= total - 0.001
                  }
                  aria-label="Zoom out timeline"
                  onClick={() =>
                    changeRange(zoomTimelineRange(range, 2, total, time))
                  }
                >
                  Zoom out
                </button>
                <button
                  disabled={!onDomainChange}
                  onClick={() => changeRange(null)}
                >
                  Follow selected moment
                </button>
                <button
                  disabled={
                    !onDomainChange || (range[0] === 0 && range[1] >= total)
                  }
                  onClick={() => changeRange([0, total])}
                >
                  Whole round
                </button>
              </div>
              <form onSubmit={applySeek}>
                <label>
                  Time
                  <input
                    aria-label="Seek time"
                    type="number"
                    min="0"
                    max={total}
                    step="0.001"
                    value={seekDraft}
                    placeholder={format(time, 3)}
                    onChange={(e) => setSeekDraft(e.target.value)}
                  />
                </label>
                <button type="submit" disabled={seekDraft.trim() === ""}>
                  Go to time
                </button>
              </form>
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
          {rows && (
            <ViewPicker
              visible={views}
              setVisible={(next) => {
                setViews(next);
                setExpanded(null);
                setListPage(0);
                hint.dismiss();
              }}
              together={together}
              setTogether={setTogether}
            />
          )}
          {showMovement && (
            <ConstraintChart
              constraints={constraints}
              domain={range}
              time={time}
              choose={chooseConstraint}
              selectedConstraint={selectedConstraint}
              selectedRecord={selectedRecord}
              final={final}
              analysisState={analysisState}
            />
          )}
          {(showTimeline || showMovement) && (
            <>
              <details className="survive-timeline-filters">
                <summary>Filter events</summary>
                <div
                  className="survive-marker-filters"
                  aria-label="Timeline filters"
                >
                  {Object.entries(MARKER_FILTERS)
                    .filter(
                      ([key]) =>
                        showTimeline || (key !== "findings" && key !== "gaps"),
                    )
                    .map(([key, label]) => (
                      <span key={key} className="survive-filter-item">
                        <label>
                          <input
                            type="checkbox"
                            checked={filters[key]}
                            onChange={(e) => {
                              setFilters({
                                ...filters,
                                [key]: e.target.checked,
                              });
                              setExpanded(null);
                              setListPage(0);
                            }}
                          />
                          <i
                            className={`survive-marker-key category-${key}`}
                            aria-hidden="true"
                          />
                          {label}
                        </label>
                        <Info label={label}>{filterHelp[key]}</Info>
                      </span>
                    ))}
                </div>
              </details>
              <svg
                width="100%"
                height={detailHeight}
                viewBox={`0 0 ${width} ${detailHeight}`}
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
                <g aria-label="Timeline marker meanings">
                  {["Needs review", "Cannot assess", "Recorded event"].map(
                    (label, i) =>
                      (showTimeline || i === 2) && (
                        <g
                          key={label}
                          tabIndex="0"
                          role="img"
                          aria-label={`${label}. ${laneHelp[i]}`}
                          {...hint.bindings(laneHelp[i])}
                        >
                          <text x="0" y={laneY(i) + 4}>
                            {label}
                          </text>
                          <line
                            x1={left}
                            x2={right}
                            y1={laneY(i)}
                            y2={laneY(i)}
                            className="survive-gridline"
                          />
                        </g>
                      ),
                  )}
                </g>
                {showTimeline &&
                  rangeGaps.map((r) => (
                    <rect
                      key={`shade-${r.id}`}
                      x={x(Math.max(range[0], r.start))}
                      y="4"
                      width={Math.max(
                        1,
                        x(Math.min(range[1], r.time)) -
                          x(Math.max(range[0], r.start)),
                      )}
                      height={plotBottom - 4}
                      className="survive-gap"
                      tabIndex="-1"
                      role="button"
                      aria-label={`Position gap · ${format(r.start, 3)}–${format(r.time, 3)} s · record ${r.seq}`}
                      {...hint.bindings(markerDescription(r))}
                      onClick={(e) => {
                        e.stopPropagation();
                        activate(r);
                      }}
                      onKeyDown={(e) => {
                        if (["Enter", " "].includes(e.key)) {
                          e.preventDefault();
                          activate(r);
                        }
                      }}
                    />
                  ))}
                {time >= range[0] && time <= range[1] && (
                  <line
                    x1={x(time)}
                    x2={x(time)}
                    y1="4"
                    y2={plotBottom}
                    className="survive-playhead"
                    pointerEvents="stroke"
                    {...hint.bindings(
                      `Replay cursor · ${format(time, 3)} s. Selected evidence follows this moment.`,
                    )}
                  />
                )}
                {groups.map((group) => {
                  if (!showTimeline && group.lane !== 2) return null;
                  const one = group.items.length === 1,
                    r = group.items[0];
                  const label = one
                    ? `Timeline ${r.label} · record ${r.seq}`
                    : `Timeline cluster · ${group.items.length} events · ${TIMELINE_LANES[group.lane]} · ${format(group.items[0].time, 3)}–${format(group.items.at(-1).time, 3)} s`;
                  const description = one
                    ? markerDescription(r)
                    : `${label}. ${laneHelp[group.lane]} Open the group to choose an exact record.`;
                  const selected =
                    group ===
                      selectedGroups.recordGroups.get(
                        `${group.lane}:${selectedRecord?.seq}`,
                      ) ||
                    group ===
                      selectedGroups.ruleGroups.get(
                        selectedConstraint?.event_id,
                      );
                  return (
                    <g
                      key={group.id}
                      role="button"
                      tabIndex="0"
                      className={`survive-marker category-${group.category}`}
                      aria-label={label}
                      aria-description={description}
                      aria-pressed={selected}
                      {...hint.bindings(description)}
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
                      <title>{description}</title>
                      {one ? (
                        <>
                          <circle
                            cx={x(group.time)}
                            cy={laneY(group.lane)}
                            r="8"
                            fill="transparent"
                            stroke="none"
                          />
                          {r.category === "gaps" ? (
                            <rect
                              x={x(group.time) - 4}
                              y={laneY(group.lane) - 4}
                              width="8"
                              height="8"
                              className="survive-coverage-symbol"
                            />
                          ) : r.category === "findings" ? (
                            <path
                              d={`M ${x(group.time)} ${laneY(group.lane) - 6} l 6 6 -6 6 -6 -6 Z`}
                              className="survive-review-symbol"
                            />
                          ) : (
                            <circle
                              cx={x(group.time)}
                              cy={laneY(group.lane)}
                              r="3.5"
                            />
                          )}
                        </>
                      ) : (
                        <>
                          <rect
                            x={x(group.time) - 13}
                            y={laneY(group.lane) - 8}
                            width="26"
                            height="16"
                            rx="5"
                            className={
                              group.category === "gaps"
                                ? "survive-coverage-symbol"
                                : undefined
                            }
                          />
                          <text
                            className={`survive-cluster-count${group.category === "gaps" ? " is-coverage" : ""}`}
                            x={x(group.time)}
                            y={laneY(group.lane) + 4}
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
                    y={detailHeight - 8}
                    textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}
                  >
                    {format(range[0] + (i / 3) * (range[1] - range[0]), 2)} s
                  </text>
                ))}
              </svg>
            </>
          )}
          {hint.bubble}
        </div>
      </div>
      {(showTimeline || showMovement) && (
        <div className="survive-timeline-footer">
          <span>
            {visible.length} in range · {markers.length - enabled.length}{" "}
            filtered · {unknownCount} missing/unsupported markers{" "}
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
        </div>
      )}
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
                  title={markerDescription(r)}
                  aria-description={markerDescription(r)}
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
      {views.includes("records") && rows && (
        <EventRecords
          key={source}
          rows={rows}
          domain={range}
          record={selectedRecord}
          constraints={constraints}
          choose={chooseRecord}
          final={final}
          analysisState={analysisState}
        />
      )}
    </section>
  );
}

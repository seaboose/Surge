import React, { useLayoutEffect, useMemo, useRef } from "react";
import { useChartWidth } from "../SurviveFlow.jsx";
import { Info } from "../Info.jsx";
import { usePlotHint } from "./ReviewViews.jsx";
import { number } from "./replay-model.mjs";

export default function ConstraintChart({
  constraints,
  domain,
  time,
  choose,
  final,
  analysisState,
  selectedConstraint,
  selectedRecord,
}) {
  const [ref, width] = useChartWidth();
  const hint = usePlotHint();
  const left = width < 400 ? 76 : 86,
    right = width - 12,
    top = 18,
    bottom = 145;
  const values = useMemo(
    () =>
      constraints.filter(
        (r) =>
          r.constraint === "walking_displacement" &&
          r.elapsed_s >= domain[0] &&
          r.elapsed_s <= domain[1],
      ),
    [constraints, domain[0], domain[1]],
  );
  const ymax = useMemo(
    () =>
      values.reduce(
        (max, r) =>
          Number.isFinite(r.constraint_ratio)
            ? Math.max(max, r.constraint_ratio * 1.12)
            : max,
        1.4,
      ),
    [values],
  );
  const x = (t) =>
      left + ((t - domain[0]) / (domain[1] - domain[0])) * (right - left),
    y = (v) => bottom - (v / ymax) * (bottom - top);
  const markLayer = useRef(null);
  const indices = useMemo(
    () => new Map(values.map((r, i) => [r.event_id, i])),
    [values],
  );
  const selectedIndex = indices.get(selectedConstraint?.event_id);
  // The playhead advances every frame. Point geometry only changes with the
  // measurements, window or width; update the two selection attributes alone.
  const marks = useMemo(
    () =>
      values.map((r, i) => {
        const measured =
          r.status !== "Unknown" && Number.isFinite(r.constraint_ratio);
        const description = measured
          ? `${number(r.elapsed_s, 3)} s · ${r.status} · ${number(r.observed)} of ${number(r.allowed)} ${r.unit || ""}. Select to inspect records ${r.start_seq}–${r.end_seq}.`
          : `${number(r.elapsed_s, 3)} s · Cannot assess · ${r.coverage || "unsupported interval"}. Select to inspect record ${r.end_seq}.`;
        const target = {
          role: "button",
          tabIndex: -1,
          "data-point": i,
          "aria-pressed": false,
          "aria-label": `Movement interval ${measured ? r.status : "Unknown"} · record ${r.end_seq}`,
          "aria-description": description,
        };
        return measured ? (
          <circle
            key={r.event_id}
            cx={x(r.elapsed_s)}
            cy={y(r.constraint_ratio)}
            r="3.5"
            {...target}
            className={
              r.status === "Review"
                ? "survive-review-mark"
                : "survive-known-mark"
            }
          />
        ) : (
          <rect
            key={r.event_id}
            x={x(r.elapsed_s) - 2}
            y={bottom - 5}
            width="4"
            height="10"
            {...target}
            className="survive-gap"
          />
        );
      }),
    [values, left, right, domain[0], domain[1], ymax],
  );
  useLayoutEffect(() => {
    const chosen = markLayer.current?.children[selectedIndex];
    if (!chosen) return;
    chosen.setAttribute("aria-pressed", "true");
    return () => chosen.setAttribute("aria-pressed", "false");
  }, [selectedIndex, marks]);
  function pointHint(event) {
    const text = event.target.getAttribute("aria-description");
    if (text) hint.show(event, text, event.target);
  }
  function navigatePoints(event) {
    if (event.key === "Escape") {
      hint.dismiss();
      return;
    }
    if (!values.length) return;
    const pointIndex = event.target.dataset.point;
    const current =
      pointIndex === undefined ? selectedIndex : Number(pointIndex);
    const positions = {
      ArrowRight: Math.min(values.length - 1, (current ?? -1) + 1),
      ArrowLeft: Math.max(0, (current ?? values.length) - 1),
      Home: 0,
      End: values.length - 1,
    };
    if (Object.hasOwn(positions, event.key)) {
      event.preventDefault();
      markLayer.current.children[positions[event.key]].focus();
    } else if (["Enter", " "].includes(event.key) && current !== undefined) {
      event.preventDefault();
      choose(values[current]);
    }
  }
  return (
    <section
      className="survive-linked-movement"
      aria-label="Movement constraint graph"
    >
      <div className="survive-field-heading">
        <h3>Walking displacement</h3>
        <Info label="Walking displacement">
          Each point compares observed movement to its allowance. The 1× line is
          the limit including tolerance. Grey marks identify unknown intervals.
          Empty time has no supported walking observation. Select a point for
          its exact records, or choose a gameplay event below. With the chart
          focused, use the arrow keys to explore points and Enter to inspect
          one.
        </Info>
      </div>
      {!final && (
        <p className="survive-pending">
          {analysisState === "unavailable"
            ? "Unavailable — the recording is incomplete or failed validation."
            : "Pending — final movement analysis requires a validated completed game capture."}
        </p>
      )}
      <div ref={ref} className="survive-chart">
        <div ref={hint.container} className="survive-chart-with-hint">
          <svg
            width="100%"
            height="190"
            viewBox={`0 0 ${width} 190`}
            role="group"
            tabIndex="0"
            onKeyDown={navigatePoints}
            onFocus={pointHint}
            onBlur={hint.dismiss}
            onPointerOver={pointHint}
            onPointerOut={(e) => {
              if (e.target.dataset.point !== undefined) hint.dismiss();
            }}
            aria-label="Movement allowance ratio over game time; one is the selected allowance"
            onClick={(e) => {
              if (e.target.dataset.point !== undefined) {
                choose(values[Number(e.target.dataset.point)]);
                return;
              }
              const rect = e.currentTarget.getBoundingClientRect(),
                t =
                  domain[0] +
                  Math.max(
                    0,
                    Math.min(
                      1,
                      (e.clientX - rect.left - left) / (right - left),
                    ),
                  ) *
                    (domain[1] - domain[0]);
              const nearest = values.reduce(
                (best, r) =>
                  !best ||
                  Math.abs(r.elapsed_s - t) < Math.abs(best.elapsed_s - t)
                    ? r
                    : best,
                null,
              );
              if (nearest) choose(nearest);
            }}
          >
            {[0, 1, ymax].map((n, i) => (
              <g
                key={i}
                {...hint.bindings(
                  n === 1
                    ? "1× is the displacement allowance for a measured interval."
                    : `${number(n, 1)}× the displacement allowance.`,
                )}
              >
                <line
                  x1={left}
                  x2={right}
                  y1={y(n)}
                  y2={y(n)}
                  className={n === 1 ? "survive-limit" : "survive-gridline"}
                />
                <text x={left - 8} y={y(n) + 4} textAnchor="end">
                  {number(n, n === ymax ? 1 : 0)}×
                </text>
              </g>
            ))}
            <g ref={markLayer}>{marks}</g>
            {time >= domain[0] && time <= domain[1] && (
              <line
                x1={x(time)}
                x2={x(time)}
                y1={top}
                y2={bottom}
                className="survive-playhead"
                pointerEvents="none"
              />
            )}
            {[0, 1, 2, 3].map((i) => (
              <text
                key={i}
                x={x(domain[0] + (i / 3) * (domain[1] - domain[0]))}
                y="166"
                textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}
              >
                {number(domain[0] + (i / 3) * (domain[1] - domain[0]), 1)} s
              </text>
            ))}
            <text x={(left + right) / 2} y="185" textAnchor="middle">
              Game elapsed time (seconds)
            </text>
          </svg>
          {hint.bubble}
        </div>
      </div>
      {selectedRecord && (
        <small>
          Selected record {selectedRecord.seq} ·{" "}
          {number(selectedRecord.elapsed_s, 3)} s
        </small>
      )}
    </section>
  );
}

import React from "react";
import { useChartWidth } from "../SurviveFlow.jsx";
import { number } from "./replay-model.mjs";

export default function ConstraintChart({
  constraints,
  domain,
  time,
  choose,
  final,
  analysisState,
}) {
  const [ref, width] = useChartWidth();
  const left = 44,
    right = width - 14,
    top = 18,
    bottom = 145;
  const values = constraints.filter(
    (r) =>
      r.constraint === "walking_displacement" &&
      r.elapsed_s >= domain[0] &&
      r.elapsed_s <= domain[1],
  );
  const known = values.filter((r) => Number.isFinite(r.constraint_ratio));
  const ymax = Math.max(1.4, ...known.map((r) => r.constraint_ratio * 1.12));
  const x = (t) =>
      left + ((t - domain[0]) / (domain[1] - domain[0])) * (right - left),
    y = (v) => bottom - (v / ymax) * (bottom - top);
  return (
    <section className="survive-panel" aria-label="Movement constraint graph">
      <h3>Walking displacement / allowed displacement</h3>
      {!final && (
        <p className="survive-pending">
          {analysisState === "unavailable"
            ? "Unavailable — the recording is incomplete or failed validation."
            : "Pending — final movement analysis requires a validated completed game capture."}
        </p>
      )}
      <div ref={ref} className="survive-chart">
        <svg
          width="100%"
          height="190"
          viewBox={`0 0 ${width} 190`}
          role="img"
          aria-label="Movement allowance ratio over game time; one is the selected allowance"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect(),
              t =
                domain[0] +
                Math.max(
                  0,
                  Math.min(1, (e.clientX - rect.left - left) / (right - left)),
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
            <g key={i}>
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
          {values.map((r) =>
            r.status !== "Unknown" && Number.isFinite(r.constraint_ratio) ? (
              <circle
                key={r.event_id}
                cx={x(r.elapsed_s)}
                cy={y(r.constraint_ratio)}
                r="3.5"
                role="button"
                tabIndex="0"
                aria-label={`Movement interval ${r.status} · record ${r.end_seq}`}
                onClick={(e) => {
                  e.stopPropagation();
                  choose(r);
                }}
                onKeyDown={(e) => {
                  if (["Enter", " "].includes(e.key)) {
                    e.preventDefault();
                    choose(r);
                  }
                }}
                className={
                  r.status === "Review"
                    ? "survive-review-mark"
                    : "survive-known-mark"
                }
              >
                <title>
                  {number(r.elapsed_s, 3)} s · {r.status || "Unavailable"} ·{" "}
                  {number(r.observed)} / {number(r.allowed)} {r.unit}
                </title>
              </circle>
            ) : (
              <rect
                key={r.event_id}
                x={x(r.elapsed_s) - 2}
                y={bottom - 5}
                width="4"
                height="10"
                className="survive-gap"
                role="button"
                tabIndex="0"
                aria-label={`Movement interval Unknown · record ${r.end_seq}`}
                onClick={(e) => {
                  e.stopPropagation();
                  choose(r);
                }}
                onKeyDown={(e) => {
                  if (["Enter", " "].includes(e.key)) {
                    e.preventDefault();
                    choose(r);
                  }
                }}
              >
                <title>Unknown: {r.coverage}</title>
              </rect>
            ),
          )}
          <line
            x1={x(time)}
            x2={x(time)}
            y1={top}
            y2={bottom}
            className="survive-playhead"
          />
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
      </div>
      <small>
        1× is the selected displacement allowance, including interval tolerance.
        Grey marks are Unknown; blank spans have no supported walking
        observation. Mobility uses separate constraints.
      </small>
    </section>
  );
}

import React from "react";
import { lastAt, number, pretty } from "./replay-model.mjs";

const TERMINALS = new Set([
  "threat_hit",
  "threat_expired",
  "threat_blocked",
  "threat_cancelled",
]);

export default function Arena({ rows, points, time, exactRecord }) {
  const point = exactRecord || lastAt(points, time);
  const trail = points.filter(
    (r) => r.elapsed_s >= time - 4 && r.elapsed_s <= time,
  );
  const segments = [];
  for (let i = 1; i < trail.length; i++) {
    const a = trail[i - 1],
      b = trail[i],
      dt = b.elapsed_s - a.elapsed_s;
    if (
      dt > 0 &&
      dt <= 0.15 &&
      ![a, b].some(
        (r) => r.movement_mode === "blink" || r.detail === "blink",
      ) &&
      [a, b].every((r) => ["walking", "dash"].includes(r.movement_mode))
    )
      segments.push([a, b]);
  }
  const threats = new Map();
  for (const r of rows) {
    if (r.elapsed_s > time) break;
    if (r.event === "threat_warning") threats.set(r.related_id, { warning: r });
    else if (r.event === "threat_fire" && threats.has(r.related_id))
      threats.get(r.related_id).fire = r;
    else if (TERMINALS.has(r.event)) threats.delete(r.related_id);
  }
  const lastAction = [...rows]
    .reverse()
    .find(
      (r) =>
        r.elapsed_s <= time &&
        ((r.event === "command_grant" && r.detail === "move") ||
          r.event === "command_stop" ||
          r.event === "ability_start"),
    );
  const destination = lastAction?.event === "command_grant" ? lastAction : null;
  const x = (n) => n,
    y = (n) => -n;
  return (
    <section className="survive-panel" aria-label="Recorded arena replay">
      <h3>Recorded arena replay</h3>
      <svg
        className="survive-arena"
        viewBox="-1450 -1450 2900 2900"
        role="img"
        aria-label="Recorded player trail, active threats and accepted movement destination"
      >
        <rect
          x="-1300"
          y="-1300"
          width="2600"
          height="2600"
          className="survive-arena-floor"
        />
        {[
          [-520, -430, -280, -70],
          [300, 240, 580, 480],
        ].map(([a, b, c, d], i) => (
          <rect
            key={i}
            x={x(a)}
            y={y(d)}
            width={c - a}
            height={d - b}
            className="survive-obstacle"
          />
        ))}
        {segments.map(([a, b], i) => (
          <line
            key={i}
            x1={x(a.x_cm)}
            y1={y(a.y_cm)}
            x2={x(b.x_cm)}
            y2={y(b.y_cm)}
            className={
              a.movement_mode === "dash"
                ? "survive-dash-path"
                : "survive-walk-path"
            }
          />
        ))}
        {[...threats].map(([id, { warning: r, fire }]) => {
          if (r.detail.startsWith("circle"))
            return (
              <circle
                key={id}
                cx={x(r.a)}
                cy={y(r.b)}
                r={r.c}
                className="survive-threat-circle"
              >
                <title>{pretty(r.detail)}</title>
              </circle>
            );
          const speed = Math.hypot(r.velocity_x_cm_s, r.velocity_y_cm_s);
          if (!speed) return null;
          const distance = fire
            ? Math.min(1300, Math.max(0, time - fire.elapsed_s) * speed)
            : 0;
          const px = r.source_x_cm + (distance * r.velocity_x_cm_s) / speed,
            py = r.source_y_cm + (distance * r.velocity_y_cm_s) / speed;
          return (
            <g key={id}>
              <line
                x1={x(r.source_x_cm)}
                y1={y(r.source_y_cm)}
                x2={x(r.source_x_cm + (1300 * r.velocity_x_cm_s) / speed)}
                y2={y(r.source_y_cm + (1300 * r.velocity_y_cm_s) / speed)}
                className="survive-threat-path"
              />
              {fire && (
                <circle
                  cx={x(px)}
                  cy={y(py)}
                  r={r.c}
                  className="survive-projectile"
                />
              )}
              <title>
                {pretty(r.detail)} · reconstructed constant-speed flight
              </title>
            </g>
          );
        })}
        {destination && (
          <g className="survive-destination">
            <line
              x1={x(destination.a) - 60}
              x2={x(destination.a) + 60}
              y1={y(destination.b)}
              y2={y(destination.b)}
            />
            <line
              x1={x(destination.a)}
              x2={x(destination.a)}
              y1={y(destination.b) - 60}
              y2={y(destination.b) + 60}
            />
            <title>Accepted move destination</title>
          </g>
        )}
        {point && (
          <g>
            <circle
              cx={x(point.x_cm)}
              cy={y(point.y_cm)}
              r={point.hit_radius_cm || 65}
              className="survive-hit-circle"
            />
            <circle
              cx={x(point.x_cm)}
              cy={y(point.y_cm)}
              r="30"
              className="survive-player"
            />
            <title>
              Last recorded position, {number(point.elapsed_s, 3)} seconds
            </title>
          </g>
        )}
      </svg>
      <small>
        {point && time - point.elapsed_s > 0.15
          ? "Position unavailable at this time; showing the last observation. "
          : ""}
        {point
          ? `Last recorded position: ${number(point.elapsed_s, 3)} s · ${point.movement_mode}`
          : "Awaiting recorded positions."}{" "}
      </small>
      <details>
        <summary>Replay details</summary>
        <p>
          No interpolation across blink or sample gaps. Arena geometry is
          illustrative; projectile flight is reconstructed from recorded fire
          and velocity.
        </p>
        <div className="survive-legend">
          <span>● Player / hit radius</span>
          <span>× Accepted destination</span>
          <span>Dashed: dash / threat path</span>
        </div>
      </details>
    </section>
  );
}

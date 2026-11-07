import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import { lastAt, number, pretty } from "./replay-model.mjs";
import { Info } from "../Info.jsx";
import "./arena.css";

const TERMINALS = new Set([
  "threat_hit",
  "threat_expired",
  "threat_blocked",
  "threat_cancelled",
]);

export default function Arena({
  rows,
  points,
  time,
  exactRecord,
  recordingId,
  onPause,
  onJump,
}) {
  const map = useRef(null);
  const key = "surge.replay.marks.v1." + recordingId;
  const [marks, setMarks] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(saved)
        ? saved.filter(
            (m) =>
              m &&
              Number.isFinite(m.x) &&
              Number.isFinite(m.y) &&
              Number.isFinite(m.time) &&
              Number.isInteger(m.seq) &&
              typeof m.note === "string",
          )
        : [];
    } catch {
      return [];
    }
  });
  const [note, setNote] = useState("");
  const [placing, setPlacing] = useState(false);
  const [message, setMessage] = useState("");
  const [toolsOpen, setToolsOpen] = useState(false);
  const [camera, setCamera] = useState("player");
  const [palette, setPalette] = useState("standard");
  const [large, setLarge] = useState(false);
  const [aspect, setAspect] = useState(2);
  useLayoutEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setAspect(width / height);
    });
    observer.observe(map.current);
    return () => observer.disconnect();
  }, []);
  const point = exactRecord || lastAt(points, time);
  const record = exactRecord || lastAt(rows, time);
  const width = Math.min(2600, 1200 * aspect);
  const height = width / aspect;
  const center = (value, size) =>
    size >= 2600
      ? 0
      : Math.max(-1300 + size / 2, Math.min(1300 - size / 2, value || 0));
  const cameraBox =
    camera === "whole"
      ? "-1340 -1340 2680 2680"
      : [
          center(point?.x_cm, width) - width / 2,
          center(-point?.y_cm, height) - height / 2,
          width,
          height,
        ].join(" ");

  function saveMarks(next, success) {
    try {
      localStorage.setItem(key, JSON.stringify(next));
      setMarks(next);
      setMessage(success);
      return true;
    } catch {
      setMessage("Could not save marks on this device.");
      return false;
    }
  }
  function addMark(x, y) {
    if (!record || !recordingId || !Number.isFinite(x) || !Number.isFinite(y))
      return;
    if (Math.abs(x) > 1300 || Math.abs(y) > 1300) {
      setMessage("Choose a point inside the arena.");
      return;
    }
    const mark = {
      id: crypto.randomUUID(),
      seq: record.seq,
      time,
      x,
      y,
      note: note.trim() || "Replay mark",
    };
    if (saveMarks([...marks, mark], "Mark saved.")) {
      setNote("");
      setPlacing(false);
    }
  }
  function inspectObject(event) {
    const object = event.target.closest("[data-record]");
    if (!object) return;
    const row = rows.find((item) => item.seq === Number(object.dataset.record));
    if (row) onJump({ seq: row.seq, time: row.elapsed_s });
  }
  function place(event) {
    if (!placing) {
      inspectObject(event);
      return;
    }
    const matrix = map.current.getScreenCTM();
    if (!matrix) return;
    const pos = new DOMPoint(event.clientX, event.clientY).matrixTransform(
      matrix.inverse(),
    );
    addMark(pos.x, -pos.y);
  }
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
  const threatRows = useMemo(
    () =>
      rows.filter(
        (r) =>
          r.event === "threat_warning" ||
          r.event === "threat_fire" ||
          TERMINALS.has(r.event),
      ),
    [rows],
  );
  for (const r of threatRows) {
    if (r.elapsed_s > time) break;
    if (r.event === "threat_warning") threats.set(r.related_id, { warning: r });
    else if (r.event === "threat_fire" && threats.has(r.related_id))
      threats.get(r.related_id).fire = r;
    else if (TERMINALS.has(r.event)) threats.delete(r.related_id);
  }
  const actions = useMemo(
    () =>
      rows.filter(
        (r) =>
          (r.event === "command_grant" && r.detail === "move") ||
          r.event === "command_stop" ||
          r.event === "ability_start",
      ),
    [rows],
  );
  const lastAction = lastAt(actions, time);
  const destination = lastAction?.event === "command_grant" ? lastAction : null;
  const x = (n) => n,
    y = (n) => -n;
  return (
    <section
      className="survive-panel arena-view"
      data-large={large}
      data-palette={palette}
      aria-label="Recorded arena replay"
    >
      <header className="arena-header">
        <h3>
          Recorded arena replay{" "}
          <Info label="arena replay">
            Select a player, trail or threat to inspect its source record. The
            circle follows the last recorded position. Trails break at gaps and
            blinks. Terrain is illustrative and projectile flight is
            reconstructed.
          </Info>
        </h3>
        <button
          aria-expanded={toolsOpen}
          onClick={() => {
            setToolsOpen(!toolsOpen);
            setPlacing(false);
          }}
        >
          Replay tools
        </button>
      </header>
      {toolsOpen && (
        <div className="arena-tools">
          <label>
            Camera{" "}
            <select
              aria-label="Camera"
              value={camera}
              onChange={(e) => setCamera(e.target.value)}
            >
              <option value="player">Follow player</option>
              <option value="whole">Whole arena</option>
            </select>
          </label>
          <label>
            Colors{" "}
            <select
              aria-label="Colors"
              value={palette}
              onChange={(e) => setPalette(e.target.value)}
            >
              <option value="standard">Standard</option>
              <option value="contrast">High contrast</option>
            </select>
          </label>
          <button aria-pressed={large} onClick={() => setLarge(!large)}>
            {large ? "Standard size" : "Enlarge replay"}
          </button>
          <div className="arena-mark-tools">
            <label>
              Mark label{" "}
              <input
                maxLength={100}
                placeholder="Optional note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            <button
              disabled={!record || !recordingId}
              aria-pressed={placing}
              onClick={() => {
                onPause();
                setMessage("");
                setPlacing(!placing);
              }}
            >
              {placing ? "Cancel placement" : "Mark a location"}
            </button>
            <button
              disabled={!point || !recordingId}
              onClick={() => {
                onPause();
                addMark(point.x_cm, point.y_cm);
              }}
            >
              Mark player
            </button>
            <Info label="replay marks">
              Save a location, time and source record on this device. Choose a
              saved mark to reopen that record. Marks are personal notes and the
              source evidence stays intact.
            </Info>
          </div>
        </div>
      )}
      {placing && (
        <small>Click a location on the map, or choose Mark player.</small>
      )}
      <svg
        ref={map}
        className="survive-arena"
        data-placing={placing}
        onClick={place}
        viewBox={cameraBox}
        role="group"
        onKeyDown={(event) => {
          if (
            placing ||
            !["Enter", " "].includes(event.key) ||
            !event.target.closest("[data-record]")
          )
            return;
          event.preventDefault();
          inspectObject(event);
        }}
        aria-label="Recorded player trail, active threats and accepted movement destination"
      >
        <rect
          x="-1300"
          y="-1300"
          width="2600"
          height="2600"
          className="survive-arena-floor"
        >
          <title>Illustrative arena boundary</title>
        </rect>
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
          >
            <title>Illustrative terrain obstacle</title>
          </rect>
        ))}
        {segments.map(([a, b], i) => (
          <line
            key={b.seq}
            data-record={b.seq}
            x1={x(a.x_cm)}
            y1={y(a.y_cm)}
            x2={x(b.x_cm)}
            y2={y(b.y_cm)}
            className={
              a.movement_mode === "dash"
                ? "survive-dash-path"
                : "survive-walk-path"
            }
          >
            <title>
              {pretty(a.movement_mode)} trail · {number(a.elapsed_s, 3)}–
              {number(b.elapsed_s, 3)} s · records {a.seq}–{b.seq}
            </title>
          </line>
        ))}
        {[...threats].map(([id, { warning: r, fire }]) => {
          if (r.detail?.startsWith("circle"))
            return (
              <circle
                key={id}
                tabIndex={placing ? -1 : 0}
                role="button"
                data-record={r.seq}
                cx={x(r.a)}
                cy={y(r.b)}
                r={r.c}
                className="survive-threat-circle"
              >
                <title>
                  {pretty(r.detail)} warning · {number(r.elapsed_s, 3)} s ·
                  record {r.seq}
                </title>
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
            <g
              key={id}
              tabIndex={placing ? -1 : 0}
              role="button"
              data-record={(fire || r).seq}
            >
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
                {pretty(r.detail)} · reconstructed flight ·{" "}
                {number((fire || r).elapsed_s, 3)} s · record {(fire || r).seq}
              </title>
            </g>
          );
        })}
        {destination && (
          <g
            className="survive-destination"
            tabIndex={placing ? -1 : 0}
            role="button"
            data-record={destination.seq}
          >
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
            <title>
              Accepted move destination · {number(destination.elapsed_s, 3)} s ·
              record {destination.seq}
            </title>
          </g>
        )}
        {point && (
          <g tabIndex={placing ? -1 : 0} role="button" data-record={point.seq}>
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
              Last recorded position · {number(point.elapsed_s, 3)} s · record{" "}
              {point.seq}
            </title>
          </g>
        )}
        {marks
          .filter((m) => Math.abs(m.time - time) < 0.15)
          .map((mark) => (
            <g
              key={mark.id}
              className="arena-pin"
              transform={`translate(${mark.x} ${-mark.y})`}
            >
              <path d="M0 0 l-26 -38 26 -32 26 32 z" />
              <title>
                {mark.note} · {number(mark.time, 3)} s · record {mark.seq}
              </title>
            </g>
          ))}
      </svg>
      <small>
        {point && time - point.elapsed_s > 0.15
          ? "Position unavailable at this time; showing the last observation. "
          : ""}
        {point
          ? `Last recorded position: ${number(point.elapsed_s, 3)} s · ${point.movement_mode}`
          : "Awaiting recorded positions."}{" "}
      </small>
      {message && toolsOpen && <small role="status">{message}</small>}
      {marks.length > 0 && (
        <details className="arena-marks">
          <summary>Replay marks · {marks.length}</summary>
          <ul>
            {marks.map((m) => (
              <li key={m.id}>
                <button onClick={() => onJump(m)}>
                  {number(m.time, 3)} s · {m.note}
                </button>
                <button
                  aria-label={`Remove mark ${m.note} at ${number(m.time, 3)} seconds`}
                  onClick={() =>
                    saveMarks(
                      marks.filter((item) => item.id !== m.id),
                      "Mark removed.",
                    )
                  }
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

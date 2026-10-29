import React, { useState } from "react";
import { PROFILE } from "./replay-model.mjs";

export default function TrialControls({
  sources,
  busy,
  running,
  gameRunning,
  hidden,
  panelRef,
  onAction,
  onRefresh,
}) {
  const [source, setSource] = useState("next"),
    [profile, setProfile] = useState(PROFILE);
  const [mode, setMode] = useState("human"),
    [participant, setParticipant] = useState("player"),
    [seed, setSeed] = useState("1337"),
    [phase, setPhase] = useState("practice");
  return (
    <section
      className="survive-panel"
      aria-label="Trial and recording controls"
      ref={panelRef}
      hidden={hidden}
    >
      <h2>Play and record</h2>
      <p className="survive-launch-description">
        One 60-second round. The recorder arms before the game opens; your
        session is saved for review when the round ends.
      </p>
      <div className="survive-controls survive-launch-fields">
        <label>
          Participant alias
          <input
            aria-label="Participant alias"
            value={participant}
            maxLength={40}
            title="Letters, numbers, underscores and hyphens; start with a letter or number"
            onChange={(e) => setParticipant(e.target.value)}
            disabled={busy || running}
          />
        </label>
        <label>
          Input condition
          <select
            aria-label="Input condition"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            disabled={busy || running}
          >
            <option value="human">Human — your play</option>
            <option value="scripted">Scripted — legal game commands</option>
            <option value="mixed">Mixed — scheduled assistance</option>
            <option value="speed_probe">Controlled speed violation</option>
          </select>
        </label>
        <label>
          Seed
          <input
            aria-label="Seed"
            type="number"
            min="0"
            max="2147483647"
            step="1"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            disabled={busy || running}
          />
        </label>
        <label>
          Phase
          <select
            aria-label="Phase"
            value={phase}
            onChange={(e) => setPhase(e.target.value)}
            disabled={busy || running}
          >
            <option value="practice">Practice</option>
            <option value="development">Development</option>
            <option value="held-out">Held out — freeze required</option>
          </select>
        </label>
        <label>
          Profile
          <select
            aria-label="Profile"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            disabled={busy || running}
          >
            <option value={PROFILE}>Practice · Q 4 s / E 12 s</option>
            <option value="survive-lucian-reference-v1">
              Reference · Q 16 s / E 300 s
            </option>
          </select>
        </label>
        <button
          className="primary"
          disabled={
            busy ||
            running ||
            gameRunning ||
            !/^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/.test(participant.trim()) ||
            seed === "" ||
            !Number.isInteger(Number(seed)) ||
            Number(seed) < 0 ||
            Number(seed) > 2147483647
          }
          onClick={() =>
            onAction("survive_trial_start", {
              mode,
              seed: Number(seed),
              profile_id: profile,
              participant: participant.trim(),
              phase,
            })
          }
        >
          Play and record trial
        </button>
      </div>
      <div className="survive-launch-recap">
        <span>Right-click move</span>
        <span>S stop moving</span>
        <span>Q dash</span>
        <span>E blink</span>
        <span>
          {phase === "practice"
            ? "Practice · excluded from comparison rates"
            : phase === "held-out"
              ? "Held-out · frozen inputs required"
              : "Development collection"}
        </span>
      </div>
      {gameRunning && !running && (
        <p className="survive-notice">
          Recording has ended; the current game is still finishing. Your next
          trial becomes available when it exits.
        </p>
      )}
      <details>
        <summary>About collection settings</summary>
        <small>
          Human, scripted and mixed conditions are external study labels. Legal
          scripted behavior may produce no movement finding; this does not
          establish whether input was human. Practice sessions are excluded from
          mechanical outcome rates; choose Development when collecting a
          comparison baseline.
        </small>
      </details>
      <details>
        <summary>Record an existing or next game session</summary>
        <div className="survive-controls">
          <label>
            Source
            <select
              aria-label="Source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              disabled={busy || running}
            >
              <option value="next">Next newly created Survive round</option>
              {sources.map((s) => (
                <option key={s.source_id} value={s.source_id}>
                  {s.filename || s.source_id} · {s.bytes} bytes
                </option>
              ))}
            </select>
          </label>
          <button
            disabled={busy || running}
            onClick={() =>
              onAction("survive_start", {
                source_id: source,
                profile_id: profile,
              })
            }
          >
            Start recording
          </button>
          <button disabled={busy} onClick={onRefresh}>
            Refresh sessions
          </button>
        </div>
        <small>
          Existing sources are read from their beginning and labeled as
          backfill. Choosing Next waits for a new round; recording does not
          change gameplay.
        </small>
      </details>
    </section>
  );
}

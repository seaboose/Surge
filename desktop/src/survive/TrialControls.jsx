import React, { useEffect, useId, useState } from "react";
import { Info } from "../Info.jsx";
import { PROFILE, pretty } from "./replay-model.mjs";

function Field({ label, help, children }) {
  const id = useId();
  return (
    <div className="survive-field">
      <div className="survive-field-heading">
        <label htmlFor={id}>{label}</label>
        <Info label={label}>{help}</Info>
      </div>
      {React.cloneElement(children, { id, "aria-label": label })}
    </div>
  );
}

function ProfileOptions() {
  return (
    <>
      <option value={PROFILE}>Practice · Q 4 s / E 12 s</option>
      <option value="survive-lucian-reference-v1">
        Reference · Q 16 s / E 300 s
      </option>
    </>
  );
}

export default function TrialControls({
  busy,
  running,
  gameRunning,
  onAction,
}) {
  const [profile, setProfile] = useState(PROFILE);
  const [mode, setMode] = useState("human"),
    [participant, setParticipant] = useState("player"),
    [seed, setSeed] = useState("1337"),
    [phase, setPhase] = useState("practice");
  const locked = busy || running;
  return (
    <section
      className="survive-panel"
      aria-label="Trial and recording controls"
    >
      <p className="survive-launch-description">
        One 60-second round. Recording starts before the game opens.
      </p>
      <div className="survive-controls survive-launch-fields">
        <Field
          label="Participant alias"
          help="Give this player a short name so you can group their sessions. Use letters, digits, underscores or hyphens."
        >
          <input
            value={participant}
            maxLength={40}
            onChange={(e) => setParticipant(e.target.value)}
            disabled={locked}
          />
        </Field>
        <Field
          label="Input condition"
          help="Choose who supplies movement commands. Human, scripted and mixed describe the trial setup. The detector assesses movement independently."
        >
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            disabled={locked}
          >
            <option value="human">Human — your play</option>
            <option value="scripted">Scripted — legal game commands</option>
            <option value="mixed">Mixed — scheduled assistance</option>
            <option value="speed_probe">Controlled speed violation</option>
          </select>
        </Field>
        <Field
          label="Seed"
          help="Use the same number to repeat the round’s initial conditions across sessions."
        >
          <input
            type="number"
            min="0"
            max="2147483647"
            step="1"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            disabled={locked}
          />
        </Field>
        <Field
          label="Phase"
          help="Practice is for exploring. Development contributes to comparison rates. Held-out sessions use a frozen setup for independent evaluation."
        >
          <select
            value={phase}
            onChange={(e) => setPhase(e.target.value)}
            disabled={locked}
          >
            <option value="practice">Practice</option>
            <option value="development">Development</option>
            <option value="held-out">Held out — freeze required</option>
          </select>
        </Field>
        <Field
          label="Profile"
          help="Choose the game’s movement and ability limits. Surge checks the recording against this same profile."
        >
          <select
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            disabled={locked}
          >
            <ProfileOptions />
          </select>
        </Field>
        <button
          className="primary"
          disabled={
            locked ||
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
      </div>
      {gameRunning && !running && (
        <p className="survive-notice">
          The current game is finishing. You can launch another round when it
          exits.
        </p>
      )}
    </section>
  );
}

export function RecordingLibrary({
  sources,
  sessions,
  busy,
  running,
  selectedId,
  onAction,
  onRefresh,
}) {
  const [choice, setChoice] = useState("");
  const [profile, setProfile] = useState(PROFILE);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [feedback, setFeedback] = useState("");
  const saved = sessions.filter((s) => !s.in_progress);
  const value =
    choice ||
    (saved.find((s) => s.recording_id === selectedId)
      ? "saved:" + selectedId
      : saved.length
        ? "saved:" + saved[0].recording_id
        : "example");
  const current = saved.find((s) => value === "saved:" + s.recording_id);
  const source = value.startsWith("source:") ? value.slice(7) : null;
  useEffect(() => {
    if (choice.startsWith("saved:") && !current) setChoice("");
    if (
      source &&
      source !== "next" &&
      !sources.some((s) => s.source_id === source)
    )
      setChoice("");
  }, [choice, current, source, sources]);
  function choose(option) {
    setChoice(option);
    setEditing(false);
    setFeedback("");
  }
  async function openChoice() {
    if (source) {
      const started = await onAction("survive_start", {
        source_id: source,
        profile_id: profile,
      });
      if (started !== false) choose("");
    } else if (value === "example") {
      await onAction("survive_template", {}, "open");
    } else if (current) {
      await onAction(
        "survive_open",
        { recording_id: current.recording_id },
        "open",
      );
    }
  }
  function startRename() {
    setChoice("saved:" + current.recording_id);
    setDraft(current.display_name);
    setEditing(true);
    setFeedback("");
  }
  async function rename(event) {
    event.preventDefault();
    if (!current || !draft.trim() || busy) return;
    const ok = await onAction(
      "survive_rename",
      { recording_id: current.recording_id, name: draft.trim() },
      "rename",
    );
    if (ok !== false) {
      setEditing(false);
      setFeedback("Name saved.");
    }
  }
  return (
    <section
      className="survive-panel survive-library"
      aria-label="Recorded session library"
    >
      <details open>
        <summary>
          Recordings{" "}
          <Info label="Recordings">
            Open or rename a saved recording, try the standard example, or start
            recording a game source.
          </Info>
        </summary>
        <div className="survive-controls">
          <Field
            label="Recording"
            help="Open saved evidence or the simulated example to unlock Review and Explain. To collect an existing or upcoming round, choose a game source."
          >
            <select
              value={value}
              disabled={busy}
              onChange={(e) => choose(e.target.value)}
            >
              {saved.length > 0 && (
                <optgroup label="Saved recordings">
                  {saved.map((s) => (
                    <option
                      key={s.recording_id}
                      value={"saved:" + s.recording_id}
                    >
                      {s.display_name} · {pretty(s.state || "saved")} ·{" "}
                      {s.records ?? "?"} records
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label="Example">
                <option value="example">Standard example · simulated</option>
              </optgroup>
              <optgroup label="Record a game source">
                <option value="source:next">
                  Next newly created Survive round
                </option>
                {sources.map((s) => (
                  <option key={s.source_id} value={"source:" + s.source_id}>
                    {s.filename || s.source_id} · {s.bytes} bytes
                  </option>
                ))}
              </optgroup>
            </select>
          </Field>
          {source && (
            <Field
              label="Source profile"
              help="Match the game’s profile. Surge reads existing data from its beginning. Choosing the next round waits for a newly created source."
            >
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                disabled={busy || running}
              >
                <ProfileOptions />
              </select>
            </Field>
          )}
          <button
            className="primary"
            disabled={
              busy || (source ? running : !current && value !== "example")
            }
            onClick={openChoice}
          >
            {source
              ? "Start recording"
              : value === "example"
                ? "Open example"
                : "Open recording"}
          </button>
          {current && !editing && (
            <button disabled={busy} onClick={startRename}>
              Rename
            </button>
          )}
          <button disabled={busy} onClick={onRefresh}>
            Refresh sessions
          </button>
        </div>
        {current?.state === "interrupted" && (
          <small>
            This interrupted recording may have incomplete evidence.
          </small>
        )}
        {current && editing && (
          <form className="survive-controls" onSubmit={rename}>
            <Field
              label="Recording name"
              help="Use a name you will recognize in the library. Existing evidence links keep their original recording ID."
            >
              <input
                autoFocus
                required
                maxLength={80}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={busy}
              />
            </Field>
            <button type="submit" disabled={busy || !draft.trim()}>
              Save name
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </form>
        )}
        {feedback && <small role="status">{feedback}</small>}
      </details>
    </section>
  );
}

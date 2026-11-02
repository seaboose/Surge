import React, { useEffect, useMemo, useRef, useState } from "react";
import SurviveInvestigations from "./SurviveInvestigations";
import {
  WorkflowBar,
  RecordingStrip,
  SessionSummary,
  MarkerTimeline,
} from "./SurviveFlow";
import { advanceReplay, clampTimelineRange } from "./survive-flow.mjs";
import ResizableReview from "./ResizableReview";
import TrialControls from "./survive/TrialControls.jsx";
import RecordingPanel from "./survive/RecordingPanel.jsx";
import StudyComparison from "./survive/StudyComparison.jsx";
import Arena from "./survive/ArenaReplay.jsx";
import ConstraintChart from "./survive/ConstraintChart.jsx";
import Inspector from "./survive/SelectedEvidence.jsx";
import {
  ACTIVE,
  POINTS,
  number,
  pretty,
  lastAt,
  viewRows,
  lastViewTime,
} from "./survive/replay-model.mjs";

async function api(method, args = {}) {
  const reply = await window.surge.request(method, args);
  if (!reply?.ok) throw new Error(reply?.error || "Survive request failed.");
  return reply.value;
}

export default function SurviveWorkspace({ onClose }) {
  const [sources, setSources] = useState([]),
    [sessions, setSessions] = useState([]),
    [trials, setTrials] = useState([]);
  const [active, setActive] = useState(null),
    [snapshot, setSnapshot] = useState(null),
    [viewMode, setViewMode] = useState("live");
  const [paused, setPaused] = useState(false),
    [follow, setFollow] = useState(true),
    [time, setTime] = useState(0),
    [fixedDomain, setFixedDomain] = useState(null);
  const [selectedSeq, setSelectedSeq] = useState(null),
    [constraintId, setConstraintId] = useState(null),
    [showSamples, setShowSamples] = useState(false),
    [eventPage, setEventPage] = useState(0);
  const [rawSelection, setRawSelection] = useState(null);
  const [investigationOpenRequest, setInvestigationOpenRequest] = useState(0);
  const [attachRequest, setAttachRequest] = useState(null);
  const [investigationState, setInvestigationState] = useState(null);
  const [stage, setStage] = useState("play");
  const [activeTrial, setActiveTrial] = useState(null);
  const [completedRecording, setCompletedRecording] = useState(null);
  const [lastStatusAt, setLastStatusAt] = useState(null);
  const [statusFailed, setStatusFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const workspaceRef = useRef(null);
  const launcherRef = useRef(null),
    recordingRef = useRef(null),
    reviewRef = useRef(null),
    notebookRef = useRef(null);
  const requestNumber = useRef(0);
  const investigationLeaveGuard = useRef(() => true);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(
      "Choose a trial, or record a Survive session already on this computer.",
    ),
    [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const buffer = useRef(null),
    cursor = useRef(0),
    actionLock = useRef(false),
    viewRef = useRef({ paused, follow, viewMode }),
    epoch = useRef(0);
  viewRef.current = { paused, follow, viewMode };
  const running = ACTIVE.has(active?.state);
  const gameRunning = activeTrial?.process_state === "running";
  const rows = useMemo(() => viewRows(snapshot), [snapshot]);
  const events =
    snapshot?.view?.events || rows.filter((r) => r.event !== "sample");
  const points = useMemo(() => rows.filter((r) => POINTS.has(r.event)), [rows]);
  const constraints = snapshot?.view?.constraints || [];
  const capture = snapshot?.capture;
  const final = capture?.analysis_state === "complete";
  const duration = Math.max(0.001, lastViewTime(snapshot));
  const playbackClock = useRef({ duration, rate: playbackRate });
  playbackClock.current = { duration, rate: playbackRate };
  const selectedTime = Math.min(Math.max(0, time), duration);
  const domain = useMemo(() => {
    if (fixedDomain) return clampTimelineRange(fixedDomain, duration);
    if (duration <= 8) return [0, Math.max(1, duration)];
    const begin = Math.max(0, Math.min(duration - 8, selectedTime - 4));
    return [begin, begin + 8];
  }, [duration, selectedTime, fixedDomain]);
  const selectedRecord =
    rows.find((r) => r.seq === selectedSeq) || lastAt(rows, selectedTime);
  const selectedConstraint =
    constraints.find((r) => r.event_id === constraintId) ||
    constraints.find((r) => r.end_seq === selectedRecord?.seq);
  const inspectedRaw =
    rawSelection &&
    rawSelection.recording_id === capture?.recording_id &&
    rawSelection.seq === selectedRecord?.seq
      ? rawSelection
      : null;
  const investigationSelection = {
    recording_id: capture?.recording_id,
    seq: selectedRecord?.seq,
    time_s: selectedRecord?.elapsed_s,
    constraint_id: selectedConstraint?.event_id || null,
    finalized: Boolean(
      capture &&
      ["complete", "stopped", "failed"].includes(capture.state) &&
      !capture.finalizing,
    ),
  };
  const visibleEvents = (showSamples ? rows : events).filter(
    (r) => r.elapsed_s >= domain[0] && r.elapsed_s <= domain[1],
  );
  const lastPage = Math.max(0, Math.ceil(visibleEvents.length / 30) - 1);
  const boundedPage = Math.min(eventPage, lastPage);
  const health = active?.health || {};

  function accept(value, force = false) {
    if (!value?.capture) return;
    setLastStatusAt(performance.now());
    setStatusFailed(false);
    setError((value) =>
      value.startsWith("Recording status unavailable:") ? "" : value,
    );
    if ("trial" in value) setActiveTrial(value.trial);
    setActive(value.capture);
    const old = buffer.current;
    const isSame = old?.capture?.recording_id === value.capture.recording_id;
    const merged =
      isSame && !force
        ? [...old.records, ...(value.records || [])]
        : value.records || [];
    const seen = new Set();
    const records = merged
      .filter((r) => {
        if (seen.has(r.seq)) return false;
        seen.add(r.seq);
        return true;
      })
      .slice(0, 10000);
    const next = { ...value, records };
    buffer.current = next;
    cursor.current = value.next_cursor ?? records.length;
    if (!ACTIVE.has(value.capture.state) && !value.capture.finalizing) {
      setCompletedRecording(value.capture);
    }
    if (
      force ||
      (!viewRef.current.paused && viewRef.current.viewMode === "live")
    ) {
      setSnapshot(next);
      if (force || viewRef.current.follow) setTime(lastViewTime(next));
    }
  }

  async function refreshLists() {
    const [a, b, c] = await Promise.all([
      api("survive_sources"),
      api("survive_sessions"),
      api("survive_trials"),
    ]);
    setSources(a.sources || []);
    setSessions(b.sessions || []);
    setTrials(c.trials || []);
  }

  useEffect(() => {
    let alive = true;
    const initialEpoch = epoch.current;
    Promise.all([
      api("survive_sources"),
      api("survive_sessions"),
      api("survive_trials"),
      api("survive_status", { after: 0 }),
    ])
      .then(([a, b, c, d]) => {
        if (!alive || initialEpoch !== epoch.current) return;
        setSources(a.sources || []);
        setSessions(b.sessions || []);
        setTrials(c.trials || []);
        if (d.capture) accept(d, true);
      })
      .catch((e) => {
        if (alive && initialEpoch === epoch.current) setError(e.message);
      });
    return () => {
      alive = false;
      epoch.current++;
    };
  }, []);

  useEffect(() => {
    if (!running && !gameRunning) return;
    let alive = true,
      timer;
    const poll = async () => {
      const started = epoch.current;
      if (!actionLock.current) {
        try {
          const value = await api("survive_status", { after: cursor.current });
          if (alive && started === epoch.current) {
            const previousCapture = buffer.current?.capture;
            accept(value);
            if (
              !ACTIVE.has(value.capture?.state) &&
              (ACTIVE.has(previousCapture?.state) ||
                previousCapture?.finalizing ||
                (gameRunning && value.trial?.process_state !== "running"))
            ) {
              setNotice(
                value.capture?.state === "complete"
                  ? "Game capture finalized. Saved evidence and final movement analysis are available."
                  : "Recording ended. Inspect its completion and coverage before comparison.",
              );
              refreshLists().catch((e) => setError(e.message));
            }
          }
        } catch (e) {
          if (alive && started === epoch.current) {
            setStatusFailed(true);
            setError(`Recording status unavailable: ${e.message}`);
          }
        }
      }
      if (alive) timer = setTimeout(poll, 500);
    };
    timer = setTimeout(poll, 250);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [running, gameRunning]);

  useEffect(() => {
    if (!playing) return;
    let frame, previous;
    const tick = (now) => {
      if (previous !== undefined) {
        const delta = Math.max(0, (now - previous) / 1000);
        setTime((value) =>
          advanceReplay(
            value,
            delta,
            playbackClock.current.rate,
            playbackClock.current.duration,
          ),
        );
      }
      previous = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    const hidden = () => {
      if (document.hidden) setPlaying(false);
    };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, [playing]);
  useEffect(() => {
    if (playing && time >= duration) setPlaying(false);
  }, [time, duration, playing]);

  useEffect(() => {
    const recording_id = capture?.recording_id,
      seq = selectedRecord?.seq;
    if (!recording_id || !Number.isInteger(seq)) {
      setRawSelection(null);
      return;
    }
    let alive = true;
    if (playing) {
      setRawSelection({
        recording_id,
        seq,
        error: "Pause replay to inspect the exact source record.",
      });
      return;
    }
    const cached = snapshot?.records?.find((row) => row.seq === seq);
    if (cached) {
      setRawSelection({ recording_id, seq, record: cached });
      return;
    }
    setRawSelection(null);
    api("survive_record", { recording_id, seq })
      .then((value) => {
        if (alive && value.recording_id === recording_id && value.seq === seq)
          setRawSelection({ recording_id, seq, record: value.record });
      })
      .catch((e) => {
        if (alive) setRawSelection({ recording_id, seq, error: e.message });
      });
    return () => {
      alive = false;
    };
  }, [capture?.recording_id, selectedRecord?.seq, playing]);

  useEffect(() => {
    if (stage !== "review") setPlaying(false);
    workspaceRef.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [stage]);

  function resetViewMode(mode) {
    const follow = mode === "live";
    viewRef.current = { paused: false, follow, viewMode: mode };
    setViewMode(mode);
    setPaused(false);
    setFollow(follow);
  }

  async function act(method, args = {}, kind = "normal") {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setError("");
    epoch.current++;
    setPlaying(false);
    try {
      const value = await api(method, args);
      if (kind === "open") {
        setFixedDomain(null);
        resetViewMode("saved");
        setSnapshot(value);
        setTime(viewRows(value)[0]?.elapsed_s || 0);
        setSelectedSeq(null);
        setConstraintId(null);
        setEventPage(0);
        setStage("review");
        setNotice(
          "Saved recording reopened and verified. This view is recorded evidence.",
        );
      } else if (value.capture && method === "survive_stop") {
        accept(value);
        setNotice(
          "Recording stopped. Gameplay continues independently; the selected time and view are retained. A mid-round segment stays partial.",
        );
      } else if (value.capture) {
        resetViewMode("live");
        setSelectedSeq(null);
        setConstraintId(null);
        setEventPage(0);
        setCompletedRecording(null);
        setFixedDomain(null);
        setStage("record");
        cursor.current = 0;
        buffer.current = null;
        accept(value, true);
        setNotice(
          value.trial
            ? "Trial launched and recorder armed. Return here to inspect the recorded game."
            : "Recorder started. Waiting for source records if the selected round has not begun.",
        );
      } else if (kind === "report") setReport(value);
      else
        setNotice(
          value.message ||
            "Study setting saved separately from detector evidence.",
        );
      await refreshLists();
    } catch (e) {
      setError(e.message);
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }

  function selectTime(value) {
    setPlaying(false);
    viewRef.current.follow = false;
    setTime(value);
    setFollow(false);
    setSelectedSeq(null);
    setConstraintId(null);
    setEventPage(0);
  }
  async function navigateInvestigationEvidence(target) {
    if (actionLock.current)
      throw new Error("Wait for the current replay operation to finish.");
    actionLock.current = true;
    epoch.current++;
    setBusy(true);
    setPlaying(false);
    try {
      // Resolve returns one verified immutable snapshot. Additional source reads
      // here could replace the pinned version between verification and display.
      const value = target.replay;
      const exact = {
        recording_id: target.recording_id,
        seq: target.seq,
        record: target.raw_record,
      };
      if (
        !value ||
        value.capture?.recording_id !== target.recording_id ||
        exact.record?.seq !== target.seq ||
        exact.record?.elapsed_s !== target.time_s ||
        exact.record?.session_id !== value.capture?.session_id ||
        (target.constraint_id &&
          target.constraint?.event_id !== target.constraint_id)
      )
        throw new Error(
          "The verified evidence response does not match its replay selection.",
        );
      value.records = [
        ...(value.records || []).filter((row) => row.seq !== target.seq),
        exact.record,
      ];
      if (target.constraint)
        value.view = {
          ...value.view,
          constraints: [
            ...(value.view?.constraints || []).filter(
              (item) => item.event_id !== target.constraint_id,
            ),
            target.constraint,
          ],
        };
      setSnapshot(value);
      resetViewMode("saved");
      setTime(target.time_s);
      setFixedDomain(null);
      setSelectedSeq(target.seq);
      setConstraintId(target.constraint_id || null);
      setEventPage(0);
      setRawSelection(exact);
      setNotice(
        `${target.evidence_id} restored from investigation revision ${target.revision}. Active recording is unchanged.`,
      );
      setStage("review");
      reviewRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }
  function chooseConstraint(value) {
    selectTime(value.elapsed_s);
    setConstraintId(value.event_id);
    setSelectedSeq(value.end_seq);
  }
  function chooseRecord(value) {
    if (!value) return;
    selectTime(value.elapsed_s);
    setSelectedSeq(value.seq);
    const linked = constraints.find((item) => item.end_seq === value.seq);
    setConstraintId(linked?.event_id || null);
  }
  function navigateStage(value) {
    setNotice("");
    if (stage === "review" && value !== "review") {
      setFollow(false);
      viewRef.current.follow = false;
    }
    setStage(value);
    if (value === "explain") setInvestigationOpenRequest((v) => v + 1);
  }
  function changeDomain(value) {
    setFixedDomain(value === null ? null : clampTimelineRange(value, duration));
    setEventPage(0);
  }
  function addSelection() {
    setNotice("");
    setPlaying(false);
    setFollow(false);
    viewRef.current.follow = false;
    setStage("explain");
    setAttachRequest({
      request_id: ++requestNumber.current,
      selection: investigationSelection,
    });
    setInvestigationOpenRequest((v) => v + 1);
  }
  function togglePlayback() {
    if (playing) {
      setPlaying(false);
      return;
    }
    setFollow(false);
    viewRef.current.follow = false;
    setSelectedSeq(null);
    setConstraintId(null);
    if (time >= duration) setTime(0);
    setPlaying(true);
  }
  function resumeLive() {
    setPlaying(false);
    resetViewMode("live");
    setSelectedSeq(null);
    setConstraintId(null);
    if (buffer.current) {
      setSnapshot(buffer.current);
      setTime(lastViewTime(buffer.current));
    }
  }
  function togglePause() {
    setPlaying(false);
    if (paused) {
      setPaused(false);
      if (buffer.current && viewMode === "live") {
        setSnapshot(buffer.current);
        if (follow) setTime(lastViewTime(buffer.current));
      }
    } else setPaused(true);
  }

  return (
    <div
      ref={workspaceRef}
      className="survive-workspace"
      data-working={busy}
      data-stage={stage}
    >
      <header className="survive-header">
        <button
          onClick={() => {
            if (investigationLeaveGuard.current()) onClose();
            else navigateStage("explain");
          }}
          title="Recording continues independently when you return to Surge"
        >
          Back to Surge
        </button>
        <div>
          <h1>Survive sessions</h1>
          <p>Play. Review evidence. Explain what you found.</p>
        </div>
      </header>
      <WorkflowBar
        stage={stage}
        onNavigate={navigateStage}
        hasRecording={Boolean(rows.length || sessions.length)}
        hasReport={Boolean(investigationState?.investigationId)}
      />
      <div
        ref={recordingRef}
        className="survive-scroll-target"
        hidden={!running && !gameRunning && stage !== "record"}
      >
        <RecordingStrip
          capture={active}
          updatedAt={lastStatusAt}
          requestFailed={statusFailed}
          busy={busy}
          trialRunning={gameRunning}
          onStop={() => act("survive_stop")}
        />
      </div>
      {health.error && (
        <p role="alert" className="survive-error">
          {health.error}
        </p>
      )}
      {error && (
        <p role="alert" className="survive-error">
          {error}
        </p>
      )}
      <TrialControls
        sources={sources}
        busy={busy}
        running={running}
        gameRunning={gameRunning}
        hidden={stage !== "play"}
        panelRef={launcherRef}
        onAction={act}
        onRefresh={() => refreshLists().catch((e) => setError(e.message))}
      />
      <RecordingPanel
        active={active}
        running={running}
        hasRecording={Boolean(buffer.current)}
        hidden={stage !== "record"}
        onNavigate={navigateStage}
      />
      <p
        role="status"
        className="survive-notice"
        hidden={
          !["record", "review"].includes(stage) ||
          !(notice || paused || (viewMode === "saved" && running))
        }
      >
        {notice}
        {paused
          ? running
            ? " View paused; recording continues."
            : " View paused; use Follow latest recording to inspect the final state."
          : ""}
        {viewMode === "saved" && running
          ? " A separate live recording continues in the background."
          : ""}
      </p>
      {completedRecording &&
        (["play", "record"].includes(stage) ||
          capture?.recording_id !== completedRecording.recording_id ||
          viewMode !== "saved") && (
          <section className="survive-handoff" aria-label="Post-game handoff">
            <div>
              <h2>
                {completedRecording.analysis_state === "complete"
                  ? "Your recording is ready"
                  : "Recording ended · review its coverage"}
              </h2>
              <p>
                {number(completedRecording.source_elapsed_s, 1)} s of game time
                · {completedRecording.records ?? 0} records ·{" "}
                {pretty(
                  completedRecording.completion || completedRecording.state,
                )}
                .
                {paused || viewMode === "saved"
                  ? " Your current inspection stays in place until you choose Review."
                  : " Open the saved recording to see its summary and findings."}
              </p>
            </div>
            <button
              className="primary"
              disabled={busy}
              onClick={async () => {
                await act(
                  "survive_open",
                  { recording_id: completedRecording.recording_id },
                  "open",
                );
                reviewRef.current?.scrollIntoView({
                  block: "start",
                  behavior: "smooth",
                });
              }}
            >
              Review this session
            </button>
          </section>
        )}
      <div
        ref={reviewRef}
        className="survive-scroll-target"
        hidden={stage !== "review"}
      >
        {capture && (
          <details className="survive-summary-disclosure">
            <summary>
              Session summary{" "}
              <span>
                {number(capture.source_elapsed_s, 1)} s ·{" "}
                {final
                  ? `${snapshot?.view?.analysis?.counts?.Review ?? "Unavailable"} Review · ${snapshot?.view?.analysis?.counts?.Unknown ?? "Unavailable"} Unknown`
                  : "Assessment pending or incomplete"}
              </span>
            </summary>
            <SessionSummary snapshot={snapshot} />
          </details>
        )}
      </div>
      <section
        className="survive-panel survive-library"
        aria-label="Recorded session library"
        hidden={!["play", "review"].includes(stage)}
      >
        <details open={stage === "play"}>
          <summary>
            {stage === "play" ? "Saved recordings" : "Switch recording"} ·{" "}
            {sessions.length}
          </summary>
          <h2>Recorded sessions</h2>
          <div className="survive-session-list">
            {sessions.length ? (
              sessions.map((s) => (
                <button
                  key={s.recording_id}
                  disabled={busy}
                  className={
                    capture?.recording_id === s.recording_id ? "active" : ""
                  }
                  onClick={() =>
                    act(
                      "survive_open",
                      { recording_id: s.recording_id },
                      "open",
                    )
                  }
                >
                  <strong>
                    {String(
                      s.session_id || s.source_id || s.recording_id,
                    ).slice(0, 12)}
                  </strong>
                  <span>
                    {pretty(s.state || s.completion || "saved")} ·{" "}
                    {s.records ?? "?"} rows
                    {s.state === "interrupted" ? " · Unknown evidence" : ""}
                    {s.verified === false ? " · verify on open" : ""}
                  </span>
                </button>
              ))
            ) : (
              <p>
                No saved recordings yet. A trial will create a new session
                without replacing earlier evidence.
              </p>
            )}
          </div>
        </details>
      </section>
      <div
        className="survive-review-view"
        aria-label="Review workspace"
        hidden={stage !== "review"}
      >
        {rows.length === 0 && (
          <section className="survive-panel">
            <h2>Choose a recording</h2>
            <p>Open a saved session above, or start a round in Play.</p>
          </section>
        )}
        {rows.length > 0 && (
          <>
            {snapshot?.view?.metadata?.display_truncated === true && (
              <p className="survive-error" role="status">
                This display is bounded and does not include every recorded
                item. Retained source evidence remains separate; do not
                interpret missing display items as missing source events.
              </p>
            )}
            <section
              className="survive-panel"
              aria-label="Shared time controls"
            >
              <div className="survive-controls">
                <h2>
                  {viewMode === "saved"
                    ? "Recorded evidence"
                    : paused
                      ? "Pinned recording view"
                      : "Recording evidence"}
                </h2>
                <strong>{number(selectedTime, 3)} s</strong>
                <div className="survive-controls survive-record-actions">
                  <button
                    disabled={(!running && !paused) || viewMode !== "live"}
                    aria-pressed={paused}
                    onClick={togglePause}
                  >
                    {paused ? "Resume view" : "Pause view"}
                  </button>
                  <button
                    disabled={
                      !buffer.current ||
                      (follow && !paused && viewMode === "live")
                    }
                    onClick={resumeLive}
                  >
                    Follow latest recording
                  </button>
                </div>

                <button
                  aria-pressed={playing}
                  disabled={busy || !rows.length}
                  onClick={togglePlayback}
                >
                  {playing ? "Pause replay" : "Play replay"}
                </button>
                <label>
                  Replay speed
                  <select
                    aria-label="Replay speed"
                    value={playbackRate}
                    onChange={(e) => setPlaybackRate(Number(e.target.value))}
                  >
                    <option value="0.5">0.5×</option>
                    <option value="1">1×</option>
                    <option value="2">2×</option>
                  </select>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={Boolean(
                      fixedDomain && domain[0] === 0 && domain[1] >= duration,
                    )}
                    onChange={(e) =>
                      changeDomain(e.target.checked ? [0, duration] : null)
                    }
                  />{" "}
                  Whole round
                </label>
                <button
                  disabled={!constraints.some((r) => r.status === "Review")}
                  onClick={() => {
                    const reviews = constraints.filter(
                      (r) => r.status === "Review",
                    );
                    const next =
                      reviews.find((r) => r.elapsed_s > selectedTime + 0.001) ||
                      reviews[0];
                    if (next) chooseConstraint(next);
                  }}
                >
                  Next review
                </button>
              </div>
              <label className="survive-time-label">
                Game time
                <input
                  aria-label="Game time"
                  type="range"
                  min="0"
                  max={duration}
                  step="0.001"
                  value={selectedTime}
                  onChange={(e) => selectTime(Number(e.target.value))}
                />
              </label>
              <small>
                {capture?.analysis_state === "complete"
                  ? "Complete-run analysis"
                  : `Analysis ${capture?.analysis_state || "pending"}`}{" "}
                · {capture?.completion || "No game completion recorded"} · local
                unsigned evidence
              </small>
            </section>
            <ResizableReview
              replay={
                <Arena
                  rows={
                    Number.isInteger(selectedSeq)
                      ? rows.filter((r) => r.seq <= selectedSeq)
                      : rows
                  }
                  points={
                    Number.isInteger(selectedSeq)
                      ? points.filter((r) => r.seq <= selectedSeq)
                      : points
                  }
                  exactRecord={
                    Number.isInteger(selectedSeq) ? selectedRecord : null
                  }
                  time={selectedTime}
                />
              }
              evidence={
                <Inspector
                  record={selectedRecord}
                  rawRecord={inspectedRaw?.record}
                  rawError={inspectedRaw?.error}
                  constraint={selectedConstraint}
                  capture={capture}
                  metadata={snapshot?.view?.metadata}
                  final={final}
                />
              }
            />
            <div className="survive-controls">
              <button
                onClick={addSelection}
                disabled={
                  busy || !selectedRecord || !investigationSelection.finalized
                }
              >
                Add selection to investigation
              </button>
              <small>
                Attach the selected event or movement interval to an
                evidence-linked report.
              </small>
            </div>
            <MarkerTimeline
              recordingId={capture?.recording_id}
              events={events}
              duration={duration}
              onDomainChange={changeDomain}
              points={points}
              domain={domain}
              time={selectedTime}
              selectTime={selectTime}
              constraints={constraints}
              chooseRecord={chooseRecord}
              chooseConstraint={chooseConstraint}
              truncated={snapshot?.view?.metadata?.display_truncated === true}
            />
            <details className="survive-panel survive-secondary">
              <summary>Movement measurements</summary>
              <ConstraintChart
                constraints={constraints}
                domain={domain}
                time={selectedTime}
                choose={chooseConstraint}
                final={final}
                analysisState={capture?.analysis_state}
              />
            </details>
            <details className="survive-panel survive-secondary">
              <summary>Event records</summary>
              <section aria-label="Related events">
                <div className="survive-controls">
                  <h2>Related events</h2>
                  <label>
                    <input
                      type="checkbox"
                      checked={showSamples}
                      onChange={(e) => {
                        setShowSamples(e.target.checked);
                        setEventPage(0);
                      }}
                    />{" "}
                    Include position samples
                  </label>
                  <span>
                    {number(domain[0], 1)}–{number(domain[1], 1)} s
                  </span>
                </div>
                <div className="survive-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Sequence</th>
                        <th>Game time</th>
                        <th>Event</th>
                        <th>Detail / related ID</th>
                        <th>Assessment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleEvents
                        .slice(boundedPage * 30, boundedPage * 30 + 30)
                        .map((r) => {
                          const linked = constraints.find(
                            (c) => c.end_seq === r.seq,
                          );
                          return (
                            <tr
                              key={r.seq}
                              className={
                                selectedRecord?.seq === r.seq
                                  ? "survive-selected"
                                  : ""
                              }
                            >
                              <td>
                                <button
                                  className="survive-sequence"
                                  aria-label={`Inspect record ${r.seq}`}
                                  onClick={() => {
                                    chooseRecord(r);
                                  }}
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
                                {!final
                                  ? capture?.analysis_state === "unavailable"
                                    ? "Unknown"
                                    : "Pending"
                                  : linked?.status || "No linked constraint"}
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
                <div className="survive-controls">
                  <button
                    disabled={boundedPage === 0}
                    onClick={() => setEventPage(boundedPage - 1)}
                  >
                    Previous events
                  </button>
                  <span>
                    Page {boundedPage + 1} of {lastPage + 1} ·{" "}
                    {visibleEvents.length} events in this time window
                  </span>
                  <button
                    disabled={boundedPage >= lastPage}
                    onClick={() => setEventPage(boundedPage + 1)}
                  >
                    Next events
                  </button>
                </div>
              </section>
            </details>
          </>
        )}
      </div>
      <div
        ref={notebookRef}
        className="survive-scroll-target"
        hidden={!["explain", "export"].includes(stage)}
      >
        <SurviveInvestigations
          selection={investigationSelection}
          onNavigateEvidence={navigateInvestigationEvidence}
          leaveGuardRef={investigationLeaveGuard}
          openRequest={investigationOpenRequest}
          attachRequest={attachRequest}
          onWorkflowState={setInvestigationState}
          viewMode={["explain", "export"].includes(stage) ? stage : "hidden"}
          onRequestStage={navigateStage}
        />
      </div>
      <StudyComparison
        report={report}
        trials={trials}
        busy={busy}
        running={running}
        hidden={stage !== "review"}
        onAction={act}
      />
    </div>
  );
}

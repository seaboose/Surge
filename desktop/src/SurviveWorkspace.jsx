import React, {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import WorkspaceHeader from "./case-workspace/WorkspaceHeader.jsx";
import SurviveInvestigations from "./SurviveInvestigations";
import {
  WorkflowBar,
  RecordingStrip,
  SessionSummary,
  MarkerTimeline,
} from "./SurviveFlow";
import { advanceReplay, clampTimelineRange } from "./survive-flow.mjs";
import ResizableReview from "./ResizableReview";
import "./survive-review.css";
import { Info } from "./Info.jsx";
import TrialControls, { RecordingLibrary } from "./survive/TrialControls.jsx";
import RecordingPanel from "./survive/RecordingPanel.jsx";
import StudyComparison from "./survive/StudyComparison.jsx";
import Arena from "./survive/ArenaReplay.jsx";
import Inspector from "./survive/SelectedEvidence.jsx";
import {
  attachedEvidenceId,
  findVisitedEvidence,
} from "./survive/investigation-model.mjs";
import {
  ACTIVE,
  POINTS,
  number,
  pretty,
  lastAt,
  viewRows,
  lastViewTime,
  nameRecordings,
  recordingName,
} from "./survive/replay-model.mjs";

async function api(method, args = {}) {
  const reply = await window.surge.request(method, args);
  if (!reply?.ok) throw new Error(reply?.error || "Survive request failed.");
  return reply.value;
}

export default function SurviveWorkspace({
  onClose,
  onHome = onClose,
  settings,
}) {
  const [sources, setSources] = useState([]),
    [sessions, setSessions] = useState([]),
    [trials, setTrials] = useState([]);
  const [active, setActive] = useState(null),
    [snapshot, setSnapshot] = useState(null),
    [viewMode, setViewMode] = useState("live");
  const [paused, setPaused] = useState(false),
    [follow, setFollow] = useState(true),
    [time, setTime] = useState(0),
    [fixedDomain, setFixedDomain] = useState("round");
  const [selectedSeq, setSelectedSeq] = useState(null),
    [constraintId, setConstraintId] = useState();
  const [rawSelection, setRawSelection] = useState(null);
  const [investigationOpenRequest, setInvestigationOpenRequest] = useState(0);
  const [attachRequest, setAttachRequest] = useState(null);
  const [investigationState, setInvestigationState] = useState(null);
  const [cardVisit, setCardVisit] = useState(null);
  const [stage, setStage] = useState("play");
  const [setupOpen, setSetupOpen] = useState(true);
  const [activeTrial, setActiveTrial] = useState(null);
  const [completedRecording, setCompletedRecording] = useState(null);
  const [lastStatusAt, setLastStatusAt] = useState(null);
  const [statusFailed, setStatusFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const workspaceRef = useRef(null);
  const attachedButton = useRef(null);
  const nextStageFocus = useRef(null);
  const reviewRef = useRef(null);
  const requestNumber = useRef(0);
  const investigationLeaveGuard = useRef(() => true);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
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
    if (fixedDomain === "round") return [0, duration];
    if (fixedDomain) return clampTimelineRange(fixedDomain, duration);
    if (duration <= 8) return [0, Math.max(1, duration)];
    const begin = Math.max(0, Math.min(duration - 8, selectedTime - 4));
    return [begin, begin + 8];
  }, [duration, selectedTime, fixedDomain]);
  const selectedRecord =
    rows.find((r) => r.seq === selectedSeq) || lastAt(rows, selectedTime);
  // A restored raw record has an explicit null constraint, even if a rule ends on that record.
  const selectedConstraint =
    constraintId === undefined
      ? constraints.find((r) => r.end_seq === selectedRecord?.seq)
      : constraintId && constraints.find((r) => r.event_id === constraintId);
  const inspectedRaw =
    rawSelection &&
    rawSelection.recording_id === capture?.recording_id &&
    rawSelection.seq === selectedRecord?.seq
      ? rawSelection
      : null;
  const namedSessions = useMemo(
    () => nameRecordings(sessions, trials),
    [sessions, trials],
  );
  const isExample = capture?.provenance === "simulated_standard_example";
  const selectedName = useMemo(() => {
    if (!capture) return "";
    if (isExample) return "Standard example · simulated";
    const saved = namedSessions.find(
      (item) => item.recording_id === capture.recording_id,
    );
    return (
      saved?.display_name ||
      recordingName(
        capture,
        activeTrial?.recording_id === capture.recording_id
          ? activeTrial.phase
          : undefined,
      )
    );
  }, [namedSessions, capture, isExample, activeTrial]);
  const investigationSelection = {
    display_name: selectedName,
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
  const attachedId = attachedEvidenceId(
    investigationState?.evidence,
    investigationSelection,
  );
  const hasRecording = Boolean(
    capture?.recording_id && (rows.length || viewMode === "saved"),
  );
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
    if (!isSame) setSetupOpen(false);
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
                  ? ""
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
    if (stage !== "explain") setCardVisit(null);
  }, [stage]);

  useLayoutEffect(() => {
    const destination = nextStageFocus.current;
    nextStageFocus.current = null;
    if (stage === "explain" && destination?.target === "card") return;
    workspaceRef.current?.scrollTo({
      top: destination?.scrollTop ?? 0,
      behavior: "instant",
    });
    if (stage === "review" && destination?.target === "replay") {
      attachedButton.current?.focus({ preventScroll: true });
      attachedButton.current?.scrollIntoView({
        block: "nearest",
        behavior: "instant",
      });
    }
  }, [stage]);

  function updateInvestigation(state) {
    setInvestigationState(state);
    setCardVisit((visit) =>
      findVisitedEvidence(
        visit,
        state?.investigationId,
        state?.revision,
        state?.evidence,
      )
        ? visit
        : null,
    );
  }

  function openAttachedCard() {
    if (!attachedId || !investigationState?.revision || actionLock.current)
      return;
    setPlaying(false);
    setFollow(false);
    viewRef.current.follow = false;
    if (viewMode === "live" && (running || gameRunning || active?.finalizing)) {
      setPaused(true);
      viewRef.current.paused = true;
    }
    setCardVisit({
      investigationId: investigationState.investigationId,
      revision: investigationState.revision,
      evidenceId: attachedId,
      selection: investigationSelection,
      snapshot,
      replayTime: selectedTime,
      domain: fixedDomain,
      scrollTop: workspaceRef.current?.scrollTop ?? 0,
    });
    setNotice("");
    nextStageFocus.current = { target: "card" };
    setStage("explain");
  }

  function returnToReplay() {
    if (!cardVisit) return;
    setSnapshot(cardVisit.snapshot);
    setTime(cardVisit.replayTime);
    setSelectedSeq(cardVisit.selection.seq);
    setConstraintId(cardVisit.selection.constraint_id);
    setFixedDomain(cardVisit.domain);
    nextStageFocus.current = {
      target: "replay",
      scrollTop: cardVisit.scrollTop,
    };
    setCardVisit(null);
    setStage("review");
  }

  function resetViewMode(mode) {
    const follow = mode === "live";
    viewRef.current = { paused: false, follow, viewMode: mode };
    setViewMode(mode);
    setPaused(false);
    setFollow(follow);
  }

  async function act(method, args = {}, kind = "normal") {
    if (actionLock.current) return false;
    actionLock.current = true;
    setBusy(true);
    setError("");
    epoch.current++;
    setPlaying(false);
    try {
      const value = await api(method, args);
      if (kind === "open") {
        setFixedDomain("round");
        resetViewMode("saved");
        setSnapshot(value);
        setTime(viewRows(value)[0]?.elapsed_s || 0);
        setSelectedSeq(null);
        setConstraintId(undefined);
        setStage("review");
        setNotice("");
      } else if (value.capture && method === "survive_stop") {
        accept(value);
        setNotice(
          "Recording stopped. Gameplay continues independently; the selected time and view are retained. A mid-round segment stays partial.",
        );
      } else if (value.capture) {
        resetViewMode("live");
        setSelectedSeq(null);
        setConstraintId(undefined);
        setCompletedRecording(null);
        setFixedDomain("round");
        setStage("play");
        cursor.current = 0;
        buffer.current = null;
        accept(value, true);
        setNotice(
          value.trial
            ? "Trial launched and recorder armed. Return here to inspect the recorded game."
            : "Recorder started. Waiting for source records if the selected round has not begun.",
        );
      } else if (kind === "report") setReport(value);
      else if (kind !== "rename")
        setNotice(
          value.message ||
            "Study setting saved separately from detector evidence.",
        );
      await refreshLists();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
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
    setConstraintId(undefined);
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
      setFixedDomain("round");
      setSelectedSeq(target.seq);
      setConstraintId(target.constraint_id || null);
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
    setConstraintId(linked?.event_id);
  }
  function navigateStage(value) {
    if (value !== "play" && !hasRecording) return;
    if (value === "export" && !investigationState?.investigationId) return;
    setNotice("");
    if (stage === "review" && value !== "review") {
      setFollow(false);
      viewRef.current.follow = false;
    }
    setStage(value);
    if (value === "explain") setInvestigationOpenRequest((v) => v + 1);
  }
  function changeDomain(value) {
    setFixedDomain(
      value === null
        ? null
        : value[0] === 0 && value[1] >= duration
          ? "round"
          : clampTimelineRange(value, duration),
    );
  }
  function addSelection() {
    if (attachedId) return;
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
  async function reopenMark(mark) {
    setPlaying(false);
    const recordingId = capture?.recording_id;
    const pinnedEpoch = epoch.current;
    let row = rows.find((item) => item.seq === mark.seq);
    if (!row) {
      try {
        const result = await api("survive_record", {
          recording_id: recordingId,
          seq: mark.seq,
        });
        if (epoch.current !== pinnedEpoch) return;
        if (
          result.recording_id !== recordingId ||
          result.record?.seq !== mark.seq
        ) {
          throw new Error(
            "The source record for this mark could not be verified.",
          );
        }
        row = result.record;
        setSnapshot((current) =>
          current?.capture?.recording_id === recordingId
            ? {
                ...current,
                records: [
                  ...(current.records || []).filter(
                    (item) => item.seq !== row.seq,
                  ),
                  row,
                ],
              }
            : current,
        );
        setRawSelection(result);
      } catch (error) {
        if (epoch.current === pinnedEpoch) setError(error.message);
        return;
      }
    }
    chooseRecord(row);
    setTime(mark.time);
  }
  function togglePlayback() {
    if (playing) {
      setPlaying(false);
      return;
    }
    setFollow(false);
    viewRef.current.follow = false;
    setSelectedSeq(null);
    setConstraintId(undefined);
    if (time >= duration) setTime(0);
    setPlaying(true);
  }
  function resumeLive() {
    setPlaying(false);
    resetViewMode("live");
    setSelectedSeq(null);
    setConstraintId(undefined);
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

  const recordingPanel = (
    <RecordingPanel
      active={active}
      running={running}
      hasRecording={Boolean(
        buffer.current?.capture?.records || viewRows(buffer.current).length,
      )}
      hidden={stage !== "play"}
      onInspect={() => {
        if (viewMode === "saved") resumeLive();
        setStage("review");
      }}
    />
  );

  return (
    <div
      ref={workspaceRef}
      className="survive-workspace"
      data-working={busy}
      data-stage={stage}
    >
      <WorkspaceHeader
        className="survive-header"
        title="Survive sessions"
        subtitle="Play. Review evidence. Explain what you found."
        settings={settings}
        onHome={() => {
          if (investigationLeaveGuard.current()) onHome();
          else navigateStage("explain");
        }}
        homeTitle="Return home; recording continues independently"
      >
        <button
          onClick={() => {
            if (investigationLeaveGuard.current()) onClose();
            else navigateStage("explain");
          }}
          title="Recording continues independently when you return to Surge"
        >
          Back to Surge
        </button>
      </WorkspaceHeader>
      <WorkflowBar
        stage={stage}
        onNavigate={navigateStage}
        hasRecording={hasRecording}
        hasReport={Boolean(investigationState?.investigationId)}
      />
      {(running || active?.finalizing) && (
        <div className="survive-scroll-target survive-live-session">
          <RecordingStrip
            capture={active}
            updatedAt={lastStatusAt}
            requestFailed={statusFailed}
            busy={busy}
            trialRunning={gameRunning}
            onStop={() => act("survive_stop")}
          />
          {recordingPanel}
        </div>
      )}
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

      {completedRecording &&
        (stage === "play" ||
          capture?.recording_id !== completedRecording.recording_id) && (
          <section className="survive-handoff" aria-label="Post-game handoff">
            <div>
              <div className="survive-field-heading">
                <h2>
                  {completedRecording.analysis_state === "complete"
                    ? "Recording saved"
                    : "Recording ended · review its coverage"}
                </h2>
                <Info label="saved recording">
                  The recording is available in your library. Review opens its
                  saved evidence from the beginning. You can rename it in Play
                  &amp; record.
                </Info>
              </div>
              <p>
                {number(completedRecording.source_elapsed_s, 1)} s of game time
                · {completedRecording.records ?? 0} records ·{" "}
                {pretty(
                  completedRecording.completion || completedRecording.state,
                )}
                .
                {paused || viewMode === "saved"
                  ? " Your current inspection stays in place until you choose Review."
                  : ""}
              </p>
              {gameRunning && !running && (
                <small>
                  The game is still running. The next round unlocks when it
                  exits.
                </small>
              )}
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
      {!running && !active?.finalizing && active && recordingPanel}
      <details
        className="survive-panel survive-setup-disclosure"
        aria-label="Round setup"
        hidden={stage !== "play"}
        open={setupOpen}
        onToggle={(event) => setSetupOpen(event.currentTarget.open)}
      >
        <summary>
          <span>Round setup</span>
          <Info label="round setup">
            Choose the conditions for a new round. Starting the trial opens the
            game and records it with those settings.
          </Info>
        </summary>
        <TrialControls
          busy={busy || Boolean(active?.finalizing)}
          running={running}
          gameRunning={gameRunning}
          onAction={act}
        />
      </details>
      <p
        role="status"
        className="survive-notice"
        hidden={
          !["play", "review"].includes(stage) ||
          !(
            notice ||
            (paused && stage === "review") ||
            (viewMode === "saved" && running)
          )
        }
      >
        {notice}
        {paused && stage === "review"
          ? running
            ? " View paused; recording continues."
            : " View paused; use Follow latest recording to inspect the final state."
          : ""}
        {viewMode === "saved" && running
          ? " A separate live recording continues in the background."
          : ""}
      </p>
      <div
        className="survive-session-context"
        hidden={!["play", "review"].includes(stage)}
      >
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
                    ? snapshot?.view?.analysis?.counts
                      ? `${snapshot.view.analysis.counts.Review ?? "Unavailable"} to review · ${snapshot.view.analysis.counts.Unknown ?? "Unavailable"} cannot assess`
                      : "Assessment counts unavailable"
                    : "Assessment pending or incomplete"}
                </span>
              </summary>
              <SessionSummary snapshot={snapshot} />
            </details>
          )}
        </div>
        <div hidden={stage !== "play"}>
          <RecordingLibrary
            sources={sources}
            sessions={namedSessions}
            busy={busy || Boolean(active?.finalizing)}
            running={running}
            selectedId={capture?.recording_id}
            onAction={act}
            onRefresh={() => refreshLists().catch((e) => setError(e.message))}
          />
        </div>
      </div>
      <div
        className="survive-review-view"
        aria-label="Review workspace"
        hidden={stage !== "review"}
      >
        {rows.length === 0 && (
          <section className="survive-panel">
            <h2>No replay records</h2>
            <p>
              This recording has no replayable events. Choose another in Play
              &amp; record.
            </p>
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
            <ResizableReview
              header={
                <div className="survive-studio-title">
                  <div className="survive-field-heading">
                    <h2>
                      {viewMode === "saved"
                        ? "Recorded evidence"
                        : paused
                          ? "Pinned recording view"
                          : "Recording evidence"}
                    </h2>
                    <Info label="recorded evidence">
                      Replay, charts and the inspector share one selection.
                      Select a source record to see what happened at that
                      moment.
                    </Info>
                  </div>
                  {selectedName && <small>{selectedName}</small>}
                </div>
              }
              timeline={
                <>
                  <MarkerTimeline
                    controls={
                      <>
                        <section
                          className="survive-transport"
                          aria-label="Shared time controls"
                        >
                          <div className="survive-controls survive-transport-row">
                            <div className="survive-time-readout">
                              <strong aria-label="Replay time">
                                {number(selectedTime, 3)} s
                              </strong>
                              <span>/ {number(duration, 1)} s</span>
                            </div>
                            {(running || paused) && (
                              <div className="survive-controls survive-record-actions">
                                <button
                                  disabled={
                                    (!running && !paused) || viewMode !== "live"
                                  }
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
                            )}

                            <button
                              className="survive-play-toggle primary"
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
                                onChange={(e) =>
                                  setPlaybackRate(Number(e.target.value))
                                }
                              >
                                <option value="0.5">0.5×</option>
                                <option value="1">1×</option>
                                <option value="2">2×</option>
                              </select>
                            </label>
                            <button
                              className="survive-next-review"
                              disabled={
                                !constraints.some((r) => r.status === "Review")
                              }
                              onClick={() => {
                                const reviews = constraints.filter(
                                  (r) => r.status === "Review",
                                );
                                const next =
                                  reviews.find(
                                    (r) => r.elapsed_s > selectedTime + 0.001,
                                  ) || reviews[0];
                                if (next) chooseConstraint(next);
                              }}
                            >
                              Next review
                            </button>
                          </div>
                          <small>
                            {capture?.analysis_state === "complete"
                              ? "Complete-run analysis"
                              : `Analysis ${capture?.analysis_state || "pending"}`}{" "}
                            ·{" "}
                            {capture?.completion ||
                              "No game completion recorded"}{" "}
                            ·{" "}
                            {isExample
                              ? "simulated example"
                              : "local unsigned evidence"}
                          </small>
                        </section>
                      </>
                    }
                    rows={rows}
                    selectedRecord={selectedRecord}
                    selectedConstraint={selectedConstraint}
                    final={final}
                    analysisState={capture?.analysis_state}
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
                    truncated={
                      snapshot?.view?.metadata?.display_truncated === true
                    }
                  />
                </>
              }
              replay={
                <Arena
                  key={capture?.recording_id}
                  recordingId={capture?.recording_id}
                  onPause={() => {
                    setPlaying(false);
                    if (viewMode === "live" && running) {
                      viewRef.current.paused = true;
                      setPaused(true);
                    }
                  }}
                  onJump={reopenMark}
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
                <>
                  <Inspector
                    record={selectedRecord}
                    rawRecord={inspectedRaw?.record}
                    rawError={inspectedRaw?.error}
                    constraint={selectedConstraint}
                    capture={capture}
                    metadata={snapshot?.view?.metadata}
                    final={final}
                  />
                  <div className="survive-evidence-action">
                    {attachedId ? (
                      <button
                        ref={attachedButton}
                        type="button"
                        onClick={openAttachedCard}
                        disabled={busy}
                        title={`Open evidence ${attachedId} in Explain`}
                      >
                        Attached as {attachedId}
                      </button>
                    ) : (
                      <button
                        onClick={addSelection}
                        disabled={
                          busy ||
                          !selectedRecord ||
                          !investigationSelection.finalized
                        }
                      >
                        Add selection to investigation
                      </button>
                    )}
                  </div>
                </>
              }
            />
          </>
        )}
      </div>
      <div
        className="survive-scroll-target"
        hidden={!["explain", "export"].includes(stage)}
      >
        <SurviveInvestigations
          selection={investigationSelection}
          onNavigateEvidence={navigateInvestigationEvidence}
          leaveGuardRef={investigationLeaveGuard}
          openRequest={investigationOpenRequest}
          attachRequest={attachRequest}
          onWorkflowState={updateInvestigation}
          cardVisit={cardVisit}
          onReturnToReplay={returnToReplay}
          viewMode={["explain", "export"].includes(stage) ? stage : "hidden"}
          onRequestStage={navigateStage}
        />
      </div>
      <StudyComparison
        sessions={namedSessions}
        snapshot={snapshot}
        load={api}
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

import React, { useEffect, useState } from "react";
import { number, pretty } from "./replay-model.mjs";
import { sessionSummary } from "../survive-flow.mjs";
import { Info } from "../Info.jsx";

function PairComparison({ sessions, snapshot, load }) {
  const [otherId, setOtherId] = useState("");
  const [result, setResult] = useState(null);
  const currentId = snapshot.capture.recording_id;
  useEffect(() => {
    if (!otherId) return;
    let current = true;
    load("survive_open", { recording_id: otherId })
      .then((other) => {
        if (other.capture?.recording_id !== otherId)
          throw new Error("The second recording could not be verified.");
        if (current) setResult({ id: otherId, summary: sessionSummary(other) });
      })
      .catch((e) => {
        if (current) setResult({ id: otherId, error: e.message });
      });
    return () => {
      current = false;
    };
  }, [otherId, load]);
  const choices = sessions.filter(
    (s) => s.recording_id !== currentId && !s.in_progress,
  );
  const first = sessionSummary(snapshot);
  const format = (key, value) => {
    if (value == null) return "Unavailable";
    if (key === "coverage")
      return value > 99.99 && value < 100
        ? ">99.99% (<100%)"
        : value > 0 && value < 0.01
          ? "<0.01%"
          : number(value, 2) + "%";
    return key === "duration" ? number(value, 2) + " s" : value;
  };
  return (
    <div className="survive-pair">
      <label>
        Compare with
        <select
          aria-label="Compare with"
          value={otherId}
          disabled={!choices.length}
          onChange={(e) => {
            setOtherId(e.target.value);
            setResult(null);
          }}
        >
          <option value="">
            {choices.length
              ? "Choose a second recording"
              : "Save a second recording to compare"}
          </option>
          {choices.map((s) => (
            <option value={s.recording_id} key={s.recording_id}>
              {s.display_name}
            </option>
          ))}
        </select>
      </label>
      {otherId &&
        (result?.id !== otherId ? (
          <p role="status">Opening second recording…</p>
        ) : result.error ? (
          <p role="alert">{result.error}</p>
        ) : (
          <div className="survive-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Measure</th>
                  <th>Current recording</th>
                  <th>
                    {
                      choices.find((s) => s.recording_id === otherId)
                        ?.display_name
                    }
                  </th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["duration", "Game duration"],
                  ["completion", "Completion"],
                  ["coverage", "Sampled coverage"],
                  ["reviews", "Needs review"],
                  ["unknown", "Cannot assess"],
                ].map(([key, name]) => (
                  <tr key={key}>
                    <th scope="row">{name}</th>
                    <td>{format(key, first[key])}</td>
                    <td>{format(key, result.summary[key])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </div>
  );
}

export default function StudyComparison({
  report,
  trials,
  busy,
  running,
  hidden,
  onAction,
  sessions,
  snapshot,
  load,
}) {
  const [selectedTrial, setSelectedTrial] = useState(""),
    [expected, setExpected] = useState("unknown"),
    [labelNote, setLabelNote] = useState("");
  const groups = report?.groups || [];
  return (
    <section
      className="survive-panel"
      aria-label="Study comparison"
      hidden={hidden}
    >
      <details>
        <summary>
          <span>Compare recordings</span>
          <Info label="recording comparison">
            Compare coverage and findings with a second recording while keeping
            your current replay in place. Study comparisons group independently
            labelled trials.
          </Info>
        </summary>
        {snapshot?.capture && (
          <PairComparison
            key={snapshot.capture.recording_id}
            sessions={sessions}
            snapshot={snapshot}
            load={load}
          />
        )}
        <details>
          <summary>Study comparison and labels</summary>
          <div className="survive-controls">
            <h2>Study comparison</h2>
            <button
              disabled={busy}
              onClick={() => onAction("survive_report", {}, "report")}
            >
              Refresh comparison
            </button>
          </div>
          <p>
            Compare independent sessions and evidence coverage. Human sessions
            with Review are false-positive candidates until the expected
            mechanical state is independently checked.
          </p>
          {report && (
            <>
              <p role="status">
                {report.pending_recordings?.length || 0} recordings await
                verification; {report.rejected_recordings?.length || 0}{" "}
                recordings failed verification. Neither supports a clean
                outcome. Refresh comparison verifies the next batch.
              </p>
              {report.rejected_recordings?.length > 0 && (
                <details>
                  <summary>Recording verification issues</summary>
                  <pre>
                    {JSON.stringify(report.rejected_recordings, null, 2)}
                  </pre>
                </details>
              )}
              {groups.length > 0 ? (
                <div className="survive-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Condition</th>
                        <th>Session context</th>
                        <th>Sessions</th>
                        <th>Complete</th>
                        <th>Sessions with Review</th>
                        <th>Constraint observations</th>
                        <th>Unknown observations</th>
                        <th>Unverified sessions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groups.map((g) => (
                        <tr
                          key={[
                            g.condition,
                            g.participant,
                            g.phase,
                            g.profile_id,
                            g.profile_sha256,
                            g.module_sha256,
                            g.execution_context,
                          ].join(":")}
                        >
                          <td>{g.condition || g.mode || "Unspecified"}</td>
                          <td>
                            {g.participant || "—"} · {g.phase || "—"} ·{" "}
                            {g.profile_id || "—"}
                            <br />
                            <small>
                              {pretty(
                                g.execution_context ||
                                  "Execution context unavailable",
                              )}
                            </small>
                          </td>
                          <td>{g.sessions ?? g.trials ?? "—"}</td>
                          <td>{g.complete_sessions ?? "—"}</td>
                          <td>{g.review_sessions ?? "—"}</td>
                          <td>{g.records ?? "—"}</td>
                          <td>{g.unknown_records ?? "—"}</td>
                          <td>{g.unverified_sessions ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>No comparable completed sessions yet.</p>
              )}
              {report.confusion && (
                <div aria-label="Adjudicated mechanical outcomes">
                  <h3>Adjudicated mechanical outcomes</h3>
                  <p>
                    These totals pool all independently annotated, eligible
                    non-practice sessions across the groups above, including
                    development and held-out phases. They assess mechanical
                    rules, not whether input was scripted. No Review can still
                    include Unknown intervals.
                  </p>
                  <div className="survive-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Expected state</th>
                          <th>Review</th>
                          <th>No Review observed</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <th>Violation</th>
                          <td>{report.confusion.true_positive}</td>
                          <td>{report.confusion.false_negative}</td>
                        </tr>
                        <tr>
                          <th>No violation</th>
                          <td>{report.confusion.false_positive}</td>
                          <td>{report.confusion.true_negative}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p>
                    False-positive rate:{" "}
                    {Number.isFinite(report.confusion.false_positive_rate)
                      ? `${number(report.confusion.false_positive_rate * 100, 1)}%`
                      : "Unavailable — no eligible negative annotations"}{" "}
                    ({report.confusion.false_positive} false positives /{" "}
                    {report.confusion.false_positive +
                      report.confusion.true_negative}{" "}
                    eligible negative sessions).{" "}
                    {report.confusion.excluded_trials} trials excluded. This
                    pooled rate is not a held-out accuracy estimate.
                  </p>
                </div>
              )}
              <details>
                <summary>Comparison details and exclusions</summary>
                <pre>{JSON.stringify(report, null, 2)}</pre>
              </details>
            </>
          )}
          <details>
            <summary>Study labels and held-out freeze</summary>
            <p>
              Expected mechanical violation is an independent study annotation.
              It does not enter movement rules or turn scripted input into a
              positive detector label.
            </p>
            <div className="survive-controls">
              <label>
                Trial
                <select
                  aria-label="Study trial"
                  value={selectedTrial}
                  disabled={busy}
                  onChange={(e) => {
                    const trialId = e.target.value;
                    const annotation = trials.find(
                      (t) => t.trial_id === trialId,
                    )?.adjudication;
                    setSelectedTrial(trialId);
                    setExpected(
                      annotation?.expected_mechanical_violation || "unknown",
                    );
                    setLabelNote(annotation?.note || "");
                  }}
                >
                  <option value="">Choose a trial</option>
                  {trials.map((t) => (
                    <option key={t.trial_id} value={t.trial_id}>
                      {t.participant || "player"} · {t.mode} · seed {t.seed} ·{" "}
                      {String(t.trial_id).slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Expected mechanical violation
                <select
                  aria-label="Expected mechanical violation"
                  value={expected}
                  disabled={busy}
                  onChange={(e) => setExpected(e.target.value)}
                >
                  <option value="unknown">Unknown</option>
                  <option value="no">No</option>
                  <option value="yes">Yes</option>
                </select>
              </label>
              <label>
                Reason
                <input
                  aria-label="Study label reason"
                  value={labelNote}
                  maxLength={500}
                  disabled={busy}
                  onChange={(e) => setLabelNote(e.target.value)}
                />
              </label>
              <button
                disabled={busy || !selectedTrial || !labelNote.trim()}
                onClick={() =>
                  onAction("survive_adjudicate", {
                    trial_id: selectedTrial,
                    expected_mechanical_violation: expected,
                    note: labelNote.trim(),
                  })
                }
              >
                Save study label
              </button>
              <button
                disabled={busy || running}
                onClick={() => onAction("survive_study_freeze")}
              >
                Freeze held-out configuration
              </button>
            </div>
            <small>
              Reserved held-out seeds: 9001, 9007, 9011. Freeze the build and
              reviewed analysis before using them.
            </small>
          </details>
        </details>
      </details>
    </section>
  );
}

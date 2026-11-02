import React, { useEffect, useRef, useState } from "react";
import "./investigation-flow.css";
import {
  editableInvestigation,
  formatEvidenceNumber as number,
  reportReadiness,
} from "./survive/investigation-model.mjs";
import {
  NarrativePreview,
  EvidenceCard,
} from "./survive/InvestigationEvidence.jsx";
import { NarrativeEditor, RevisionControls } from "./survive/ReportEditor.jsx";
import InvestigationReadiness from "./survive/InvestigationReadiness.jsx";

const OPERATION_WAIT =
  "Wait for the investigation operation to finish before leaving.";
async function api(method, args = {}) {
  const reply = await window.surge.request(method, args);
  if (!reply?.ok)
    throw new Error(reply?.error || "Investigation request failed.");
  return reply.value;
}

export default function SurviveInvestigations({
  selection,
  onNavigateEvidence,
  leaveGuardRef,
  openRequest = 0,
  attachRequest = null,
  onWorkflowState,
  viewMode = "explain",
  onRequestStage,
}) {
  const [expanded, setExpanded] = useState(viewMode !== "hidden");
  const [section, setSection] = useState("question");
  const [inventory, setInventory] = useState([]);
  const [unavailable, setUnavailable] = useState([]);
  const [loaded, setLoaded] = useState(null);
  const [form, setForm] = useState(null);
  const [base, setBase] = useState("");
  const [newTitle, setNewTitle] = useState("Movement investigation");
  const [newAuthor, setNewAuthor] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [pendingSelection, setPendingSelection] = useState(null);
  const [exportedRevision, setExportedRevision] = useState(null);
  const lock = useRef(false);
  const alive = useRef(true);
  const panel = useRef(null);
  const handledAttachment = useRef(null);
  const workflowValue = useRef("");
  const workflowCallback = useRef(onWorkflowState);
  workflowCallback.current = onWorkflowState;
  const document = loaded?.document;
  const evidence = document?.evidence || [];
  const choices =
    document &&
    !inventory.some(
      (item) => item.investigation_id === document.investigation_id,
    )
      ? [document, ...inventory]
      : inventory;
  const latest = loaded?.latest_revision ?? document?.revision;
  const historical = Boolean(document && document.revision !== latest);
  const dirty = Boolean(form && JSON.stringify(form) !== base);
  const verification = loaded?.verification;
  const attachmentSelection = pendingSelection || selection;
  const canAttach = Boolean(
    attachmentSelection?.recording_id &&
    Number.isInteger(attachmentSelection.seq) &&
    attachmentSelection.finalized,
  );
  const { readiness, ready, unresolvedCitations } = reportReadiness({
    document,
    form,
    evidence,
    verification,
    dirty,
  });
  const exported = Boolean(
    document &&
    exportedRevision &&
    !dirty &&
    exportedRevision?.id === document?.investigation_id &&
    exportedRevision?.revision === document?.revision,
  );

  useEffect(() => {
    const value =
      expanded || document
        ? {
            stage: exported ? "export" : "explain",
            ready,
            dirty,
            investigationId: document?.investigation_id || null,
          }
        : null;
    const serialized = JSON.stringify(value);
    if (serialized !== workflowValue.current) {
      workflowValue.current = serialized;
      workflowCallback.current?.(value);
    }
  }, [expanded, exported, ready, dirty, document?.investigation_id]);

  useEffect(() => () => workflowCallback.current?.(null), []);
  useEffect(() => {
    if (viewMode !== "hidden") setExpanded(true);
  }, [viewMode]);

  function allowLeave() {
    if (lock.current) {
      setError(OPERATION_WAIT);
      return false;
    }
    return (
      !dirty ||
      window.confirm(
        "Discard unsaved investigation edits? Saved revisions and evidence will remain unchanged.",
      )
    );
  }

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (leaveGuardRef) leaveGuardRef.current = allowLeave;
    const guard = (event) => {
      if (dirty || lock.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => {
      window.removeEventListener("beforeunload", guard);
      if (leaveGuardRef) leaveGuardRef.current = () => true;
    };
  }, [dirty, busy, leaveGuardRef]);
  useEffect(() => {
    if (!openRequest) return;
    setExpanded(true);
  }, [openRequest]);

  useEffect(() => {
    if (
      !attachRequest ||
      handledAttachment.current === attachRequest.request_id
    )
      return;
    handledAttachment.current = attachRequest.request_id;
    const pinned = { ...attachRequest.selection };
    setExpanded(true);
    setPendingSelection(pinned);
    if (
      !pinned.recording_id ||
      !Number.isInteger(pinned.seq) ||
      !pinned.finalized
    ) {
      setError(
        "Choose a finalized recording and an exact record before attaching evidence.",
      );
      return;
    }
    if (
      document &&
      form &&
      !dirty &&
      !historical &&
      !lock.current &&
      evidence.length < 32 &&
      form.author.trim()
    ) {
      attach(pinned);
    } else {
      setNotice(
        lock.current
          ? "Selection pinned. Wait for the current report operation, then attach it."
          : historical
            ? "Selection pinned. Reload the latest revision before attaching it."
            : document
              ? "Selection pinned. Save or discard edits before attaching it."
              : "Selection pinned. Choose an investigation, or create one with your name or alias and attach it.",
      );
    }
  }, [attachRequest?.request_id]);

  async function refresh() {
    const value = await api("survive_investigations");
    if (!alive.current) return;
    setInventory(value.investigations || []);
    setUnavailable(value.unavailable || []);
  }

  useEffect(() => {
    if (expanded) refresh().catch((e) => alive.current && setError(e.message));
  }, [expanded]);

  function accept(value) {
    if (!value?.document)
      throw new Error("Investigation reply did not include a saved document.");
    const next = editableInvestigation(value.document);
    setLoaded(value);
    setForm(next);
    setBase(JSON.stringify(next));
    setReading(false);
  }

  async function operation(work) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (e) {
      if (alive.current) setError(e.message);
    } finally {
      lock.current = false;
      if (alive.current) {
        setBusy(false);
        setError((current) => (current === OPERATION_WAIT ? "" : current));
      }
    }
  }

  function open(id, revision = null) {
    if (!id || !allowLeave()) return;
    operation(async () => {
      const value = await api("survive_investigation_open", {
        investigation_id: id,
        revision,
      });
      if (!alive.current) return;
      accept(value);
      setNotice(
        "Saved revision opened. Evidence references were checked against their pinned source.",
      );
    });
  }

  async function navigate(evidence_id) {
    return operation(async () => {
      const target = await api("survive_investigation_resolve", {
        investigation_id: document.investigation_id,
        evidence_id,
        revision: document.revision,
      });
      await onNavigateEvidence(target);
      if (alive.current)
        setNotice(
          `${evidence_id} opened at its exact recorded moment. Your report edits are retained.`,
        );
    });
  }

  async function recheckEvidence() {
    const checked = await api("survive_investigation_open", {
      investigation_id: document.investigation_id,
      revision: document.revision,
    });
    if (alive.current) {
      // Verification refreshes only source health. Never replace typed narrative
      // or silently adopt a newer saved revision while the analyst is writing.
      setLoaded((current) =>
        current?.document.investigation_id ===
          checked.document.investigation_id &&
        current?.document.revision === checked.document.revision
          ? { ...current, verification: checked.verification }
          : current,
      );
    }
    return checked.verification;
  }

  function change(key, value) {
    setForm((old) => ({ ...old, [key]: value }));
  }

  function cite(evidence_id) {
    const observations = `${form.sections.observations}${form.sections.observations ? "\n" : ""}[${evidence_id}] `;
    if (observations.length > 4000) {
      setError(
        "Observations reached the 4,000-character limit. Shorten them before adding a reference.",
      );
      return;
    }
    change("sections", { ...form.sections, observations });
    setSection("observations");
    setReading(false);
  }

  async function attachTo(saved, author, pinnedSelection) {
    return api("survive_investigation_attach", {
      investigation_id: saved.investigation_id,
      expected_revision: saved.revision,
      recording_id: pinnedSelection.recording_id,
      seq: pinnedSelection.seq,
      constraint_id: pinnedSelection.constraint_id || null,
      author: author.trim(),
      change_reason: `Attached selected evidence at record ${pinnedSelection.seq}.`,
    });
  }

  function clearAttachedSelection(attached) {
    setPendingSelection((pending) =>
      pending &&
      (pending.recording_id !== attached.recording_id ||
        pending.seq !== attached.seq ||
        (pending.constraint_id || null) !== (attached.constraint_id || null))
        ? pending
        : null,
    );
  }

  function attach(selected = attachmentSelection) {
    const pinnedSelection = { ...selected };
    const existing = evidence.find(
      (item) =>
        item.recording_id === pinnedSelection.recording_id &&
        item.seq === pinnedSelection.seq &&
        (item.constraint_id || null) ===
          (pinnedSelection.constraint_id || null),
    );
    if (existing) {
      clearAttachedSelection(pinnedSelection);
      setError("");
      setNotice(
        `This moment is already attached as ${existing.evidence_id}. Replay time and saved revisions are unchanged.`,
      );
      return;
    }
    operation(async () => {
      const value = await attachTo(document, form.author, pinnedSelection);
      if (!alive.current) return;
      accept(value);
      clearAttachedSelection(pinnedSelection);
      setNotice(
        "Evidence snapshot attached in a new Draft revision. Recorded evidence was not changed.",
      );
      await refresh();
    });
  }

  function create(attachSelection = false) {
    if (!allowLeave()) return;
    const pinnedSelection = { ...attachmentSelection };
    operation(async () => {
      const created = await api("survive_investigation_create", {
        title: newTitle.trim(),
        author: newAuthor.trim(),
      });
      if (!alive.current) return;
      accept(created);
      if (attachSelection) {
        setNotice(
          "Investigation created. Attaching the pinned evidence selection.",
        );
        const attached = await attachTo(
          created.document,
          newAuthor,
          pinnedSelection,
        );
        if (!alive.current) return;
        accept(attached);
        clearAttachedSelection(pinnedSelection);
        setNotice(
          "Investigation created with the selected evidence. Replay time is unchanged; add your reasoning and cite the evidence.",
        );
      } else {
        setNotice(
          "Investigation created. Attach evidence, then record your reasoning.",
        );
      }
      await refresh();
    });
  }

  function saveRevision() {
    operation(async () => {
      const value = await api("survive_investigation_save", {
        investigation_id: document.investigation_id,
        expected_revision: document.revision,
        title: form.title.trim(),
        author: form.author.trim(),
        change_reason: form.change_reason.trim(),
        status: form.status,
        sections: form.sections,
      });
      if (!alive.current) return;
      accept(value);
      setNotice(
        "A new revision was saved. Previous revisions and evidence remain preserved.",
      );
      await refresh();
    });
  }

  function discardEdits() {
    if (!allowLeave()) return;
    const restored = editableInvestigation(document);
    setForm(restored);
    setBase(JSON.stringify(restored));
  }

  const exportView = viewMode === "export";
  function requestStage(stage) {
    onRequestStage?.(stage);
  }
  return (
    <section
      className="survive-panel survive-investigations investigation-focused"
      ref={panel}
      hidden={viewMode === "hidden"}
      aria-label="Investigation notebook"
      data-report-view={viewMode}
    >
      {expanded && (
        <div className="investigation-content">
          <div className="investigation-view-heading">
            <div>
              <h2>{exportView ? "Export report" : "Explain the evidence"}</h2>
              <p>
                {exportView
                  ? "Check the saved report, then export a portable copy."
                  : "Write what happened, support it with evidence, and state the limits."}
              </p>
            </div>
            {document && (
              <button
                disabled={busy}
                onClick={() => requestStage(exportView ? "explain" : "export")}
              >
                {exportView ? "Edit report" : "Continue to export"}
              </button>
            )}
          </div>
          {error && (
            <p role="alert" className="survive-error">
              {error}
              {dirty ? " Unsaved edits are retained." : ""}
            </p>
          )}
          {notice && (
            <p role="status" className="investigation-notice">
              {notice}
            </p>
          )}
          <details className="investigation-manager" open={!document}>
            <summary>
              {document ? "Switch or create report" : "Open or create report"}
            </summary>
            <div className="investigation-picker survive-controls">
              <label>
                Saved investigation
                <select
                  aria-label="Saved investigation"
                  value={document?.investigation_id || ""}
                  disabled={busy}
                  onChange={(event) => open(event.target.value)}
                >
                  <option value="">Choose an investigation</option>
                  {choices.map((item) => (
                    <option
                      key={item.investigation_id}
                      value={item.investigation_id}
                    >
                      {item.title || item.investigation_id} · revision{" "}
                      {item.revision ?? item.latest_revision}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={busy} onClick={() => operation(refresh)}>
                Refresh investigations
              </button>
            </div>
            {unavailable.length > 0 && (
              <details className="investigation-warning">
                <summary>
                  {unavailable.length} investigations could not be opened
                </summary>
                {unavailable.map((item) => (
                  <p key={item.investigation_id}>
                    {item.investigation_id}: {item.error}
                  </p>
                ))}
              </details>
            )}
            {!exportView && (
              <details className="investigation-create" open={!document}>
                <summary>Create an investigation</summary>
                <div className="survive-controls">
                  <label>
                    New investigation title
                    <input
                      aria-label="New investigation title"
                      value={newTitle}
                      maxLength={120}
                      disabled={busy}
                      onChange={(e) => setNewTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    Your name or alias
                    <input
                      aria-label="New investigation author"
                      value={newAuthor}
                      maxLength={80}
                      disabled={busy}
                      onChange={(e) => setNewAuthor(e.target.value)}
                    />
                  </label>
                  <button
                    disabled={busy || !newTitle.trim() || !newAuthor.trim()}
                    onClick={() => create()}
                  >
                    Create investigation
                  </button>
                  {canAttach && (
                    <button
                      className="primary"
                      disabled={busy || !newTitle.trim() || !newAuthor.trim()}
                      onClick={() => create(true)}
                    >
                      Create and attach selected evidence
                    </button>
                  )}
                </div>
              </details>
            )}
            {exportView && !document && (
              <p>
                Select a saved investigation, or{" "}
                <button onClick={() => requestStage("explain")}>
                  write a report
                </button>
                .
              </p>
            )}
          </details>
          {document && form && (
            <>
              <div className="investigation-document-heading">
                <h3>{document.title}</h3>
                <span>
                  {historical
                    ? "Historical revision — read only"
                    : dirty
                      ? "Unsaved changes"
                      : "Saved"}{" "}
                  · revision {document.revision} of {latest} · {document.status}
                </span>
              </div>
              <div
                className={
                  verification?.state === "verified"
                    ? "investigation-verification"
                    : "investigation-warning"
                }
                role="status"
              >
                <strong>
                  {evidence.length === 0
                    ? "No evidence attached"
                    : verification?.state === "verified"
                      ? "Evidence references verified"
                      : "Evidence needs attention"}
                </strong>
                <span>
                  {" "}
                  · {evidence.length} {evidence.length === 1 ? "item" : "items"}
                </span>
                {document.status === "reviewed" &&
                  verification?.review_valid === false && (
                    <p>
                      This previously reviewed revision no longer has fully
                      verified evidence.
                    </p>
                  )}
                {verification?.items?.some(
                  (item) => item.state !== "verified",
                ) && (
                  <>
                    <p>
                      {["missing", "changed", "unavailable"]
                        .map((state) => {
                          const count = verification.items.filter(
                            (item) => item.state === state,
                          ).length;
                          return count ? `${count} ${state}` : null;
                        })
                        .filter(Boolean)
                        .join(" · ")}
                      . Replay is blocked for unverified references.
                    </p>
                    <details>
                      <summary>Source check details</summary>
                      {verification.items
                        .filter((item) => item.state !== "verified")
                        .map((item) => (
                          <p key={item.evidence_id}>
                            {item.evidence_id}: {item.state} — {item.message}
                          </p>
                        ))}
                    </details>
                  </>
                )}
              </div>
              {!exportView && (
                <>
                  <details className="investigation-report-details">
                    <summary>Report details and revision history</summary>
                    <div className="survive-controls">
                      <label>
                        Report title
                        <input
                          aria-label="Report title"
                          value={form.title}
                          maxLength={120}
                          disabled={busy || historical}
                          onChange={(e) => change("title", e.target.value)}
                        />
                      </label>
                      <label>
                        Author for this revision
                        <input
                          aria-label="Revision author"
                          value={form.author}
                          maxLength={80}
                          disabled={busy || historical}
                          onChange={(e) => change("author", e.target.value)}
                        />
                      </label>
                      <label>
                        Revision history
                        <select
                          aria-label="Investigation revision"
                          value={document.revision}
                          disabled={busy}
                          onChange={(e) =>
                            open(
                              document.investigation_id,
                              Number(e.target.value),
                            )
                          }
                        >
                          {(document.history || []).map((item) => (
                            <option key={item.revision} value={item.revision}>
                              Revision {item.revision} · {item.author} ·{" "}
                              {item.status}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        disabled={busy}
                        onClick={() => open(document.investigation_id)}
                      >
                        Reload latest and verify
                      </button>
                    </div>
                    <small>
                      Author names are local, self-reported attribution. Source
                      check: {verification?.checked_utc || "Unavailable"}.
                    </small>
                    <ol className="investigation-history">
                      {[...(document.history || [])].reverse().map((item) => (
                        <li key={item.revision}>
                          <button
                            disabled={busy}
                            onClick={() =>
                              open(document.investigation_id, item.revision)
                            }
                          >
                            Revision {item.revision}
                          </button>{" "}
                          · {item.author} ·{" "}
                          {item.updated_utc || item.created_utc} · {item.status}
                          <p>{item.change_reason}</p>
                        </li>
                      ))}
                    </ol>
                  </details>
                  <div className="investigation-grid">
                    <section
                      aria-label="Investigation narrative"
                      className="investigation-narrative"
                    >
                      <div className="investigation-writing-toolbar">
                        <h3>Your interpretation</h3>
                        <button onClick={() => setReading(!reading)}>
                          {reading ? "Edit narrative" : "Read narrative"}
                        </button>
                      </div>
                      <details className="investigation-help">
                        <summary>Writing guidance</summary>
                        <p>
                          Use [E1] references to support a claim. Keep
                          observations separate from hypotheses. State what the
                          evidence cannot establish. Reviewed records analyst
                          review, not a clean-play verdict.
                        </p>
                      </details>
                      {reading || historical ? (
                        <NarrativePreview
                          sections={form.sections}
                          evidence={evidence}
                          verification={verification}
                          navigate={navigate}
                          disabled={busy}
                        />
                      ) : (
                        <>
                          <NarrativeEditor
                            sections={form.sections}
                            section={section}
                            disabled={busy}
                            onSectionChange={setSection}
                            onChange={(sections) =>
                              change("sections", sections)
                            }
                          />
                        </>
                      )}
                      {!historical && (
                        <RevisionControls
                          form={form}
                          busy={busy}
                          dirty={dirty}
                          onChange={change}
                          onSave={saveRevision}
                          onDiscard={discardEdits}
                        />
                      )}
                    </section>
                    <section
                      className="investigation-evidence"
                      aria-label="Investigation evidence"
                    >
                      <h3>Measured evidence</h3>
                      <div className="investigation-selection">
                        <strong>
                          {pendingSelection
                            ? "Pinned selection to attach"
                            : "Current replay selection"}
                        </strong>
                        <p>
                          {attachmentSelection?.recording_id
                            ? `Record ${attachmentSelection.seq ?? "—"} · ${number(attachmentSelection.time_s)} s`
                            : "Select a moment in Review to attach evidence."}
                        </p>
                        <div className="investigation-selection-actions">
                          <button
                            disabled={
                              busy ||
                              dirty ||
                              historical ||
                              !canAttach ||
                              evidence.length >= 32 ||
                              !form.author.trim()
                            }
                            onClick={() => attach()}
                          >
                            Attach selected evidence
                          </button>
                          {pendingSelection && (
                            <button
                              disabled={busy}
                              onClick={() => setPendingSelection(null)}
                            >
                              Use current replay selection
                            </button>
                          )}
                        </div>
                        {dirty && (
                          <small>
                            Save or discard edits before attaching evidence.
                          </small>
                        )}
                        {!dirty && !canAttach && (
                          <small>
                            Attach evidence after recording is finalized.
                          </small>
                        )}
                      </div>
                      {evidence.length === 0 && (
                        <p>No evidence attached yet.</p>
                      )}
                      <div className="investigation-evidence-list">
                        {evidence.map((item) => (
                          <EvidenceCard
                            key={item.evidence_id}
                            item={item}
                            verification={verification}
                            busy={busy}
                            historical={historical}
                            navigate={navigate}
                            cite={cite}
                          />
                        ))}
                      </div>
                    </section>
                  </div>
                </>
              )}
              {exportView && (
                <>
                  <InvestigationReadiness
                    readiness={readiness}
                    ready={ready}
                    dirty={dirty}
                    busy={busy}
                    checkedUtc={verification?.checked_utc}
                    onRecheck={() =>
                      operation(async () => {
                        const checked = await recheckEvidence();
                        if (alive.current)
                          setNotice(
                            checked?.state === "verified"
                              ? "Evidence sources rechecked. Your narrative and saved revision are unchanged."
                              : "Evidence sources need attention. Original snapshots and your narrative are retained.",
                          );
                      })
                    }
                  />
                  <div className="investigation-export survive-controls">
                    <button
                      className="primary"
                      disabled={busy || dirty || unresolvedCitations.length > 0}
                      onClick={() =>
                        operation(async () => {
                          await recheckEvidence();
                          const value = await api(
                            "survive_investigation_export",
                            {
                              investigation_id: document.investigation_id,
                              revision: document.revision,
                            },
                          );
                          if (alive.current) {
                            if (value.saved)
                              setExportedRevision({
                                id: document.investigation_id,
                                revision: document.revision,
                              });
                            setNotice(
                              value.canceled
                                ? "Export canceled. Saved revisions remain unchanged."
                                : value.saved
                                  ? "Portable investigation report exported, with evidence snapshots and verification limitations."
                                  : "Export did not report a saved file.",
                            );
                          }
                        })
                      }
                    >
                      Export investigation report
                    </button>
                    <span>
                      {dirty
                        ? "Save changes in Explain before exporting."
                        : `Saved revision ${document.revision} · HTML with evidence appendix`}
                    </span>
                  </div>
                  <details className="investigation-export-preview">
                    <summary>
                      Preview narrative{dirty ? " — unsaved draft" : ""}
                    </summary>
                    {
                      <NarrativePreview
                        sections={form.sections}
                        evidence={evidence}
                        verification={verification}
                        navigate={navigate}
                        disabled={busy}
                      />
                    }
                  </details>
                  <details className="investigation-export-evidence">
                    <summary>
                      Evidence appendix · {evidence.length} items
                    </summary>
                    {evidence.map((item) => (
                      <EvidenceCard
                        key={item.evidence_id}
                        item={item}
                        compact
                        verification={verification}
                        busy={busy}
                        historical={historical}
                        navigate={navigate}
                        cite={cite}
                      />
                    ))}
                  </details>
                  <details className="investigation-help">
                    <summary>What the export includes</summary>
                    <p>
                      Saved narrative, selected evidence snapshots, revision
                      history and current source warnings. Export rechecks
                      source consistency. It does not change detector results or
                      include the complete original recording.
                    </p>
                  </details>
                </>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

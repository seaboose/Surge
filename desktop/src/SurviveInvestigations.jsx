import React, { useEffect, useRef, useState } from "react";
import "./investigation-flow.css";
import {
  attachedEvidenceId,
  editableInvestigation,
  findVisitedEvidence,
  formatEvidenceNumber as number,
  reportReadiness,
  sameEvidenceSelection,
} from "./survive/investigation-model.mjs";
import {
  NarrativePreview,
  EvidenceCard,
} from "./survive/InvestigationEvidence.jsx";
import { Info } from "./Info.jsx";
import {
  NarrativeEditor,
  ReportField,
  RevisionControls,
} from "./survive/ReportEditor.jsx";
import InvestigationReadiness from "./survive/InvestigationReadiness.jsx";

const NEW_REPORT = "new";
const OPERATION_WAIT =
  "Wait for the investigation operation to finish before leaving.";
function recordingCaption(record) {
  const id = record.recording_id.slice(0, 12);
  return record.display_name && record.display_name !== id
    ? `${record.display_name} (${id})`
    : id;
}

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
  cardVisit = null,
  onReturnToReplay,
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
  const [creating, setCreating] = useState(false);
  const [newAttachment, setNewAttachment] = useState(null);
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
  const visitedCard =
    viewMode === "explain" &&
    !creating &&
    findVisitedEvidence(
      cardVisit,
      document?.investigation_id,
      document?.revision,
      evidence,
    );
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
  const attachedId = attachedEvidenceId(evidence, attachmentSelection);
  const newEvidence = newAttachment || attachmentSelection;
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
            revision: creating ? null : (document?.revision ?? null),
            evidence: creating
              ? []
              : (document?.evidence || []).map(
                  ({ evidence_id, recording_id, seq, constraint_id }) => ({
                    evidence_id,
                    recording_id,
                    seq,
                    constraint_id,
                  }),
                ),
          }
        : null;
    const serialized = JSON.stringify(value);
    if (serialized !== workflowValue.current) {
      workflowValue.current = serialized;
      workflowCallback.current?.(value);
    }
  }, [expanded, exported, ready, dirty, creating, document]);

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
    setNewAttachment(pinned);
    if (!creating && attachedEvidenceId(evidence, pinned)) {
      setError("");
      setNotice("");
      return;
    }
    const additionalSource =
      evidence.length > 0 &&
      !evidence.some((item) => item.recording_id === pinned.recording_id);
    if (
      document &&
      !creating &&
      form &&
      !dirty &&
      !historical &&
      !additionalSource &&
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
            : creating || !document
              ? "Selection pinned. Choose an investigation or create one."
              : dirty
                ? "Selection pinned. Save or discard edits before attaching it."
                : additionalSource
                  ? `This record is from another recording. Attach it to “${document.title}” below, or choose another investigation.`
                  : "Selection pinned. Check the report author and evidence limit before attaching.",
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
    setCreating(false);
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
      sameEvidenceSelection(pending, attached) ? null : pending,
    );
  }

  function attach(selected = attachmentSelection) {
    const pinnedSelection = { ...selected };
    if (attachedEvidenceId(evidence, pinnedSelection)) return;
    operation(async () => {
      const value = await attachTo(document, form.author, pinnedSelection);
      if (!alive.current) return;
      accept(value);
      clearAttachedSelection(pinnedSelection);
      setNotice("Evidence attached in a new draft revision.");
      await refresh();
    });
  }

  function create(pinnedSelection) {
    if (!allowLeave()) return;
    if (pinnedSelection) setPendingSelection(pinnedSelection);
    operation(async () => {
      const created = await api("survive_investigation_create", {
        title: newTitle.trim(),
        author: newAuthor.trim(),
      });
      if (!alive.current) return;
      accept(created);
      if (pinnedSelection) {
        setNotice("Investigation created. The selected record is pinned.");
        const attached = await attachTo(
          created.document,
          newAuthor,
          pinnedSelection,
        );
        if (!alive.current) return;
        accept(attached);
        clearAttachedSelection(pinnedSelection);
        setNotice(
          "Investigation created with the selected evidence. Cite it in your observations.",
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
  const showNew = creating && !exportView;
  function chooseReport(value) {
    if (value === NEW_REPORT) {
      setCreating(true);
      setNewAttachment(
        pendingSelection && canAttach ? { ...pendingSelection } : null,
      );
    } else if (value === document?.investigation_id) {
      setCreating(false);
    } else {
      open(value);
    }
  }
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
            <h2>{exportView ? "Export report" : "Explain the evidence"}</h2>
            <Info label={exportView ? "Export report" : "Explain the evidence"}>
              {exportView
                ? "Review the saved revision and its sources before exporting an HTML copy."
                : "Open or create an investigation, attach recorded moments, then write what they show and where the evidence falls short."}
            </Info>
            {exportView && document && (
              <button disabled={busy} onClick={() => requestStage("explain")}>
                Edit report
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
          <div className="investigation-manager">
            <div className="investigation-picker survive-controls">
              <ReportField
                label="Investigation"
                help={
                  exportView
                    ? "Choose a saved report to check its latest revision and export it."
                    : "Choose a saved report to open its latest revision, or choose New investigation to start a draft."
                }
              >
                <select
                  value={
                    showNew ? NEW_REPORT : document?.investigation_id || ""
                  }
                  disabled={busy}
                  onChange={(event) => chooseReport(event.target.value)}
                >
                  <option value="" disabled>
                    Choose an investigation
                  </option>
                  {!exportView && (
                    <option value={NEW_REPORT}>New investigation…</option>
                  )}
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
              </ReportField>
              <button disabled={busy} onClick={() => operation(refresh)}>
                Refresh list
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
            {showNew && (
              <form
                className="investigation-new"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!busy && newTitle.trim() && newAuthor.trim())
                    create(newAttachment);
                }}
              >
                <div className="survive-controls">
                  <ReportField
                    label="Title"
                    help="Name the question or incident so you can find this report later."
                  >
                    <input
                      aria-label="New investigation title"
                      value={newTitle}
                      maxLength={120}
                      disabled={busy}
                      onChange={(e) => setNewTitle(e.target.value)}
                    />
                  </ReportField>
                  <ReportField
                    label="Your name or alias"
                    help="Your name appears beside the revision and any evidence you attach."
                  >
                    <input
                      aria-label="New investigation author"
                      value={newAuthor}
                      maxLength={80}
                      disabled={busy}
                      onChange={(e) => setNewAuthor(e.target.value)}
                    />
                  </ReportField>
                  <button
                    type="submit"
                    className="primary"
                    disabled={busy || !newTitle.trim() || !newAuthor.trim()}
                  >
                    Create investigation
                  </button>
                </div>
                {(newAttachment || canAttach) && (
                  <label
                    className="investigation-include"
                    title={newEvidence.recording_id}
                  >
                    <input
                      type="checkbox"
                      checked={Boolean(newAttachment)}
                      disabled={busy}
                      onChange={(event) =>
                        setNewAttachment(
                          event.target.checked
                            ? { ...attachmentSelection }
                            : null,
                        )
                      }
                    />
                    Attach record {newEvidence.seq} ·{" "}
                    {number(newEvidence.time_s)} s ·{" "}
                    {recordingCaption(newEvidence)}
                  </label>
                )}
              </form>
            )}
            {exportView && !document && (
              <button onClick={() => requestStage("explain")}>
                Create an investigation in Explain
              </button>
            )}
          </div>
          {document && form && !showNew && (
            <>
              <div className="investigation-document-heading">
                <div className="report-heading">
                  <h3>{document.title}</h3>
                  <Info label="Investigation revision">
                    This is the open revision. Saved revisions and their
                    evidence remain available in revision history.
                  </Info>
                </div>
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
                  {evidence.length > 0 &&
                    `· ${evidence.length} ${evidence.length === 1 ? "item" : "items"}`}
                </span>
                <Info label="Source verification">
                  Opening an investigation checks its linked records against
                  their saved fingerprints. Open a verified reference to return
                  to the original moment.
                </Info>
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
                  <div className="investigation-grid">
                    <section
                      className="investigation-evidence"
                      aria-label="Investigation evidence"
                    >
                      <div className="report-heading">
                        <h3>Measured evidence</h3>
                        <Info label="Measured evidence">
                          Attach the selected record or movement interval to
                          save a snapshot in the report. Open it to see the
                          moment in replay, or cite it in your observations.
                        </Info>
                      </div>
                      <div className="investigation-selection">
                        <div className="report-heading">
                          <strong>
                            {pendingSelection
                              ? "Pinned replay selection"
                              : "Current replay selection"}
                          </strong>
                          <Info
                            label={
                              attachedId
                                ? "Attached evidence"
                                : "Record to attach"
                            }
                          >
                            {attachedId
                              ? `This revision already contains this exact selection as ${attachedId}. Use that ID to cite it in your observations.`
                              : pendingSelection
                                ? "Review pinned this exact record for the report. Use current replay selection to replace it with the moment now selected."
                                : "This is the selected moment in Review. Attaching creates a new draft revision with a permanent evidence reference."}
                          </Info>
                        </div>
                        <p title={attachmentSelection?.recording_id}>
                          {attachmentSelection?.recording_id
                            ? `Record ${attachmentSelection.seq ?? "—"} · ${number(attachmentSelection.time_s)} s · ${recordingCaption(attachmentSelection)}`
                            : "Select a moment in Review to attach evidence."}
                        </p>
                        <div className="investigation-selection-actions">
                          {attachedId ? (
                            <span className="investigation-state" role="status">
                              Attached as {attachedId}
                            </span>
                          ) : (
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
                          )}
                          {pendingSelection && (
                            <button
                              disabled={busy}
                              onClick={() => setPendingSelection(null)}
                            >
                              Use current replay selection
                            </button>
                          )}
                        </div>
                        {dirty && !attachedId && (
                          <small>
                            Save or discard edits before attaching evidence.
                          </small>
                        )}
                        {!dirty && !canAttach && !attachedId && (
                          <small>
                            Attach evidence after recording is finalized.
                          </small>
                        )}
                      </div>

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
                            visit={item === visitedCard ? cardVisit : null}
                            onReturnToReplay={onReturnToReplay}
                          />
                        ))}
                      </div>
                    </section>
                    <section
                      aria-label="Investigation narrative"
                      className="investigation-narrative"
                    >
                      <div className="investigation-writing-toolbar">
                        <div className="report-heading">
                          <h3>Your interpretation</h3>
                          <Info label="Your interpretation">
                            Write in each section and cite attached records with
                            references such as [E1]. Read narrative shows the
                            sections together. Save a revision to keep your
                            edits.
                          </Info>
                        </div>
                        {!historical && (
                          <button onClick={() => setReading(!reading)}>
                            {reading ? "Edit narrative" : "Read narrative"}
                          </button>
                        )}
                      </div>
                      {reading || historical ? (
                        <NarrativePreview
                          sections={form.sections}
                          evidence={evidence}
                          verification={verification}
                          navigate={navigate}
                          disabled={busy}
                        />
                      ) : (
                        <NarrativeEditor
                          sections={form.sections}
                          section={section}
                          disabled={busy}
                          onSectionChange={setSection}
                          onChange={(sections) => change("sections", sections)}
                        />
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
                  </div>
                  <details className="investigation-report-details">
                    <summary>Report details and revision history</summary>
                    <div className="survive-controls">
                      <ReportField
                        label="Report title"
                        help="Rename the report in your next saved revision."
                      >
                        <input
                          aria-label="Report title"
                          value={form.title}
                          maxLength={120}
                          disabled={busy || historical}
                          onChange={(e) => change("title", e.target.value)}
                        />
                      </ReportField>
                      <ReportField
                        label="Author for this revision"
                        help="Identify who made these edits in the revision history."
                      >
                        <input
                          aria-label="Revision author"
                          value={form.author}
                          maxLength={80}
                          disabled={busy || historical}
                          onChange={(e) => change("author", e.target.value)}
                        />
                      </ReportField>
                      <ReportField
                        label="Revision history"
                        help="Select a revision to read its saved narrative and evidence. Open the latest revision to continue editing."
                      >
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
                      </ReportField>
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
                  <button
                    className="investigation-continue"
                    disabled={busy}
                    onClick={() => requestStage("export")}
                  >
                    Continue to export
                  </button>
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
                    <Info label="Export contents">
                      Export rechecks the sources and saves the report, evidence
                      snapshots, revision history, and source warnings in an
                      HTML file.
                    </Info>
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
                </>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

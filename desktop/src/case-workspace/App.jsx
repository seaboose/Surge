import React, { useState, useEffect, useRef } from "react";
import { Context, request } from "./context.jsx";
import { Button, Modal } from "./controls.jsx";
import { CaseNameDialog, CaseLibraryDialog } from "./CaseDialogs.jsx";
import DataView from "./DataView.jsx";
import Results from "./Results.jsx";
import Compare from "./Compare.jsx";
import Evaluate from "./Evaluate.jsx";
import Details from "./Details.jsx";
import CollectionPanel from "./CollectionPanel.jsx";
import Welcome from "./Welcome.jsx";
import EntryChooser from "./EntryChooser.jsx";
import SavedCaseStatus from "./SavedCaseStatus.jsx";
import WorkspaceHeader from "./WorkspaceHeader.jsx";
import SurviveWorkspace from "../SurviveWorkspace.jsx";
import usePreferences from "./usePreferences.jsx";
import { newestCase } from "./preferences.mjs";

const VIEWS = ["Data", "Results", "Compare", "Evaluate", "Details"];

const VIEW_LABELS = { Details: "Case details" };

const VIEW_HELP = {
  Data: "Import evidence and configure analysis",
  Results: "Review conclusions and inspect supporting records",
  Compare: "Compare the current investigation with a saved case",
  Evaluate: "Measure detection performance with independent labels",
  Details: "Inspect source fingerprints, settings and provenance",
};

function suggestedCopyName(name) {
  const characters = Array.from(name);
  while (characters.join("").length > 93) characters.pop();
  return `${characters.join("").trimEnd()} — copy`;
}

export default function App() {
  const settings = usePreferences();
  const startupAttempted = useRef(false);
  const interacted = useRef(false);
  const pending = useRef(false);
  const [working, setWorking] = useState(false);
  const [homeVisible, setHomeVisible] = useState(false);
  const [entry, setEntry] = useState(null);
  const [libraryRefresh, setLibraryRefresh] = useState(0);
  const [mappingUndo, setMappingUndo] = useState(null);
  const [capture, setCapture] = useState(null);
  const [captureVisible, setCaptureVisible] = useState(false);
  const [captureDemo, setCaptureDemo] = useState(false);
  const [surviveVisible, setSurviveVisible] = useState(false);
  const [libraryVisible, setLibraryVisible] = useState(false);
  const [saveVisible, setSaveVisible] = useState(false);
  const [savedNotice, setSavedNotice] = useState(null);
  const [openedCase, setOpenedCase] = useState(null);
  const captureEpoch = useRef(0);
  const [state, setState] = useState(null),
    [busy, setBusy] = useState(false),
    [status, setStatus] = useState("Opening Surge…");
  const [error, setError] = useState(""),
    [page, setPage] = useState("Data");
  const atHome =
    !entry && (homeVisible || (!state?.current && !captureVisible));
  const workspaceVisible = !atHome && !entry;
  const openEntry = (kind) => {
    if (pending.current) return;
    setHomeVisible(false);
    setCaptureVisible(false);
    setEntry(kind);
  };
  const openCapture = () => {
    setEntry(null);
    setHomeVisible(false);
    setCaptureVisible(true);
  };
  const navigateView = (target) => {
    setHomeVisible(false);
    setEntry(null);
    setPage(target);
  };
  const goHome = () => {
    if (pending.current) return;
    setEntry(null);
    setLibraryRefresh((n) => n + 1);
    setHomeVisible(true);
    setCaptureVisible(false);
    requestAnimationFrame(() =>
      document.querySelector(".surge-wordmark")?.focus(),
    );
  };
  useEffect(() => {
    if (entry && !surviveVisible)
      document.querySelector(".instrument-heading h1")?.focus();
  }, [entry, surviveVisible]);
  useEffect(() => {
    // A user's action always wins over a delayed startup library lookup.
    const markInteraction = () => {
      interacted.current = true;
    };
    document.addEventListener("pointerdown", markInteraction, true);
    document.addEventListener("keydown", markInteraction, true);
    return () => {
      document.removeEventListener("pointerdown", markInteraction, true);
      document.removeEventListener("keydown", markInteraction, true);
    };
  }, []);
  useEffect(() => {
    request("state")
      .then((v) => {
        setState(v);
        if (v.capture) {
          setCapture(v.capture);
          setCaptureVisible(true);
        }
        setStatus("Import evidence or open a case.");
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!state || startupAttempted.current) return;
    startupAttempted.current = true;
    if (
      !settings.preferences.openLatestCase ||
      state.current ||
      state.capture ||
      interacted.current
    )
      return;
    let alive = true;
    request("library_list")
      .then(async (library) => {
        if (!alive || interacted.current || pending.current) return;
        const latest = newestCase(library.entries);
        if (!latest) {
          setStatus(
            library.unavailable
              ? "Recent cases are unavailable. Home is ready."
              : "No saved cases yet. Home is ready.",
          );
          return;
        }
        await run("library_open", { id: latest.id }, undefined, false, true);
      })
      .catch(() => {
        if (alive && !interacted.current)
          setStatus("Recent cases could not be read. Home is ready.");
      });
    return () => {
      alive = false;
    };
  }, [!!state]);
  useEffect(() => {
    if (capture?.state !== "running") return;
    let alive = true;
    let timer;
    const poll = async () => {
      const epoch = captureEpoch.current;
      if (!pending.current) {
        try {
          const value = await request("native_status");
          if (alive && epoch === captureEpoch.current)
            setCapture(value.capture);
        } catch (e) {
          if (alive && epoch === captureEpoch.current)
            setCapture((old) => ({
              ...old,
              error: `Status unavailable: ${e.message}`,
            }));
        }
      }
      if (alive) timer = setTimeout(poll, 1000);
    };
    timer = setTimeout(poll, 1000);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [capture?.state]);
  async function run(
    method,
    args = {},
    after,
    restoring = false,
    automatic = false,
  ) {
    if (method === "save") {
      setSaveVisible(true);
      return;
    }
    if (method === "export_case") method = "save";
    if (pending.current) {
      setStatus("An action is still running. Try again when it finishes.");
      return;
    }
    pending.current = true;
    setWorking(true);
    // Reading and exporting do not replace the workspace. Keep investigation
    // controls available, while serializing commands that may change state.
    const reading =
      (method.startsWith("library_") && method !== "library_open") ||
      [
        "copy",
        "save",
        "alerts",
        "policy_save",
        "labels_template",
        "evaluation_save",
        "native_start",
        "native_export",
      ].includes(method);
    setBusy(!reading);
    setStatus(
      {
        copy: "Copying…",
        save: "Saving case…",
        alerts: "Exporting alerts…",
        policy_save: "Saving policy…",
        labels_template: "Saving label template…",
        evaluation_save: "Saving evaluation…",
        analyze: "Analyzing records…",
        import: "Importing data…",
        open: "Opening case…",
        configure: "Updating mapping…",
        native_start: "Starting collection…",
        native_snapshot: "Opening captured evidence…",
        native_stop: "Stopping collection…",
        native_export: "Saving captured evidence…",
      }[method] || "Updating workspace…",
    );
    try {
      const v = await request(method, {
        ...(state &&
        method !== "import" &&
        method !== "open" &&
        method !== "state" &&
        !method.startsWith("native_") &&
        !(method.startsWith("library_") && method !== "library_save")
          ? { revision: state.revision }
          : {}),
        ...args,
      });
      if (v.canceled) {
        setStatus("Canceled. Your workspace is unchanged.");
        return;
      }
      if (
        [
          "library_save",
          "library_import",
          "library_rename",
          "library_delete",
        ].includes(method)
      )
        setLibraryRefresh((n) => n + 1);
      if (v.capture) {
        captureEpoch.current++;
        setCapture(v.capture);
      }
      if (v.protocol) {
        setSavedNotice(null);
        if (["open", "library_open"].includes(method)) {
          setOpenedCase(v.library_case || { name: v.case_file.name });
          setCaptureVisible(false);
        } else if (
          (method === "import" && args.role !== "reference") ||
          ["native_snapshot", "native_stop"].includes(method)
        ) {
          setOpenedCase(null);
        } else if (v.case_file?.modified) {
          setOpenedCase((old) => old && { ...old, modified: true });
        }
        if (method === "configure") {
          if (restoring) setMappingUndo(null);
          else if (
            JSON.stringify(v.config) !== JSON.stringify(state.config) ||
            v.rules_text !== state.rules_text
          )
            setMappingUndo({
              config: structuredClone(state.config),
              rules_text: state.rules_text,
            });
        } else if (
          [
            "import",
            "open",
            "library_open",
            "policy_load",
            "native_snapshot",
            "native_stop",
          ].includes(method)
        ) {
          setMappingUndo(null);
        }
        setState(v);
        setStatus(
          v.summary
            ? "Results linked to original evidence."
            : "Check the mappings, then Analyze.",
        );
      } else {
        setStatus(v.message || "Complete.");
        if (method === "library_rename") {
          const rename = (old) =>
            old?.id === args.id ? { ...old, name: args.name.trim() } : old;
          setOpenedCase(rename);
          setSavedNotice(rename);
        }
        if (method === "library_delete") {
          // Keep the loaded snapshot's provenance, but detach library membership.
          setOpenedCase((old) =>
            old?.id === args.id ? { ...old, id: undefined } : old,
          );
          setSavedNotice((old) => (old?.id === args.id ? null : old));
        }
        if (v.case_file)
          setState((old) => ({ ...old, case_file: v.case_file }));
      }
      if (["open", "library_open", "analyze"].includes(method))
        setPage("Results");
      if (method === "native_start") setSavedNotice(null);
      if (["native_snapshot", "native_stop"].includes(method) && v.summary)
        setPage("Results");
      if (["import", "policy_load", "configure"].includes(method))
        setPage("Data");
      if (restoring) setStatus("Mapping restored. Analyze to refresh results.");
      if (
        [
          "import",
          "open",
          "library_open",
          "analyze",
          "native_start",
          "native_snapshot",
          "native_stop",
        ].includes(method)
      ) {
        setHomeVisible(false);
        setEntry(null);
      }
      after?.(v);
    } catch (e) {
      if (automatic) {
        setHomeVisible(true);
        setStatus(
          "The latest case could not be opened. Choose a case from Home.",
        );
      } else {
        setError(e.message);
        setStatus("Operation failed. Previous evidence was retained.");
      }
    } finally {
      pending.current = false;
      setWorking(false);
      setBusy(false);
    }
  }
  useEffect(() => {
    const shortcut = (e) => {
      if (
        busy ||
        surviveVisible ||
        document.querySelector("dialog[open], .settings-panel:popover-open")
      )
        return;
      if (e.ctrlKey || e.metaKey) {
        if (e.key.toLowerCase() === "o") {
          e.preventDefault();
          run("import", { role: "current" });
        }
        if (e.key === "Enter" && state?.current && !state.blocked) {
          e.preventDefault();
          run("analyze");
        }
        if (e.key.toLowerCase() === "s" && state?.summary) {
          e.preventDefault();
          run("save");
        }
        if (e.key.toLowerCase() === "f" && state?.summary) {
          e.preventDefault();
          navigateView("Results");
          requestAnimationFrame(() =>
            document.querySelector('[aria-label="Search records"]')?.focus(),
          );
        }
      }
      if (
        e.altKey &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.shiftKey &&
        /^[1-5]$/.test(e.key)
      ) {
        const target = VIEWS[Number(e.key) - 1];
        if (state?.current && (target === "Data" || state.summary)) {
          e.preventDefault();
          navigateView(target);
        }
      }
    };
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, [state, busy, surviveVisible]);
  const setupPosition = useRef({ top: 0, focus: null });
  const inspectedCurrentCapture =
    !!state?.inspected_capture &&
    state.inspected_capture.session_id === capture?.session_id;
  const finalSnapshotOpen =
    inspectedCurrentCapture &&
    capture?.state === "stopped" &&
    state.inspected_capture.capture_state === "stopped" &&
    state.inspected_capture.final_sequence === capture.final_sequence;
  const footerText =
    working ||
    error ||
    /^(Canceled|Operation failed|An action is still running)/.test(status)
      ? status
      : openedCase
        ? openedCase.modified
          ? "Working from a saved case · the saved copy is unchanged."
          : "Ready."
        : captureVisible
          ? savedNotice?.revision === state?.revision
            ? "Ready."
            : capture?.state === "failed"
              ? "Collection failed · review the reported error."
              : capture?.state === "running"
                ? capture?.error
                  ? "Collection needs attention."
                  : "Collecting."
                : capture?.has_evidence
                  ? "Collection stopped."
                  : "Capture ready."
          : status;
  const ctx = {
    saveActionLabel: openedCase
      ? openedCase.modified
        ? "Save as new case"
        : "Save a copy"
      : savedNotice?.revision === state?.revision
        ? "Save a copy"
        : "Save case",
    savedInLibrary:
      (!openedCase?.modified && !!openedCase?.id) ||
      (savedNotice && savedNotice.revision === state?.revision),
    state,
    run,
    busy,
    setError,
    setStatus,
    setupPosition,
    mappingUndo,
    showCapture: openCapture,
    showLibrary: () => setLibraryVisible(true),
    capture,
    captureVisible,
    working,
    demoReadyToSave: !savedNotice && !!state?.summary && finalSnapshotOpen,
  };
  if (!state)
    return (
      <main className="loading">
        <p>{error || status}</p>
      </main>
    );
  if (surviveVisible)
    return (
      <SurviveWorkspace
        settings={settings}
        onClose={() => setSurviveVisible(false)}
        onHome={() => {
          setSurviveVisible(false);
          goHome();
        }}
      />
    );
  const viewButtons = VIEWS.map((view, index) => (
    <Button
      key={view}
      title={`${VIEW_HELP[view]} (Alt+${index + 1})${view !== "Data" && !state.summary ? " · Analyze evidence first" : ""}`}
      aria-keyshortcuts={`Alt+${index + 1}`}
      aria-current={view === page ? "page" : undefined}
      aria-controls={`workspace-${view.toLowerCase()}`}
      className={view === page ? "active" : ""}
      disabled={busy || (view !== "Data" && !state.summary)}
      onClick={() => navigateView(view)}
    >
      {VIEW_LABELS[view] || view}
    </Button>
  ));
  return (
    <Context.Provider value={ctx}>
      <div
        className={`app ${busy ? "busy" : ""} ${atHome ? "at-home" : ""}`}
        data-working={working}
      >
        <WorkspaceHeader
          title={
            atHome
              ? null
              : entry
                ? entry === "demo"
                  ? "Try Demo"
                  : "Start capture"
                : captureVisible && !state.current
                  ? "Capture"
                  : "Investigation"
          }
          onHome={goHome}
          working={working}
          settings={settings}
          homeContent={
            atHome && (
              <Button
                className="home-demo-control"
                disabled={working}
                onClick={() => openEntry("demo")}
              >
                <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                  <path d="M5 3 17 10 5 17Z" />
                </svg>
                Try Demo
              </Button>
            )
          }
        >
          <Button disabled={working} onClick={() => openEntry("capture")}>
            Start capture
          </Button>
          <Button disabled={working} onClick={() => openEntry("demo")}>
            Try Demo
          </Button>
          <Button disabled={working} onClick={() => setLibraryVisible(true)}>
            Case library
          </Button>
          {state.current && !workspaceVisible && viewButtons}
        </WorkspaceHeader>
        <main
          className={
            workspaceVisible &&
            (captureVisible ||
              openedCase ||
              savedNotice?.revision === state.revision)
              ? "with-capture"
              : undefined
          }
        >
          {workspaceVisible && openedCase && (
            <SavedCaseStatus
              openedCase={openedCase}
              onShowCapture={openCapture}
            />
          )}
          {workspaceVisible && savedNotice?.revision === state.revision && (
            <div
              className="saved-confirmation"
              role="region"
              aria-label="Case saved"
            >
              <span role="status">
                Saved “{savedNotice.name}” to Case library.
              </span>
              <small>
                Your case is already saved. Reopening it is optional.
              </small>
              <Button
                className="primary"
                disabled={working}
                onClick={() => run("library_open", { id: savedNotice.id })}
              >
                Open saved case
              </Button>
              <Button
                disabled={working}
                onClick={() => setLibraryVisible(true)}
              >
                Open library
              </Button>
            </div>
          )}
          {workspaceVisible && captureVisible && (
            <CollectionPanel
              demoMode={captureDemo}
              onSources={() => openEntry("capture")}
              openedCase={openedCase}
              savedNotice={savedNotice}
              page={page}
              inspectedCurrentCapture={inspectedCurrentCapture}
              finalSnapshotOpen={finalSnapshotOpen}
              onClose={() => setCaptureVisible(false)}
            />
          )}
          {(atHome || entry) && (capture || state.current) && (
            <div
              className="home-resume"
              role="region"
              aria-label="Current work"
            >
              <span>
                {capture?.state === "running"
                  ? "Live capture is running"
                  : "Your current work is still open"}
              </span>
              {capture && (
                <Button onClick={openCapture} disabled={working}>
                  Return to capture
                </Button>
              )}
              {state.current && (
                <Button
                  onClick={() => {
                    setHomeVisible(false);
                    setEntry(null);
                  }}
                  disabled={working}
                >
                  Return to evidence
                </Button>
              )}
              {capture?.state === "running" && (
                <Button
                  onClick={() =>
                    run("native_stop", {}, () => setCaptureVisible(true))
                  }
                  disabled={working}
                >
                  Stop collection
                </Button>
              )}
            </div>
          )}
          {atHome && (
            <Welcome
              onLibrary={() => setLibraryVisible(true)}
              onCapture={() => openEntry("capture")}
              onDemo={() => openEntry("demo")}
              libraryRefresh={libraryRefresh}
            />
          )}
          {entry && (
            <EntryChooser
              kind={entry}
              onNative={() => {
                setCaptureDemo(entry === "demo");
                openCapture();
              }}
              onSurvive={() => setSurviveVisible(true)}
              working={working}
            />
          )}
          {state.current && (
            <fieldset
              disabled={busy}
              className="workspace"
              data-view={page}
              hidden={!workspaceVisible}
            >
              <header className="case-heading">
                <div>
                  <h2>{openedCase?.name || state.current.name}</h2>
                  <p>
                    {openedCase
                      ? "Saved case"
                      : state.inspected_capture
                        ? "Viewed snapshot"
                        : "Imported evidence"}
                    {" · "}
                    {state.current.records.toLocaleString()} records
                    {state.observation_counts && (
                      <>
                        {" "}
                        · {state.observation_counts.samples.toLocaleString()}{" "}
                        retained samples
                      </>
                    )}
                  </p>
                </div>
              </header>
              <nav className="workspace-views" aria-label="Investigation views">
                {viewButtons}
              </nav>
              <div
                className="view"
                id="workspace-data"
                hidden={page !== "Data"}
              >
                <DataView
                  key={state.revision}
                  active={workspaceVisible && page === "Data"}
                />
              </div>
              {state.summary && (
                <>
                  <div
                    className="view"
                    id="workspace-results"
                    hidden={page !== "Results"}
                  >
                    <Results
                      key={state.revision}
                      active={workspaceVisible && page === "Results"}
                    />
                  </div>
                  <div
                    className="view"
                    id="workspace-compare"
                    hidden={page !== "Compare"}
                  >
                    <Compare
                      key={state.revision}
                      active={workspaceVisible && page === "Compare"}
                    />
                  </div>
                  <div
                    className="view"
                    id="workspace-evaluate"
                    hidden={page !== "Evaluate"}
                  >
                    <Evaluate
                      key={state.revision}
                      active={workspaceVisible && page === "Evaluate"}
                    />
                  </div>
                  <div
                    className="view"
                    id="workspace-details"
                    hidden={page !== "Details"}
                  >
                    <Details active={workspaceVisible && page === "Details"} />
                  </div>
                </>
              )}
            </fieldset>
          )}
        </main>
        <footer
          role="status"
          data-quiet={footerText === "Import evidence or open a case."}
        >
          <span className="status-light" aria-hidden="true" />
          {footerText}
        </footer>
        {libraryVisible && (
          <CaseLibraryDialog
            run={run}
            working={working}
            close={() => setLibraryVisible(false)}
          />
        )}
        {saveVisible && (
          <CaseNameDialog
            label={
              ctx.saveActionLabel === "Save case"
                ? "Save case to library"
                : ctx.saveActionLabel
            }
            initialName={
              openedCase?.name || savedNotice?.revision === state.revision
                ? suggestedCopyName(openedCase?.name || savedNotice.name)
                : state.inspected_capture
                  ? `Capture investigation — ${new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`
                  : ""
            }
            collecting={capture?.state === "running"}
            working={working}
            close={() => setSaveVisible(false)}
            apply={(name) =>
              run("library_save", { name }, (value) => {
                setSaveVisible(false);
                setSavedNotice({
                  id: value.entry.id,
                  name: value.entry.name,
                  revision: state.revision,
                });
              })
            }
          />
        )}
        {error && (
          <Modal close={() => setError("")} label="Check input">
            <pre className="error-message">{error}</pre>
          </Modal>
        )}
      </div>
    </Context.Provider>
  );
}

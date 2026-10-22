import React, {
  useState,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useContext,
  createContext,
} from "react";
import { createRoot } from "react-dom/client";

const Context = createContext(null);
const VIEWS = ["Data", "Findings", "Compare", "Evaluate", "Details"];
async function request(method, args = {}) {
  const reply = await window.surge.request(method, args);
  if (!reply.ok) throw new Error(reply.error);
  return reply.value;
}
function useData(method, args, enabled = true, refresh = 0) {
  const [result, setResult] = useState(null),
    [failure, setFailure] = useState(null);
  const key = JSON.stringify(args);
  const cache = useRef(null);
  useEffect(() => {
    let alive = true;
    if (
      enabled &&
      !(cache.current?.key === key && cache.current?.refresh === refresh)
    ) {
      setFailure(null);
      request(method, JSON.parse(key))
        .then((v) => {
          if (alive) {
            cache.current = { key, refresh };
            setResult({ key, refresh, value: v });
          }
        })
        .catch((e) => {
          if (alive) setFailure({ key, refresh, error: e.message });
        });
    }
    return () => {
      alive = false;
    };
  }, [method, key, enabled, refresh]);
  return [
    result?.key === key && result?.refresh === refresh ? result.value : null,
    failure?.key === key && failure?.refresh === refresh ? failure.error : "",
  ];
}
function useDebounce(value) {
  const [result, set] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => set(value), 120);
    return () => clearTimeout(id);
  }, [value]);
  return result;
}
const Button = ({ children, ...props }) => (
  <button type="button" {...props}>
    {children}
  </button>
);
function rowKey(event, items, row, select) {
  if (["Enter", " "].includes(event.key)) {
    event.preventDefault();
    select(row);
    return;
  }
  const index = items.findIndex((r) => r.row === row);
  const next =
    event.key === "ArrowDown"
      ? index + 1
      : event.key === "ArrowUp"
        ? index - 1
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? items.length - 1
            : null;
  if (next !== null) {
    event.preventDefault();
    if (items[next]) {
      select(items[next].row);
      const target = event.currentTarget.parentElement.children[next];
      target?.focus();
      target?.scrollIntoView({ block: "nearest" });
    }
  }
}
function Select({ label, value, onChange, options, ...props }) {
  return (
    <label className="control">
      <span>{label}</span>
      <select
        aria-label={label}
        title={String(value ?? "Not mapped")}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        {...props}
      >
        {options.map((o) => (
          <option key={o.value ?? o} value={o.value ?? o}>
            {o.label ?? o}
          </option>
        ))}
      </select>
    </label>
  );
}
function Pager({ page, total, onChange }) {
  return (
    <div className="actions pager">
      <Button disabled={!page} onClick={() => onChange(page - 1)}>
        Previous
      </Button>
      <span>
        {total
          ? `${page * 100 + 1}–${Math.min((page + 1) * 100, total)} of ${total}`
          : "0 records"}
      </span>
      <Button
        disabled={(page + 1) * 100 >= total}
        onClick={() => onChange(page + 1)}
      >
        Next
      </Button>
    </div>
  );
}
function PreviewTable({ preview, row, select, height }) {
  const host = useRef();
  const [viewport, setViewport] = useState({ left: 0, width: 800 });
  const columns = useMemo(() => {
    let left = 0;
    return preview.fields.map((field, index) => {
      const length = Math.max(
        field.length,
        ...preview.rows.map((r) => r.values[index].length),
      );
      const width = Math.min(220, Math.max(80, length * 7 + 24));
      const column = { field, index, left, width, right: left + width };
      left += width;
      return column;
    });
  }, [preview]);
  useLayoutEffect(() => {
    const measure = () => {
      const width = host.current?.clientWidth || 0;
      if (width) setViewport((v) => (v.width === width ? v : { ...v, width }));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  const total = columns.at(-1)?.right || 0;
  const recordWidth = preview.rows.some((r) => r.related) ? 132 : 84;
  // Keep one maximum-width column of overscan on either side. The full page,
  // source order and horizontal scroll range remain available.
  const visible = columns.filter(
    (c) =>
      c.right > viewport.left - 220 &&
      c.left < viewport.left + viewport.width - recordWidth + 220,
  );
  const before = visible[0]?.left || 0,
    after = total - (visible.at(-1)?.right || 0);
  const spacer = (width, tag) =>
    width > 0
      ? React.createElement(
          tag,
          {
            className: "preview-spacer",
            "aria-hidden": true,
            style: { width },
          },
          null,
        )
      : null;
  return (
    <div
      ref={host}
      className="preview-table scroll"
      style={row && height ? { flex: `0 0 ${height}px` } : undefined}
      onScroll={(e) => {
        const left = e.currentTarget.scrollLeft;
        setViewport((v) => (v.left === left ? v : { ...v, left }));
      }}
    >
      <table
        aria-label="Preview"
        aria-colcount={columns.length + 1}
        style={{ tableLayout: "fixed", width: total + recordWidth }}
      >
        <colgroup>
          <col style={{ width: recordWidth }} />
          {before > 0 && <col style={{ width: before }} />}
          {visible.map((c) => (
            <col key={c.field} style={{ width: c.width }} />
          ))}
          {after > 0 && <col style={{ width: after }} />}
        </colgroup>
        <thead>
          <tr>
            <th className="record-column" scope="col" aria-colindex={1}>
              Record
            </th>
            {spacer(before, "th")}
            {visible.map((c) => (
              <th
                key={c.field}
                scope="col"
                aria-colindex={c.index + 2}
                title={c.field}
              >
                {preview.marked.includes(c.field) ? "→ " : ""}
                {c.field}
              </th>
            ))}
            {spacer(after, "th")}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((r, i) => (
            <tr
              key={r.row}
              className={row === r.row ? "selected" : ""}
              tabIndex={row === r.row || (!row && i === 0) ? 0 : -1}
              aria-selected={row === r.row}
              onClick={() => select(r.row)}
              onKeyDown={(e) => rowKey(e, preview.rows, r.row, select)}
            >
              <td className="record-column" aria-colindex={1}>
                {r.row}
                {r.related ? " · related" : ""}
              </td>
              {spacer(before, "td")}
              {visible.map((c) => (
                <td
                  key={c.field}
                  aria-colindex={c.index + 2}
                  title={r.values[c.index]}
                >
                  {r.values[c.index]}
                </td>
              ))}
              {spacer(after, "td")}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Modal({ children, close, label = "Details" }) {
  const ref = useRef();
  useEffect(() => {
    const previous = document.activeElement;
    ref.current.showModal();
    return () => {
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={label}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      {children}
      <div className="actions end">
        <Button onClick={close}>Close</Button>
      </div>
    </dialog>
  );
}
function Split({ left, right, name }) {
  const initial = () => {
    try {
      const v = Number(localStorage.getItem(name));
      return v >= 30 && v <= 70 ? v : 50;
    } catch {
      return 50;
    }
  };
  const [size, setSize] = useState(initial);
  const ref = useRef();
  function update(v) {
    const n = Math.max(30, Math.min(70, v));
    setSize(n);
  }
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(name, String(size));
      } catch {}
    }, 180);
    return () => clearTimeout(timer);
  }, [name, size]);
  return (
    <div
      className="split"
      ref={ref}
      style={{
        gridTemplateColumns: `minmax(0,${size}fr) 9px minmax(0,${100 - size}fr)`,
      }}
    >
      <div className="split-pane">{left}</div>
      <div
        className="divider"
        role="separator"
        aria-label="Resize evidence"
        aria-orientation="vertical"
        aria-valuenow={Math.round(size)}
        aria-valuemin="30"
        aria-valuemax="70"
        tabIndex="0"
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
            e.preventDefault();
            update(size + (e.key === "ArrowLeft" ? -2 : 2));
          }
        }}
        onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
        onPointerMove={(e) => {
          if (e.currentTarget.hasPointerCapture(e.pointerId)) {
            const r = ref.current.getBoundingClientRect();
            update(((e.clientX - r.left) / r.width) * 100);
          }
        }}
        onPointerUp={(e) => e.currentTarget.releasePointerCapture(e.pointerId)}
      />
      <div className="split-pane">{right}</div>
    </div>
  );
}
function App() {
  const pending = useRef(false);
  const [working, setWorking] = useState(false);
  const [mappingUndo, setMappingUndo] = useState(null);
  const [capture, setCapture] = useState(null);
  const [captureVisible, setCaptureVisible] = useState(false);
  const [captureBuild, setCaptureBuild] = useState("v1");
  const captureEpoch = useRef(0);
  const [state, setState] = useState(null),
    [busy, setBusy] = useState(false),
    [status, setStatus] = useState("Opening Surge…");
  const [error, setError] = useState(""),
    [page, setPage] = useState("Data");
  useEffect(() => {
    request("state")
      .then((v) => {
        setState(v);
        if (v.capture) {
          setCapture(v.capture);
          setCaptureVisible(true);
        }
        setStatus("Import data or open a case.");
      })
      .catch((e) => setError(e.message));
  }, []);
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
  async function run(method, args = {}, after, restoring = false) {
    if (pending.current) {
      setStatus("An action is still running. Try again when it finishes.");
      return;
    }
    pending.current = true;
    setWorking(true);
    // Reading and exporting do not replace the workspace. Keep investigation
    // controls available, while serializing commands that may change state.
    const reading = [
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
        !method.startsWith("native_")
          ? { revision: state.revision }
          : {}),
        ...args,
      });
      if (v.canceled) {
        setStatus("Canceled. Your workspace is unchanged.");
        return;
      }
      if (v.capture) {
        captureEpoch.current++;
        setCapture(v.capture);
      }
      if (v.protocol) {
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
            ? "Findings linked to original evidence."
            : "Check the mappings, then Analyze.",
        );
      } else {
        setStatus(v.message || "Complete.");
        if (v.case_file)
          setState((old) => ({ ...old, case_file: v.case_file }));
      }
      if (["open", "analyze"].includes(method)) setPage("Findings");
      if (["native_snapshot", "native_stop"].includes(method) && v.summary)
        setPage("Findings");
      if (["import", "policy_load", "configure"].includes(method))
        setPage("Data");
      if (restoring)
        setStatus("Mapping restored. Analyze to refresh findings.");
      after?.(v);
    } catch (e) {
      setError(e.message);
      setStatus("Operation failed. Previous evidence was retained.");
    } finally {
      pending.current = false;
      setWorking(false);
      setBusy(false);
    }
  }
  useEffect(() => {
    const shortcut = (e) => {
      if (busy || document.querySelector("dialog[open]")) return;
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
          setPage("Findings");
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
          setPage(target);
        }
      }
    };
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, [state, busy]);
  const setupPosition = useRef({ top: 0, focus: null });
  const ctx = {
    state,
    run,
    busy,
    setError,
    setStatus,
    setupPosition,
    mappingUndo,
    showCapture: () => setCaptureVisible(true),
  };
  if (!state)
    return (
      <main className="loading">
        <p>{error || status}</p>
      </main>
    );
  return (
    <Context.Provider value={ctx}>
      <div className={`app ${busy ? "busy" : ""}`} data-working={working}>
        {state.current && (
          <nav aria-label="Views">
            {VIEWS.map((p, index) => (
              <Button
                key={p}
                title={`${p} (Alt+${index + 1})`}
                aria-keyshortcuts={`Alt+${index + 1}`}
                aria-current={p === page ? "page" : undefined}
                className={p === page ? "active" : ""}
                disabled={busy || (p !== "Data" && !state.summary)}
                onClick={() => setPage(p)}
              >
                {p}
              </Button>
            ))}
          </nav>
        )}
        <main className={captureVisible ? "with-capture" : undefined}>
          {captureVisible && (
            <section
              className="capture-controls"
              aria-label="Our app collection"
            >
              <div className="actions">
                <Select
                  label="Build"
                  value={captureBuild}
                  onChange={setCaptureBuild}
                  disabled={working || capture?.state === "running"}
                  options={[
                    { value: "v1", label: "v1" },
                    { value: "v2", label: "v2" },
                  ]}
                />
                <Button
                  disabled={working || capture?.state === "running"}
                  onClick={() => run("native_start", { build: captureBuild })}
                >
                  Start
                </Button>
                <Button
                  disabled={working || !capture?.has_evidence}
                  onClick={() => run("native_snapshot")}
                >
                  Inspect
                </Button>
                <Button
                  disabled={working || capture?.state !== "running"}
                  onClick={() => run("native_stop")}
                >
                  Stop
                </Button>
                <Button
                  disabled={working || !capture?.has_evidence}
                  onClick={() => run("native_export")}
                >
                  Export
                </Button>
              </div>
              <div className="capture-status">
                <span role="status">
                  Our app ·{" "}
                  {capture?.state === "running"
                    ? "Collecting"
                    : capture?.state === "failed"
                      ? "Collection failed"
                      : capture
                        ? "Stopped"
                        : "Ready"}
                </span>
                {capture && (
                  <span>
                    {capture.build} · {capture.records.toLocaleString()} records
                    · {(capture.elapsed_ms / 1000).toFixed(1)} s elapsed ·{" "}
                    {capture.dropped_samples.toLocaleString()} missing samples
                    {capture.evicted_samples > 0 &&
                      ` · ${capture.evicted_samples.toLocaleString()} earlier samples removed`}
                  </span>
                )}
              </div>
              <small>
                {capture?.error ||
                  (capture?.state === "running"
                    ? "Inspect opens a stable snapshot while collection continues. Only configured code ranges are checked."
                    : capture?.records
                      ? "Inspect or export the captured records. Only configured code ranges were checked."
                      : capture
                        ? "No observations captured. Existing evidence is unchanged."
                        : "Start our app to collect evidence. Only configured code ranges are checked.")}
              </small>
              <small>
                Keeps the latest {capture?.limit_samples || 500} samples · Stops
                after 10 minutes
              </small>
            </section>
          )}
          {!state.current ? (
            <div className="empty">
              <div className="empty-orbit" aria-hidden="true" />
              <div className="actions">
                <Button
                  className="primary"
                  disabled={busy}
                  onClick={() => run("import", { role: "current" })}
                >
                  Import data
                </Button>
                <Button disabled={busy} onClick={() => run("open")}>
                  Open case
                </Button>
                {!captureVisible && (
                  <Button
                    disabled={busy}
                    onClick={() => setCaptureVisible(true)}
                  >
                    Our app
                  </Button>
                )}
              </div>
              <p>Choose your data. Follow the evidence.</p>
              <small>
                CSV · JSON · JSONL · NDJSON
                <br />
                Local analysis · No uploads
              </small>
            </div>
          ) : (
            <fieldset disabled={busy} className="workspace">
              <div className="view" hidden={page !== "Data"}>
                <DataView key={state.revision} active={page === "Data"} />
              </div>
              {state.summary && (
                <>
                  <div className="view" hidden={page !== "Findings"}>
                    <Findings
                      key={state.revision}
                      active={page === "Findings"}
                    />
                  </div>
                  <div className="view" hidden={page !== "Compare"}>
                    <Compare key={state.revision} active={page === "Compare"} />
                  </div>
                  <div className="view" hidden={page !== "Evaluate"}>
                    <Evaluate
                      key={state.revision}
                      active={page === "Evaluate"}
                    />
                  </div>
                  <div className="view" hidden={page !== "Details"}>
                    <Details active={page === "Details"} />
                  </div>
                </>
              )}
            </fieldset>
          )}
        </main>
        <footer role="status">
          <span className="status-light" aria-hidden="true" />
          {status}
        </footer>
        {error && (
          <Modal close={() => setError("")} label="Check input">
            <pre className="error-message">{error}</pre>
          </Modal>
        )}
      </div>
    </Context.Provider>
  );
}
function DataView({ active }) {
  const {
    state: s,
    run,
    setupPosition,
    mappingUndo,
    showCapture,
  } = useContext(Context);
  const [optionsOpen, setOptionsOpen] = useState(
    () =>
      setupPosition.current.source === s.current.sha256 &&
      !!setupPosition.current.optionsOpen,
  );
  const setup = useRef();
  useEffect(() => {
    const pane = setup.current;
    if (setupPosition.current.source === s.current.sha256) {
      pane.scrollTop = setupPosition.current.top;
      const target = [...pane.querySelectorAll("input,select,button")].find(
        (el) =>
          (el.getAttribute("aria-label") ||
            el.closest("label")?.textContent ||
            el.textContent) === setupPosition.current.focus,
      );
      target?.focus({ preventScroll: true });
    } else
      setupPosition.current = { top: 0, focus: null, source: s.current.sha256 };
  }, []);
  const [note, setNote] = useState(null),
    [page, setPage] = useState(0),
    [row, setRow] = useState(null);
  const [editor, setEditor] = useState(null),
    [rules, setRules] = useState(s.rules_text),
    [previewHeight, setPreviewHeight] = useState(null);
  const [threshold, setThreshold] = useState(String(s.config.threshold ?? ""));
  const [preview, previewError] = useData(
    "preview",
    { revision: s.revision, note, page },
    active,
  );
  const options = [{ value: "", label: "Not mapped" }, ...s.current.fields];
  const config = (changes, done, ruleText = s.rules_text) =>
    run(
      "configure",
      { config: { ...s.config, ...changes }, rules_text: ruleText },
      done,
    );
  function follow(i) {
    setNote(i);
    setPage(0);
    setRow(null);
  }
  async function step(direction) {
    try {
      const v = await request("record_step", {
        revision: s.revision,
        note,
        row: row ?? 0,
        step: direction,
      });
      if (v.row) {
        setPage(v.page);
        setRow(v.row);
      }
    } catch (e) {
      ctx.setError(e.message);
    }
  }
  const ctx = useContext(Context);
  return (
    <div className="data-layout">
      <aside
        className="setup scroll"
        ref={setup}
        onScroll={(e) => {
          setupPosition.current.top = e.currentTarget.scrollTop;
        }}
        onFocusCapture={(e) => {
          setupPosition.current.focus =
            e.target.getAttribute("aria-label") ||
            e.target.closest("label")?.textContent ||
            e.target.textContent;
        }}
      >
        <div className="actions">
          <Button onClick={() => run("import", { role: "current" })}>
            Import data
          </Button>
          <Button onClick={() => run("open")}>Open case</Button>
          <Button onClick={showCapture}>Our app</Button>
        </div>
        {mappingUndo && (
          <Button
            onClick={() => run("configure", mappingUndo, undefined, true)}
          >
            Undo mapping
          </Button>
        )}
        <p className="filename">{s.current.name}</p>
        <small>
          {s.current.records.toLocaleString()} records ·{" "}
          {s.current.fields.length} fields
        </small>
        <Button onClick={() => run("import", { role: "reference" })}>
          Import reference
        </Button>
        <small>
          {s.reference
            ? `${s.reference.name} · ${s.reference.records} records`
            : "Reference: not loaded"}
        </small>
        {["session", "event_id", "time"].map((key, i) => (
          <Select
            key={key}
            label={["Session", "Record ID", "Time"][i]}
            value={s.config[key]}
            options={options}
            onChange={(v) => config({ [key]: v })}
          />
        ))}
        {s.config.time && (
          <Select
            label="Time format"
            value={s.config.time_format}
            onChange={(v) => config({ time_format: v })}
            options={["milliseconds", "seconds", "iso8601"]}
          />
        )}
        {s.config.time && s.config.time_format !== "iso8601" && (
          <>
            <Select
              label="Clock"
              value={s.config.time_origin || "unspecified"}
              onChange={(v) => config({ time_origin: v })}
              options={[
                { value: "unspecified", label: "Not specified" },
                { value: "elapsed", label: "Elapsed time" },
                { value: "unix", label: "Unix epoch (UTC)" },
              ]}
            />
            {(s.config.time_origin || "unspecified") === "unspecified" && (
              <small className="warning">
                Choose the clock meaning from your source. Units alone do not
                identify it.
              </small>
            )}
          </>
        )}
        {s.config.time && s.config.time_format === "iso8601" && (
          <small>Absolute time · timezone required · shown in UTC</small>
        )}
        {!!s.numeric.length && (
          <>
            <span className="label">Values to compare</span>
            <div className="feature-list">
              {s.numeric.map((f) => (
                <label key={f}>
                  <input
                    type="checkbox"
                    checked={s.config.features.includes(f)}
                    onChange={(e) =>
                      config({
                        features: e.target.checked
                          ? [...s.config.features, f]
                          : s.config.features.filter((v) => v !== f),
                      })
                    }
                  />
                  {f}
                </label>
              ))}
            </div>
          </>
        )}
        {(s.config.features.length > 0 || s.config.threshold === null) && (
          <label className="control">
            Threshold
            <input
              aria-label="Threshold"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              onBlur={() => {
                if (threshold !== String(s.config.threshold ?? ""))
                  config({ threshold });
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
              }}
            />
          </label>
        )}
        <details
          open={optionsOpen}
          onToggle={(e) => {
            const open = e.currentTarget.open;
            setOptionsOpen(open);
            setupPosition.current.optionsOpen = open;
          }}
        >
          <summary>Options</summary>
          <div className="column">
            {(!!s.config.features.length ||
              !!s.config.reference_by?.length) && (
              <>
                <Select
                  label="Reference group"
                  value={s.config.reference_by?.[0] || ""}
                  options={options}
                  onChange={(v) => config({ reference_by: v ? [v] : [] })}
                />
                {!!s.config.reference_by?.length && (
                  <>
                    <Select
                      label="Also group by"
                      value={s.config.reference_by?.[1] || ""}
                      options={options}
                      onChange={(v) =>
                        config({
                          reference_by: v
                            ? [s.config.reference_by[0], v]
                            : [s.config.reference_by[0]],
                        })
                      }
                    />
                    <small>
                      Compare like categories. Each group needs 20 valid
                      reference values per signal. Missing or small groups use
                      the global profile with an explicit gap.
                    </small>
                  </>
                )}
              </>
            )}
            <div className="actions">
              <Button
                onClick={() => {
                  setRules(s.rules_text);
                  setEditor("rules");
                }}
              >
                Edit rules
              </Button>
              <Button onClick={() => setEditor("context")}>Map context</Button>
            </div>
            <small>
              {s.config.rules.length} rules ·{" "}
              {Object.keys(s.config.context || {}).length} context fields
            </small>
            <div className="actions">
              <Button onClick={() => run("policy_load")}>Load policy</Button>
              <Button disabled={s.blocked} onClick={() => run("policy_save")}>
                Save policy
              </Button>
            </div>
          </div>
        </details>
        <div className="notes">
          {s.notes.map((n, i) => (
            <React.Fragment key={i}>
              {n.level !== "info" &&
                (n.source ? (
                  <Button
                    className={`note ${n.level} ${note === i ? "chosen" : ""}`}
                    onClick={() => follow(i)}
                  >
                    {n.text}
                  </Button>
                ) : (
                  <p className={`note ${n.level}`}>{n.text}</p>
                ))}
            </React.Fragment>
          ))}
        </div>
        {s.config_error && <p className="warning">{s.config_error}</p>}
        <Button
          className="primary"
          disabled={s.blocked}
          onClick={() => run("analyze")}
        >
          Analyze
        </Button>
        <details>
          <summary>Mapping details</summary>
          {s.notes
            .filter((n) => n.level === "info")
            .map((n, i) => (
              <p key={i}>{n.text}</p>
            ))}
        </details>
      </aside>
      <div className="preview column">
        {preview?.note && (
          <div className="pinned warning">
            <span>{preview.note.text}</span>
            <Button
              onClick={() => {
                setNote(null);
                setPage(0);
                setRow(null);
              }}
            >
              Back to preview
            </Button>
          </div>
        )}
        {previewError && <p role="alert">{previewError}</p>}
        {preview && (
          <>
            <div className="source-strip">
              {preview.manifest.name} ·{" "}
              {preview.source === "reference" ? "Reference" : "Data"} · SHA-256{" "}
              {preview.manifest.sha256.slice(0, 12)}…
            </div>
            <PreviewTable
              preview={preview}
              row={row}
              select={setRow}
              height={previewHeight}
            />
            <Pager
              page={preview.page}
              total={preview.total}
              onChange={(n) => {
                setPage(n);
                setRow(null);
              }}
            />
          </>
        )}
        {row && (
          <div
            className="horizontal-divider"
            role="separator"
            tabIndex="0"
            aria-label="Resize preview"
            aria-orientation="horizontal"
            aria-valuenow={previewHeight || 200}
            aria-valuemin="100"
            aria-valuemax="400"
            onPointerDown={(e) =>
              e.currentTarget.setPointerCapture(e.pointerId)
            }
            onPointerMove={(e) => {
              if (e.currentTarget.hasPointerCapture(e.pointerId)) {
                const table =
                  e.currentTarget.parentElement.querySelector(".preview-table");
                const total = e.currentTarget.parentElement.clientHeight;
                setPreviewHeight(
                  Math.max(
                    100,
                    Math.min(
                      total - 370,
                      e.clientY - table.getBoundingClientRect().top,
                    ),
                  ),
                );
              }
            }}
            onPointerUp={(e) =>
              e.currentTarget.releasePointerCapture(e.pointerId)
            }
            onKeyDown={(e) => {
              if (["ArrowUp", "ArrowDown"].includes(e.key)) {
                e.preventDefault();
                setPreviewHeight((v) =>
                  Math.max(
                    100,
                    Math.min(
                      300,
                      (v || 200) + (e.key === "ArrowUp" ? -10 : 10),
                    ),
                  ),
                );
              }
            }}
          />
        )}
        {row && (
          <RecordInspector
            key={`${s.revision}-${note === null ? "current" : s.notes[note].source}-${note}`}
            source={note === null ? "current" : s.notes[note].source}
            row={row}
            note={note}
            visible={active}
            warning={note === null ? null : s.notes[note].text}
            step={step}
          />
        )}
        {!row && (
          <p className="muted">Select a record to inspect full values.</p>
        )}
      </div>
      {editor === "rules" && (
        <Modal label="Edit rules" close={() => setEditor(null)}>
          <p>
            Rules are JSON conditions. Use name, field, op, value, and optional
            priority.
          </p>
          <p className="muted">
            Operators: gt, ge, lt, le, eq, ne. Priorities: Notice, Warning,
            Error, Critical. Equality preserves types.
          </p>
          <textarea
            aria-label="Rules"
            value={rules}
            onChange={(e) => setRules(e.target.value)}
            spellCheck="false"
          />
          <div className="actions">
            <Button
              className="primary"
              onClick={() => config({}, () => setEditor(null), rules)}
            >
              Apply rules
            </Button>
            <Button
              onClick={() =>
                setRules(
                  JSON.stringify(
                    [
                      {
                        name: "",
                        field: s.current.fields[0],
                        op: "eq",
                        value: "",
                        priority: "Notice",
                      },
                    ],
                    null,
                    2,
                  ),
                )
              }
            >
              Example structure
            </Button>
          </div>
        </Modal>
      )}
      {editor === "context" && (
        <ContextDialog
          config={s.config}
          options={options}
          close={() => setEditor(null)}
          apply={(v) => config({ context: v }, () => setEditor(null))}
        />
      )}
    </div>
  );
}
function ContextDialog({ config, options, close, apply }) {
  const [values, setValues] = useState(config.context || {});
  return (
    <Modal label="Map context" close={close}>
      <p>Choose fields already present in your data.</p>
      {["User", "Host", "Process"].map((role) => (
        <Select
          key={role}
          label={role}
          options={options}
          value={values[role]}
          onChange={(v) =>
            setValues((old) => {
              const n = { ...old };
              if (v) n[role] = v;
              else delete n[role];
              return n;
            })
          }
        />
      ))}
      <Button className="primary" onClick={() => apply(values)}>
        Apply context
      </Button>
    </Modal>
  );
}
function Highlight({ text, spans, field, part, matches, active, select }) {
  const chars = Array.from(text),
    elements = [];
  let at = 0;
  for (const [start, end] of spans) {
    elements.push(chars.slice(at, start).join(""));
    const index = matches.find(
      (m) =>
        m.field === field &&
        m.part === part &&
        m.start === start &&
        m.end === end,
    )?.index;
    elements.push(
      <mark
        key={start}
        data-match={index}
        role="button"
        tabIndex={index === active ? 0 : -1}
        aria-label={`Match ${index + 1} in ${field}`}
        aria-pressed={index === active}
        className={index === active ? "current-match" : ""}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            select(index);
          }
        }}
        onClick={() => {
          if (window.getSelection()?.isCollapsed !== false) select(index);
        }}
      >
        {chars.slice(start, end).join("")}
      </mark>,
    );
    at = end;
  }
  elements.push(chars.slice(at).join(""));
  return elements;
}
function RecordInspector({ source, row, note, warning, step, visible }) {
  const { state: s, run } = useContext(Context);
  const [query, setQuery] = useState(""),
    [position, setPosition] = useState({ key: "", index: 0 }),
    [field, setField] = useState("");
  const selectionKey = JSON.stringify([source, row, query]);
  const active = position.key === selectionKey ? position.index : 0;
  const needle = useDebounce(query);
  const [value, error] = useData(
    "inspect",
    {
      revision: s.revision,
      source,
      row,
      note,
      query: needle,
      match: Math.floor(active / 200) * 200,
    },
    visible && needle === query,
  );
  const ready = needle === query && !!value;
  const container = useRef(),
    scrollToMatch = useRef(null);
  useEffect(() => {
    if (value) {
      setField(
        (previous) =>
          value.matches.find((m) => m.index === active)?.field ||
          (value.fields.some((f) => f.field === previous)
            ? previous
            : value.fields[0]?.field || ""),
      );
      if (scrollToMatch.current === active) {
        container.current
          ?.querySelector(`[data-match="${active}"]`)
          ?.scrollIntoView({ block: "nearest" });
        scrollToMatch.current = null;
      }
    }
  }, [value, active]);
  function select(index, scroll = false) {
    scrollToMatch.current = scroll ? index : null;
    setPosition({ key: selectionKey, index });
    const match = value?.matches.find((m) => m.index === index);
    if (match) setField(match.field);
  }
  const current = ready && value?.matches.find((m) => m.index === active);
  function copy(scope) {
    run("copy", { source, row, note, query, field, match: active, scope });
  }
  return (
    <section
      className="record-inspector column"
      aria-label="Full record"
      onKeyDown={(e) => {
        if (e.key === "F3") {
          e.preventDefault();
          const next = active + (e.shiftKey ? -1 : 1);
          if (ready && next >= 0 && next < (value?.match_total || 0))
            select(next, true);
        }
      }}
    >
      <div className="inspector-controls">
        <div className="actions">
          <span>
            Record {row} · {source === "reference" ? "Reference" : "Data"}
          </span>
          <Button disabled={!value?.has_previous} onClick={() => step(-1)}>
            Previous record
          </Button>
          <Button disabled={!value?.has_next} onClick={() => step(1)}>
            Next record
          </Button>
          {value && (
            <small>
              {value.related
                ? "Related record"
                : `${value.position} / ${value.affected} ${note === null ? "records" : "affected"}`}
            </small>
          )}
        </div>
        {warning && <p className="warning">{warning}</p>}
        <div className="actions">
          <label className="search-label">
            Find in record
            <input
              aria-label="Find in record"
              value={query}
              maxLength={4096}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setQuery("");
              }}
            />
          </label>
          <Button onClick={() => setQuery("")}>Clear</Button>
        </div>
        {query && (
          <div className="actions">
            <span>
              {ready
                ? `${value.match_total ? active + 1 : 0} / ${value.match_total} matches · ${value.fields.length} fields`
                : "Searching…"}
            </span>
            <Button
              disabled={!ready || active === 0}
              onClick={() => select(active - 1, true)}
            >
              Previous match
            </Button>
            <Button
              disabled={!ready || active + 1 >= value.match_total}
              onClick={() => select(active + 1, true)}
            >
              Next match
            </Button>
            <Button disabled={!current} onClick={() => copy("match")}>
              Copy match
            </Button>
          </div>
        )}
        {ready && value.match_total > 200 && (
          <small>
            200 nearby matches highlighted. Use Previous match or Next match to
            reach every match.
          </small>
        )}
        <div className="actions">
          <Select
            label="Field"
            value={field}
            options={value?.fields.map((f) => f.field) || []}
            onChange={setField}
          />
          <Button
            disabled={
              !ready || !value?.fields.find((f) => f.field === field)?.present
            }
            onClick={() => copy("value")}
          >
            Copy value
          </Button>
          <Button disabled={!ready} onClick={() => copy("record")}>
            Copy record
          </Button>
        </div>
      </div>
      <div
        className="full-values scroll"
        tabIndex="0"
        role="region"
        aria-label="Field values"
        ref={container}
        aria-busy={visible && !ready && !error}
      >
        {error && <p role="alert">{error}</p>}
        {visible && !ready && !error && (
          <p role="status">Loading record {row}…</p>
        )}
        {ready &&
          value?.fields.map((f) => (
            <div
              key={f.field}
              className={`field-value ${field === f.field ? "chosen-field" : ""}`}
            >
              <div className="field-name">
                <Highlight
                  text={f.field}
                  spans={f.names}
                  field={f.field}
                  part="name"
                  matches={value.matches}
                  active={active}
                  select={select}
                />
              </div>
              <pre>
                <Highlight
                  text={f.value}
                  spans={f.spans}
                  field={f.field}
                  part="value"
                  matches={value.matches}
                  active={active}
                  select={select}
                />
              </pre>
            </div>
          ))}
        {value && !value.fields.length && <p>No fields match this search.</p>}
      </div>
    </section>
  );
}
function Findings({ active }) {
  const { state: s, run, setError } = useContext(Context);
  const [query, setQuery] = useState(""),
    [minimum, setMinimum] = useState("All"),
    [hide, setHide] = useState(true);
  const [page, setPage] = useState(0),
    [row, setRow] = useState(null),
    [reveal, setReveal] = useState(null);
  const needle = useDebounce(query);
  const [data, error] = useData(
    "findings",
    {
      revision: s.revision,
      query: needle,
      minimum,
      hide,
      page,
      reveal,
      locate: reveal,
    },
    active,
  );
  const chartVisible = useRef(false);
  if (data)
    chartVisible.current =
      s.numeric_evidence &&
      (!data.rows.length ||
        !row ||
        row === reveal ||
        data.rows.some((r) => r.row === row && r.numeric_evidence));
  const searchRef = useRef();
  useEffect(() => {
    const handler = (e) => {
      if (active && (e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [active]);
  useEffect(() => {
    setPage(0);
    setReveal(null);
  }, [needle, minimum, hide]);
  useEffect(() => {
    if (data && !data.rows.some((r) => r.row === row))
      setRow(data.rows[0]?.row ?? null);
  }, [data]);
  function choose(n) {
    setReveal(n);
    setRow(n);
  }
  const left = (
    <div className="column full">
      <div className="actions">
        <Button onClick={() => run("save")}>Save case</Button>
        <Button onClick={() => run("alerts", { minimum })}>
          Export alerts
        </Button>
      </div>
      <div className="actions">
        <input
          ref={searchRef}
          className="grow"
          aria-label="Search records"
          placeholder="Record ID, session, user, rule"
          maxLength={4096}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setQuery("");
          }}
        />
        <Button onClick={() => setQuery("")}>Clear</Button>
      </div>
      <div className="actions">
        <Select
          label="Priority"
          value={minimum}
          options={["All", "Notice", "Warning", "Error", "Critical"]}
          onChange={setMinimum}
        />
        <label>
          <input
            type="checkbox"
            checked={hide}
            onChange={(e) => setHide(e.target.checked)}
          />
          Findings only
        </label>
      </div>
      <small>
        {data?.total ?? "…"} shown / {s.summary.total} · {s.summary.Review} need
        review · {s.summary.Unknown} unknown
      </small>
      <small aria-label="Active filters">
        {[
          query ? `Search: ${query}` : null,
          minimum !== "All" ? `Priority: ${minimum}+` : null,
          hide ? "Findings only" : null,
        ]
          .filter(Boolean)
          .join(" · ") || "All records · no filters"}
      </small>
      <small className={data?.hidden_gaps ? "warning" : ""}>
        {data?.hidden_gaps
          ? `${data.hidden_gaps} records with gaps hidden by search. Clear to see them.`
          : "Priority keeps gaps visible."}{" "}
        Exports use priority.
      </small>
      {error && <p role="alert">{error}</p>}
      <div className="scroll grow">
        <table aria-label="Findings">
          <thead>
            <tr>
              <th>Record</th>
              <th>Priority</th>
              <th>Result</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows.map((r, i) => (
              <tr
                key={r.row}
                className={row === r.row ? "selected" : ""}
                tabIndex={row === r.row || (!row && i === 0) ? 0 : -1}
                aria-selected={row === r.row}
                onClick={() => {
                  setReveal(null);
                  setRow(r.row);
                }}
                onKeyDown={(e) =>
                  rowKey(e, data.rows, r.row, (n) => {
                    setReveal(null);
                    setRow(n);
                  })
                }
              >
                <td>{r.row}</td>
                <td
                  className={
                    ["Critical", "Error"].includes(r.priority) ? "danger" : ""
                  }
                >
                  {r.priority || "—"}
                </td>
                <td>{r.status}</td>
                <td>{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && !data.total && (
        <p>
          No records match these filters. This does not establish that the data
          is safe.
        </p>
      )}
      {data && (
        <Pager
          page={data.page}
          total={data.total}
          onChange={(n) => {
            setReveal(null);
            setPage(n);
          }}
        />
      )}
      {chartVisible.current && (
        <Chart
          row={row}
          select={choose}
          outside={row === reveal && data?.outside}
          active={active}
        />
      )}
      {data?.outside && (
        <Button onClick={() => setReveal(null)}>Return to filters</Button>
      )}
    </div>
  );
  return (
    <Split
      name="surge.findings.split"
      left={left}
      right={
        row ? (
          <Evidence row={row} active={active} />
        ) : (
          <p>Select a record to inspect evidence.</p>
        )
      }
    />
  );
}
function Evidence({ row, active }) {
  const { state: s } = useContext(Context);
  const [data, error] = useData(
    "evidence",
    { revision: s.revision, row },
    active,
  );
  return (
    <div
      className="evidence scroll"
      tabIndex="0"
      role="region"
      aria-label="Record evidence"
      aria-busy={active && !data && !error}
    >
      {active && !data && !error && <p role="status">Loading record {row}…</p>}
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          {!data.groups.length && (
            <p>
              {data.gaps.length
                ? "Cannot fully assess this record."
                : "No configured condition matched."}
            </p>
          )}
          {data.groups.map((g) => (
            <div className="evidence-group" key={g.field}>
              <pre className="observed">
                {g.field}: {g.value}
              </pre>
              {g.lines.map((l, i) => (
                <div key={i}>
                  <p className="condition">{l.text}</p>
                  {l.details && (
                    <details>
                      <summary>Details</summary>
                      <p>{l.details}</p>
                    </details>
                  )}
                </div>
              ))}
            </div>
          ))}
          {data.numeric && (
            <p className="muted">A reference median is not a safe limit.</p>
          )}
          {data.reference_group && (
            <p className="muted">
              Reference group:{" "}
              {data.reference_group.fields
                .map(
                  (f, i) =>
                    `${f} = ${JSON.stringify(data.reference_group.values[i])}`,
                )
                .join(" · ")}
              <br />
              {data.reference_group.mode} ·{" "}
              {data.reference_group.reference_rows} reference records
            </p>
          )}
          {data.gaps.map((g, i) => (
            <p key={i} className="warning">
              Check: {g}
            </p>
          ))}
          <p>
            {data.status} · Priority: {data.priority || "None"}
          </p>
          <pre>
            Record: {row} · ID: {data.event_id}
            {"\n"}Session: {data.session}
            {"\n"}Time: {data.time}
          </pre>
          {data.context.map((c) => (
            <p key={c.role}>
              {c.role}: <code>{c.value}</code> · from {c.field}
            </p>
          ))}
          <p className="muted">
            Source: {data.source.name}
            <br />
            SHA-256: {data.source.sha256.slice(0, 12)}… · source record {row}
          </p>
          {data.reference && (
            <details>
              <summary>Reference</summary>
              <p>{data.reference.name}</p>
              <pre>SHA-256: {data.reference.sha256}</pre>
            </details>
          )}
          <details>
            <summary>Source values</summary>
            <pre>SHA-256: {data.source.sha256}</pre>
            {data.values.map((v) => (
              <div className="field-value" key={v.field}>
                <span className="field-name">{v.field}</span>
                <pre>{v.value}</pre>
              </div>
            ))}
          </details>
        </>
      )}
    </div>
  );
}
function Chart({ row, select, outside, active }) {
  const { state: s, setError } = useContext(Context);
  const host = useRef(),
    [width, setWidth] = useState(0);
  const measured = useRef(width);
  useEffect(() => {
    if (!active) return;
    let timer;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) {
        measured.current = Math.max(
          180,
          Math.min(2400, Math.round(entry.contentRect.width)),
        );
        clearTimeout(timer);
        timer = setTimeout(() => setWidth(measured.current), 120);
      }
    });
    observer.observe(host.current);
    return () => {
      observer.disconnect();
      clearTimeout(timer);
    };
  }, [active]);
  const [data, error] = useData(
    "chart",
    { revision: s.revision, width, row },
    active && width > 0,
  );
  const lastPlot = useRef(null);
  if (data) lastPlot.current = { width, data };
  const plot = data || lastPlot.current?.data;
  const plotWidth = data ? width : lastPlot.current?.width || width || 600;
  async function step(direction) {
    try {
      const v = await request("chart_step", {
        revision: s.revision,
        row: row || 0,
        step: direction,
      });
      if (v.row) select(v.row);
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <div
      ref={host}
      className="chart"
      tabIndex="0"
      role="group"
      aria-label="Numeric chart"
      onKeyDown={(e) => {
        if (["ArrowLeft", "ArrowRight"].includes(e.key)) {
          e.preventDefault();
          step(e.key === "ArrowLeft" ? -1 : 1);
        }
      }}
    >
      <small>Max deviation / threshold · capped at 2×</small>
      <svg
        width="100%"
        height="104"
        viewBox={`0 0 ${plotWidth} 104`}
        aria-label="All records in source order"
      >
        <line
          x1="58"
          x2={plotWidth - 18}
          y1="54"
          y2="54"
          className="threshold"
        />
        <text x="10" y="29">
          2×
        </text>
        <text x="10" y="57">
          1×
        </text>
        <text x="10" y="85">
          0
        </text>
        {plot?.points.map((p) => (
          <g
            key={p.row}
            className={p.score >= plot.threshold ? "peak" : ""}
            onClick={() => select(p.row)}
            data-row={p.row}
          >
            <title>
              Record {p.row} · {p.field} · deviation {p.score} · peak of{" "}
              {p.count}
            </title>
            <line x1={p.x} x2={p.x} y1="82" y2={p.y} />
            <circle cx={p.x} cy={p.y} r="2.5" />
            <line x1={p.x} x2={p.x} y1="82" y2={p.y} className="hit-target" />
          </g>
        ))}
        {data?.selected && (
          <g onClick={() => select(data.selected.row)}>
            <circle
              cx={data.selected.x}
              cy={data.selected.y}
              r="5"
              className="selected-point"
            />
            <circle
              cx={data.selected.x}
              cy={data.selected.y}
              r="6"
              className="selected-hit"
            />
          </g>
        )}
      </svg>
      {error && <p role="alert">{error}</p>}
      <div className="chart-readout">
        {data?.selected ? (
          <>
            Record {data.selected.row}
            {outside ? " · outside filters" : ""} · {data.selected.field}:{" "}
            {data.selected.value}
            <br />
            Deviation: {data.selected.score}
          </>
        ) : (
          "Click a point to inspect its exact value."
        )}
      </div>
      <small>All records in source order · click / ← →</small>
    </div>
  );
}
function Compare({ active }) {
  const { state: s, run } = useContext(Context),
    [refresh, setRefresh] = useState(0),
    [changePage, setChangePage] = useState(0);
  const [row, setRow] = useState(null),
    [changed, setChanged] = useState(false);
  const [kind, setKind] = useState("All"),
    [showRecords, setShowRecords] = useState(false);
  const [data, error] = useData(
    "comparison",
    { revision: s.revision, row, changes_only: changed },
    active,
    `${refresh}:${s.case_file?.sha256 || ""}`,
  );
  const choices = useRef(null);
  if (data) choices.current = data;
  const affected = (choices.current?.changes || []).filter(
    ([, reason]) => kind === "All" || reason.split(", ").includes(kind),
  );
  const pageRecords = affected.slice(changePage * 100, (changePage + 1) * 100);
  function follow(filter) {
    setKind(filter);
    setShowRecords(true);
    setRow(null);
    setChangePage(0);
  }
  return (
    <div className="column full">
      <div className="actions">
        <Button
          onClick={() =>
            run("compare", {}, (v) => {
              choices.current = v;
              setRow(null);
              setKind("All");
              setShowRecords(false);
              setChangePage(0);
              setRefresh((n) => n + 1);
            })
          }
        >
          Choose case
        </Button>
        <Button
          disabled={!choices.current?.sources}
          className={row === null && !showRecords ? "active" : ""}
          onClick={() => {
            setRow(null);
            setShowRecords(false);
          }}
        >
          Settings
        </Button>
        <Select
          label="Changed records"
          value={row ?? ""}
          options={[
            { value: "", label: "Select record" },
            ...pageRecords.map(([r, reason]) => ({
              value: r,
              label: `${r} · ${reason}`,
            })),
          ]}
          disabled={!affected.length}
          onChange={(v) => setRow(v ? Number(v) : null)}
        />
        {row === null && (
          <label>
            <input
              type="checkbox"
              checked={changed}
              onChange={(e) => setChanged(e.target.checked)}
            />
            Changes only
          </label>
        )}
      </div>
      {choices.current?.paired && (
        <div className="actions" aria-label="Comparison changes">
          {[
            ["Result", "outcome"],
            ["Priority", "priority"],
            ["Reasons", "reason"],
          ].map(([filter, label]) => {
            const count = choices.current.counts?.[filter] || 0;
            return (
              <Button
                key={filter}
                disabled={!count}
                className={showRecords && kind === filter ? "active" : ""}
                onClick={() => follow(filter)}
              >
                {count} changed{" "}
                {count === 1
                  ? label
                  : label === "priority"
                    ? "priorities"
                    : label + "s"}
              </Button>
            );
          })}
          <Button
            disabled={!choices.current.changes.length}
            className={showRecords && kind === "All" ? "active" : ""}
            onClick={() => follow("All")}
          >
            {choices.current.changes.length} changed{" "}
            {choices.current.changes.length === 1 ? "record" : "records"}
          </Button>
        </div>
      )}
      {affected.length > 100 && (
        <Pager
          page={changePage}
          total={affected.length}
          onChange={(n) => {
            setChangePage(n);
            setRow(null);
          }}
        />
      )}
      {showRecords && (
        <>
          <small>
            {affected.length} affected{" "}
            {affected.length === 1 ? "record" : "records"} ·{" "}
            {kind === "All" ? "All changes" : kind}
          </small>
          <div className="scroll changed-records">
            <table aria-label="Affected records">
              <thead>
                <tr>
                  <th>Record</th>
                  <th>Changed</th>
                </tr>
              </thead>
              <tbody>
                {pageRecords.map(([n, reason], i) => (
                  <tr
                    key={n}
                    tabIndex={row === n || (!row && i === 0) ? 0 : -1}
                    aria-selected={row === n}
                    className={row === n ? "selected" : ""}
                    onClick={() => setRow(n)}
                    onKeyDown={(e) =>
                      rowKey(
                        e,
                        pageRecords.map(([row]) => ({ row })),
                        n,
                        setRow,
                      )
                    }
                  >
                    <td>{n}</td>
                    <td>{reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="muted" role={error ? "alert" : undefined}>
        {error ||
          (data
            ? data.paired
              ? "Same incoming evidence · select a record to compare its decisions."
              : data.note
            : "Loading comparison…")}
      </p>
      {data?.sources && (
        <div className="comparison-sources">
          {["Current", "Previous"].map((label, i) => (
            <ComparisonSource
              key={label}
              label={label}
              file={i === 0 ? s.case_file : data.cases?.[i]}
              source={data.provenance?.[i]}
              fallback={data.sources[i]}
            />
          ))}
        </div>
      )}
      <div className="scroll grow">
        <table className="comparison" aria-label="Comparison">
          <thead>
            <tr>
              <th>Field</th>
              <th>Current</th>
              <th>Previous</th>
              <th>Change</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows.map((r, i) => (
              <tr key={i} className={r.changed ? "changed" : ""}>
                <td>{r.label}</td>
                <td>{r.current}</td>
                <td>{r.previous}</td>
                <td>{r.changed ? "Changed" : "Same"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
function ComparisonSource({ label, file, source, fallback }) {
  return (
    <div className="comparison-source">
      <p>
        {label} · {file?.name || "Unsaved case"}
        {file?.modified ? " · unsaved changes" : ""}
      </p>
      <small>
        {source
          ? `Data: ${source.data.name} · SHA-256 ${source.data.sha256.slice(0, 12)}…`
          : fallback}
      </small>
      <details>
        <summary>{label} source</summary>
        {file ? (
          <>
            <pre>
              Case: {file.path}
              {"\n"}SHA-256: {file.sha256}
            </pre>
            {file.modified && (
              <p>
                This fingerprint identifies the loaded file before your changes.
              </p>
            )}
          </>
        ) : (
          <p>Case has not been saved.</p>
        )}
        {source && (
          <>
            <pre>
              Data: {source.data.name}
              {"\n"}Path:{" "}
              {source.paths.current ||
                "Embedded in case; original path not stored"}
              {"\n"}SHA-256: {source.data.sha256}
            </pre>
            {source.reference ? (
              <pre>
                Reference: {source.reference.name}
                {"\n"}Path:{" "}
                {source.paths.reference ||
                  "Embedded in case; original path not stored"}
                {"\n"}SHA-256: {source.reference.sha256}
              </pre>
            ) : (
              <p>Reference: None</p>
            )}
          </>
        )}
      </details>
    </div>
  );
}
function Evaluate({ active }) {
  const { state: s, run } = useContext(Context);
  const [outcome, setOutcome] = useState("All"),
    [group, setGroup] = useState(""),
    [page, setPage] = useState(0),
    [row, setRow] = useState(null);
  const [data, error] = useData(
    "evaluation",
    { revision: s.revision, outcome, group, page },
    active,
  );
  const rate = (r) => {
    if (r.value === null) return "Not available";
    const percent = r.value * 100;
    // Do not round a small nonzero miss rate to zero, or imperfect recall to 100%.
    const digits =
      (percent > 0 && percent < 0.1) || (percent > 99.9 && percent < 100)
        ? 2
        : 1;
    return `${percent.toFixed(digits)}% (${r.numerator}/${r.denominator})`;
  };
  function filter(value) {
    setOutcome(value);
    setPage(0);
    setRow(null);
  }
  const selected = data?.rows?.find((r) => r.row === row);
  const left = (
    <div className="column full evaluation">
      <div className="actions">
        <Button onClick={() => run("labels_load")}>Import labels</Button>
        <Button onClick={() => run("labels_template")}>
          Save label template
        </Button>
        <Button disabled={!s.labels} onClick={() => run("evaluation_save")}>
          Save evaluation
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
      {!s.labels && (
        <div className="scroll grow">
          <p>
            Current data is the test source. Reference data sets the numeric
            profile; labels never enter detection.
          </p>
          <p>
            Save a blank template for this source. Ask a reviewer to label
            records from independent evidence, without seeing Surge’s decisions.
            Import their completed JSON file.
          </p>
          <p>
            Use legitimate or target for truth, a short group such as
            “legitimate update”, and a note explaining the label. Leave unknown
            truth as null.
          </p>
          <p>
            Record the author, labeling method, reference/test partition,
            purpose, and whether labels were independent of the detector. Use
            untouched sessions, users, or time periods where appropriate.
          </p>
          <p>
            Keep labels outside the source data and reference. Do not map answer
            fields into rules or numeric signals.
          </p>
          <p>
            Labels and evaluations are separate files. Save the case, labels,
            and evaluation together; reopening a case requires importing its
            labels again.
          </p>
          <small>
            Independent annotation and representative data are needed before
            claiming real detection accuracy.
          </small>
        </div>
      )}
      {data?.available && (
        <>
          <small>
            {data.summary.labeled} / {data.summary.total} labeled ·{" "}
            {data.summary.legitimate} legitimate · {data.summary.targets}{" "}
            targets
          </small>
          <div className="actions" aria-label="Evaluation counts">
            <Button
              className={outcome === "All" ? "active" : ""}
              onClick={() => filter("All")}
            >
              All · {data.summary.total}
            </Button>
            {Object.entries(data.summary.counts).map(([key, count]) => (
              <Button
                key={key}
                className={outcome === key ? "active" : ""}
                onClick={() => filter(key)}
              >
                {key} · {count}
              </Button>
            ))}
          </div>
          <small>Rates · all labeled records, before view filters</small>
          <div className="evaluation-rates">
            <span>
              False positives: {rate(data.summary.rates.false_positive)}
            </span>
            <span>Missed: {rate(data.summary.rates.missed)}</span>
            <span>Precision: {rate(data.summary.rates.precision)}</span>
            <span>Recall: {rate(data.summary.rates.recall)}</span>
          </div>
          <small>
            Missed includes {data.summary.unresolved_targets} unassessable
            targets. Unresolved means legitimate labels with missing evidence.
            Rates use labeled records only.
          </small>
          <div className="actions">
            <Select
              label="Group"
              value={group}
              options={[
                { value: "", label: "All groups" },
                ...data.groups.map((g) => ({ value: g.group, label: g.group })),
              ]}
              onChange={(v) => {
                setGroup(v || "");
                setPage(0);
                setRow(null);
              }}
            />
            <Button
              onClick={() => {
                filter("All");
                setGroup("");
              }}
            >
              Clear filters
            </Button>
          </div>
          <details className="evaluation-details">
            <summary>Groups and provenance</summary>
            <p>
              {data.provenance.purpose} · Independence:{" "}
              {data.provenance.independent_of_detector
                ? "declared by label author"
                : "not declared"}
            </p>
            <pre>
              Author: {data.provenance.author}
              {"\n"}Method: {data.provenance.method}
              {"\n"}Partition: {data.provenance.partition}
            </pre>
            <table aria-label="Label groups">
              <thead>
                <tr>
                  <th>Group</th>
                  <th>False positives</th>
                  <th>Missed</th>
                </tr>
              </thead>
              <tbody>
                {data.groups.map((g) => (
                  <tr key={g.group}>
                    <td>{g.group}</td>
                    <td>{rate(g.rates.false_positive)}</td>
                    <td>{rate(g.rates.missed)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.warnings.map((w) => (
              <p key={w} className="warning">
                {w}
              </p>
            ))}
            <pre>
              Test: {data.source.name}
              {"\n"}SHA-256: {data.source.sha256}
              {"\n"}Reference: {data.reference?.name || "None"}
              {"\n"}SHA-256: {data.reference?.sha256 || "None"}
              {"\n"}Labels: {data.labels.name}
              {"\n"}SHA-256: {data.labels.sha256}
              {"\n"}Settings SHA-256: {data.settings_sha256}
            </pre>
            <p>{data.definitions.rates}</p>
          </details>
          <small className="warning">
            {data.provenance.purpose} labels · independence{" "}
            {data.provenance.independent_of_detector
              ? "declared, not verified"
              : "not declared"}
            . {data.warnings.length} notes in Groups and provenance.
          </small>
          <small>
            {data.total} records · {outcome} · {group || "All groups"}
          </small>
          <div className="scroll grow">
            <table aria-label="Evaluation records">
              <thead>
                <tr>
                  <th>Record</th>
                  <th>Label</th>
                  <th>Result</th>
                  <th>Group</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr
                    key={r.row}
                    tabIndex={row === r.row || (!row && i === 0) ? 0 : -1}
                    aria-selected={row === r.row}
                    className={row === r.row ? "selected" : ""}
                    onClick={() => setRow(r.row)}
                    onKeyDown={(e) => rowKey(e, data.rows, r.row, setRow)}
                  >
                    <td>{r.row}</td>
                    <td>{r.truth || "Unlabeled"}</td>
                    <td>
                      {r.outcome}
                      {r.gaps ? " · gaps" : ""}
                    </td>
                    <td>{r.group || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={data.page}
            total={data.total}
            onChange={(n) => {
              setPage(n);
              setRow(null);
            }}
          />
        </>
      )}
    </div>
  );
  return (
    <Split
      name="surge.evaluation.split"
      left={left}
      right={
        selected ? (
          <div className="column full">
            <div className="evaluation-label">
              <p>
                Record {row} · Label: {selected.truth || "Unlabeled"} ·{" "}
                {selected.outcome}
              </p>
              <p>{selected.note || "No independent label supplied."}</p>
            </div>
            <div className="grow">
              <Evidence row={row} active={active} />
            </div>
          </div>
        ) : (
          <p>
            Select a record to compare its label with the detection evidence.
          </p>
        )
      }
    />
  );
}
function Details({ active }) {
  const { state: s } = useContext(Context),
    [data, error] = useData("details", { revision: s.revision }, active);
  return (
    <div className="details scroll">
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          <p>Data: {data.source.name}</p>
          <pre>SHA-256: {data.source.sha256}</pre>
          <p>Reference: {data.reference?.name || "None"}</p>
          {data.reference && <pre>SHA-256: {data.reference.sha256}</pre>}
          <p>
            {Object.entries(data.summary)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" · ")}
          </p>
          <pre>{data.settings}</pre>
          <pre>{data.profiles}</pre>
          <p>
            Constant references use 1% of the absolute median as scale, with a
            1e-9 minimum.
          </p>
          <p>
            Deviation = distance from the median / scale. The threshold sets
            when to flag it.
          </p>
          <p>
            Imported records are unverified claims. Fingerprints do not prove
            who collected them.
          </p>
          <p>
            Engine: {data.engine}. {data.meaning}
          </p>
        </>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);

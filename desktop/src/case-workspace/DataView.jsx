import React, {
  useState,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useContext,
} from "react";
import { Context, request, useData } from "./context.jsx";
import { Button, rowKey, Select, Pager, Modal } from "./controls.jsx";
import RecordInspector from "./RecordInspector.jsx";

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

export default function DataView({ active }) {
  const {
    state: s,
    run,
    setupPosition,
    mappingUndo,
    showCapture,
    showLibrary,
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
            Import evidence
          </Button>
          <Button onClick={showCapture}>Try Demo</Button>
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

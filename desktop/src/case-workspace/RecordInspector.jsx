import React, { useState, useEffect, useRef, useContext } from "react";
import { Context, useData, useDebounce } from "./context.jsx";
import { Button, Select } from "./controls.jsx";

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

export default function RecordInspector({
  source,
  row,
  note,
  warning,
  step,
  visible,
}) {
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

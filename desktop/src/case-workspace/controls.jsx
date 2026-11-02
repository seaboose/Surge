import React, { useState, useEffect, useRef, useId } from "react";

export const Button = ({ children, ...props }) => (
  <button type="button" {...props}>
    {children}
  </button>
);

export function InfoBubble({ label, children }) {
  const id = useId(),
    panel = useRef();
  useEffect(() => {
    const dismiss = () => {
      if (panel.current?.matches(":popover-open")) panel.current.hidePopover();
    };
    window.addEventListener("resize", dismiss);
    return () => window.removeEventListener("resize", dismiss);
  }, []);
  return (
    <span className="info-bubble">
      <Button
        aria-label={label}
        popoverTarget={id}
        onClick={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          panel.current.style.left = `${Math.max(16, Math.min(box.left, window.innerWidth - 376))}px`;
          const below = box.bottom < window.innerHeight / 2;
          panel.current.style.top = below ? `${box.bottom + 8}px` : "auto";
          panel.current.style.bottom = below
            ? "auto"
            : `${window.innerHeight - box.top + 8}px`;
        }}
      >
        <span aria-hidden="true">i</span>
      </Button>
      <span
        ref={panel}
        id={id}
        popover="auto"
        className="info-panel"
        role="note"
        aria-label={label}
        tabIndex={0}
      >
        {children}
      </span>
    </span>
  );
}

export function ExportOptions({ items }) {
  const host = useRef();
  useEffect(() => {
    const dismiss = (event) => {
      if (host.current?.open && !host.current.contains(event.target))
        host.current.open = false;
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, []);
  return (
    <details
      ref={host}
      className="export-options"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          host.current.open = false;
          host.current.querySelector("summary").focus();
        }
      }}
    >
      <summary>Export…</summary>
      <div>
        {items.map((item) => (
          <div key={item.label}>
            <Button
              disabled={item.disabled}
              onClick={() => {
                host.current.open = false;
                item.run();
              }}
            >
              {item.label}
            </Button>
            <small>{item.description}</small>
          </div>
        ))}
      </div>
    </details>
  );
}

export function rowKey(event, items, row, select) {
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

export function Select({ label, value, onChange, options, ...props }) {
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

export function Pager({ page, total, onChange }) {
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

export function Modal({ children, close, label = "Details" }) {
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

export function Split({ left, right, name }) {
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

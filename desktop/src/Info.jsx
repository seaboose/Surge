import React, {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import "./info.css";

export function Info({ label, children }) {
  const id = useId();
  const trigger = useRef(null);
  const bubble = useRef(null);
  const timer = useRef(null);
  const pinned = useRef(false);
  const [open, setOpen] = useState(false);

  function dismiss() {
    clearTimeout(timer.current);
    pinned.current = false;
    setOpen(false);
  }
  function show() {
    clearTimeout(timer.current);
    setOpen(true);
  }
  function leave() {
    if (!pinned.current) timer.current = setTimeout(dismiss, 160);
  }
  useLayoutEffect(() => {
    if (!open) return;
    function position() {
      const rect = trigger.current.getBoundingClientRect();
      const box = bubble.current;
      if (!trigger.current.getClientRects().length) {
        dismiss();
        return;
      }
      const left = Math.max(
        8,
        Math.min(rect.left - 8, window.innerWidth - box.offsetWidth - 8),
      );
      const top =
        rect.bottom + 6 + box.offsetHeight <= window.innerHeight - 8
          ? rect.bottom + 6
          : Math.max(8, rect.top - box.offsetHeight - 6);
      box.style.left = left + "px";
      box.style.top = top + "px";
    }
    function outside(event) {
      if (
        !trigger.current.contains(event.target) &&
        !bubble.current.contains(event.target)
      )
        dismiss();
    }
    function escape(event) {
      if (event.key === "Escape") dismiss();
    }
    position();
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="surge-info"
        aria-label={`About ${label}`}
        aria-describedby={open ? id : undefined}
        onPointerEnter={(e) => {
          if (e.pointerType !== "touch") show();
        }}
        onPointerLeave={leave}
        onFocus={show}
        onBlur={dismiss}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (pinned.current) dismiss();
          else {
            pinned.current = true;
            show();
          }
        }}
      >
        <span aria-hidden="true">i</span>
      </button>
      {open &&
        createPortal(
          <span
            ref={bubble}
            id={id}
            role="tooltip"
            className="surge-info-bubble"
            onPointerEnter={show}
            onPointerLeave={leave}
          >
            {children}
          </span>,
          document.body,
        )}
    </>
  );
}

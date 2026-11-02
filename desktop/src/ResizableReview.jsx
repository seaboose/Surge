import React, { useRef, useState } from "react";

const DEFAULT = 55;
const clamp = (value) => Math.min(65, Math.max(35, value));

export default function ResizableReview({ replay, evidence }) {
  const container = useRef(null);
  const [ratio, setRatio] = useState(DEFAULT);
  const [dragging, setDragging] = useState(false);
  function move(clientX) {
    const rect = container.current?.getBoundingClientRect();
    if (rect?.width)
      setRatio(clamp(((clientX - rect.left) / rect.width) * 100));
  }
  return (
    <section
      className="survive-split-review"
      aria-label="Replay and evidence layout"
    >
      <div className="survive-layout-tools">
        <small>Replay and selected evidence</small>
        <button onClick={() => setRatio(DEFAULT)}>Reset review layout</button>
      </div>
      <div
        ref={container}
        className="survive-review-grid"
        style={{ "--replay-share": `${ratio}%` }}
      >
        <div className="survive-replay-pane">{replay}</div>
        <div
          className="survive-resize-handle"
          role="separator"
          tabIndex="0"
          aria-label="Resize replay and evidence"
          aria-orientation="vertical"
          aria-valuemin={35}
          aria-valuemax={65}
          aria-valuenow={Math.round(ratio)}
          aria-valuetext={`${Math.round(ratio)} percent replay width`}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            e.currentTarget.setPointerCapture(e.pointerId);
            setDragging(true);
            move(e.clientX);
          }}
          onPointerMove={(e) => {
            if (dragging) move(e.clientX);
          }}
          onPointerUp={(e) => {
            setDragging(false);
            if (e.currentTarget.hasPointerCapture(e.pointerId))
              e.currentTarget.releasePointerCapture(e.pointerId);
          }}
          onPointerCancel={() => setDragging(false)}
          onLostPointerCapture={() => setDragging(false)}
          onDoubleClick={() => setRatio(DEFAULT)}
          onKeyDown={(e) => {
            const changes = { ArrowLeft: -2, ArrowRight: 2 };
            if (e.key in changes) {
              e.preventDefault();
              setRatio((v) => clamp(v + changes[e.key]));
            } else if (e.key === "Home" || e.key === "End") {
              e.preventDefault();
              setRatio(e.key === "Home" ? 35 : 65);
            }
          }}
        >
          <span aria-hidden="true">⋮</span>
        </div>
        <div className="survive-evidence-pane">{evidence}</div>
      </div>
    </section>
  );
}

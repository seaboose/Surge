import React, { useId, useRef } from "react";
import { Button } from "./controls.jsx";
import Settings from "./Settings.jsx";

// Native light-dismiss, with explicit keyboard entry/return for the navigation.
export default function Instruments({ children, settings }) {
  const id = useId();
  const panel = useRef();
  const trigger = useRef();
  return (
    <div className="instrument-access">
      <Button ref={trigger} popoverTarget={id} className="instrument-trigger">
        Tools
      </Button>
      <nav
        id={id}
        ref={panel}
        popover="auto"
        aria-label="Views"
        className="instrument-menu"
        onToggle={(event) => {
          if (event.newState === "open")
            panel.current.querySelector("button:not(:disabled)")?.focus();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            panel.current.hidePopover();
            trigger.current.focus();
          }
        }}
        onClick={(event) => {
          if (event.target.closest("button:not(:disabled)")) {
            panel.current.hidePopover();
            trigger.current.focus();
          }
        }}
      >
        {children}
      </nav>
      {settings && <Settings {...settings} />}
    </div>
  );
}

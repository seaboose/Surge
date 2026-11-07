import React, { useId, useRef } from "react";
import { Button } from "./controls.jsx";
import "./settings.css";

export default function Settings({
  preferences,
  reducedMotion,
  error,
  update,
}) {
  const id = useId();
  const panel = useRef();
  const trigger = useRef();
  const close = () => {
    panel.current.hidePopover();
    trigger.current.focus();
  };
  return (
    <>
      <Button
        ref={trigger}
        className="settings-trigger"
        popoverTarget={id}
        aria-label="Settings"
        title="Settings"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="m9.5 3-.6 2.2-2 .9-2-.7-2.4 4.1 1.7 1.5v2l-1.7 1.5 2.4 4.1 2-.7 2 .9.6 2.2h5l.6-2.2 2-.9 2 .7 2.4-4.1-1.7-1.5v-2l1.7-1.5-2.4-4.1-2 .7-2-.9-.6-2.2z" />
          <circle cx="12" cy="12" r="3.2" />
        </svg>
      </Button>
      <section
        id={id}
        ref={panel}
        popover="auto"
        className="settings-panel"
        role="dialog"
        aria-label="Settings"
        onToggle={(event) => {
          if (event.newState === "open")
            panel.current.querySelector('[role="switch"]')?.focus();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            close();
          }
        }}
      >
        <div className="settings-heading">
          <h2>Settings</h2>
          <Button onClick={close} aria-label="Close settings">
            ×
          </Button>
        </div>
        <div className="settings-row">
          <div>
            <span id={`${id}-motion`}>Reduce motion</span>
            <p id={`${id}-motion-help`}>Keep the interface still.</p>
          </div>
          <Button
            role="switch"
            aria-labelledby={`${id}-motion`}
            aria-describedby={`${id}-motion-help`}
            aria-checked={reducedMotion}
            className="preference-switch"
            onClick={() => update({ reduceMotion: !reducedMotion })}
          >
            <span className="switch-track" aria-hidden="true">
              <i />
            </span>
            <span aria-hidden="true">{reducedMotion ? "On" : "Off"}</span>
          </Button>
        </div>
        <Button
          className="system-motion"
          disabled={preferences.reduceMotion === null}
          onClick={() => update({ reduceMotion: null })}
        >
          {preferences.reduceMotion === null
            ? "Following system setting"
            : "Use system setting"}
        </Button>
        <div className="settings-row startup-preference">
          <div>
            <span id={`${id}-startup`}>Open latest case on startup</span>
            <p id={`${id}-startup-help`}>
              Skip Home and open your newest saved case.
            </p>
          </div>
          <Button
            role="switch"
            aria-labelledby={`${id}-startup`}
            aria-describedby={`${id}-startup-help`}
            aria-checked={preferences.openLatestCase}
            className="preference-switch"
            onClick={() =>
              update({ openLatestCase: !preferences.openLatestCase })
            }
          >
            <span className="switch-track" aria-hidden="true">
              <i />
            </span>
            <span aria-hidden="true">
              {preferences.openLatestCase ? "On" : "Off"}
            </span>
          </Button>
        </div>
        <p className="settings-note">
          If no recent case is available, show Home.
        </p>
        {error && (
          <p role="alert" className="settings-error">
            {error}
          </p>
        )}
      </section>
    </>
  );
}

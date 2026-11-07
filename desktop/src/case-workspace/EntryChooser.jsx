import React from "react";
import { Button } from "./controls.jsx";

export default function EntryChooser({ kind, onNative, onSurvive, working }) {
  const demo = kind === "demo";
  const choices = demo
    ? [
        {
          label: "Survive",
          description: "Gameplay detection in a controlled game.",
          action: onSurvive,
          className: "entry-gameplay",
        },
        {
          label: "Code integrity",
          description: "Capture the approved baseline and inspect its limits.",
          action: onNative,
          className: "entry-native",
        },
      ]
    : [
        {
          label: "Owned process",
          description:
            "Collect code-integrity observations from Surge’s controlled process.",
          action: onNative,
          className: "entry-native",
        },
        {
          label: "Survive telemetry",
          description: "Record a session in the controlled game.",
          action: onSurvive,
          className: "entry-gameplay",
        },
      ];
  return (
    <section
      className="entry-chooser"
      aria-label={demo ? "Demo choices" : "Capture sources"}
    >
      <p className="entry-chooser-intro">
        {demo
          ? "Explore what Surge detects, and where its limits begin."
          : "Choose a supported source."}
      </p>
      <div className="entry-choices">
        {choices.map(({ label, description, action, className }) => (
          <Button
            key={label}
            className={`entry-choice ${className}`}
            aria-label={label}
            disabled={working}
            onClick={action}
          >
            <span>
              <strong>{label}</strong>
              <small>{description}</small>
            </span>
            <span className="entry-choice-arrow" aria-hidden="true">
              →
            </span>
          </Button>
        ))}
      </div>
      <p className="entry-chooser-note">
        {demo
          ? "Capture → inspect evidence → save a case"
          : "Current sources are controlled environments owned by Surge."}
      </p>
    </section>
  );
}

import React, { useId } from "react";
import { Info } from "../Info.jsx";
import { SECTIONS } from "./investigation-model.mjs";

const tabLabels = {
  question: "Question",
  observations: "Observations",
  hypothesis: "Alternatives",
  conclusion: "Conclusion",
  next_steps: "Next steps",
};

const sectionHelp = {
  question: "State the question this recording can help answer.",
  observations:
    "Describe what you saw or measured. Cite an attached item with its reference, such as [E1].",
  hypothesis:
    "Give plausible explanations and note which evidence supports or weakens each one.",
  conclusion:
    "Answer the question and state what the recording leaves uncertain, including gaps in coverage.",
  next_steps:
    "Describe the next check or recording that would resolve an open question.",
};

export function ReportField({ label, help, children }) {
  const id = useId();
  return (
    <div className="investigation-field">
      <div className="report-heading">
        <label htmlFor={id}>{label}</label>
        <Info label={label}>{help}</Info>
      </div>
      {React.cloneElement(children, { id })}
    </div>
  );
}

export function NarrativeEditor({
  sections,
  section,
  disabled,
  onSectionChange,
  onChange,
}) {
  return (
    <>
      <div
        role="tablist"
        aria-label="Report sections"
        className="investigation-section-tabs"
      >
        {SECTIONS.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            id={`report-tab-${key}`}
            aria-selected={section === key}
            aria-controls={`report-section-${key}`}
            tabIndex={section === key ? 0 : -1}
            onClick={() => onSectionChange(key)}
            onKeyDown={(event) => {
              const index = SECTIONS.findIndex(([id]) => id === key);
              const next =
                event.key === "ArrowRight"
                  ? (index + 1) % SECTIONS.length
                  : event.key === "ArrowLeft"
                    ? (index + SECTIONS.length - 1) % SECTIONS.length
                    : event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? SECTIONS.length - 1
                        : null;
              if (next === null) return;
              event.preventDefault();
              onSectionChange(SECTIONS[next][0]);
              event.currentTarget.parentElement
                .querySelectorAll('[role="tab"]')
                [next]?.focus();
            }}
          >
            {tabLabels[key]}
          </button>
        ))}
      </div>
      {SECTIONS.map(([key, label]) => (
        <div
          key={key}
          role="tabpanel"
          id={`report-section-${key}`}
          aria-labelledby={`report-tab-${key}`}
          hidden={section !== key}
        >
          <ReportField label={label} help={sectionHelp[key]}>
            <textarea
              aria-label={label}
              value={sections[key]}
              maxLength={4000}
              rows={7}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...sections,
                  [key]: e.target.value,
                })
              }
            />
          </ReportField>
          <small>
            {sections[key].length.toLocaleString()} / 4,000 characters
          </small>
        </div>
      ))}
    </>
  );
}

export function RevisionControls({
  form,
  busy,
  dirty,
  onChange,
  onSave,
  onDiscard,
}) {
  return (
    <div className="investigation-save-block">
      <div className="investigation-save-fields">
        <ReportField
          label="Revision reason"
          help="Briefly describe what changed so another reviewer can follow the revision history."
        >
          <textarea
            aria-label="Revision reason"
            value={form.change_reason}
            maxLength={500}
            rows={2}
            disabled={busy}
            onChange={(e) => onChange("change_reason", e.target.value)}
          />
        </ReportField>
        <ReportField
          label="Review status"
          help="Keep work in Draft, or mark it Reviewed to record your assessment. Save the revision to apply this choice."
        >
          <select
            aria-label="Investigation review status"
            value={form.status}
            disabled={busy}
            onChange={(e) => onChange("status", e.target.value)}
          >
            <option value="draft">Draft</option>
            <option value="reviewed">Reviewed by named analyst</option>
          </select>
        </ReportField>
      </div>
      <div className="survive-controls">
        <button
          className="primary"
          disabled={
            busy ||
            !dirty ||
            !form.title.trim() ||
            !form.author.trim() ||
            !form.change_reason.trim()
          }
          onClick={onSave}
        >
          Save revision
        </button>
        <button disabled={busy || !dirty} onClick={onDiscard}>
          Discard unsaved edits
        </button>
      </div>
    </div>
  );
}

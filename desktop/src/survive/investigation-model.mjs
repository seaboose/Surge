export const SECTIONS = [
  ["question", "Investigation question"],
  ["observations", "Observations"],
  ["hypothesis", "Hypotheses and alternatives"],
  ["conclusion", "Conclusion and limitations"],
  ["next_steps", "Next steps"],
];
const emptySections = () =>
  Object.fromEntries(SECTIONS.map(([key]) => [key, ""]));
export const editableInvestigation = (document) => ({
  title: document.title,
  author: document.author,
  status: document.status,
  change_reason: "",
  sections: { ...emptySections(), ...document.sections },
});
export const formatEvidenceNumber = (value, digits = 3) =>
  Number.isFinite(value) ? value.toFixed(digits) : "Unavailable";
export function reportReadiness({
  document,
  form,
  evidence,
  verification,
  dirty,
}) {
  const attachedIds = new Set(evidence.map((item) => item.evidence_id));
  const citedIds = new Set(
    (
      Object.values(form?.sections || {})
        .join("\n")
        .match(/\[E[1-9][0-9]*\]/g) || []
    ).map((reference) => reference.slice(1, -1)),
  );
  const unresolvedCitations = [...citedIds].filter(
    (id) => !attachedIds.has(id),
  );
  const uncitedEvidence = [...attachedIds].filter((id) => !citedIds.has(id));
  const sourcesVerified =
    evidence.length > 0 &&
    evidence.every((item) =>
      verification?.items?.some(
        (check) =>
          check.evidence_id === item.evidence_id && check.state === "verified",
      ),
    );
  const readiness = [
    {
      label: "Saved revision",
      pass: !dirty,
      detail: dirty
        ? "Save your edits before exporting."
        : `Revision ${document?.revision || "—"} is saved.`,
    },
    {
      label: "Evidence sources",
      pass: sourcesVerified,
      detail: !evidence.length
        ? "Attach the measured evidence behind your findings."
        : sourcesVerified
          ? "All attached sources matched their saved fingerprints at the last check."
          : "Some sources are missing, changed or unavailable. Their original snapshots remain in the report.",
    },
    {
      label: "Evidence citations",
      pass:
        evidence.length > 0 &&
        !uncitedEvidence.length &&
        !unresolvedCitations.length,
      detail: unresolvedCitations.length
        ? `Unknown references: ${unresolvedCitations.join(", ")}. Attach the evidence or correct the text.`
        : uncitedEvidence.length
          ? `Not yet cited in the narrative: ${uncitedEvidence.join(", ")}.`
          : evidence.length
            ? "Every attached evidence item is cited in the narrative."
            : "Use references such as [E1] after attaching evidence.",
    },
    {
      label: "Question and conclusion",
      pass: Boolean(
        form?.sections.question.trim() && form?.sections.conclusion.trim(),
      ),
      detail:
        form?.sections.question.trim() && form?.sections.conclusion.trim()
          ? "The report states its question and conclusion."
          : "State the investigation question, conclusion and its limits.",
    },
    {
      label: "Analyst review",
      pass: form?.status === "reviewed",
      detail:
        form?.status === "reviewed"
          ? "Marked Reviewed by the named analyst; this is not a detector verdict."
          : "Draft reports can be exported for further review.",
    },
  ];
  const ready = readiness.every((item) => item.pass);
  return { readiness, ready, unresolvedCitations };
}

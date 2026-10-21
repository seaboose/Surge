"use strict";
const operations = Object.freeze({
  state: [],
  import: ["role"],
  open: [],
  configure: ["revision", "config", "rules_text"],
  analyze: ["revision"],
  policy_load: ["revision"],
  policy_save: ["revision"],
  labels_load: ["revision"],
  labels_template: ["revision"],
  evaluation_save: ["revision"],
  evaluation: ["revision", "outcome", "group", "page"],
  preview: ["revision", "page", "note"],
  inspect: ["revision", "source", "row", "query", "note", "match"],
  record_step: ["revision", "row", "note", "step"],
  copy: [
    "revision",
    "source",
    "row",
    "query",
    "note",
    "scope",
    "field",
    "match",
  ],
  findings: [
    "revision",
    "query",
    "minimum",
    "hide",
    "page",
    "reveal",
    "locate",
  ],
  evidence: ["revision", "row"],
  chart: ["revision", "width", "row"],
  chart_step: ["revision", "row", "step"],
  details: ["revision"],
  save: ["revision"],
  alerts: ["revision", "minimum"],
  compare: ["revision"],
  comparison: ["revision", "row", "changes_only"],
});
function validate(method, args) {
  if (
    !Object.hasOwn(operations, method) ||
    !args ||
    typeof args !== "object" ||
    Array.isArray(args)
  )
    throw new Error("Unsupported desktop request.");
  if (Object.keys(args).some((k) => !operations[method].includes(k)))
    throw new Error("Unexpected request field.");
  if (Buffer.byteLength(JSON.stringify(args), "utf8") > 300 * 1024)
    throw new Error("Request exceeds the desktop limit.");
  if (
    method !== "state" &&
    method !== "import" &&
    method !== "open" &&
    !Number.isSafeInteger(args.revision)
  )
    throw new Error("Missing workspace revision.");
  return args;
}
module.exports = { validate, operations };

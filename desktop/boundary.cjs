"use strict";
const operations = Object.freeze({
  state: [],
  native_start: ["build"],
  native_status: [],
  native_snapshot: [],
  native_stop: [],
  native_export: [],
  import: ["role"],
  open: [],
  library_list: [],
  library_save: ["revision", "name"],
  library_open: ["id"],
  library_rename: ["id", "name"],
  library_delete: ["id"],
  library_import: [],
  library_export: ["id"],
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
  if (method === "native_start" && !["v1", "v2"].includes(args.build))
    throw new Error("Choose an available app build.");
  if (
    [
      "library_open",
      "library_rename",
      "library_delete",
      "library_export",
    ].includes(method) &&
    (typeof args.id !== "string" ||
      !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(args.id))
  )
    throw new Error("Invalid case identifier.");
  if (["library_save", "library_rename"].includes(method))
    require("./case-library.cjs").caseName(args.name);
  if (
    method !== "state" &&
    method !== "import" &&
    method !== "open" &&
    !method.startsWith("native_") &&
    !(method.startsWith("library_") && method !== "library_save") &&
    !Number.isSafeInteger(args.revision)
  )
    throw new Error("Missing workspace revision.");
  return args;
}
module.exports = { validate, operations };

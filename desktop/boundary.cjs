"use strict";
const operations = Object.freeze({
  state: [],
  native_start: ["build"],
  native_status: [],
  native_snapshot: [],
  native_stop: [],
  native_export: [],
  survive_sources: [],
  survive_start: ["source_id", "profile_id"],
  survive_status: ["after"],
  survive_stop: [],
  survive_sessions: [],
  survive_open: ["recording_id"],
  survive_record: ["recording_id", "seq"],
  survive_trials: [],
  survive_trial_start: ["mode", "seed", "profile_id", "participant", "phase"],
  survive_report: [],
  survive_study_freeze: [],
  survive_adjudicate: ["trial_id", "expected_mechanical_violation", "note"],
  survive_investigations: [],
  survive_investigation_create: ["title", "author"],
  survive_investigation_open: ["investigation_id", "revision"],
  survive_investigation_save: [
    "investigation_id",
    "expected_revision",
    "title",
    "author",
    "change_reason",
    "status",
    "sections",
  ],
  survive_investigation_attach: [
    "investigation_id",
    "expected_revision",
    "recording_id",
    "seq",
    "constraint_id",
    "author",
    "change_reason",
  ],
  survive_investigation_resolve: [
    "investigation_id",
    "evidence_id",
    "revision",
  ],
  survive_investigation_export: ["investigation_id", "revision"],
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
  if (method.startsWith("survive_")) {
    const required = method === "survive_status" ? [] : operations[method];
    if (required.some((key) => !Object.hasOwn(args, key)))
      throw new Error("Missing Survive setting.");
    const profiles = [
      "survive-lucian-practice-v1",
      "survive-lucian-reference-v1",
    ];
    if (
      Object.hasOwn(args, "profile_id") &&
      !profiles.includes(args.profile_id)
    )
      throw new Error("Select a reviewed Survive profile.");
    const identifier = (value) =>
      typeof value === "string" && /^[a-fA-F0-9]{32}$/.test(value);
    if (
      Object.hasOwn(args, "source_id") &&
      args.source_id !== "next" &&
      !identifier(args.source_id)
    )
      throw new Error("Invalid Survive source identifier.");
    for (const key of ["recording_id", "trial_id", "investigation_id"])
      if (
        Object.hasOwn(args, key) &&
        (typeof args[key] !== "string" || !/^[a-f0-9]{32}$/.test(args[key]))
      )
        throw new Error("Invalid Survive identifier.");
    if (
      Object.hasOwn(args, "after") &&
      (!Number.isSafeInteger(args.after) ||
        args.after < 0 ||
        args.after > 10000)
    )
      throw new Error("Invalid recording cursor.");
    if (
      Object.hasOwn(args, "seq") &&
      (!Number.isSafeInteger(args.seq) || args.seq < 0 || args.seq >= 10000)
    )
      throw new Error("Invalid record sequence.");
    if (method.startsWith("survive_investigation")) {
      const readable = (value, limit, multiline = false) =>
        typeof value === "string" &&
        value.length <= limit &&
        !(multiline ? /[\x00-\x08\x0b-\x1f]/ : /[\x00-\x1f]/).test(value) &&
        value.isWellFormed();
      for (const [key, limit] of [
        ["title", 120],
        ["author", 80],
        ["change_reason", 500],
      ])
        if (
          Object.hasOwn(args, key) &&
          (!readable(args[key], limit) || !args[key].trim())
        )
          throw new Error(`Invalid investigation ${key}.`);
      for (const key of ["revision", "expected_revision"])
        if (
          Object.hasOwn(args, key) &&
          !(key === "revision" && args[key] === null) &&
          (!Number.isSafeInteger(args[key]) || args[key] < 1 || args[key] > 256)
        )
          throw new Error("Invalid investigation revision.");
      if (
        Object.hasOwn(args, "status") &&
        !["draft", "reviewed"].includes(args.status)
      )
        throw new Error("Choose draft or reviewed.");
      if (
        Object.hasOwn(args, "evidence_id") &&
        (typeof args.evidence_id !== "string" ||
          !/^E(?:[1-9]|[12][0-9]|3[0-2])$/.test(args.evidence_id))
      )
        throw new Error("Invalid evidence reference.");
      if (
        Object.hasOwn(args, "constraint_id") &&
        args.constraint_id !== null &&
        (typeof args.constraint_id !== "string" ||
          !/^[A-Za-z0-9_:.-]{1,160}$/.test(args.constraint_id))
      )
        throw new Error("Invalid constraint reference.");
      if (Object.hasOwn(args, "sections")) {
        const keys = [
          "question",
          "observations",
          "hypothesis",
          "conclusion",
          "next_steps",
        ];
        if (
          !args.sections ||
          typeof args.sections !== "object" ||
          Array.isArray(args.sections) ||
          Object.keys(args.sections).length !== keys.length ||
          keys.some(
            (k) =>
              !Object.hasOwn(args.sections, k) ||
              !readable(args.sections[k], 4000, true),
          )
        )
          throw new Error(
            "Use the five supported sections, at most 4000 readable characters each.",
          );
      }
    }
    if (
      Object.hasOwn(args, "mode") &&
      !["human", "scripted", "mixed", "speed_probe"].includes(args.mode)
    )
      throw new Error("Choose a supported study mode.");
    if (
      Object.hasOwn(args, "phase") &&
      !["practice", "development", "held-out"].includes(args.phase)
    )
      throw new Error("Choose a supported study phase.");
    if (
      Object.hasOwn(args, "seed") &&
      (!Number.isSafeInteger(args.seed) ||
        args.seed < 0 ||
        args.seed > 2147483647)
    )
      throw new Error("Seed must be a nonnegative 32-bit integer.");
    if (
      Object.hasOwn(args, "participant") &&
      (typeof args.participant !== "string" ||
        !/^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/.test(args.participant))
    )
      throw new Error(
        "Use a short participant alias with letters, numbers, _ or -.",
      );
    if (
      Object.hasOwn(args, "expected_mechanical_violation") &&
      !["yes", "no", "unknown"].includes(args.expected_mechanical_violation)
    )
      throw new Error(
        "Choose yes, no or unknown for the independent assessment.",
      );
    if (
      Object.hasOwn(args, "note") &&
      (typeof args.note !== "string" ||
        args.note.length > 500 ||
        /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(args.note))
    )
      throw new Error(
        "Assessment note must be at most500 readable characters.",
      );
  }
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
    !method.startsWith("survive_") &&
    !(method.startsWith("library_") && method !== "library_save") &&
    !Number.isSafeInteger(args.revision)
  )
    throw new Error("Missing workspace revision.");
  return args;
}
module.exports = { validate, operations };

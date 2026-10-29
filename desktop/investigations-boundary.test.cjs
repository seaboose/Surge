const { test } = require("node:test");
const assert = require("node:assert/strict");
const { validate } = require("./boundary.cjs");
const id = "a".repeat(32);
const sections = {
  question: "What happened?",
  observations: "",
  hypothesis: "",
  conclusion: "",
  next_steps: "",
};
const requests = {
  survive_investigations: {},
  survive_investigation_create: { title: "Example", author: "Reviewer" },
  survive_investigation_open: { investigation_id: id, revision: null },
  survive_investigation_save: {
    investigation_id: id,
    expected_revision: 1,
    title: "Example",
    author: "Reviewer",
    change_reason: "Explain observation",
    status: "draft",
    sections,
  },
  survive_investigation_attach: {
    investigation_id: id,
    expected_revision: 1,
    recording_id: id,
    seq: 300,
    constraint_id: "300:walking_displacement",
    author: "Reviewer",
    change_reason: "Attach measured interval",
  },
  survive_investigation_resolve: {
    investigation_id: id,
    evidence_id: "E1",
    revision: 2,
  },
  survive_investigation_export: { investigation_id: id, revision: 2 },
};

test("investigation requests cannot supply paths, evidence facts, or executable report content", () => {
  for (const [method, args] of Object.entries(requests)) {
    assert.doesNotThrow(() => validate(method, args));
    for (const key of [
      "path",
      "html",
      "raw_record",
      "constraint",
      "source_sha256",
      "policy",
      "command",
      "pid",
    ])
      assert.throws(() => validate(method, { ...args, [key]: "untrusted" }));
    for (const key of Object.keys(args)) {
      const missing = { ...args };
      delete missing[key];
      assert.throws(() => validate(method, missing));
    }
  }
});

test("investigation input and revision bounds reject malformed or oversized payloads", () => {
  const save = requests.survive_investigation_save;
  for (const [key, values] of Object.entries({
    investigation_id: ["../file", "A".repeat(32)],
    expected_revision: [true, 0, 257, null],
    title: ["", "x".repeat(121), "bad\nname", "\ud800"],
    author: [" ", {}, "x".repeat(81)],
    change_reason: ["", "x".repeat(501)],
    status: ["approved", "clean", {}],
    sections: [
      [],
      { ...sections, extra: "" },
      { ...sections, conclusion: "x".repeat(4001) },
      { ...sections, question: "\0" },
    ],
  }))
    for (const value of values)
      assert.throws(
        () => validate("survive_investigation_save", { ...save, [key]: value }),
        key,
      );
  for (const evidence_id of ["E0", "E33", "E01", "../../file", null])
    assert.throws(() =>
      validate("survive_investigation_resolve", {
        ...requests.survive_investigation_resolve,
        evidence_id,
      }),
    );
  assert.throws(() =>
    validate("survive_investigation_attach", {
      ...requests.survive_investigation_attach,
      seq: 10000,
    }),
  );
  assert.doesNotThrow(() =>
    validate("survive_investigation_attach", {
      ...requests.survive_investigation_attach,
      constraint_id: null,
    }),
  );
  // Analyst text is data, rendered escaped by the editor/report rather than executed.
  assert.doesNotThrow(() =>
    validate("survive_investigation_save", {
      ...save,
      sections: {
        ...sections,
        observations: "<script>alert(1)</script>\n[E1]",
      },
    }),
  );
});

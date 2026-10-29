const { test } = require("node:test");
const assert = require("node:assert/strict");
const { validate, operations } = require("./boundary.cjs");
test("Survive renderer can select only bounded owned sources and study choices", () => {
  const trial = {
    mode: "human",
    seed: 1337,
    profile_id: "survive-lucian-practice-v1",
    participant: "player",
    phase: "development",
  };
  assert.doesNotThrow(() => validate("survive_trial_start", trial));
  assert.doesNotThrow(() =>
    validate("survive_start", {
      source_id: "next",
      profile_id: trial.profile_id,
    }),
  );
  assert.doesNotThrow(() =>
    validate("survive_open", { recording_id: "a".repeat(32) }),
  );
  for (const [key, value] of [
    ["seed", -1],
    ["seed", true],
    ["seed", 2 ** 31],
    ["mode", "external"],
    ["participant", "../player"],
    ["participant", "a".repeat(41)],
    ["profile_id", "custom"],
    ["phase", "test"],
  ])
    assert.throws(() =>
      validate("survive_trial_start", { ...trial, [key]: value }),
    );
  for (const source_id of ["../data", "C:\\private", "a".repeat(33), null, 1])
    assert.throws(() =>
      validate("survive_start", { source_id, profile_id: trial.profile_id }),
    );
  for (const method of Object.keys(operations).filter((x) =>
    x.startsWith("survive_"),
  ))
    for (const key of [
      "path",
      "executable",
      "command",
      "pid",
      "truth",
      "policy",
    ])
      assert.throws(() => validate(method, { [key]: "injected" }));
});
test("Survive controls reject missing fields, unbounded cursors and label payloads", () => {
  assert.throws(() => validate("survive_trial_start", {}));
  assert.throws(() => validate("survive_status", { after: 10001 }));
  assert.throws(() => validate("survive_status", { after: true }));
  assert.throws(() =>
    validate("survive_adjudicate", {
      trial_id: "a".repeat(32),
      expected_mechanical_violation: "no",
      note: "x".repeat(501),
    }),
  );
  assert.doesNotThrow(() =>
    validate("survive_adjudicate", {
      trial_id: "a".repeat(32),
      expected_mechanical_violation: "unknown",
      note: "Needs review",
    }),
  );
});

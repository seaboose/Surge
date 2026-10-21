const { test } = require("node:test");
const assert = require("node:assert/strict");
const { validate, operations } = require("./boundary.cjs");
test("renderer cannot choose paths or arbitrary operations", () => {
  for (const method of Object.keys(operations)) {
    assert.throws(() => validate(method, { revision: 1, path: "C:\\secret" }));
  }
  for (const name of [
    "exec",
    "spawn",
    "readFile",
    "__proto__",
    "constructor",
    "toString",
  ])
    assert.throws(() => validate(name, {}));
});
test("requests are bounded, revisioned and object-shaped", () => {
  assert.throws(() => validate("inspect", null));
  assert.throws(() => validate("inspect", []));
  assert.throws(() => validate("inspect", { row: 1 }));
  assert.throws(() =>
    validate("inspect", { revision: 1, query: "x".repeat(400000) }),
  );
  assert.doesNotThrow(() =>
    validate("inspect", {
      revision: 1,
      row: 2,
      source: "current",
      query: "Straße",
    }),
  );
  assert.doesNotThrow(() => validate("import", { role: "current" }));
});

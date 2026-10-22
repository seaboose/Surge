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
test("collection can only start a fixed owned build", () => {
  for (const build of ["v1", "v2"])
    assert.doesNotThrow(() => validate("native_start", { build }));
  for (const build of [undefined, null, "external", "../v1", "v1 --pid 1", 1])
    assert.throws(() => validate("native_start", { build }));
  for (const args of [
    { build: "v1", pid: 12 },
    { build: "v1", scenario: "memory-change" },
    { build: "v1", executable: "another.exe" },
    { build: "v1", interval_ms: 0 },
  ])
    assert.throws(() => validate("native_start", args));
  for (const method of [
    "native_status",
    "native_snapshot",
    "native_stop",
    "native_export",
  ]) {
    assert.doesNotThrow(() => validate(method, {}));
    assert.throws(() => validate(method, { build: "v2" }));
    assert.throws(() => validate(method, { revision: 1 }));
  }
});

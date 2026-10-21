const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pythonPath } = require("./runtime.cjs");

test("runtime resolves a relocated environment and explicit override without a shell", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "surge runtime "));
  try {
    const local = path.join(root, ".venv", "Scripts", "python.exe");
    fs.mkdirSync(path.dirname(local), { recursive: true });
    fs.writeFileSync(local, "fixture");
    assert.equal(pythonPath(root, {}, "win32"), local);
    const override = path.join(root, "custom python.exe");
    fs.writeFileSync(override, "fixture");
    assert.equal(
      pythonPath(root, { SURGE_PYTHON: override }, "win32"),
      override,
    );
    assert.throws(() =>
      pythonPath(root, { SURGE_PYTHON: "relative.exe" }, "win32"),
    );
    assert.throws(() => pythonPath(root, { SURGE_PYTHON: root }, "win32"));
    assert.throws(
      () => pythonPath(path.join(root, "missing"), {}, "win32"),
      /Setup-Surge/,
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

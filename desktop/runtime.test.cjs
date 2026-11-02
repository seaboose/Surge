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

test("packaged runtime ignores overrides and never falls back to a developer environment", () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), "surge packaged é "));
  try {
    const resources = path.join(folder, "resources");
    const root = path.join(resources, "app");
    const bundled = path.join(resources, "python", "python.exe");
    const developer = path.join(root, ".venv", "Scripts", "python.exe");
    fs.mkdirSync(path.dirname(developer), { recursive: true });
    fs.writeFileSync(developer, "developer fixture");
    fs.mkdirSync(path.dirname(bundled), { recursive: true });
    fs.writeFileSync(bundled, "bundled fixture");
    const options = { packaged: true, resourcesPath: resources };
    const env = {
      SURGE_PYTHON: developer,
      PYTHONHOME: folder,
      PYTHONPATH: folder,
    };
    assert.equal(pythonPath(root, env, "win32", options), bundled);
    fs.unlinkSync(bundled);
    assert.throws(() => pythonPath(root, env, "win32", options), {
      code: "SURGE_BUNDLED_PYTHON_MISSING",
    });
    fs.mkdirSync(bundled);
    assert.throws(() => pythonPath(root, env, "win32", options), {
      code: "SURGE_BUNDLED_PYTHON_MISSING",
    });
  } finally {
    fs.rmSync(folder, { recursive: true, force: true });
  }
});

test("missing source override reports configuration guidance instead of raw filesystem errors", () => {
  const missing = path.join(
    os.tmpdir(),
    "surge missing interpreter",
    "python.exe",
  );
  assert.throws(() => pythonPath(".", { SURGE_PYTHON: missing }, "win32"), {
    code: "SURGE_PYTHON_INVALID",
    message: /SURGE_PYTHON must name/,
  });
});

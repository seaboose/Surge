const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {
  configureProfile,
  checkResources,
  StartupDiagnostics,
  failureMessage,
  LOG_LIMIT_BYTES,
} = require("./startup.cjs");

function owned(run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "surge startup é "));
  try {
    run(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}
function appFor(
  root,
  { name = "Surge", profile = path.join(root, name), explicit = "" } = {},
) {
  const paths = { appData: root, userData: profile };
  return {
    getName: () => name,
    getPath: (key) => paths[key],
    setPath: (key, value) => {
      paths[key] = value;
    },
    commandLine: { getSwitchValue: () => explicit },
  };
}
function put(root, relative) {
  const file = path.join(root, relative);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, "owned fixture");
  return file;
}

test("stable data identity survives branding and preserves an externally owned profile", () =>
  owned((root) => {
    const app = appFor(root);
    assert.equal(configureProfile(app), path.join(root, "surge-desktop"));
    const externallySet = path.join(root, "isolated previous profile");
    const ownedApp = appFor(root, { profile: externallySet });
    assert.equal(configureProfile(ownedApp), externallySet);
    assert.equal(ownedApp.getPath("userData"), externallySet);
  }));

test("an explicit absolute profile is isolated and relative profiles are refused", () =>
  owned((root) => {
    const explicit = path.join(root, "profiles", "owned é");
    const app = appFor(root, { explicit });
    assert.equal(configureProfile(app), explicit);
    assert.equal(app.getPath("userData"), explicit);
    assert.ok(fs.statSync(explicit).isDirectory());
    const relative = appFor(root, { explicit: "relative-profile" });
    assert.throws(() => configureProfile(relative), {
      code: "SURGE_PROFILE_INVALID",
    });
    const blocked = put(root, "blocked-profile");
    assert.throws(() => configureProfile(appFor(root, { explicit: blocked })), {
      code: "SURGE_PROFILE_INVALID",
    });
    assert.equal(fs.readFileSync(blocked, "utf8"), "owned fixture");
  }));

test("required backend and renderer files are checked before a packaged sample is required", () =>
  owned((root) => {
    assert.throws(() => checkResources(root, false), {
      code: "SURGE_BACKEND_MISSING",
    });
    for (const file of ["desktop_worker.py", "engine.py", "native_stream.py"])
      put(root, file);
    assert.throws(() => checkResources(root, false), {
      code: "SURGE_RENDERER_MISSING",
    });
    for (const file of [
      "desktop/preload.cjs",
      "desktop/dist/index.html",
      "desktop/dist/app.js",
      "desktop/dist/style.css",
      "desktop/dist/app.css",
    ])
      put(root, file);
    checkResources(root, false);
    assert.throws(() => checkResources(root, true), {
      code: "SURGE_SAMPLE_MISSING",
    });
    for (const file of [
      "native/build/surge_owned_app.exe",
      "native/build/lab_module_v2.dll",
      "native/baselines.json",
    ])
      put(root, file);
    checkResources(root, true);
    fs.unlinkSync(path.join(root, "desktop_worker.py"));
    fs.mkdirSync(path.join(root, "desktop_worker.py"));
    assert.throws(() => checkResources(root, true), {
      code: "SURGE_BACKEND_MISSING",
    });
  }));

test("startup diagnostics and failure guidance never retain arbitrary error or evidence text", () =>
  owned((root) => {
    const canary = "PRIVATE-EVIDENCE-CANARY.csv content=secret";
    const log = new StartupDiagnostics(root, canary, true);
    assert.equal(log.record(canary, canary, canary), true);
    const raw = fs.readFileSync(log.file, "utf8");
    assert.ok(!raw.includes(canary));
    const record = JSON.parse(raw);
    assert.deepEqual(Object.keys(record).sort(), [
      "code",
      "mode",
      "phase",
      "status",
      "time",
      "version",
    ]);
    assert.equal(record.code, "SURGE_STARTUP_FAILED");
    assert.equal(record.version, "unknown");
    const failure = failureMessage(
      Object.assign(new Error(canary), { code: canary }),
      true,
      log,
    );
    assert.ok(!failure.detail.includes(canary));
    assert.match(failure.detail, /Extract a complete copy/);
    assert.ok(failure.detail.includes(log.file));
  }));

test("startup diagnostics rotate within two bounded files", () =>
  owned((root) => {
    const log = new StartupDiagnostics(root, "0.4.0", true);
    for (let i = 0; i < 600; i++)
      assert.equal(log.record("worker", "ready"), true);
    const files = fs.readdirSync(path.dirname(log.file));
    assert.deepEqual(files.sort(), ["startup.jsonl", "startup.jsonl.1"]);
    for (const file of files) {
      const full = path.join(path.dirname(log.file), file);
      assert.ok(fs.statSync(full).size <= LOG_LIMIT_BYTES);
      for (const line of fs.readFileSync(full, "utf8").trim().split("\n"))
        assert.equal(JSON.parse(line).phase, "worker");
    }
  }));

test("unavailable diagnostics preserve the blocking file and provide a safe fallback", () =>
  owned((root) => {
    const blocked = put(root, "logs");
    const log = new StartupDiagnostics(root, "0.4.0", true);
    assert.equal(
      log.record("startup", "failed", "SURGE_PROFILE_INVALID"),
      false,
    );
    const failure = failureMessage(
      { code: "SURGE_PROFILE_INVALID", message: "private content" },
      true,
      log,
    );
    assert.match(failure.detail, /diagnostics could not be saved/);
    assert.ok(!failure.detail.includes("private content"));
    assert.equal(fs.readFileSync(blocked, "utf8"), "owned fixture");
  }));

test("oversized versions cannot exceed the diagnostic bound", () =>
  owned((root) => {
    const log = new StartupDiagnostics(
      root,
      "1.2.3-" + "a".repeat(LOG_LIMIT_BYTES),
      true,
    );
    assert.equal(log.record("startup", "starting"), true);
    assert.ok(fs.statSync(log.file).size <= LOG_LIMIT_BYTES);
    assert.equal(
      JSON.parse(fs.readFileSync(log.file, "utf8")).version,
      "unknown",
    );
  }));

"use strict";
const fs = require("node:fs");
const path = require("node:path");
const { isFile } = require("./runtime.cjs");

const STARTUP_TIMEOUT_MS = 5000;
const LOG_LIMIT_BYTES = 32 * 1024;
const messages = Object.freeze({
  SURGE_BUNDLED_PYTHON_MISSING: "The bundled Python runtime is missing.",
  SURGE_PYTHON_INVALID: "The configured Python executable is unavailable.",
  SURGE_PYTHON_MISSING: "Python is not configured.",
  SURGE_BACKEND_MISSING: "The analysis engine files are missing.",
  SURGE_RENDERER_MISSING: "The interface files are missing.",
  SURGE_SAMPLE_MISSING:
    "The included sample or its reviewed baseline is missing.",
  SURGE_PROFILE_INVALID: "The local data folder is unavailable.",
  SURGE_WORKER_SPAWN: "The analysis engine could not start.",
  SURGE_WORKER_TIMEOUT: "The analysis engine did not become ready in time.",
  SURGE_WORKER_STOPPED: "The analysis engine stopped during startup.",
  SURGE_WORKER_PROTOCOL:
    "The analysis engine could not confirm its startup state.",
  SURGE_STARTUP_FAILED: "Surge could not finish starting.",
});

function startupError(code) {
  return Object.assign(new Error(messages[code]), { code });
}

function configureProfile(app) {
  // A trusted command-line profile is useful for isolated release checks. It
  // never crosses the renderer boundary. Existing app.setPath profiles survive.
  const explicit = app.commandLine.getSwitchValue("user-data-dir");
  let profile = app.getPath("userData");
  if (explicit) {
    if (!path.isAbsolute(explicit)) throw startupError("SURGE_PROFILE_INVALID");
    profile = path.resolve(explicit);
  } else {
    const defaultPath = path.join(app.getPath("appData"), app.getName());
    if (path.resolve(profile) === path.resolve(defaultPath))
      profile = path.join(app.getPath("appData"), "surge-desktop");
  }
  try {
    fs.mkdirSync(profile, { recursive: true });
    if (profile !== app.getPath("userData")) app.setPath("userData", profile);
  } catch {
    throw startupError("SURGE_PROFILE_INVALID");
  }
  return profile;
}

function checkResources(root, packaged) {
  const required = [
    [
      "SURGE_BACKEND_MISSING",
      ["desktop_worker.py", "engine.py", "native_stream.py"],
    ],
    [
      "SURGE_RENDERER_MISSING",
      [
        "desktop/preload.cjs",
        "desktop/dist/index.html",
        "desktop/dist/app.js",
        "desktop/dist/style.css",
      ],
    ],
  ];
  if (packaged)
    required.push([
      "SURGE_SAMPLE_MISSING",
      [
        "native/build/surge_owned_app.exe",
        "native/build/lab_module_v2.dll",
        "native/baselines.json",
      ],
    ]);
  for (const [code, files] of required)
    if (files.some((file) => !isFile(path.join(root, file))))
      throw startupError(code);
}

class StartupDiagnostics {
  constructor(profile, version, packaged) {
    this.file = path.join(profile, "logs", "startup.jsonl");
    this.version =
      typeof version === "string" &&
      version.length <= 64 &&
      /^\d+\.\d+\.\d+(?:[-.][a-zA-Z0-9.]+)?$/.test(version)
        ? version
        : "unknown";
    this.mode = packaged ? "packaged" : "source";
    this.available = false;
  }

  record(phase, status, code = "NONE") {
    // Never accept exception text, process output, paths or request payloads.
    const safePhase = ["startup", "resources", "worker", "renderer"].includes(
      phase,
    )
      ? phase
      : "startup";
    const safeStatus = ["starting", "ready", "failed"].includes(status)
      ? status
      : "failed";
    const safeCode =
      code === "NONE" || Object.hasOwn(messages, code)
        ? code
        : "SURGE_STARTUP_FAILED";
    const line =
      JSON.stringify({
        time: new Date().toISOString(),
        phase: safePhase,
        status: safeStatus,
        code: safeCode,
        version: this.version,
        mode: this.mode,
      }) + "\n";
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      const backup = this.file + ".1";
      if (isFile(backup) && fs.statSync(backup).size > LOG_LIMIT_BYTES)
        fs.unlinkSync(backup);
      if (isFile(this.file)) {
        const size = fs.statSync(this.file).size;
        if (size > LOG_LIMIT_BYTES) fs.truncateSync(this.file, 0);
        else if (size + Buffer.byteLength(line) > LOG_LIMIT_BYTES) {
          if (fs.existsSync(backup)) fs.unlinkSync(backup);
          fs.renameSync(this.file, backup);
        }
      }
      fs.appendFileSync(this.file, line, "utf8");
      this.available = true;
    } catch {
      this.available = false;
    }
    return this.available;
  }
}

function failureMessage(error, packaged, diagnostics) {
  const code = Object.hasOwn(messages, error?.code)
    ? error.code
    : "SURGE_STARTUP_FAILED";
  const action =
    code === "SURGE_PROFILE_INVALID"
      ? "Check that your Windows account can write to its application data folder. Saved cases have not been removed."
      : packaged
        ? "Extract a complete copy of Surge into a new local folder and try again. Your case library is stored separately."
        : "Run Setup-Surge.ps1, or check the configured Python executable, then reopen Surge.";
  const diagnostic = diagnostics?.available
    ? `Diagnostic: ${diagnostics.file}`
    : "Startup diagnostics could not be saved. Record this error code for support.";
  return {
    code,
    detail: `${messages[code]} ${action}\n\n${diagnostic}\nCode: ${code}`,
  };
}

module.exports = {
  STARTUP_TIMEOUT_MS,
  LOG_LIMIT_BYTES,
  configureProfile,
  checkResources,
  StartupDiagnostics,
  failureMessage,
  startupError,
};

"use strict";
const fs = require("node:fs");
const path = require("node:path");

// Runtime selection is local configuration; the renderer cannot set it.
function pythonPath(
  root = path.resolve(__dirname, ".."),
  env = process.env,
  platform = process.platform,
) {
  if (env.SURGE_PYTHON) {
    if (
      !path.isAbsolute(env.SURGE_PYTHON) ||
      !fs.statSync(env.SURGE_PYTHON).isFile()
    ) {
      throw new Error(
        "SURGE_PYTHON must name an existing Python executable using an absolute path.",
      );
    }
    return env.SURGE_PYTHON;
  }
  const local = path.join(
    root,
    ".venv",
    platform === "win32" ? "Scripts" : "bin",
    platform === "win32" ? "python.exe" : "python",
  );
  if (fs.existsSync(local)) return local;
  throw new Error(
    "Python is not configured. Run Setup-Surge.ps1 or set SURGE_PYTHON to your Python executable.",
  );
}

module.exports = { pythonPath };

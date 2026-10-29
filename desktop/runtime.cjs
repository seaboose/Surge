"use strict";
const fs = require("node:fs");
const path = require("node:path");

function isFile(file) {
  try {
    return fs.statSync(file).isFile();
  } catch {
    return false;
  }
}

// Runtime selection is local configuration; the renderer cannot set it.
function pythonPath(
  root = path.resolve(__dirname, ".."),
  env = process.env,
  platform = process.platform,
  { packaged = false, resourcesPath } = {},
) {
  if (packaged) {
    const bundled =
      resourcesPath && path.isAbsolute(resourcesPath)
        ? path.join(resourcesPath, "python", "python.exe")
        : null;
    if (!bundled || !isFile(bundled))
      throw Object.assign(
        new Error(
          "The bundled Python runtime is missing. Extract a complete copy of Surge into a new folder.",
        ),
        {
          code: "SURGE_BUNDLED_PYTHON_MISSING",
        },
      );
    return bundled;
  }
  if (env.SURGE_PYTHON) {
    if (!path.isAbsolute(env.SURGE_PYTHON) || !isFile(env.SURGE_PYTHON)) {
      throw Object.assign(
        new Error(
          "SURGE_PYTHON must name an existing Python executable using an absolute path.",
        ),
        { code: "SURGE_PYTHON_INVALID" },
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
  if (isFile(local)) return local;
  throw Object.assign(
    new Error(
      "Python is not configured. Run Setup-Surge.ps1 or set SURGE_PYTHON to your Python executable.",
    ),
    { code: "SURGE_PYTHON_MISSING" },
  );
}

module.exports = { pythonPath, isFile };

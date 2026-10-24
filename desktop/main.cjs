"use strict";
const {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
  clipboard,
  protocol,
  session,
} = require("electron");
const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs/promises");
const { validate } = require("./boundary.cjs");
const runtime = require("./runtime.cjs");
const startup = require("./startup.cjs");

protocol.registerSchemesAsPrivileged([
  {
    scheme: "surge",
    privileges: { standard: true, secure: true, supportFetchAPI: true },
  },
]);
let win,
  worker,
  sequence = 0,
  pending = new Map(),
  output = "",
  queue = Promise.resolve(),
  queued = 0;
const ROOT = path.resolve(__dirname, "..");
const { CaseLibrary } = require("./case-library.cjs");
let library;
let profileError;
let profile = app.getPath("userData");
try {
  profile = startup.configureProfile(app);
} catch (error) {
  profileError = error;
}
const diagnostics = new startup.StartupDiagnostics(
  profile,
  app.getVersion(),
  app.isPackaged,
);
const runtimeIdentity = {
  packaged: app.isPackaged,
  applicationRoot: ROOT,
  backendPath: path.join(ROOT, "desktop_worker.py"),
  pythonExecutable: null,
  profilePath: profile,
  nativeExecutable: path.join(ROOT, "native/build/surge_owned_app.exe"),
  baselinePath: path.join(ROOT, "native/baselines.json"),
  diagnosticPath: diagnostics.file,
  workerPid: null,
  pythonVersion: null,
  backendModulePaths: null,
  ready: false,
  status: "starting",
  errorCode: null,
};
// Read-only metadata for trusted main-process qualification. This is not IPC
// and is never exposed to the renderer or written into startup diagnostics.
Object.defineProperty(app, "surgeRuntimeIdentity", {
  get: () => Object.freeze({ ...runtimeIdentity }),
});
function failWorker(message, code = "SURGE_WORKER_STOPPED") {
  for (const item of pending.values()) {
    clearTimeout(item.timer);
    item.reject(Object.assign(new Error(message), { code }));
  }
  pending.clear();
}
function startWorker() {
  const python = runtime.pythonPath(ROOT, process.env, process.platform, {
    packaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
  });
  runtimeIdentity.pythonExecutable = python;
  diagnostics.record("worker", "starting");
  const workerEnv = {};
  for (const key of ["SystemRoot", "WINDIR", "TEMP", "TMP"]) {
    if (process.env[key]) workerEnv[key] = process.env[key];
  }
  worker = spawn(
    python,
    [
      "-I",
      "-B",
      "-u",
      "-c",
      "import json, sys; sys.path.insert(0, sys.argv[1]); import desktop_worker; print(json.dumps({'surge_runtime_identity': 1, 'executable': sys.executable, 'version': sys.version.split()[0], 'modules': {name: sys.modules[name].__file__ for name in ('desktop_worker', 'engine', 'native_integrity', 'native_stream')}}), flush=True); desktop_worker.main()",
      ROOT,
    ],
    {
      cwd: ROOT,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
      shell: false,
      env: workerEnv,
    },
  );
  runtimeIdentity.workerPid = worker.pid || null;
  worker.stdout.setEncoding("utf8");
  worker.stdout.on("data", (chunk) => {
    output += chunk;
    if (output.length > 32 * 1024 * 1024) {
      failWorker(
        "Worker response exceeded its limit. Reopen Surge.",
        "SURGE_WORKER_PROTOCOL",
      );
      worker.kill();
      return;
    }
    let newline;
    while ((newline = output.indexOf("\n")) >= 0) {
      const line = output.slice(0, newline);
      output = output.slice(newline + 1);
      try {
        const reply = JSON.parse(line);
        if (reply?.surge_runtime_identity === 1) {
          const samePath = (actual, expected) =>
            typeof actual === "string" &&
            path.isAbsolute(actual) &&
            (process.platform === "win32"
              ? path.resolve(actual).toLowerCase() ===
                path.resolve(expected).toLowerCase()
              : path.resolve(actual) === path.resolve(expected));
          if (
            runtimeIdentity.pythonVersion ||
            !/^\d+\.\d+\.\d+/.test(reply.version) ||
            !samePath(reply.executable, python) ||
            ![
              "desktop_worker",
              "engine",
              "native_integrity",
              "native_stream",
            ].every((name) =>
              samePath(reply.modules?.[name], path.join(ROOT, name + ".py")),
            )
          )
            throw startup.startupError("SURGE_WORKER_PROTOCOL");
          runtimeIdentity.pythonVersion = reply.version;
          runtimeIdentity.backendModulePaths = Object.freeze({
            ...reply.modules,
          });
          continue;
        }
        const item = pending.get(reply.id);
        if (!item) continue;
        clearTimeout(item.timer);
        pending.delete(reply.id);
        reply.ok
          ? item.resolve(reply.value)
          : item.reject(new Error(reply.error || "Operation failed."));
      } catch {
        failWorker(
          "Worker response was invalid. Reopen Surge.",
          "SURGE_WORKER_PROTOCOL",
        );
        worker.kill();
      }
    }
  });
  // Drain stderr without logging imported evidence.
  worker.stderr.on("data", () => {});
  worker.stdin.on("error", () =>
    failWorker("Worker connection closed. Reopen Surge."),
  );
  worker.on("error", () =>
    failWorker(
      "Python could not start. Check the configured runtime and reopen Surge.",
      "SURGE_WORKER_SPAWN",
    ),
  );
  worker.on("exit", () =>
    failWorker(
      "Analysis worker stopped. Reopen Surge; saved files are unchanged.",
    ),
  );
}
function call(method, args, timeout = 120000) {
  return new Promise((resolve, reject) => {
    if (!worker || worker.exitCode !== null || !worker.stdin.writable)
      return reject(
        Object.assign(
          new Error("Analysis worker is unavailable. Reopen Surge."),
          { code: "SURGE_WORKER_STOPPED" },
        ),
      );
    const id = ++sequence;
    const timer = setTimeout(() => {
      failWorker(
        "Operation timed out. Reopen Surge before continuing.",
        "SURGE_WORKER_TIMEOUT",
      );
      worker.kill();
    }, timeout);
    pending.set(id, { resolve, reject, timer });
    worker.stdin.write(
      JSON.stringify({ protocol: 1, id, method, args }) + "\n",
      (error) => {
        if (error) {
          clearTimeout(timer);
          pending.delete(id);
          reject(new Error("Worker connection closed."));
        }
      },
    );
  });
}
async function execute(method, args) {
  if (method.startsWith("library_")) {
    library ||= new CaseLibrary(
      path.join(app.getPath("userData"), "cases"),
      call,
    );
    if (method === "library_list") return library.list();
    if (method === "library_save")
      return library.save(args.name, args.revision);
    if (method === "library_open") return library.open(args.id);
    if (method === "library_rename") return library.rename(args.id, args.name);
    if (method === "library_delete") {
      const entry = await library.entry(args.id);
      const answer = await dialog.showMessageBox(win, {
        type: "question",
        title: "Delete saved case?",
        message: `Delete “${entry.meta.name}” from the library?`,
        detail:
          "This removes only this saved case. Original evidence, exported files, and the open investigation remain unchanged. This cannot be undone.",
        buttons: ["Cancel", "Delete case"],
        defaultId: 0,
        cancelId: 0,
        noLink: true,
      });
      if (answer.response !== 1) return { canceled: true };
      return library.delete(args.id);
    }
    if (method === "library_import") {
      const selected = await dialog.showOpenDialog(win, {
        title: "Import case into library",
        filters: [{ name: "Evidence case", extensions: ["json"] }],
        properties: ["openFile"],
      });
      if (selected.canceled || selected.filePaths.length !== 1)
        return { canceled: true };
      const source = selected.filePaths[0];
      return library.import(
        source,
        path
          .basename(source)
          .replace(/(?:\.case)?\.json$/i, "")
          .slice(0, 100) || "Imported case",
      );
    }
    if (method === "library_export") {
      await library.entry(args.id);
      const selected = await dialog.showSaveDialog(win, {
        title: "Export portable case to a new file",
        defaultPath: "investigation.case.json",
      });
      if (selected.canceled || !selected.filePath) return { canceled: true };
      return library.export(args.id, selected.filePath);
    }
  }
  const files = {
    import: [
      "Choose data",
      [{ name: "Data", extensions: ["csv", "json", "jsonl", "ndjson"] }],
    ],
    open: [
      "Open saved case",
      [{ name: "Evidence case", extensions: ["json"] }],
    ],
    compare: [
      "Compare case",
      [{ name: "Evidence case", extensions: ["json"] }],
    ],
    policy_load: ["Load policy", [{ name: "Policy", extensions: ["json"] }]],
    labels_load: [
      "Import labels",
      [{ name: "Independent labels", extensions: ["json"] }],
    ],
  };
  if (Object.hasOwn(files, method)) {
    const [title, filters] = files[method];
    const result = await dialog.showOpenDialog(win, {
      title,
      filters,
      properties: ["openFile"],
    });
    if (result.canceled || result.filePaths.length !== 1)
      return { canceled: true };
    args = { ...args, path: result.filePaths[0] };
  }
  const saves = {
    save: "investigation.case.json",
    policy_save: "surge.policy.json",
    alerts: "surge.alerts.jsonl",
    labels_template: "surge.labels.json",
    evaluation_save: "surge.evaluation.json",
    native_export: "native-stream.jsonl",
  };
  if (Object.hasOwn(saves, method)) {
    const result = await dialog.showSaveDialog(win, {
      title: "Save new file",
      defaultPath: saves[method],
    });
    if (result.canceled || !result.filePath) return { canceled: true };
    args = { ...args, path: result.filePath };
  }
  const value = await call(method, args);
  if (method === "copy") {
    clipboard.writeText(value.text);
    return {
      message:
        args.scope === "match"
          ? "Match copied."
          : args.scope === "value"
            ? "Full field value copied."
            : "Record copied.",
    };
  }
  return value;
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.setAppUserModelId("local.surge.desktop");
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.show();
      win.focus();
    }
  });
  app
    .whenReady()
    .then(async () => {
      diagnostics.record("startup", "starting");
      if (profileError) throw profileError;
      // Resolve the bundled runtime first; packaged launches never use PATH or
      // a developer override, including when a required file is missing.
      runtime.pythonPath(ROOT, process.env, process.platform, {
        packaged: app.isPackaged,
        resourcesPath: process.resourcesPath,
      });
      startup.checkResources(ROOT, app.isPackaged);
      diagnostics.record("resources", "ready");
      const assets = new Map([
        ["/index.html", "index.html"],
        ["/app.js", "app.js"],
        ["/style.css", "style.css"],
      ]);
      protocol.handle("surge", async (request) => {
        const url = new URL(request.url);
        const asset = url.host === "app" && assets.get(url.pathname);
        if (!asset || request.method !== "GET")
          return new Response("Not found", { status: 404 });
        const types = {
          "index.html": "text/html; charset=utf-8",
          "app.js": "text/javascript; charset=utf-8",
          "style.css": "text/css; charset=utf-8",
        };
        return new Response(
          await fs.readFile(path.join(__dirname, "dist", asset)),
          {
            headers: {
              "Content-Type": types[asset],
              "X-Content-Type-Options": "nosniff",
            },
          },
        );
      });
      session.defaultSession.setPermissionRequestHandler(
        (_web, _permission, callback) => callback(false),
      );
      session.defaultSession.setPermissionCheckHandler(() => false);
      session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
        callback({ cancel: !details.url.startsWith("surge://app/") });
      });
      startWorker();
      const initial = await call("state", {}, startup.STARTUP_TIMEOUT_MS);
      if (initial?.protocol !== 1 || !runtimeIdentity.pythonVersion)
        throw startup.startupError("SURGE_WORKER_PROTOCOL");
      diagnostics.record("worker", "ready");
      win = new BrowserWindow({
        width: 1360,
        height: 880,
        minWidth: 720,
        minHeight: 540,
        title: "Surge",
        backgroundColor: "#080c12",
        show: false,
        autoHideMenuBar: true,
        webPreferences: {
          preload: path.join(__dirname, "preload.cjs"),
          nodeIntegration: false,
          contextIsolation: true,
          sandbox: true,
          webSecurity: true,
          allowRunningInsecureContent: false,
          spellcheck: false,
        },
      });
      win.removeMenu();
      // Keep standard zoom keys available even without a desktop menu.
      win.webContents.on("before-input-event", (event, input) => {
        if (
          input.type !== "keyDown" ||
          !(input.control || input.meta) ||
          input.alt
        )
          return;
        const key = input.key;
        if (!["+", "=", "-", "0"].includes(key)) return;
        event.preventDefault();
        const current = win.webContents.getZoomFactor();
        win.webContents.setZoomFactor(
          key === "0"
            ? 1
            : Math.max(0.75, Math.min(2, current + (key === "-" ? -0.1 : 0.1))),
        );
      });
      win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
      win.webContents.on("will-navigate", (event) => event.preventDefault());
      win.webContents.on("will-attach-webview", (event) =>
        event.preventDefault(),
      );
      ipcMain.handle("surge:request", (event, method, input) => {
        if (
          event.sender !== win.webContents ||
          event.senderFrame !== win.webContents.mainFrame ||
          event.senderFrame.url !== "surge://app/index.html"
        )
          throw new Error("Untrusted request origin.");
        validate(method, input);
        if (queued >= 32)
          throw new Error(
            "Too many pending operations. Wait for the current operation.",
          );
        queued++;
        const args = structuredClone(input);
        const operation = queue.then(() => execute(method, args));
        queue = operation.catch(() => {});
        return operation
          .then(
            (value) => ({ ok: true, value }),
            (error) => ({ ok: false, error: error.message }),
          )
          .finally(() => queued--);
      });
      win.once("ready-to-show", () => win.show());
      await win.loadURL("surge://app/index.html");
      runtimeIdentity.ready = true;
      runtimeIdentity.status = "ready";
      diagnostics.record("renderer", "ready");
    })
    .catch(async (error) => {
      runtimeIdentity.ready = false;
      runtimeIdentity.status = "failed";
      if (worker && worker.exitCode === null && worker.signalCode === null)
        worker.kill();
      const failure = startup.failureMessage(
        error,
        app.isPackaged,
        diagnostics,
      );
      runtimeIdentity.errorCode = failure.code;
      diagnostics.record("startup", "failed", failure.code);
      // Async native guidance keeps trusted diagnostics inspectable. No worker
      // stderr, imported filenames, exception text or payload enters this UI.
      const detail = startup.failureMessage(
        error,
        app.isPackaged,
        diagnostics,
      ).detail;
      await dialog.showMessageBox({
        type: "error",
        title: "Surge could not start",
        message: "Surge could not start",
        detail,
        buttons: ["Close"],
        defaultId: 0,
        cancelId: 0,
        noLink: true,
      });
      app.exit(1);
    });
}
app.on("window-all-closed", () => app.quit());
let quitting = false;
app.on("before-quit", (event) => {
  failWorker("Surge closed.");
  if (
    quitting ||
    !worker ||
    worker.exitCode !== null ||
    worker.signalCode !== null
  )
    return;
  // Keep Electron alive until the worker releases its owned child, or the
  // bounded fallback terminates the worker and closes the child's pipes.
  event.preventDefault();
  quitting = true;
  let finished = false;
  let forced;
  const finish = () => {
    if (finished) return;
    finished = true;
    clearTimeout(grace);
    clearTimeout(forced);
    app.quit();
  };
  const grace = setTimeout(() => {
    worker.kill();
    forced = setTimeout(finish, 1000);
  }, 5000);
  worker.once("exit", finish);
  worker.stdin.end();
});

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
function failWorker(message) {
  for (const item of pending.values()) {
    clearTimeout(item.timer);
    item.reject(new Error(message));
  }
  pending.clear();
}
function startWorker() {
  const python = require("./runtime.cjs").pythonPath(ROOT);
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
      "import sys; sys.path.insert(0, sys.argv[1]); import desktop_worker; desktop_worker.main()",
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
  worker.stdout.setEncoding("utf8");
  worker.stdout.on("data", (chunk) => {
    output += chunk;
    if (output.length > 32 * 1024 * 1024) {
      failWorker("Worker response exceeded its limit. Reopen Surge.");
      worker.kill();
      return;
    }
    let newline;
    while ((newline = output.indexOf("\n")) >= 0) {
      const line = output.slice(0, newline);
      output = output.slice(newline + 1);
      try {
        const reply = JSON.parse(line),
          item = pending.get(reply.id);
        if (!item) continue;
        clearTimeout(item.timer);
        pending.delete(reply.id);
        reply.ok
          ? item.resolve(reply.value)
          : item.reject(new Error(reply.error || "Operation failed."));
      } catch {
        failWorker("Worker response was invalid. Reopen Surge.");
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
    ),
  );
  worker.on("exit", () =>
    failWorker(
      "Analysis worker stopped. Reopen Surge; saved files are unchanged.",
    ),
  );
}
function call(method, args) {
  return new Promise((resolve, reject) => {
    if (!worker || worker.exitCode !== null || !worker.stdin.writable)
      return reject(new Error("Analysis worker is unavailable. Reopen Surge."));
    const id = ++sequence;
    const timer = setTimeout(() => {
      failWorker("Operation timed out. Reopen Surge before continuing.");
      worker.kill();
    }, 120000);
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
    })
    .catch((error) => {
      dialog.showErrorBox("Surge could not start", error.message);
      app.quit();
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

// Exercise live owned-app collection through the same desktop boundary as users.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const out = path.join(root, "verification/electron");
fs.mkdirSync(out, { recursive: true });
const temp = fs.mkdtempSync(path.join(out, "stream-"));
const entry = path.join(temp, "entry.cjs");
const source = path.join(temp, "original.json");
const exported = path.join(temp, "stream.jsonl");
const saved = path.join(temp, "stream.case.json");
fs.writeFileSync(source, JSON.stringify([{ id: "original", value: 12 }]));
fs.writeFileSync(
  entry,
  `const {app, ipcMain} = require('electron');
const cp = require('node:child_process');
const spawn = cp.spawn;
global.__children = [];
cp.spawn = (...args) => {
  const child = spawn(...args);
  global.__children.push(child);
  return child;
};
global.__statusFailures = 0;
const handle = ipcMain.handle.bind(ipcMain);
ipcMain.handle = (channel, callback) => handle(channel, (event, method, args) => {
  if (method === 'native_status' && global.__captureStatus) {
    const capture = global.__captureStatus;
    global.__captureStatus = null;
    return {ok: true, value: {capture}};
  }
  if (method === 'native_status' && global.__statusFailures > 0) {
    global.__statusFailures--;
    return {ok: false, error: 'Temporary status failure'};
  }
  return callback(event, method, args);
});
app.setPath('userData', ${JSON.stringify(path.join(temp, "profile"))});
require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
let app;
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  app = await electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
  });
  const page = await app.firstWindow();
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const ready = () =>
    page.waitForFunction(
      () => document.querySelector(".app")?.dataset.working === "false",
    );
  const call = (method, args = {}) =>
    page.evaluate(
      async ({ method, args }) => {
        const reply = await window.surge.request(method, args);
        if (!reply.ok) throw new Error(reply.error);
        return reply.value;
      },
      { method, args },
    );
  const click = async (name) => {
    await page.getByRole("button", { name, exact: true }).click();
    await ready();
  };
  const waitRecords = async (count) => {
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline) {
      const capture = (await call("native_status")).capture;
      if (capture.state === "running" && capture.records >= count)
        return capture;
      assert.notEqual(capture.state, "failed", capture.error);
      await page.waitForTimeout(100);
    }
    throw new Error("The owned app did not produce observations in time.");
  };
  await ready();
  await app.evaluate(({ dialog }, file) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [file],
    });
  }, source);
  await click("Import data");
  const original = await call("state");
  await click("Our app");
  const controls = page.getByRole("region", { name: "Our app collection" });
  await controls.waitFor();
  await click("Start");
  await page.getByText("Our app · Collecting", { exact: true }).waitFor();
  await waitRecords(4);
  assert.equal(
    (await call("state")).current.sha256,
    original.current.sha256,
    "Starting collection must preserve the current evidence",
  );
  await click("Inspect");
  await page.getByRole("button", { name: "Findings", exact: true }).waitFor();
  const inspected = await call("state");
  assert.ok(inspected.summary);
  assert.ok(inspected.current.records >= 4);
  assert.equal(await page.locator("fieldset.workspace").isDisabled(), false);
  await page
    .locator(".evidence")
    .getByText(/Coverage:/)
    .waitFor();
  await page
    .locator(".evidence")
    .getByText(/executable bytes in scope/)
    .waitFor();
  assert.equal(await page.locator("h1, h2, h3").count(), 0);
  await page
    .getByRole("textbox", { name: "Search records" })
    .fill("LabCodeProbe");
  await app.evaluate(() => (global.__statusFailures = 1));
  await controls
    .getByText("Status unavailable: Temporary status failure", { exact: true })
    .waitFor();
  assert.ok(
    await controls
      .getByRole("button", { name: "Stop", exact: true })
      .isEnabled(),
    "A failed status read must not disable stopping the owned app",
  );
  await controls
    .getByText("Status unavailable: Temporary status failure", { exact: true })
    .waitFor({ state: "hidden" });
  const later = await call("state");
  assert.equal(
    later.revision,
    inspected.revision,
    "Background collection must not replace the inspected snapshot",
  );
  assert.equal(later.current.sha256, inspected.current.sha256);
  // A failed capture can contain health evidence even before its first sample.
  await app.evaluate(() => {
    global.__captureStatus = {
      state: "failed",
      records: 0,
      samples: 0,
      dropped_samples: 0,
      evicted_samples: 0,
      elapsed_ms: 0,
      build: "v1",
      session_id: null,
      limit_samples: 500,
      has_evidence: true,
      error: "Collection stopped before its first sample.",
    };
  });
  await controls
    .getByText("Our app · Collection failed", { exact: true })
    .waitFor();
  assert.ok(
    await controls
      .getByRole("button", { name: "Inspect", exact: true })
      .isEnabled(),
  );
  assert.ok(
    await controls
      .getByRole("button", { name: "Export", exact: true })
      .isEnabled(),
  );
  await click("Inspect");
  await click("Data");
  assert.ok(
    await controls
      .getByRole("button", { name: "Stop", exact: true })
      .isEnabled(),
  );
  await click("Stop");
  await page.getByText("Our app · Stopped", { exact: true }).waitFor();
  const stopped = await call("state");
  assert.ok(stopped.current.records >= inspected.current.records);
  assert.ok(stopped.summary);
  const status = (await call("native_status")).capture;
  assert.equal(status.state, "stopped");
  await page.waitForTimeout(650);
  assert.equal((await call("native_status")).capture.records, status.records);
  await app.evaluate(({ dialog }, file) => {
    dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
  }, exported);
  await click("Export");
  const rows = fs
    .readFileSync(exported, "utf8")
    .trim()
    .split("\n")
    .map(JSON.parse);
  assert.equal(rows.length, stopped.current.records);
  assert.ok(rows.every((row) => row.phase === "live"));
  await app.evaluate(({ dialog }, file) => {
    dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
  }, saved);
  await click("Save case");
  await click("Data");
  await app.evaluate(({ dialog }, file) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [file],
    });
  }, saved);
  await click("Open case");
  assert.deepEqual(
    (await call("state")).summary,
    stopped.summary,
    "Reopened evidence must reproduce the capture findings",
  );
  const sessions = new Set([status.session_id]);
  for (let cycle = 0; cycle < 2; cycle++) {
    await click("Start");
    await waitRecords(2);
    await click("Stop");
    const again = (await call("native_status")).capture;
    assert.equal(again.state, "stopped");
    assert.ok(
      !sessions.has(again.session_id),
      "Each app run needs a distinct session",
    );
    sessions.add(again.session_id);
  }
  await page.setViewportSize({ width: 900, height: 650 });
  await page.evaluate(
    () => (document.documentElement.style.fontSize = "19.5px"),
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth + 2,
    ),
    false,
  );
  await controls.getByRole("button", { name: "Start", exact: true }).focus();
  await page.keyboard.press("Enter");
  await ready();
  await page.getByText("Our app · Collecting", { exact: true }).waitFor();
  await waitRecords(2);
  await controls.getByRole("button", { name: "Stop", exact: true }).focus();
  await page.keyboard.press("Enter");
  await ready();
  await page.getByText("Our app · Stopped", { exact: true }).waitFor();
  const keyboardStopped = (await call("native_status")).capture;
  assert.ok(keyboardStopped.records >= 2, JSON.stringify(keyboardStopped));
  await controls
    .getByText(new RegExp(`${keyboardStopped.records} records`))
    .waitFor();
  await page.setViewportSize({ width: 1360, height: 900 });
  await page.evaluate(() => (document.documentElement.style.fontSize = "13px"));
  await page.screenshot({ path: path.join(out, "continuous-evidence.png") });
  assert.deepEqual(errors, []);
  await click("Start");
  const active = await waitRecords(2);
  const ownedPid = Number(active.session_id.split("-")[0]);
  const workerPid = await app.evaluate(() => global.__children[0].pid);
  assert.ok(Number.isInteger(ownedPid) && ownedPid > 0);
  await app.close();
  app = null;
  const exited = (pid) => {
    try {
      process.kill(pid, 0);
      return false;
    } catch (error) {
      if (error.code === "ESRCH") return true;
      throw error;
    }
  };
  const waitExit = async (pid) => {
    const deadline = Date.now() + 5000;
    while (!exited(pid) && Date.now() < deadline)
      await new Promise((resolve) => setTimeout(resolve, 100));
    assert.ok(exited(pid), `Owned child ${pid} remained after shutdown`);
  };
  await waitExit(workerPid);
  await waitExit(ownedPid);
  // Suppress graceful EOF in this test only to exercise the timeout fallback.
  app = await electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
  });
  const closingPage = await app.firstWindow();
  await closingPage.waitForFunction(() => !!document.querySelector(".app"));
  await closingPage.evaluate(async () => {
    const result = await window.surge.request("native_start", { build: "v1" });
    if (!result.ok) throw new Error(result.error);
  });
  let forcedCapture;
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    forcedCapture = await closingPage.evaluate(
      async () =>
        (await window.surge.request("native_status", {})).value.capture,
    );
    if (forcedCapture.records >= 2) break;
    await closingPage.waitForTimeout(100);
  }
  assert.ok(forcedCapture.records >= 2);
  const forcedWorker = await app.evaluate(() => {
    const child = global.__children[0];
    child.stdin.end = () => child.stdin;
    return child.pid;
  });
  const forcedOwned = Number(forcedCapture.session_id.split("-")[0]);
  await app.close();
  app = null;
  await waitExit(forcedWorker);
  await waitExit(forcedOwned);
  console.log(
    "Continuous desktop journey passed: start, stable inspect, stop, export, replay, restart, keyboard, text scaling, graceful and forced shutdown.",
  );
})()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

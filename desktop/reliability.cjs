// Full-duration measurement through the production desktop IPC boundary.
// Run via scripts/measure_reliability.py; isolated dialog destinations/profile only.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const folder = path.resolve(process.argv[2]);
fs.mkdirSync(folder, { recursive: true });
const entry = path.join(folder, "entry.cjs");
const exported = path.join(folder, "capture.jsonl");
const saved = path.join(folder, "capture.case.json");
const smoke = process.argv.includes("--smoke");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');
const cp=require('node:child_process'), original=cp.spawn;
global.__children=[];
cp.spawn=(...args)=>{const child=original(...args);global.__children.push(child);return child;};
app.setPath('userData',${JSON.stringify(path.join(folder, "profile"))});
require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
const report = { operations: [], cycles: [], errors: [] };
let app, page;
const emit = (value) => console.log(JSON.stringify(value));
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function call(method, args = {}) {
  if (["save", "analyze"].includes(method))
    args.revision = (await call("state")).revision;
  const start = performance.now();
  const value = await page.evaluate(
    async ({ method, args }) => {
      const reply = await window.surge.request(method, args);
      if (!reply.ok) throw new Error(reply.error);
      return reply.value;
    },
    { method, args },
  );
  if (method !== "native_status" && method !== "state")
    report.operations.push({ method, ms: performance.now() - start });
  return value;
}
async function action(name, method) {
  await require("./test-export-menu.cjs").revealExport(page, name);
  const start = performance.now();
  await page.getByRole("button", { name, exact: true }).click();
  await page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
  const dialog = page.locator("dialog[open]");
  if (await dialog.count()) throw new Error(await dialog.innerText());
  report.operations.push({
    method,
    ms: performance.now() - start,
    includes_render: true,
  });
  return call("state");
}
function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    throw error;
  }
}
async function waitExit(pid) {
  const start = performance.now();
  while (alive(pid) && performance.now() - start < 5000) await pause(50);
  assert.ok(!alive(pid), `Process ${pid} remained alive`);
  return performance.now() - start;
}
async function tick(phase, elapsed, capture) {
  const processes = await app.evaluate(({ app }) => [
    ...app
      .getAppMetrics()
      .map((p) => ({ pid: p.pid, role: `electron-${p.type}` })),
    { pid: global.__children[0].pid, role: "python" },
  ]);
  if (capture?.state === "running" && capture.session_id)
    processes.push({
      pid: Number(capture.session_id.split("-")[0]),
      role: "native",
    });
  emit({ type: "resources", phase, elapsed, processes, capture });
}
async function firstSample() {
  const start = performance.now();
  while (performance.now() - start < 10000) {
    const capture = (await call("native_status")).capture;
    assert.notEqual(capture.state, "failed", capture.error);
    if (capture.samples > 0) return { capture, ms: performance.now() - start };
    await pause(50);
  }
  throw new Error("No initial evidence within ten seconds");
}
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  app = await electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
  });
  page = await app.firstWindow();
  page.on("pageerror", (error) => report.errors.push(error.message));
  await page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
  report.versions = await app.evaluate(() => process.versions);
  await page.getByRole("button", { name: "Try Demo", exact: true }).click();
  await app.evaluate(({ dialog }, file) => {
    dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
  }, exported);
  const start = performance.now();
  await action("Start collection", "native_start");
  let initial = await firstSample(),
    capture = initial.capture;
  report.first_sample_ms = performance.now() - start;
  const ownedPid = Number(capture.session_id.split("-")[0]);
  let nextInspect = smoke ? 2 : 60,
    frozen = null;
  while ((performance.now() - start) / 1000 < 615) {
    const elapsed = (performance.now() - start) / 1000;
    capture = (await call("native_status")).capture;
    assert.notEqual(capture.state, "failed", capture.error);
    if (smoke && elapsed >= 8) {
      await call("native_stop");
      capture = (await call("native_status")).capture;
      break;
    }
    if (frozen) {
      const state = await call("state");
      assert.equal(state.current.sha256, frozen.current.sha256);
      assert.equal(state.revision, frozen.revision);
    }
    await tick("capture", elapsed, capture);
    if (capture.state === "stopped") break;
    if (elapsed >= nextInspect) {
      frozen = await action(
        frozen ? "Inspect newer snapshot" : "Inspect snapshot",
        "native_snapshot",
      );
      await app.evaluate(
        ({ dialog }, file) => {
          dialog.showSaveDialog = async () => ({
            canceled: false,
            filePath: file,
          });
        },
        path.join(folder, `checkpoint-${nextInspect}.jsonl`),
      );
      await action("Export captured records", "native_export");
      nextInspect += smoke ? 2 : 60;
      emit({ type: "progress", elapsed, samples: capture.samples });
    }
    await pause(2000);
  }
  report.capture_seconds = (performance.now() - start) / 1000;
  report.final_capture = capture;
  assert.equal(capture.state, "stopped");
  await waitExit(ownedPid);
  const stopped = await call("native_stop");
  await app.evaluate(({ dialog }, file) => {
    dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
  }, exported);
  await call("native_export");
  await app.evaluate(({ dialog }, file) => {
    dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
  }, saved);
  await call("save");
  await app.evaluate(({ dialog }, file) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [file],
    });
  }, exported);
  await call("import", { role: "current" });
  // Native import sets policy; run it as in the normal investigation flow.
  await call("analyze");
  assert.deepEqual((await call("state")).summary, stopped.summary);
  await app.evaluate(({ dialog }, file) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [file],
    });
  }, saved);
  await call("open");
  assert.deepEqual((await call("state")).summary, stopped.summary);
  report.summary = stopped.summary;
  report.export_bytes = fs.statSync(exported).size;
  const rows = fs
    .readFileSync(exported, "utf8")
    .trim()
    .split("\n")
    .map(JSON.parse);
  const samples = [
    ...new Map(
      rows
        .filter((r) => !r.stream_health)
        .map((r) => [r.stream_sequence, r.stream_elapsed_ms]),
    ).values(),
  ];
  report.gaps_ms = samples.slice(1).map((v, i) => v - samples[i]);
  report.health = rows
    .filter((r) => r.stream_health)
    .map((r) => ({
      evicted: r.stream_evicted_samples,
      dropped: r.stream_dropped_samples,
    }));
  await tick("before_cycles", 0, null);
  const identities = new Set([capture.session_id]);
  for (let i = 0; i < 20; i++) {
    const started = performance.now();
    await call("native_start", { build: i % 2 ? "v2" : "v1" });
    const sample = await firstSample();
    const first = performance.now() - started;
    assert.ok(!identities.has(sample.capture.session_id));
    identities.add(sample.capture.session_id);
    await call("native_stop");
    const exit = await waitExit(
      Number(sample.capture.session_id.split("-")[0]),
    );
    report.cycles.push({
      cycle: i + 1,
      first_sample_ms: first,
      exit_wait_ms: exit,
    });
  }
  await pause(2000);
  await tick("after_cycles", 0, null);
  await call("native_start", { build: "v1" });
  const active = (await firstSample()).capture;
  const workerPid = await app.evaluate(() => global.__children[0].pid);
  const closeStart = performance.now();
  await app.close();
  app = null;
  await waitExit(workerPid);
  await waitExit(Number(active.session_id.split("-")[0]));
  report.shutdown_ms = performance.now() - closeStart;
  report.passed = true;
})()
  .catch((error) => {
    report.error = error.stack;
    process.exitCode = 1;
  })
  .finally(async () => {
    if (page && !page.isClosed())
      await page
        .screenshot({ path: path.join(folder, "final.png") })
        .catch(() => {});
    if (app) await app.close();
    fs.writeFileSync(
      path.join(folder, "desktop.json"),
      JSON.stringify(report, null, 2),
    );
    emit({
      type: "complete",
      passed: report.passed === true,
      error: report.error,
    });
  });

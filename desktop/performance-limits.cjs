// Owned-fixture desktop measurements; invoked by measure_supported_limits.py.
const { _electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const folder = path.resolve(process.argv[2]);
const report = { scenarios: [], errors: [], passed: false };
const hash = (value) => crypto.createHash("sha256").update(value).digest("hex");
let app, page, timer, pendingSample, active;
const emit = (value) => console.log(JSON.stringify(value));
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
async function rpc(method, args = {}) {
  const response = await page.evaluate(
    ({ method, args }) => window.surge.request(method, args),
    { method, args },
  );
  assert.equal(response.ok, true, response.error);
  return response.value;
}
async function click(name, scope = page) {
  await scope.getByRole("button", { name, exact: true }).click();
  await page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
  const error = page.getByRole("dialog", { name: "Check input" });
  assert.equal(await error.count(), 0, "Application reported an input failure");
}
async function measure(name, budgetMs, fn) {
  const start = performance.now();
  const operation = { name, budgetMs, passed: false };
  active.operations.push(operation);
  try {
    await fn();
    operation.ms = performance.now() - start;
    assert.ok(
      operation.ms <= budgetMs,
      `${name}: ${operation.ms} > ${budgetMs} ms`,
    );
    operation.passed = true;
  } finally {
    operation.ms ??= performance.now() - start;
  }
}
async function sample() {
  const processes = await app.evaluate(({ app }) => [
    ...app
      .getAppMetrics()
      .map((p) => ({ pid: p.pid, role: `electron-${p.type}` })),
    ...global.__children
      .filter((c) => c.exitCode === null)
      .map((c) => ({ pid: c.pid, role: "python" })),
  ]);
  emit({
    type: "resources",
    scenario: active.name,
    time: Date.now(),
    processes,
  });
}
async function start(entry, operation) {
  await measure(operation, 5000, async () => {
    app = await _electron.launch({
      executablePath: require("electron"),
      args: [entry],
      env,
    });
    page = await app.firstWindow();
    page.setDefaultTimeout(30000);
    page.on("pageerror", (error) => report.errors.push(error.message));
    await page.waitForFunction(
      () => document.querySelector(".app")?.dataset.working === "false",
    );
    await page
      .getByRole("button", { name: "Import evidence", exact: true })
      .waitFor();
  });
  report.versions = await app.evaluate(() => process.versions);
  await page.evaluate(() => {
    window.__measurement = { gaps: [], last: performance.now() };
    window.__measurement.timer = setInterval(() => {
      const now = performance.now();
      window.__measurement.gaps.push(now - window.__measurement.last);
      window.__measurement.last = now;
    }, 50);
  });
  await sample();
  timer = setInterval(() => {
    if (!pendingSample)
      pendingSample = sample()
        .catch((e) => report.errors.push(e.message))
        .finally(() => {
          pendingSample = null;
        });
  }, 250);
}
async function stop() {
  clearInterval(timer);
  if (pendingSample) await pendingSample;
  if (!app) return;
  if (page) {
    const gaps = await page.evaluate(() => {
      clearInterval(window.__measurement.timer);
      return window.__measurement.gaps;
    });
    active.heartbeatGapsMs.push(...gaps);
  }
  await app.close();
  app = page = null;
}
async function file(selected) {
  await app.evaluate(({ dialog }, selected) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [selected],
    });
  }, selected);
}
async function resultDigest() {
  const state = await rpc("state"),
    rows = [];
  for (let index = 0; index < Math.ceil(state.summary.total / 100); index++) {
    const part = await rpc("findings", {
      revision: state.revision,
      query: "",
      minimum: "All",
      hide: false,
      page: index,
    });
    assert.equal(part.total, state.summary.total);
    rows.push(...part.rows);
  }
  assert.equal(rows.length, state.summary.total);
  return {
    source: state.current.sha256,
    settings: state.config,
    summary: state.summary,
    resultRowsSha256: hash(JSON.stringify(rows)),
  };
}
async function scenario(kind, repetition) {
  const combined = kind === "combined-limits",
    count = combined ? 10000 : 100,
    fields = combined ? 64 : 8,
    rules = combined ? 32 : 2,
    budget = combined ? 15000 : 3000;
  active = {
    name: `${kind}-${repetition}`,
    operations: [],
    heartbeatGapsMs: [],
    passed: false,
  };
  report.scenarios.push(active);
  const current = path.join(folder, active.name);
  fs.mkdirSync(current);
  const profile = path.join(current, "profile"),
    entry = path.join(current, "entry.cjs"),
    source = path.join(current, "owned.json"),
    policy = path.join(current, "policy.json");
  const rows = Array.from({ length: count }, (_, index) =>
    Object.fromEntries([
      ["id", `owned-${String(index).padStart(5, "0")}`],
      ["session", "owned-fixture"],
      ...Array.from({ length: fields - 2 }, (_, field) => [
        `f${String(field).padStart(2, "0")}`,
        field === 0 ? (index % 2) * 100 : field,
      ]),
    ]),
  );
  const raw = JSON.stringify(rows),
    padded = combined
      ? raw + " ".repeat(16 * 1024 ** 2 - Buffer.byteLength(raw))
      : raw;
  fs.writeFileSync(source, padded);
  const settings = {
    features: [],
    event_id: "id",
    session: "session",
    time: null,
    time_format: "milliseconds",
    threshold: 6,
    rules: Array.from({ length: rules }, (_, index) => ({
      name: `Owned rule ${index}`,
      field: `f${String(index).padStart(2, "0")}`,
      op: "gt",
      value: index ? 1000000 : 50,
      priority: "Notice",
    })),
  };
  fs.writeFileSync(
    policy,
    JSON.stringify({ schema: "surge-policy-v1", settings }),
  );
  fs.writeFileSync(
    entry,
    `const {app}=require('electron'); const cp=require('node:child_process'),original=cp.spawn; global.__children=[]; cp.spawn=(...args)=>{const c=original(...args);global.__children.push(c);return c;}; app.setPath('userData',${JSON.stringify(profile)});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
  );
  active.fixture = {
    records: count,
    fields,
    rules,
    bytes: Buffer.byteLength(padded),
    sha256: hash(padded),
  };
  try {
    await start(entry, "fresh_startup");
    await file(source);
    await measure("import", budget, () => click("Import evidence"));
    const imported = await rpc("state");
    assert.equal(imported.current.records, count);
    assert.equal(imported.current.fields.length, fields);
    assert.equal(imported.current.sha256, active.fixture.sha256);
    await file(policy);
    const options = page
      .locator(".setup details")
      .filter({ has: page.locator("summary", { hasText: /^Options$/ }) });
    if ((await options.getAttribute("open")) === null)
      await options.locator("summary").click();
    await click("Load policy");
    await measure("analyze", budget, async () => {
      await click("Analyze");
      await page.getByRole("table", { name: "Results", exact: true }).waitFor();
      await page
        .getByText(`${count / 2} shown / ${count}`, { exact: false })
        .waitFor();
    });
    const state = await rpc("state");
    assert.equal(state.summary.Review, count / 2);
    assert.equal(state.summary["No finding"], count / 2);
    assert.equal(state.summary.Unknown, 0);
    await page.getByRole("checkbox", { name: "Findings only" }).uncheck();
    await page
      .getByText(`${count} shown / ${count}`, { exact: false })
      .waitFor();
    const target = `owned-${String(count - 1).padStart(5, "0")}`;
    await measure("search", 1000, async () => {
      await page.getByLabel("Search records").fill(target);
      await page.getByText(`1 shown / ${count}`, { exact: false }).waitFor();
      const filtered = await rpc("findings", {
        revision: state.revision,
        query: target,
        minimum: "All",
        hide: false,
        page: 0,
      });
      assert.equal(filtered.rows.length, 1);
      assert.equal(filtered.rows[0].row, count);
    });
    await measure("clear_search", 1000, async () => {
      await click("Clear");
      await page
        .getByText(`${count} shown / ${count}`, { exact: false })
        .waitFor();
    });
    active.before = await resultDigest();
    await page.screenshot({ path: path.join(current, "results.png") });
    await click("Save case");
    await page.getByLabel("Case name", { exact: true }).fill(active.name);
    await measure("save_library", budget, () => click("Save to library"));
    const entries = (await rpc("library_list")).entries;
    assert.equal(entries.length, 1);
    active.caseBytes = fs.statSync(
      path.join(profile, "cases", entries[0].id, "case.json"),
    ).size;
    await stop();
    await start(entry, "saved_library_startup");
    await click("Case library");
    await measure("reopen", budget, async () => {
      await click("Open case");
      await page.getByRole("table", { name: "Results", exact: true }).waitFor();
    });
    active.after = await resultDigest();
    assert.deepEqual(active.after, active.before);
    assert.equal(hash(fs.readFileSync(source)), active.fixture.sha256);
    await page.screenshot({ path: path.join(current, "reopened.png") });
    await pause(100);
    await stop();
    const gaps = active.heartbeatGapsMs.toSorted((a, b) => a - b);
    assert.ok(gaps.length > 0);
    active.heartbeat = {
      count: gaps.length,
      maximumMs: gaps.at(-1),
      p95Ms: gaps[Math.ceil(gaps.length * 0.95) - 1],
    };
    assert.ok(active.heartbeat.maximumMs <= 500);
    assert.ok(active.heartbeat.p95Ms <= 100);
    active.passed = true;
  } catch (error) {
    active.error = error.stack;
    if (page)
      await page
        .screenshot({ path: path.join(current, "failure.png") })
        .catch(() => {});
    throw error;
  } finally {
    await stop();
    fs.writeFileSync(
      path.join(folder, "desktop.json"),
      JSON.stringify(report, null, 2),
    );
  }
}
(async () => {
  for (let repeat = 1; repeat <= 2; repeat++)
    for (const kind of ["representative", "combined-limits"])
      await scenario(kind, repeat);
  assert.deepEqual(report.errors, []);
  report.passed =
    report.scenarios.length === 4 && report.scenarios.every((s) => s.passed);
})()
  .catch((error) => {
    report.error = error.stack;
    process.exitCode = 1;
  })
  .finally(() => {
    fs.writeFileSync(
      path.join(folder, "desktop.json"),
      JSON.stringify(report, null, 2),
    );
    emit({ type: "result", passed: report.passed });
  });

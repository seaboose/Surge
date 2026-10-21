// Repeatable, isolated real-Electron workload; all evidence is synthetic.
const { _electron: electron } = require("playwright");
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const PYTHON = require("./runtime.cjs").pythonPath();
const root = path.resolve(__dirname, "..");
const label = process.argv[2] || "measurement";
const diagnostic = process.argv.includes("--diagnostic");
const soak = process.argv.includes("--soak");
const leakCheck = process.argv.includes("--leak-check");
if ((leakCheck || diagnostic) && soak)
  throw Error(
    "Keep forced-collection diagnostics separate from normal soak measurements.",
  );
const minutes = Number(
  process.argv.find((x) => x.startsWith("--minutes="))?.split("=")[1] || 5,
);
if (!Number.isInteger(minutes) || minutes < 1 || minutes > 10)
  throw Error("Use 1–10 investigation minutes.");
if (!/^[a-z0-9-]+$/.test(label)) throw Error("Use a simple run label.");
const folder = fs.mkdtempSync(
  path.join(root, "verification/electron/memory-" + label + "-"),
);
const stage = path.join(folder, "stage.txt"),
  stop = path.join(folder, "stop"),
  samples = path.join(folder, "samples.jsonl");
const entry = path.join(folder, "entry.cjs");
fs.writeFileSync(
  entry,
  `require('electron').app.setPath('userData',${JSON.stringify(path.join(folder, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
const incoming = path.join(folder, "large.json"),
  reference = path.join(folder, "reference.json"),
  policy = path.join(folder, "policy.json"),
  saved = path.join(folder, "case.json");
// Same maximum-count source as the workflow suite; release the generator before launching.
{
  const fd = fs.openSync(incoming, "w");
  fs.writeSync(fd, "[");
  for (let i = 0; i < 10000; i++) {
    const row = {
      id: i + 1,
      session: "large-session",
      time: i,
      reading: i % 13 === 0 ? 80 : 10,
      user: "ordinary-user",
      message: "Legitimate activity",
    };
    for (let f = 0; f < 58; f++) row["field" + f] = "value " + i;
    fs.writeSync(fd, (i ? "," : "") + JSON.stringify(row));
  }
  fs.writeSync(fd, "]");
  fs.closeSync(fd);
}
fs.writeFileSync(
  reference,
  JSON.stringify([8, 9, 10, 11, 12].map((reading) => ({ reading }))),
);
fs.writeFileSync(
  policy,
  JSON.stringify({
    schema: "surge-policy-v1",
    settings: {
      features: ["reading"],
      session: "session",
      event_id: "id",
      time: "time",
      time_format: "milliseconds",
      threshold: 6,
      context: { User: "user" },
      rules: [
        {
          name: "Bound",
          field: "reading",
          op: "gt",
          value: 70,
          priority: "Critical",
        },
      ],
    },
  }),
);
let app, page, sampler;
const stages = [],
  errors = [];
async function ready() {
  await page.waitForFunction(() => !document.querySelector(".app.busy"));
}
async function click(name) {
  await page.getByRole("button", { name, exact: true }).click();
  await ready();
}
async function dialog(file, save = false) {
  await app.evaluate(
    ({ dialog }, { file, save }) => {
      if (save)
        dialog.showSaveDialog = async () => ({
          canceled: false,
          filePath: file,
        });
      else
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [file],
        });
    },
    { file, save },
  );
}
async function checkpoint(name, action) {
  fs.writeFileSync(stage + ".next", name);
  fs.renameSync(stage + ".next", stage);
  const begin = Date.now();
  if (action) await action();
  // Fixed settling interval, no forced GC or working-set trimming.
  await page.waitForTimeout(800);
  const dom = await page.evaluate(() => ({
    nodes: document.querySelectorAll("*").length,
    heap: performance.memory
      ? {
          used: performance.memory.usedJSHeapSize,
          total: performance.memory.totalJSHeapSize,
        }
      : null,
  }));
  const processes = await app.evaluate(({ app }) =>
    app
      .getAppMetrics()
      .map((p) => ({ pid: p.pid, type: p.type, memory: p.memory })),
  );
  const mainHeap = await app.evaluate(() => process.memoryUsage());
  const cdp = await page.context().newCDPSession(page);
  const counters = await cdp.send("Memory.getDOMCounters");
  const liveHeap = await cdp.send("Runtime.getHeapUsage");
  await cdp.detach();
  stages.push({
    name,
    elapsedMs: Date.now() - begin,
    dom,
    processes,
    mainHeap,
    counters,
    liveHeap,
  });
  console.log("MEASURED", name);
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
  page.setDefaultTimeout(20000);
  page.on("pageerror", (e) => errors.push(e.message));
  await page
    .getByRole("button", { name: "Import data", exact: true })
    .waitFor();
  sampler = spawn(
    PYTHON,
    [
      "-B",
      path.join(root, "verification/sample_memory.py"),
      String(app.process().pid),
      samples,
      stage,
      stop,
      soak || leakCheck ? "1200" : "180",
    ],
    { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] },
  );
  let samplerError = "";
  sampler.stderr.on("data", (x) => (samplerError += x));
  await checkpoint("empty");
  await checkpoint("import", async () => {
    await dialog(incoming);
    await click("Import data");
    await page.waitForFunction(
      () =>
        document.querySelector('table[aria-label="Preview"] tbody')?.children
          .length === 100,
    );
  });
  await checkpoint("configure", async () => {
    await dialog(reference);
    await click("Import reference");
    await dialog(policy);
    await click("Load policy");
  });
  await checkpoint("analyze", async () => {
    await click("Analyze");
    await page.waitForFunction(() =>
      document
        .querySelector(".chart-readout")
        ?.textContent.includes("Record 1 ·"),
    );
  });
  await checkpoint("investigate", async () => {
    for (let i = 0; i < 15; i++) {
      await page
        .getByRole("group", { name: "Numeric chart" })
        .press("ArrowRight");
      await page.waitForFunction(
        (row) =>
          document
            .querySelector(".evidence")
            ?.textContent.includes(`ID: ${row}\n`),
        i + 2,
      );
    }
    await page.getByLabel("Search records").fill("ordinary-user");
    await page.waitForTimeout(180);
    await click("Details");
    await page.getByText("Constant references use", { exact: false }).waitFor();
    await click("Findings");
  });
  await checkpoint("save", async () => {
    await dialog(saved, true);
    await click("Save case");
    assert.ok(fs.existsSync(saved));
  });
  await checkpoint("compare", async () => {
    await click("Compare");
    await dialog(saved);
    await click("Choose case");
    await page.waitForFunction(() =>
      document.querySelector(".comparison-sources"),
    );
  });
  await checkpoint("repeat-import", async () => {
    await click("Data");
    await dialog(incoming);
    await click("Import data");
    await page.waitForFunction(
      () =>
        document.querySelector('table[aria-label="Preview"] tbody')?.children
          .length === 100,
    );
  });
  await checkpoint("small-replacement", async () => {
    const tiny = path.join(folder, "tiny.json");
    fs.writeFileSync(tiny, '[{"value":1}]');
    await dialog(tiny);
    await click("Import data");
    await page.waitForFunction(
      () =>
        document.querySelector('table[aria-label="Preview"] tbody')?.children
          .length === 1,
    );
  });
  if (diagnostic) {
    await checkpoint("small-idle", () => page.waitForTimeout(5000));
    await checkpoint("small-diagnostic-gc", async () => {
      const cdp = await page.context().newCDPSession(page);
      await cdp.send("HeapProfiler.collectGarbage");
      await cdp.detach();
    });
  }
  const dense = path.join(folder, "dense.json");
  fs.writeFileSync(
    dense,
    JSON.stringify([
      Object.fromEntries(
        Array.from({ length: 64 }, (_, i) => ["field" + i, "a".repeat(4096)]),
      ),
    ]),
  );
  await checkpoint("dense-search", async () => {
    await dialog(dense);
    await click("Import data");
    await page
      .getByRole("table", { name: "Preview" })
      .locator("tbody tr")
      .first()
      .click();
    await page.getByLabel("Find in record", { exact: true }).fill("a");
    await page
      .getByText("1 / 262144 matches · 64 fields", { exact: true })
      .waitFor();
    assert.equal(await page.locator("mark").count(), 200);
  });
  let investigationSteps = 0;
  if (soak) {
    const tiny = path.join(folder, "tiny.json");
    async function loadLarge() {
      await click("Data");
      await dialog(incoming);
      await click("Import data");
      await dialog(policy);
      await click("Load policy");
      await click("Analyze");
      await page.waitForFunction(() =>
        document
          .querySelector(".chart-readout")
          ?.textContent.includes("Record 1 ·"),
      );
      await click("Compare");
      await dialog(saved);
      await click("Choose case");
      await click("Findings");
    }
    for (let cycle = 1; cycle <= 8; cycle++) {
      await checkpoint("cycle-large-" + cycle, loadLarge);
      await checkpoint("cycle-small-" + cycle, async () => {
        await click("Data");
        await dialog(tiny);
        await click("Import data");
        await page.waitForFunction(
          () =>
            document.querySelector('table[aria-label="Preview"] tbody')
              ?.children.length === 1,
        );
      });
    }
    await checkpoint("long-start", loadLarge);
    let selected = 1;
    for (let minute = 1; minute <= minutes; minute++) {
      await checkpoint("long-minute-" + minute, async () => {
        const deadline = Date.now() + 60000;
        while (Date.now() < deadline) {
          await page
            .getByRole("group", { name: "Numeric chart" })
            .press("ArrowRight");
          selected++;
          await page.waitForFunction(
            (row) =>
              document
                .querySelector(".evidence")
                ?.textContent.includes(`ID: ${row}\n`),
            selected,
          );
          investigationSteps++;
          if (investigationSteps % 25 === 0) {
            await click("Data");
            await page
              .getByRole("table", { name: "Preview" })
              .locator("tbody tr")
              .first()
              .click();
            await page.getByRole("region", { name: "Full record" }).waitFor();
            await click("Details");
            await click("Compare");
            await click("Findings");
          }
          await page.waitForTimeout(75);
        }
      });
    }
    await checkpoint("long-small-replacement", async () => {
      await click("Data");
      await dialog(tiny);
      await click("Import data");
      await page.waitForFunction(
        () =>
          document.querySelector('table[aria-label="Preview"] tbody')?.children
            .length === 1,
      );
    });
    await checkpoint("long-small-idle", () => page.waitForTimeout(10000));
  }
  if (leakCheck) {
    // Diagnostic only: equal small workspaces after warmup and full renderer GC.
    // This measures surviving objects, never ordinary operational memory gains.
    for (let cycle = 0; cycle <= 8; cycle++) {
      if (cycle) {
        await click("Data");
        await dialog(incoming);
        await click("Import data");
        await dialog(policy);
        await click("Load policy");
        await click("Analyze");
        await page
          .getByRole("group", { name: "Numeric chart" })
          .press("ArrowRight");
        await click("Compare");
        await dialog(saved);
        await click("Choose case");
      }
      await click("Data");
      await dialog(path.join(folder, "tiny.json"));
      await click("Import data");
      await page.waitForFunction(
        () =>
          document.querySelector('table[aria-label="Preview"] tbody')?.children
            .length === 1,
      );
      await page.waitForTimeout(1000);
      await checkpoint("retained-small-" + cycle, async () => {
        const cdp = await page.context().newCDPSession(page);
        await cdp.send("HeapProfiler.collectGarbage");
        await cdp.detach();
      });
    }
    const points = stages.filter((s) => s.name.startsWith("retained-small-"));
    const floor = points[1],
      last = points.at(-1);
    assert.ok(
      last.counters.nodes <= floor.counters.nodes + 100,
      "Small workspace retained extra DOM nodes",
    );
    assert.ok(
      last.counters.jsEventListeners <= floor.counters.jsEventListeners + 50,
      "Small workspace retained listeners",
    );
    assert.ok(
      last.liveHeap.usedSize <= floor.liveHeap.usedSize + 2 * 1024 * 1024,
      "Small workspace retained over 2 MiB more JS heap",
    );
  }
  fs.writeFileSync(stop, "stop");
  await new Promise((resolve, reject) => {
    sampler.once("exit", (code) =>
      code ? reject(Error(samplerError)) : resolve(),
    );
  });
  const data = fs
    .readFileSync(samples, "utf8")
    .trim()
    .split("\n")
    .map(JSON.parse);
  const summary = stages.map((s) => {
    const rows = data
      .filter((x) => x.phase === s.name)
      .map((x) => {
        const known = x.processes.filter((p) => !p.error);
        return {
          ms: x.ms,
          private: known.reduce((n, p) => n + p.private, 0),
          workingSet: known.reduce((n, p) => n + p.working_set, 0),
          pythonPrivate: known
            .filter((p) => p.name.toLowerCase().startsWith("python"))
            .reduce((n, p) => n + p.private, 0),
        };
      });
    assert.ok(rows.length >= 3, `Insufficient samples: ${s.name}`);
    const tail = rows.slice(-5),
      median = (key) =>
        tail.map((x) => x[key]).sort((a, b) => a - b)[
          Math.floor(tail.length / 2)
        ];
    return {
      ...s,
      samples: rows.length,
      peakPrivate: Math.max(...rows.map((x) => x.private)),
      settledPrivate: median("private"),
      settledWorkingSet: median("workingSet"),
      settledPythonPrivate: median("pythonPrivate"),
    };
  });
  assert.deepEqual(errors, []);
  assert.ok(
    data.every((s) =>
      s.processes.some((p) => p.name?.toLowerCase().startsWith("python")),
    ),
  );
  assert.equal(
    data.flatMap((s) => s.processes).filter((p) => p.error).length,
    0,
    "Incomplete process accounting",
  );
  const result = {
    label,
    folder,
    sourceBytes: fs.statSync(incoming).size,
    records: 10000,
    fields: 64,
    intervalMs: 100,
    metric:
      "Windows PrivateUsage: private committed bytes; not resident RAM. Working sets include shared pages.",
    forcedGC: diagnostic || leakCheck,
    leakCheck,
    soak,
    investigationMinutes: soak ? minutes : 0,
    investigationSteps,
    summary,
  };
  fs.writeFileSync(
    path.join(root, `verification/electron/memory-${label}.json`),
    JSON.stringify(result, null, 2),
  );
  console.log(
    JSON.stringify(
      summary.map((s) => ({
        phase: s.name,
        privateMiB: Math.round(s.settledPrivate / 1048576),
        peakMiB: Math.round(s.peakPrivate / 1048576),
        pythonMiB: Math.round(s.settledPythonPrivate / 1048576),
        nodes: s.dom.nodes,
      })),
    ),
  );
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    fs.writeFileSync(stop, "stop");
    if (app) await app.close();
  });

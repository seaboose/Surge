// Actual Electron integration checks. Dialogs/clipboard are intercepted only by
// the test driver; production has no test API or fixture imports.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const OUT = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(OUT, { recursive: true });
const files = fs.mkdtempSync(path.join(OUT, "parity-"));
// Isolate tests from an investigator's running window, saved size and preferences.
const entry = path.join(files, "test-entry.cjs");
fs.writeFileSync(
  entry,
  `
const {app,ipcMain}=require('electron');
app.setPath('userData',${JSON.stringify(path.join(files, "profile"))});
global.__requests=[];global.__comparisonDelay=0;global.__chartDelay=0;
const handle=ipcMain.handle.bind(ipcMain);
ipcMain.handle=(channel,handler)=>handle(channel,async(event,method,args)=>{
  global.__requests.push(method);
  if(method==='details')await new Promise(resolve=>setTimeout(resolve,200));
  if(method==='comparison'&&args.row)await new Promise(resolve=>setTimeout(resolve,global.__comparisonDelay));
  if(method==='chart'&&args.row)await new Promise(resolve=>setTimeout(resolve,global.__chartDelay));
  return handler(event,method,args);
});
require(${JSON.stringify(path.join(__dirname, "main.cjs"))});
`,
);
const rows = Array.from({ length: 205 }, (_, i) => ({
  id: i + 1,
  session: "session-a",
  time: (i + 1) * 1000,
  reading: i % 2 === 0 ? 10 : 80,
  user: "Straße 😀",
  message: '<img src=x onerror="alert(1)">',
  text: "Line\n😀 Straße",
}));
rows[100].reading = null;
delete rows[150].reading;
const incoming = path.join(files, "incoming.json"),
  reference = path.join(files, "reference.json");
// Inject a real integer beyond JS's exact range in source bytes.
fs.writeFileSync(
  incoming,
  JSON.stringify(rows).replaceAll(
    '"message":',
    '"large":9007199254740993,"message":',
  ),
);
fs.writeFileSync(
  reference,
  JSON.stringify([8, 9, 10, 11, 12].map((reading) => ({ reading }))),
);
const malformed = path.join(files, "bad.jsonl");
fs.writeFileSync(malformed, '{"x":[1,2]}\n');
const policy = path.join(files, "settings.json");
const config = {
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
};
fs.writeFileSync(
  policy,
  JSON.stringify({ schema: "surge-policy-v1", settings: config }),
);
const saved = path.join(files, "saved.case.json"),
  changed = path.join(files, "changed.case.json");
let app, page;
const errors = [];
const checks = [];
let performanceCheck = null;
async function check(name, fn) {
  await fn();
  checks.push(name);
  console.log("PASS", name);
}
async function ready() {
  await page.waitForFunction(
    () => !document.querySelector('.app[data-working="true"]'),
  );
  await page.locator("dialog").count();
}
async function fileDialog(file, save = false) {
  await app.evaluate(
    ({ dialog }, args) => {
      if (args.save)
        dialog.showSaveDialog = async () => ({
          canceled: false,
          filePath: args.file,
        });
      else
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [args.file],
        });
    },
    { file, save },
  );
}
async function click(text) {
  await require("./test-export-menu.cjs").revealExport(page, text);
  if (text === "Open saved case") {
    await page
      .getByRole("button", { name: "Case library", exact: true })
      .click();
    await page
      .getByRole("dialog", { name: "Case library", exact: true })
      .waitFor();
    text = "Open case file";
  }
  if (
    ["Load policy", "Save policy", "Edit rules", "Map context"].includes(text)
  ) {
    const options = page
      .locator(".setup details")
      .filter({ has: page.locator("summary", { hasText: /^Options$/ }) });
    if ((await options.getAttribute("open")) === null)
      await options.locator("summary").click();
  }
  await page.getByRole("button", { name: text, exact: true }).click();
  await ready();
}
async function rpc(method, args = {}) {
  const r = await page.evaluate(
    async ({ method, args }) => window.surge.request(method, args),
    { method, args },
  );
  if (!r.ok) throw new Error(r.error);
  return r.value;
}
async function visible(locator) {
  await locator.waitFor({ state: "visible" });
}
async function screenshot(name) {
  await page.screenshot({ path: path.join(OUT, name + ".png") });
  if (
    [
      "empty",
      "mapping-inspector",
      "findings",
      "comparison",
      "configuration",
    ].includes(name)
  )
    await require("./visual-audit.cjs").auditPage(app, page, name);
}
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  const started = Date.now();
  app = await electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
    timeout: 30000,
  });
  page = await app.firstWindow();
  page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => errors.push(e.message));
  await visible(
    page.getByRole("button", { name: "Import evidence", exact: true }),
  );
  const startupMs = Date.now() - started;
  // Never write to the user's clipboard during a test.
  await app.evaluate(({ clipboard }) => {
    global.__copied = [];
    clipboard.writeText = (text) => global.__copied.push(text);
  });
  await check("empty screen and hardened renderer", async () => {
    assert.equal(
      await page
        .getByRole("heading", {
          name: "Surge",
          exact: true,
        })
        .count(),
      1,
    );
    assert.equal(
      await page.getByRole("button", { name: "Analyze", exact: true }).count(),
      0,
    );
    const isolation = await page.evaluate(() => ({
      require: typeof window.require,
      process: typeof window.process,
    }));
    assert.deepEqual(isolation, { require: "undefined", process: "undefined" });
    const settings = await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences(),
    );
    assert.equal(settings.sandbox, true);
    assert.equal(settings.contextIsolation, true);
    assert.equal(settings.nodeIntegration, false);
    await screenshot("empty");
    await app.evaluate(({ dialog }) => {
      dialog.showOpenDialog = async () => ({ canceled: true, filePaths: [] });
    });
    await click("Import evidence");
    assert.equal((await rpc("state")).current, null);
  });
  await check(
    "import preserves malformed-source diagnostics and previous data",
    async () => {
      await fileDialog(incoming);
      await click("Import evidence");
      await visible(page.getByRole("table", { name: "Preview" }));
      await require("./visual-audit.cjs").auditPage(app, page, "data");
      const before = await rpc("state");
      await fileDialog(malformed);
      await click("Import evidence");
      await visible(page.getByRole("dialog"));
      assert.match(
        await page.getByRole("dialog").innerText(),
        /Record 1.*line 1.*field 'x'/s,
      );
      await click("Close");
      assert.equal((await rpc("state")).current.sha256, before.current.sha256);
      assert.equal(await page.locator("img").count(), 0);
    },
  );
  await check("reference, reusable policy and mapping warnings", async () => {
    await fileDialog(reference);
    await click("Import reference");
    await fileDialog(policy);
    await click("Load policy");
    await page
      .locator("button.note")
      .filter({ hasText: "2 missing" })
      .first()
      .waitFor()
      .catch(async () => {
        assert.ok(
          (await rpc("state")).notes.some((n) => n.rows?.includes(101)),
        );
      });
    const warning = page
      .locator("button.note")
      .filter({ hasText: /101/ })
      .first();
    await warning.click();
    await visible(page.locator(".pinned"));
    await page
      .getByRole("table", { name: "Preview" })
      .locator("tbody tr")
      .first()
      .click();
    await visible(page.getByRole("region", { name: "Full record" }));
    assert.match(
      await page.locator(".inspector-controls").innerText(),
      /Record 101/,
    );
  });
  await check(
    "warning stays visible through full values, Unicode matches and copy scopes",
    async () => {
      await page.getByLabel("Field", { exact: true }).selectOption("user");
      await click("Next record");
      await page.waitForFunction(() =>
        document
          .querySelector(".inspector-controls")
          ?.textContent.includes("Record 151"),
      );
      await page.waitForFunction(
        () =>
          !document.querySelector(".record-inspector button:last-child")
            ?.disabled,
      );
      await visible(page.locator(".full-values .field-value").first());
      assert.equal(
        await page.getByLabel("Field", { exact: true }).inputValue(),
        "user",
      );
      await click("Previous record");
      await page.waitForFunction(() =>
        document
          .querySelector(".inspector-controls")
          ?.textContent.includes("Record 101"),
      );
      await page.getByLabel("Find in record", { exact: true }).fill("STRASSE");
      await visible(page.locator("mark").first());
      await page.locator("mark").last().click();
      await click("Copy match");
      assert.equal(await app.evaluate(() => global.__copied.at(-1)), "Straße");
      await click("Copy value");
      assert.match(await app.evaluate(() => global.__copied.at(-1)), /Straße/);
      await click("Copy record");
      assert.equal(
        JSON.parse(await app.evaluate(() => global.__copied.at(-1))).id,
        101,
      );
      assert.equal(await page.locator(".pinned").count(), 1);
      await click("Next record");
      await page.waitForFunction(() =>
        document
          .querySelector(".inspector-controls")
          ?.textContent.includes("Record 151"),
      );
      await page.getByLabel("Find in record", { exact: true }).fill("Missing");
      await visible(page.locator("mark").first());
      await click("Copy match");
      assert.equal(await app.evaluate(() => global.__copied.at(-1)), "Missing");
      assert.equal(
        await page
          .getByRole("button", { name: "Copy value", exact: true })
          .isDisabled(),
        true,
      );
      await page
        .getByLabel("Find in record", { exact: true })
        .fill("9007199254740993");
      await visible(page.locator("mark").first());
      await click("Copy value");
      assert.equal(
        await app.evaluate(() => global.__copied.at(-1)),
        "9007199254740993",
      );
      await page.getByLabel("Find in record", { exact: true }).fill("😀");
      await visible(page.locator("mark").first());
      await page.locator("mark").first().click();
      await click("Copy match");
      assert.equal(await app.evaluate(() => global.__copied.at(-1)), "😀");
      await page.getByLabel("Find in record", { exact: true }).press("F3");
      await page.waitForFunction(
        () =>
          document
            .querySelector(".current-match")
            ?.getAttribute("data-match") === "1",
      );
      await page
        .getByLabel("Find in record", { exact: true })
        .press("Shift+F3");
      await page.waitForFunction(
        () =>
          document
            .querySelector(".current-match")
            ?.getAttribute("data-match") === "0",
      );
      await app.evaluate(({ clipboard }) => {
        clipboard.writeText = () => {
          throw new Error("Clipboard unavailable");
        };
      });
      await click("Copy match");
      await visible(page.getByRole("dialog"));
      assert.match(
        await page.getByRole("dialog").innerText(),
        /Clipboard unavailable/,
      );
      await click("Close");
      assert.equal(await page.locator(".pinned").isVisible(), true);
      await app.evaluate(({ clipboard }) => {
        clipboard.writeText = (text) => global.__copied.push(text);
      });
      await screenshot("mapping-inspector");
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(1100, 760),
      );
      await screenshot("mapping-inspector-minimum");
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
      );
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(1360, 880),
      );
      await click("Back to preview");
      const previewTable = page.getByRole("table", { name: "Preview" });
      await previewTable.locator("tbody tr").last().click();
      await page.getByLabel("Find in record", { exact: true }).fill("STRASSE");
      await visible(page.locator("mark").first());
      await click("Next record");
      await page.waitForFunction(() =>
        document
          .querySelector(".inspector-controls")
          ?.textContent.includes("Record 101"),
      );
      assert.equal(
        await page.getByLabel("Find in record", { exact: true }).inputValue(),
        "STRASSE",
      );
      await visible(page.locator("mark").first());
    },
  );
  await check(
    "analysis, findings search, exact chart selection and export",
    async () => {
      await app.evaluate(() => {
        global.__requests = [];
      });
      await click("Analyze");
      await visible(page.getByRole("table", { name: "Results" }));
      await visible(page.locator(".evidence .observed"));
      assert.equal(
        await app.evaluate(() =>
          global.__requests.some((m) => ["comparison", "details"].includes(m)),
        ),
        false,
      );
      const s = await rpc("state");
      assert.deepEqual(s.summary, {
        total: 205,
        Review: 102,
        Unknown: 2,
        "No finding": 101,
        rows_with_gaps: 2,
      });
      await page.getByLabel("Search records").fill("no-such-record");
      await visible(
        page.getByText("No records match these filters.", { exact: false }),
      );
      assert.match(
        await page.locator("main").innerText(),
        /2 records with gaps hidden by search/,
      );
      await page.evaluate(() => {
        window.__plot = document.querySelector('svg g[data-row="2"]');
      });
      await app.evaluate(() => {
        global.__chartDelay = 500;
      });
      await page.locator('svg g[data-row="2"] circle').click();
      assert.equal(
        await page.evaluate(
          () => document.querySelector('svg g[data-row="2"]') === window.__plot,
        ),
        true,
      );
      await page.waitForFunction(() =>
        document.querySelector(".evidence")?.textContent.includes("ID: 2"),
      );
      await page.waitForFunction(() =>
        document
          .querySelector(".chart-readout")
          ?.textContent.includes("reading: 80"),
      );
      await app.evaluate(() => {
        global.__chartDelay = 0;
      });
      assert.match(
        await page.locator(".chart-readout").innerText(),
        /reading: 80/,
      );
      await page
        .getByRole("group", { name: "Numeric chart" })
        .press("ArrowRight");
      await page.waitForFunction(() =>
        document.querySelector(".evidence")?.textContent.includes("ID: 3"),
      );
      await click("Return to filters");
      await click("Clear");
      await fileDialog(saved, true);
      await click("Export case file");
      assert.ok(fs.existsSync(saved));
      await fileDialog(path.join(files, "alerts.jsonl"), true);
      await click("Export alerts");
      const exported = fs
        .readFileSync(path.join(files, "alerts.jsonl"), "utf8")
        .trim()
        .split("\n")
        .map(JSON.parse);
      assert.equal(exported[0].alerts, 104);
      assert.ok(exported.some((r) => r.row === 101));
      await screenshot("findings");
    },
  );
  await check(
    "rules editor, stale comparisons and aligned drill-through",
    async () => {
      await click("Data");
      await click("Edit rules");
      await require("./visual-audit.cjs").auditPage(app, page, "rules-dialog");
      await page
        .getByRole("textbox", { name: "Rules", exact: true })
        .fill("{invalid draft");
      await click("Close");
      await click("Map context");
      await require("./visual-audit.cjs").auditPage(
        app,
        page,
        "context-dialog",
      );
      await page.getByLabel("Host", { exact: true }).selectOption("message");
      await click("Apply context");
      assert.equal((await rpc("state")).config.context.Host, "message");
      await click("Edit rules");
      assert.equal(
        JSON.parse(
          await page
            .getByRole("textbox", { name: "Rules", exact: true })
            .inputValue(),
        )[0].name,
        "Bound",
      );
      await page
        .getByRole("textbox", { name: "Rules", exact: true })
        .fill("[]");
      await click("Apply rules");
      const threshold = page.getByLabel("Threshold", { exact: true });
      await threshold.fill("60");
      await threshold.press("Enter");
      await ready();
      await click("Analyze");
      await fileDialog(changed, true);
      await click("Export case file");
      await click("Compare");
      await fileDialog(saved);
      await click("Choose case");
      await page
        .getByLabel("Changed records", { exact: true })
        .selectOption("2");
      await page.waitForFunction(() =>
        document
          .querySelector(".comparison")
          ?.textContent.includes("Source record"),
      );
      assert.match(
        await page.getByRole("table", { name: "Comparison" }).innerText(),
        /Not configured/,
      );
      await screenshot("comparison");
      await app.evaluate(() => {
        global.__comparisonDelay = 800;
      });
      await page
        .getByLabel("Changed records", { exact: true })
        .selectOption("4");
      await visible(page.getByText("Loading comparison…", { exact: true }));
      assert.equal(await page.locator(".comparison tbody tr").count(), 0);
      await page.waitForFunction(() =>
        document
          .querySelector(".comparison tbody")
          ?.textContent.includes("Source record"),
      );
      const source = page.locator(".comparison tbody tr").filter({
        has: page.locator("td:first-child", { hasText: "Source record" }),
      });
      assert.match(await source.innerText(), /4/);
      await app.evaluate(() => {
        global.__comparisonDelay = 0;
      });
      await click("Settings");
      await page.getByLabel("Changes only", { exact: true }).check();
      await page.waitForFunction(
        () =>
          ![...document.querySelectorAll(".comparison tbody tr")].some(
            (r) => r.lastElementChild.textContent === "Same",
          ),
      );
      await click("Data");
      await fileDialog(policy);
      await click("Load policy");
      assert.equal(
        await page
          .getByRole("button", { name: "Compare", exact: true })
          .isDisabled(),
        true,
      );
      await click("Analyze");
      await click("Compare");
      await visible(
        page.getByText("Choose a saved case to compare.", { exact: true }),
      );
    },
  );
  await check(
    "saved legacy format reopens and UI stays bounded at minimum window size",
    async () => {
      await click("Data");
      await fileDialog(saved);
      await click("Open saved case");
      await visible(page.getByRole("table", { name: "Results" }));
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(1100, 760),
      );
      await page.waitForTimeout(150);
      assert.ok(
        (await page
          .getByRole("table", { name: "Results" })
          .locator("tbody tr")
          .count()) <= 100,
      );
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
      );
      await screenshot("findings-minimum");
      await click("Case details");
      await visible(
        page.getByText("Constant references use", { exact: false }),
      );
      assert.match(await page.locator("main").innerText(), /accuracy|Accuracy/);
      await require("./visual-audit.cjs").auditPage(app, page, "case-details");
    },
  );
  await check(
    "renderer cannot bypass file dialogs or reach network",
    async () => {
      await assert.rejects(() => rpc("open", { path: incoming }));
      await assert.rejects(() => rpc("exec", { command: "calc.exe" }));
      assert.equal(
        await page.evaluate(() =>
          fetch("https://example.com").then(
            () => true,
            () => false,
          ),
        ),
        false,
      );
      assert.equal(
        await page.evaluate(() => window.open("https://example.com")),
        null,
      );
      const s = await rpc("state");
      const failed = await page.evaluate(
        async (revision) =>
          window.surge.request("copy", {
            revision: revision - 1,
            row: 1,
            scope: "record",
          }),
        s.revision,
      );
      assert.equal(failed.ok, false);
    },
  );
  await check(
    "navigation retains search, selection and split preferences",
    async () => {
      await click("Results");
      await page.getByLabel("Search records").fill("STRASSE");
      await page.waitForFunction(
        () =>
          document.querySelector('[aria-label="Search records"]').value ===
          "STRASSE",
      );
      await page
        .getByRole("separator", { name: "Resize evidence" })
        .press("ArrowLeft");
      const position = await page
        .getByRole("separator", { name: "Resize evidence" })
        .getAttribute("aria-valuenow");
      await click("Data");
      await click("Results");
      assert.equal(
        await page.getByLabel("Search records").inputValue(),
        "STRASSE",
      );
      assert.equal(
        await page
          .getByRole("separator", { name: "Resize evidence" })
          .getAttribute("aria-valuenow"),
        position,
      );
      await page.keyboard.press("Alt+1");
      await visible(
        page.getByRole("button", { name: "Import evidence", exact: true }),
      );
      await page.keyboard.press("Control+f");
      await visible(page.getByLabel("Search records"));
      assert.equal(
        await page
          .getByLabel("Search records")
          .evaluate((el) => el === document.activeElement),
        true,
      );
      await page.keyboard.press("Alt+5");
      await visible(
        page.getByText("Constant references use", { exact: false }),
      );
      await page.keyboard.press("Alt+2");
      await page.emulateMedia({ reducedMotion: "reduce" });
      await require("./test-export-menu.cjs").revealExport(
        page,
        "Export case file",
      );
      assert.equal(
        await page
          .getByRole("button", { name: "Export case file", exact: true })
          .evaluate((el) => getComputedStyle(el).transitionDuration),
        "0s",
      );
    },
  );
  await check(
    "hidden panes stay idle and unchanged views reuse data",
    async () => {
      await page.waitForTimeout(350);
      await click("Case details");
      await visible(
        page.getByText("Constant references use", { exact: false }),
      );
      await app.evaluate(() => {
        global.__requests = [];
      });
      await click("Results");
      await visible(page.locator(".evidence .observed"));
      await click("Case details");
      await page.waitForTimeout(300);
      assert.deepEqual(await app.evaluate(() => global.__requests), []);
    },
  );
  await check(
    "mapping edits retain setup scroll and keyboard focus",
    async () => {
      await click("Data");
      const threshold = page.getByLabel("Threshold", { exact: true });
      await threshold.scrollIntoViewIfNeeded();
      await threshold.focus();
      const top = await page.locator(".setup").evaluate((el) => el.scrollTop);
      await threshold.fill("7");
      await threshold.press("Enter");
      await ready();
      assert.equal(
        await threshold.evaluate((el) => el === document.activeElement),
        true,
      );
      assert.ok(
        Math.abs(
          (await page.locator(".setup").evaluate((el) => el.scrollTop)) - top,
        ) < 3,
      );
      assert.equal((await rpc("state")).config.threshold, 7);
    },
  );
  await check(
    "dense search keeps full values with bounded selectable highlights",
    async () => {
      const dense = path.join(files, "dense.json");
      fs.writeFileSync(
        dense,
        JSON.stringify([
          Object.fromEntries(
            Array.from({ length: 64 }, (_, i) => [
              "field" + i,
              "a".repeat(4096),
            ]),
          ),
        ]),
      );
      await fileDialog(dense);
      await click("Import evidence");
      await page
        .getByRole("table", { name: "Preview" })
        .locator("tbody tr")
        .first()
        .click();
      await page.getByLabel("Find in record", { exact: true }).fill("a");
      await visible(
        page.getByText("1 / 262144 matches · 64 fields", { exact: true }),
      );
      assert.equal(await page.locator("mark").count(), 200);
      assert.equal(
        await page.locator(".full-values pre").first().innerText(),
        JSON.stringify("a".repeat(4096)),
      );
      await page.locator('mark[data-match="199"]').click();
      await click("Next match");
      await page.waitForFunction(
        () =>
          document
            .querySelector(".current-match")
            ?.getAttribute("data-match") === "200",
      );
      await click("Copy match");
      assert.equal(await app.evaluate(() => global.__copied.at(-1)), "a");
      await click("Copy value");
      assert.equal(
        await app.evaluate(() => global.__copied.at(-1)),
        JSON.stringify("a".repeat(4096)),
      );
      await click("Previous match");
      await page.waitForFunction(
        () =>
          document
            .querySelector(".current-match")
            ?.getAttribute("data-match") === "199",
      );
      assert.equal(await page.locator("mark").count(), 200);
      await screenshot("dense-search");
    },
  );
  await check(
    "maximum record and field counts stay bounded and responsive",
    async () => {
      const large = Array.from({ length: 10000 }, (_, i) => {
        const r = {
          id: i + 1,
          session: "large-session",
          time: i,
          reading: i % 13 === 0 ? 80 : 10,
          user: "ordinary-user",
          message: "Legitimate activity",
        };
        for (let f = 0; f < 58; f++) r["field" + f] = "value " + i;
        return r;
      });
      const file = path.join(files, "large.json");
      fs.writeFileSync(file, JSON.stringify(large));
      await click("Data");
      await fileDialog(file);
      const begin = Date.now();
      await click("Import evidence");
      await visible(page.getByRole("table", { name: "Preview" }));
      await page.waitForFunction(
        () =>
          document.querySelector('table[aria-label="Preview"] tbody')?.children
            .length === 100,
      );
      const importMs = Date.now() - begin;
      assert.equal(
        await page
          .getByRole("table", { name: "Preview" })
          .locator("tbody tr")
          .count(),
        100,
      );
      await fileDialog(policy);
      await click("Load policy");
      await page.evaluate(() => {
        window.__ticks = [];
        let previous = performance.now();
        window.__timer = setInterval(() => {
          const now = performance.now();
          window.__ticks.push(now - previous);
          previous = now;
        }, 20);
      });
      const analysisBegin = Date.now();
      await click("Analyze");
      await visible(page.getByRole("table", { name: "Results" }));
      await page.waitForFunction(
        () =>
          document.querySelector('table[aria-label="Results"] tbody')?.children
            .length === 100,
      );
      await visible(page.locator("svg g[data-row]").first());
      await visible(page.locator(".evidence .observed"));
      await page.waitForFunction(() =>
        document
          .querySelector(".chart-readout")
          ?.textContent.includes("Record 1 ·"),
      );
      const analysisMs = Date.now() - analysisBegin;
      const gaps = await page.evaluate(() => {
        clearInterval(window.__timer);
        return window.__ticks;
      });
      const maxFrameGap = Math.max(0, ...gaps);
      assert.equal((await rpc("state")).summary.total, 10000);
      const chartPoints = await page.locator("svg g[data-row]").count();
      assert.ok(chartPoints > 0 && chartPoints <= 2400);
      assert.ok(analysisMs < 10000, "Analysis exceeded 10 seconds");
      assert.ok(maxFrameGap < 1000, "UI stalled for at least a second");
      performanceCheck = {
        records: 10000,
        fields: 64,
        sourceBytes: fs.statSync(file).size,
        importMs,
        analysisMs,
        maxFrameGapMs: maxFrameGap,
        previewRows: 100,
        chartPoints: await page.locator("svg g[data-row]").count(),
      };
      await screenshot("large-source");
    },
  );
  await check(
    "wide previews keep every field reachable with bounded cells and exact copying",
    async () => {
      await click("Data");
      const preview = page.getByRole("table", { name: "Preview" }),
        pane = page.locator(".preview-table");
      assert.equal(await preview.getAttribute("aria-colcount"), "65");
      assert.equal(await preview.locator("tbody tr").count(), 100);
      assert.ok((await preview.locator("tbody td").count()) < 2200);
      const seen = new Set();
      const bounds = await pane.evaluate((el) => ({
        width: el.clientWidth,
        max: el.scrollWidth - el.clientWidth,
      }));
      for (
        let left = 0;
        left <= bounds.max + bounds.width;
        left += Math.floor(bounds.width / 2)
      ) {
        await pane.evaluate((el, left) => {
          el.scrollLeft = left;
        }, left);
        await page.waitForTimeout(35);
        for (const name of await preview
          .locator("th[aria-colindex]:not(.record-column)")
          .allTextContents())
          seen.add(name);
      }
      assert.equal(seen.size, 64);
      await visible(
        preview.getByRole("columnheader", { name: "field57", exact: true }),
      );
      assert.equal(
        await preview
          .locator("tbody tr")
          .first()
          .locator('td[aria-colindex="65"]')
          .innerText(),
        '"value 0"',
      );
      await preview
        .locator("tbody tr")
        .first()
        .locator("td.record-column")
        .click();
      await page.getByLabel("Field", { exact: true }).selectOption("field57");
      await click("Copy value");
      assert.equal(
        await app.evaluate(() => global.__copied.at(-1)),
        '"value 0"',
      );
      await preview.locator("tbody tr").first().press("End");
      await page.waitForFunction(() =>
        document
          .querySelector(".inspector-controls")
          ?.textContent.includes("Record 100 ·"),
      );
      await click("Copy value");
      assert.equal(
        await app.evaluate(() => global.__copied.at(-1)),
        '"value 99"',
      );
      await click("Next record");
      await page.waitForFunction(() =>
        document
          .querySelector(".inspector-controls")
          ?.textContent.includes("Record 101 ·"),
      );
      await click("Copy value");
      assert.equal(
        await app.evaluate(() => global.__copied.at(-1)),
        '"value 100"',
      );
      await pane.evaluate((el) => {
        el.scrollLeft = el.scrollWidth;
      });
      await visible(
        preview.getByRole("columnheader", { name: "field57", exact: true }),
      );
      await screenshot("wide-preview");
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
      );
      await click("Results");
      await click("Data");
      await visible(
        preview.getByRole("columnheader", { name: "field57", exact: true }),
      );
      assert.equal(
        await page.getByLabel("Field", { exact: true }).inputValue(),
        "field57",
      );
      const longField = "Very long evidence field ".repeat(4),
        longFile = path.join(files, "long-fields.json");
      fs.writeFileSync(
        longFile,
        JSON.stringify([
          { [longField]: "Exact full value", next: "second field" },
        ]),
      );
      await fileDialog(longFile);
      await click("Import evidence");
      const heading = preview.getByRole("columnheader", {
        name: longField.trim(),
        exact: true,
      });
      assert.equal(await heading.getAttribute("title"), longField);
      assert.equal(
        await heading.evaluate((el) => getComputedStyle(el).overflow),
        "hidden",
      );
      assert.ok((await heading.boundingBox()).width <= 220);
      await preview.locator("tbody tr").first().click();
      await page.getByLabel("Field", { exact: true }).selectOption(longField);
      await click("Copy value");
      assert.equal(
        await app.evaluate(() => global.__copied.at(-1)),
        '"Exact full value"',
      );
    },
  );
  await check(
    "all six investigation requirements: counts, clocks, case identity, reasons, chart relevance and entry",
    async () => {
      const source = path.join(files, "investigation.json"),
        rules = path.join(files, "investigation-policy.json");
      const previousCase = path.join(files, "previous-investigation.case.json"),
        currentCase = path.join(files, "current-investigation.case.json");
      fs.writeFileSync(
        source,
        JSON.stringify([
          {
            id: "A",
            session: "one",
            time: 800,
            reading: 20,
            flag: 0,
            user: "alice",
          },
          {
            id: "B",
            session: "one",
            time: 900,
            reading: 10,
            flag: 1,
            user: "bob",
          },
        ]),
      );
      fs.writeFileSync(
        rules,
        JSON.stringify({
          schema: "surge-policy-v1",
          settings: {
            features: ["reading"],
            session: "session",
            event_id: "id",
            time: "time",
            time_format: "milliseconds",
            time_origin: "elapsed",
            threshold: 10,
            context: { User: "user" },
            rules: [
              { name: "Special flag", field: "flag", op: "eq", value: 1 },
            ],
          },
        }),
      );
      await fileDialog(source);
      await click("Import evidence");
      await fileDialog(rules);
      await click("Load policy");
      assert.equal(
        await page.getByLabel("Clock", { exact: true }).inputValue(),
        "elapsed",
      );
      await page.getByLabel("Clock", { exact: true }).selectOption("unix");
      await ready();
      await click("Analyze");
      await page.waitForFunction(() =>
        document
          .querySelector(".evidence")
          ?.textContent.includes("1970-01-01T00:00:00.900000 UTC"),
      );
      assert.equal(
        await page.getByRole("group", { name: "Numeric chart" }).count(),
        0,
      );
      await click("Data");
      await page.getByLabel("Clock", { exact: true }).selectOption("elapsed");
      await ready();
      await click("Analyze");
      await fileDialog(previousCase, true);
      await click("Export case file");
      await click("Data");
      await page.getByLabel("Threshold", { exact: true }).fill("6");
      await page.getByLabel("Threshold", { exact: true }).press("Enter");
      await ready();
      await click("Analyze");
      await page.waitForFunction(() =>
        document
          .querySelector(".evidence")
          ?.textContent.includes("Elapsed time · 800 ms"),
      );
      await fileDialog(currentCase, true);
      await click("Export case file");
      const findings = page.getByRole("table", { name: "Results" });
      await findings
        .locator("tbody tr")
        .filter({ has: page.locator("td:first-child", { hasText: "2" }) })
        .click();
      await page.waitForFunction(() =>
        document.querySelector(".evidence")?.textContent.includes("ID: B"),
      );
      assert.equal(
        await page.getByRole("group", { name: "Numeric chart" }).count(),
        0,
      );
      assert.match(await findings.innerText(), /flag matches rule/);
      await findings
        .locator("tbody tr")
        .filter({ has: page.locator("td:first-child", { hasText: "1" }) })
        .click();
      await visible(page.getByRole("group", { name: "Numeric chart" }));
      await page.locator(".selected-hit").click();
      await page.waitForFunction(() =>
        document
          .querySelector(".chart-readout")
          ?.textContent.includes("reading: 20"),
      );
      for (const query of ["B", "bob", "Special flag"]) {
        await page.getByLabel("Search records").fill(query);
        await page.waitForFunction(
          () =>
            document.querySelector('table[aria-label="Results"] tbody')
              ?.children.length === 1,
        );
        assert.match(
          await page.getByLabel("Active filters").innerText(),
          new RegExp(query),
        );
        assert.equal(
          await page.getByRole("group", { name: "Numeric chart" }).count(),
          0,
        );
      }
      await page.getByLabel("Search records").fill("one");
      await page.waitForFunction(
        () =>
          document.querySelector('table[aria-label="Results"] tbody')?.children
            .length === 2,
      );
      await click("Clear");
      await click("Compare");
      await fileDialog(currentCase);
      await click("Choose case");
      assert.equal(
        await page
          .getByRole("button", { name: "0 changed outcomes", exact: true })
          .isDisabled(),
        true,
      );
      await fileDialog(previousCase);
      await click("Choose case");
      await click("1 changed outcome");
      const affected = page.getByRole("table", { name: "Affected records" });
      assert.equal(await affected.locator("tbody tr").count(), 1);
      await affected.locator("tbody tr").first().press("Enter");
      await page.waitForFunction(() =>
        document
          .querySelector(".comparison")
          ?.textContent.includes("Source record"),
      );
      const comparison = page.getByRole("table", { name: "Comparison" });
      assert.match(await comparison.innerText(), /No finding/);
      assert.match(
        await comparison.innerText(),
        /reading · observed\s+20\s+20/,
      );
      assert.match(await comparison.innerText(), /Not matched/);
      assert.match(
        await page.locator(".comparison-sources").innerText(),
        /Current · current-investigation.case.json/,
      );
      assert.match(
        await page.locator(".comparison-sources").innerText(),
        /Previous · previous-investigation.case.json/,
      );
      await page.getByText("Current source", { exact: true }).click();
      await page.getByText("Previous source", { exact: true }).click();
      assert.ok(
        (await page.locator(".comparison-sources").innerText()).includes(
          currentCase,
        ),
      );
      assert.ok(
        (await page.locator(".comparison-sources").innerText()).includes(
          previousCase,
        ),
      );
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(1100, 760),
      );
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
      );
      await screenshot("completed-comparison");
      await fileDialog(saved);
      await click("Choose case");
      await visible(page.getByText("Different data", { exact: false }));
      assert.equal(
        await page.getByLabel("Comparison changes", { exact: true }).count(),
        0,
      );
      await click("Data");
      await fileDialog(currentCase);
      await click("Open saved case");
      await page.waitForFunction(() =>
        document
          .querySelector(".evidence")
          ?.textContent.includes("Elapsed time · 800 ms"),
      );
      assert.equal((await rpc("state")).config.time_origin, "elapsed");
      await page.waitForFunction(() =>
        document
          .querySelector(".chart-readout")
          ?.textContent.includes("reading: 20"),
      );
      await screenshot("completed-findings");
    },
  );
  await check(
    "ordered shortcuts, compact options and bounded mapping undo",
    async () => {
      const views = ["Data", "Results", "Compare", "Evaluate", "Case details"];
      for (let i = 0; i < views.length; i++) {
        await page.keyboard.press(`Alt+${i + 1}`);
        await page.waitForFunction(
          (name) =>
            document.querySelector("nav button.active")?.textContent === name,
          views[i],
        );
        assert.equal(
          await page
            .getByRole("button", { name: views[i], exact: true })
            .getAttribute("aria-keyshortcuts"),
          `Alt+${i + 1}`,
        );
      }
      await click("Data");
      await fileDialog(incoming);
      await click("Import evidence");
      const options = page
        .locator(".setup details")
        .filter({ has: page.locator("summary", { hasText: /^Options$/ }) });
      assert.equal(await options.getAttribute("open"), null);
      assert.equal(
        await page
          .getByRole("button", { name: "Undo mapping", exact: true })
          .count(),
        0,
      );
      await page.getByLabel("Session", { exact: true }).selectOption("session");
      await ready();
      const before = (await rpc("state")).config;
      await page.getByLabel("Record ID", { exact: true }).selectOption("id");
      await ready();
      await click("Undo mapping");
      assert.deepEqual((await rpc("state")).config, before);
      assert.equal(
        await page
          .getByRole("button", { name: "Undo mapping", exact: true })
          .count(),
        0,
      );
      await options.locator("summary").click();
      await page.getByLabel("Time", { exact: true }).selectOption("time");
      await ready();
      assert.notEqual(await options.getAttribute("open"), null);
      await fileDialog(malformed);
      await click("Import evidence");
      await click("Close");
      assert.equal(
        await page
          .getByRole("button", { name: "Undo mapping", exact: true })
          .isVisible(),
        true,
      );
      await click("Undo mapping");
      assert.deepEqual((await rpc("state")).config, before);
      await page.getByLabel("Record ID", { exact: true }).selectOption("id");
      await ready();
      await fileDialog(policy);
      await click("Load policy");
      assert.equal(
        await page
          .getByRole("button", { name: "Undo mapping", exact: true })
          .count(),
        0,
      );
      await page.getByLabel("Session", { exact: true }).selectOption("");
      await ready();
      await fileDialog(incoming);
      await click("Import evidence");
      assert.equal(
        await page
          .getByRole("button", { name: "Undo mapping", exact: true })
          .count(),
        0,
      );
      await screenshot("configuration");
    },
  );
  assert.deepEqual(errors, []);
  const metrics = await app.evaluate(({ app }) =>
    app.getAppMetrics().map((p) => ({ type: p.type, memory: p.memory })),
  );
  fs.writeFileSync(
    path.join(OUT, "parity-results.json"),
    JSON.stringify(
      {
        passed: checks,
        checks: checks.length,
        startupMs,
        performance: performanceCheck,
        metrics,
        files,
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ checks: checks.length, startupMs }));
})()
  .catch(async (error) => {
    console.error(error);
    if (page) await screenshot("failure").catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

// Synthetic end-to-end scoring fixtures; not independent effectiveness evidence.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const OUT = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(OUT, { recursive: true });
const files = fs.mkdtempSync(path.join(OUT, "evaluation-"));
const entry = path.join(files, "test-entry.cjs");
fs.writeFileSync(
  entry,
  `const {app,ipcMain}=require('electron');
app.setPath('userData',${JSON.stringify(path.join(files, "profile"))});
global.__requests=[];const handle=ipcMain.handle.bind(ipcMain);
ipcMain.handle=(channel,handler)=>handle(channel,(event,method,args)=>{global.__requests.push(method);return handler(event,method,args);});
require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
const source = path.join(files, "test.json"),
  reference = path.join(files, "reference.json"),
  policy = path.join(files, "policy.json");
fs.writeFileSync(
  source,
  JSON.stringify(
    [80, 70, 11, 10, null, null, 9].map((reading, i) => ({
      id: i + 1,
      session: "test",
      reading,
    })),
  ),
);
fs.writeFileSync(
  reference,
  JSON.stringify(
    [8, 9, 10, 11, 12].map((reading) => ({ reading, session: "reference" })),
  ),
);
const settings = {
  features: ["reading"],
  event_id: "id",
  session: "session",
  time: null,
  time_format: "milliseconds",
  threshold: 6,
  rules: [],
};
fs.writeFileSync(
  policy,
  JSON.stringify({ schema: "surge-policy-v1", settings }),
);
const labels = path.join(files, "labels.json");
const document = {
  schema: "surge-labels-v1",
  source_sha256: crypto
    .createHash("sha256")
    .update(fs.readFileSync(source))
    .digest("hex"),
  provenance: {
    author: "Synthetic test author",
    method: "Explicit fixture assertions",
    partition: "Separate fixture sessions",
    purpose: "synthetic",
    independent_of_detector: false,
  },
  labels: [
    "target",
    "legitimate",
    "target",
    "legitimate",
    "target",
    "legitimate",
    null,
  ].map((truth, i) => ({
    row: i + 1,
    truth,
    group: i === 1 ? "legitimate update" : "ordinary",
    note: "Synthetic <img src=x onerror=alert(1)> rationale",
  })),
};
fs.writeFileSync(labels, JSON.stringify(document));
let app, page;
const errors = [],
  checks = [];
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
async function click(name) {
  if (
    ["Load policy", "Save policy", "Edit rules", "Map context"].includes(name)
  ) {
    const options = page
      .locator(".setup details")
      .filter({ has: page.locator("summary", { hasText: /^Options$/ }) });
    if ((await options.getAttribute("open")) === null)
      await options.locator("summary").click();
  }
  await page.getByRole("button", { name, exact: true }).click();
  await page.waitForFunction(
    () => !document.querySelector('.app[data-working="true"]'),
  );
}
async function rpc(method, args = {}) {
  const reply = await page.evaluate(
    ({ method, args }) => window.surge.request(method, args),
    { method, args },
  );
  assert.equal(reply.ok, true, reply.error);
  return reply.value;
}
async function check(name, fn) {
  await fn();
  checks.push(name);
  console.log("PASS", name);
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
  page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => errors.push(e.message));
  await page
    .getByRole("button", { name: "Import evidence", exact: true })
    .waitFor();
  await dialog(source);
  await click("Import evidence");
  await dialog(reference);
  await click("Import reference");
  await dialog(policy);
  await click("Load policy");
  await click("Analyze");
  const original = await rpc("details", {
    revision: (await rpc("state")).revision,
  });
  await check(
    "external labels workflow, blank template and no hidden evaluation work",
    async () => {
      assert.equal(
        (await app.evaluate(() => global.__requests)).filter(
          (m) => m === "evaluation",
        ).length,
        0,
      );
      await click("Evaluate");
      await page
        .getByText("Current data is the test source.", { exact: false })
        .waitFor();
      const blank = path.join(files, "blank.json");
      await dialog(blank, true);
      await click("Save label template");
      assert.ok(
        JSON.parse(fs.readFileSync(blank)).labels.every(
          (r) => r.truth === null,
        ),
      );
      await app.evaluate(({ dialog }) => {
        dialog.showOpenDialog = async () => ({ canceled: true, filePaths: [] });
      });
      await click("Import labels");
      assert.equal((await rpc("state")).labels, null);
      await dialog(labels);
      await click("Import labels");
      await page
        .getByRole("button", { name: "False positive · 1", exact: true })
        .waitFor();
      assert.match(
        await page.locator(".evaluation-rates").innerText(),
        /False positives: 33.3% \(1\/3\).*Missed: 66.7% \(2\/3\)/s,
      );
      assert.match(
        await page.locator(".evaluation-rates").innerText(),
        /Precision: 50.0% \(1\/2\).*Recall: 33.3% \(1\/3\)/s,
      );
    },
  );
  await check(
    "mistakes drill through to exact evidence, labels and keyboard selection",
    async () => {
      await click("False positive · 1");
      let row = page
        .getByRole("table", { name: "Evaluation records" })
        .locator("tbody tr");
      await row.first().click();
      await page.locator(".evidence .observed").waitFor();
      assert.match(await page.locator(".evidence").innerText(), /reading: 70/);
      assert.match(
        await page.locator(".evaluation-label").innerText(),
        /legitimate/,
      );
      assert.equal(await page.locator("img").count(), 0);
      await page
        .getByLabel("Group", { exact: true })
        .selectOption("legitimate update");
      await page.waitForFunction(() =>
        document
          .querySelector('[aria-label="Evaluation records"] tbody')
          ?.innerText.includes("legitimate update"),
      );
      await click("Clear filters");
      await click("Missed · 2");
      row = page
        .getByRole("table", { name: "Evaluation records" })
        .locator("tbody tr");
      await row.first().click();
      await row.first().press("ArrowDown");
      await page
        .getByText("Record 5 · Label: target · Missed", { exact: true })
        .waitFor();
      await page.waitForFunction(() =>
        document.querySelector(".evidence")?.innerText.includes("Unknown"),
      );
      await page
        .locator("summary")
        .filter({ hasText: "Groups and provenance" })
        .click();
      await page.getByRole("table", { name: "Label groups" }).waitFor();
      assert.match(
        await page.getByRole("table", { name: "Label groups" }).innerText(),
        /legitimate update.*100.0% \(1\/1\)/s,
      );
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(1100, 760),
      );
      await page.screenshot({ path: path.join(OUT, "evaluation-groups.png") });
      await page
        .locator("summary")
        .filter({ hasText: "Groups and provenance" })
        .click();
      await click("False positive · 1");
      await row.first().click();
      await page.waitForFunction(() =>
        document
          .querySelector(".evidence .observed")
          ?.textContent.includes("70"),
      );
      await page.screenshot({
        path: path.join(OUT, "evaluation-evidence.png"),
      });
    },
  );
  await check(
    "invalid labels retain valid results and export preserves exact identities",
    async () => {
      const bad = path.join(files, "wrong.json");
      fs.writeFileSync(
        bad,
        JSON.stringify({ ...document, source_sha256: "0".repeat(64) }),
      );
      const before = await rpc("state");
      await dialog(bad);
      await click("Import labels");
      await page.getByRole("dialog").waitFor();
      assert.match(
        await page.getByRole("dialog").innerText(),
        /different source/,
      );
      await click("Close");
      assert.deepEqual((await rpc("state")).labels, before.labels);
      assert.deepEqual(
        await rpc("details", { revision: before.revision }),
        original,
      );
      const saved = path.join(files, "evaluation.json");
      await dialog(saved, true);
      await click("Save evaluation");
      const report = JSON.parse(fs.readFileSync(saved));
      assert.equal(report.summary.counts.Missed, 2);
      assert.equal(
        report.labels.sha256,
        crypto
          .createHash("sha256")
          .update(fs.readFileSync(labels))
          .digest("hex"),
      );
      assert.equal(report.source.sha256, document.source_sha256);
      await click("Save evaluation");
      await page.getByRole("dialog").waitFor();
      await click("Close");
      assert.deepEqual(JSON.parse(fs.readFileSync(saved)), report);
    },
  );
  await check(
    "settings changes recompute evaluation and replacing data clears labels",
    async () => {
      await click("Data");
      await page.getByLabel("Threshold", { exact: true }).fill("100");
      await page.getByLabel("Threshold", { exact: true }).press("Tab");
      await page.waitForFunction(
        () => !document.querySelector('.app[data-working="true"]'),
      );
      await click("Analyze");
      await click("Evaluate");
      await page
        .getByRole("button", { name: "Missed · 3", exact: true })
        .waitFor();
      await page
        .getByRole("button", { name: "False positive · 0", exact: true })
        .waitFor();
      await click("Data");
      await dialog(source);
      await click("Import evidence");
      assert.equal((await rpc("state")).labels, null);
      assert.deepEqual(errors, []);
    },
  );
  fs.writeFileSync(
    path.join(OUT, "evaluation-results.json"),
    JSON.stringify(
      { checks, errors, fixture: "synthetic; not independent validation" },
      null,
      2,
    ),
  );
})()
  .catch(async (e) => {
    console.error(e, errors);
    if (page)
      await page
        .screenshot({ path: path.join(OUT, "evaluation-failure.png") })
        .catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

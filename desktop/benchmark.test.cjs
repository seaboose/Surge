// Evaluate the previously prepared public benchmark through the real desktop.
// No external code, packet replay, or network access in the application.
const { _electron: electron } = require("playwright");
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const root = path.resolve(__dirname, "../benchmarks/rt-iot2022");
const run = fs.mkdtempSync(path.join(root, "run-"));
const entry = path.join(run, "test-entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(run, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
let app, page;
const errors = [];
async function file(name, save = false) {
  await app.evaluate(
    ({ dialog }, v) => {
      if (v.save)
        dialog.showSaveDialog = async () => ({
          canceled: false,
          filePath: v.file,
        });
      else
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [v.file],
        });
    },
    { file: name, save },
  );
}
async function click(name) {
  await require("./test-export-menu.cjs").revealExport(page, name);
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
  const v = await page.evaluate(
    ({ method, args }) => window.surge.request(method, args),
    { method, args },
  );
  assert.equal(v.ok, true, v.error);
  return v.value;
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
  page.setDefaultTimeout(30000);
  page.on("pageerror", (e) => errors.push(e.message));
  await page
    .getByRole("button", { name: "Import evidence", exact: true })
    .waitFor();
  const begin = Date.now();
  await file(path.join(root, "test.json"));
  await click("Import evidence");
  await file(path.join(root, "reference.json"));
  await click("Import reference");
  await file(path.join(root, "policy.json"));
  await click("Load policy");
  await click("Analyze");
  const analysisMs = Date.now() - begin;
  await file(path.join(run, "rt-iot2022.case.json"), true);
  await click("Export case file");
  await click("Evaluate");
  await file(path.join(root, "labels.json"));
  const start = Date.now();
  await click("Import labels");
  await page
    .getByRole("button", { name: "All · 10000", exact: true })
    .waitFor();
  const state = await rpc("state");
  const report = await rpc("evaluation", { revision: state.revision });
  const evaluationMs = Date.now() - start;
  assert.equal(report.summary.labeled, 10000);
  assert.equal(report.summary.legitimate, 1041);
  assert.equal(report.summary.targets, 8959);
  assert.equal(report.overlap.exact_records, 0);
  assert.equal(report.rows.length, 100);
  await file(path.join(run, "rt-iot2022.evaluation.json"), true);
  await click("Save evaluation");
  await click("False positive · " + report.summary.counts["False positive"]);
  await page
    .getByRole("table", { name: "Evaluation records" })
    .locator("tbody tr")
    .first()
    .click();
  await page.locator(".evidence .observed").first().waitFor();
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0].setSize(1100, 760),
  );
  await page.screenshot({ path: path.join(run, "false-positive.png") });
  const long = report.groups.find((g) => g.group.endsWith("long duration"));
  assert.ok(long);
  await page.getByLabel("Group", { exact: true }).selectOption(long.group);
  await page.waitForFunction(
    (group) =>
      document
        .querySelector('[aria-label="Evaluation records"] tbody')
        ?.innerText.includes(group),
    long.group,
  );
  await page
    .getByRole("table", { name: "Evaluation records" })
    .locator("tbody tr")
    .first()
    .click();
  await page.screenshot({ path: path.join(run, "legitimate-edge.png") });
  await click("Clear filters");
  await click("Missed · " + report.summary.counts.Missed);
  await page
    .getByRole("table", { name: "Evaluation records" })
    .locator("tbody tr")
    .first()
    .click();
  await page.waitForFunction(() =>
    document.querySelector(".evaluation-label")?.innerText.includes("Missed"),
  );
  await page.screenshot({ path: path.join(run, "missed.png") });
  assert.deepEqual(errors, []);
  const outcome = {
    run,
    summary: report.summary,
    groups: report.groups,
    analysisMs,
    evaluationMs,
    errors,
    case: path.join(run, "rt-iot2022.case.json"),
    evaluation: path.join(run, "rt-iot2022.evaluation.json"),
    labels: path.join(root, "labels.json"),
  };
  fs.writeFileSync(
    path.join(root, "latest-run.json"),
    JSON.stringify(outcome, null, 2),
  );
  console.log(JSON.stringify(outcome, null, 2));
})()
  .catch(async (e) => {
    console.error(e, errors);
    if (page)
      await page
        .screenshot({ path: path.join(run, "failure.png") })
        .catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

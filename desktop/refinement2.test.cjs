// Policy integration uses synthetic records only. No holdout is read here.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const out = path.resolve(__dirname, "../verification/electron");
const files = fs.mkdtempSync(path.join(out, "refinement2-"));
const entry = path.join(files, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(files, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
const source = path.join(files, "source.json"),
  reference = path.join(files, "reference.json");
fs.writeFileSync(
  source,
  JSON.stringify([
    { id: 1, kind: "a", duration: 11, rate: 1000, payload: 10 },
    { id: 2, kind: "a", duration: 13.5, rate: 11, payload: 10 },
    { id: 3, kind: "a", duration: 20, rate: 11, payload: 10 },
    { id: 4, kind: "unseen", duration: 11, rate: 11, payload: 10 },
  ]),
);
fs.writeFileSync(
  reference,
  JSON.stringify(
    Array.from({ length: 20 }, (_, i) => ({
      kind: "a",
      duration: 10 + 2 * (i % 2),
      rate: 10 + 2 * (i % 2),
      payload: 10,
    })),
  ),
);
const base = {
  features: ["duration", "rate", "payload"],
  reference_by: ["kind"],
  event_id: "id",
  session: null,
  time: null,
  time_format: "milliseconds",
  threshold: 2,
  rules: [],
};
const baselinePolicy = path.join(files, "baseline.policy.json"),
  baselineCase = path.join(files, "baseline.case.json");
const candidatePolicy = path.join(files, "candidate.policy.json"),
  candidateCase = path.join(files, "candidate.case.json");
fs.writeFileSync(
  baselinePolicy,
  JSON.stringify({ schema: "surge-policy-v1", settings: base }),
);
let app, page;
const errors = [],
  checks = [];
async function dialog(file, save = false) {
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
    { file, save },
  );
}
async function idle() {
  await page.waitForFunction(() => !document.querySelector(".app.busy"));
}
async function click(name) {
  await page.getByRole("button", { name, exact: true }).click();
  await idle();
}
async function rpc(method, args = {}) {
  const v = await page.evaluate(
    ({ method, args }) => window.surge.request(method, args),
    { method, args },
  );
  assert.equal(v.ok, true, v.error);
  return v.value;
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
  page.setDefaultTimeout(20000);
  page.on("pageerror", (e) => errors.push(e.message));
  await page
    .getByRole("button", { name: "Import data", exact: true })
    .waitFor();
  await check(
    "fractional policy edits survive save and reload without clearing group gaps",
    async () => {
      await dialog(source);
      await click("Import data");
      await dialog(reference);
      await click("Import reference");
      await dialog(baselinePolicy);
      await click("Load policy");
      await click("Analyze");
      await dialog(baselineCase, true);
      await click("Save case");
      await click("Data");
      await page.getByRole("checkbox", { name: "rate", exact: true }).click();
      await idle();
      await page.getByLabel("Threshold", { exact: true }).fill("1.5");
      await page.getByLabel("Threshold", { exact: true }).press("Enter");
      await idle();
      let s = await rpc("state");
      assert.equal(s.config.threshold, 1.5);
      assert.deepEqual(s.config.features, ["duration", "payload"]);
      await dialog(candidatePolicy, true);
      await click("Save policy");
      assert.equal(
        JSON.parse(fs.readFileSync(candidatePolicy)).settings.threshold,
        1.5,
      );
      await dialog(baselinePolicy);
      await click("Load policy");
      await dialog(candidatePolicy);
      await click("Load policy");
      assert.equal(
        await page.getByLabel("Threshold", { exact: true }).inputValue(),
        "1.5",
      );
      await click("Analyze");
      s = await rpc("state");
      assert.equal(s.summary.Unknown, 1);
      const first = await rpc("evidence", { revision: s.revision, row: 1 });
      assert.equal(first.status, "No finding");
      assert.ok(first.groups.every((g) => g.field !== "rate"));
      const second = await rpc("evidence", { revision: s.revision, row: 2 });
      assert.equal(second.status, "Review");
      assert.match(second.groups[0].lines[0].text, /Review at: 1.5/);
      const chart = await rpc("chart", {
        revision: s.revision,
        row: 2,
        width: 500,
      });
      assert.equal(chart.threshold, 1.5);
      await dialog(candidateCase, true);
      await click("Save case");
    },
  );
  await check(
    "reopened case preserves fractional conditions and comparison links to both outcomes",
    async () => {
      await click("Data");
      await dialog(candidateCase);
      await click("Open case");
      const s = await rpc("state");
      assert.equal(s.config.threshold, 1.5);
      assert.deepEqual(s.config.features, ["duration", "payload"]);
      await click("Compare");
      await dialog(baselineCase);
      await click("Choose case");
      await page
        .getByRole("button", { name: "2 changed outcomes", exact: true })
        .waitFor();
      await click("2 changed outcomes");
      await page
        .getByRole("table", { name: "Affected records" })
        .locator("tbody tr")
        .first()
        .click();
      await page.waitForFunction(() =>
        document
          .querySelector('[aria-label="Comparison"]')
          ?.innerText.includes("rate · condition"),
      );
      const rows = await rpc("comparison", { revision: s.revision, row: 1 });
      assert.equal(
        rows.rows.find((r) => r.label === "rate · condition").current,
        "Not configured",
      );
      assert.equal(
        rows.rows.find((r) => r.label === "rate · condition").previous,
        "Matched",
      );
      await page
        .getByLabel("Changed records", { exact: true })
        .selectOption("2");
      await page.waitForFunction(() =>
        document
          .querySelector('[aria-label="Comparison"]')
          ?.innerText.includes("13.5"),
      );
      const second = await rpc("comparison", { revision: s.revision, row: 2 });
      assert.equal(
        second.rows.find((r) => r.label === "duration · review at").current,
        "1.5",
      );
      assert.equal(
        second.rows.find((r) => r.label === "duration · condition").current,
        "Matched",
      );
      assert.equal(
        second.rows.find((r) => r.label === "duration · condition").previous,
        "Not matched",
      );
      await page.screenshot({
        path: path.join(out, "refinement2-comparison.png"),
      });
    },
  );
  await check(
    "unseen categories stay Unknown and exact evidence remains investigable",
    async () => {
      const s = await rpc("state");
      const missing = await rpc("evidence", { revision: s.revision, row: 4 });
      assert.equal(missing.status, "Unknown");
      assert.equal(missing.reference_group.mode, "global fallback");
      assert.ok(missing.gaps.length);
      await click("Findings");
      await page
        .getByRole("table", { name: "Findings", exact: true })
        .locator("tbody tr")
        .first()
        .click();
      await page.waitForFunction(() =>
        document
          .querySelector(".evidence")
          ?.innerText.includes("Review at: 1.5"),
      );
      assert.match(await page.locator(".evidence").innerText(), /13.5/);
      assert.equal(await page.locator("h1,h2,h3,header").count(), 0);
      assert.deepEqual(errors, []);
      await page.screenshot({
        path: path.join(out, "refinement2-evidence.png"),
      });
    },
  );
  fs.writeFileSync(
    path.join(out, "refinement2-results.json"),
    JSON.stringify(
      { checks, errors, scope: "Synthetic policy workflow; no holdout read" },
      null,
      2,
    ),
  );
})()
  .catch(async (e) => {
    console.error(e, errors);
    if (page)
      await page
        .screenshot({ path: path.join(out, "refinement2-failure.png") })
        .catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

// Development-only journey. This test never opens holdout data or labels.
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { _electron: electron } = require("playwright");
const root = path.resolve(__dirname, "../benchmarks/rt-iot2022"),
  out = path.resolve(__dirname, "../verification/electron");
const files = fs.mkdtempSync(path.join(out, "refinement3-development-")),
  entry = path.join(files, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(files, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
const baselineCase = path.join(files, "baseline.case.json"),
  candidateCase = path.join(files, "candidate.case.json"),
  policyCopy = path.join(files, "copy.policy.json");
let app, page;
const checks = [],
  errors = [];
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
  const r = await page.evaluate(
    ({ method, args }) => window.surge.request(method, args),
    { method, args },
  );
  assert.equal(r.ok, true, r.error);
  return r.value;
}
async function check(name, fn) {
  await fn();
  checks.push(name);
  console.log("PASS", name);
}
async function report() {
  const s = await rpc("state");
  return rpc("evaluation", { revision: s.revision });
}
function group(r, name) {
  return r.groups.find((g) => g.group === name).counts;
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
  let before;
  await check(
    "development baseline remains reproducible before policy replacement",
    async () => {
      await dialog(path.join(root, "refinement-1/development.json"));
      await click("Import data");
      await dialog(path.join(root, "reference.json"));
      await click("Import reference");
      await dialog(path.join(root, "refinement-3/baseline/policy.json"));
      await click("Load policy");
      await click("Analyze");
      await dialog(baselineCase, true);
      await click("Save case");
      await click("Evaluate");
      await dialog(path.join(root, "refinement-1/development.labels.json"));
      await click("Import labels");
      await page
        .getByRole("button", { name: "False positive · 190", exact: true })
        .waitFor();
      before = await report();
      assert.equal(before.summary.counts.Missed, 0);
      assert.equal(group(before, "Thing_Speak")["False positive"], 119);
    },
  );
  await check(
    "candidate subgroup counts and fractional policy persist through save and reopen",
    async () => {
      await click("Data");
      await dialog(path.join(root, "refinement-3/candidate.policy.json"));
      await click("Load policy");
      assert.equal(
        await page.getByLabel("Threshold", { exact: true }).inputValue(),
        "1.8",
      );
      await dialog(policyCopy, true);
      await click("Save policy");
      assert.equal(
        JSON.parse(fs.readFileSync(policyCopy)).settings.threshold,
        1.8,
      );
      await click("Analyze");
      await dialog(candidateCase, true);
      await click("Save case");
      await click("Data");
      await dialog(candidateCase);
      await click("Open case");
      await click("Evaluate");
      await dialog(path.join(root, "refinement-1/development.labels.json"));
      await click("Import labels");
      await page
        .getByRole("button", { name: "False positive · 175", exact: true })
        .waitFor();
      await page
        .getByRole("button", { name: "Missed · 0", exact: true })
        .waitFor();
      const after = await report();
      assert.equal(group(after, "Thing_Speak")["False positive"], 104);
      assert.deepEqual(
        group(before, "MQTT_Publish"),
        group(after, "MQTT_Publish"),
      );
      assert.deepEqual(group(before, "Wipro_bulb"), group(after, "Wipro_bulb"));
      assert.equal(after.summary.counts.Unresolved, 0);
      await click("False positive · 175");
      await page
        .getByLabel("Group", { exact: true })
        .selectOption("Thing_Speak");
      await page.waitForFunction(() =>
        document
          .querySelector(".evaluation")
          ?.innerText.includes("104 records"),
      );
      await page
        .getByRole("table", { name: "Evaluation records" })
        .locator("tbody tr")
        .first()
        .click();
      await page.waitForFunction(() =>
        document
          .querySelector(".evidence")
          ?.innerText.includes("Review at: 1.8"),
      );
      await page.screenshot({
        path: path.join(out, "refinement3-development-subgroup.png"),
      });
    },
  );
  await check(
    "changed outcomes lead to exact previously flagged subgroup evidence",
    async () => {
      await click("Compare");
      await dialog(baselineCase);
      await click("Choose case");
      await page
        .getByRole("button", { name: "15 changed outcomes", exact: true })
        .waitFor();
      await click("15 changed outcomes");
      await page
        .getByRole("table", { name: "Affected records" })
        .locator("tbody tr")
        .first()
        .click();
      await page.waitForFunction(() =>
        document
          .querySelector('[aria-label="Comparison"]')
          ?.innerText.includes("1.8"),
      );
      const row = Number(
          await page
            .getByLabel("Changed records", { exact: true })
            .inputValue(),
        ),
        s = await rpc("state");
      const data = await rpc("comparison", { revision: s.revision, row });
      assert.equal(
        data.rows.find((r) => r.label === "Result").current,
        "No finding",
      );
      assert.equal(
        data.rows.find((r) => r.label === "Result").previous,
        "Review",
      );
      const labels = JSON.parse(
        fs.readFileSync(
          path.join(root, "refinement-1/development.labels.json"),
        ),
      ).labels;
      assert.equal(labels[row - 1].group, "Thing_Speak");
      assert.equal(
        data.rows.find((r) => r.label === "flow_duration · review at").current,
        "1.8",
      );
      assert.equal(
        data.rows.find((r) => r.label === "flow_duration · review at").previous,
        "1.5",
      );
      assert.equal(await page.locator("h1,h2,h3,header").count(), 0);
      assert.deepEqual(errors, []);
      await page.screenshot({
        path: path.join(out, "refinement3-development-comparison.png"),
      });
    },
  );
  fs.writeFileSync(
    path.join(out, "refinement3-results.json"),
    JSON.stringify(
      { checks, errors, scope: "Development only; no holdout opened" },
      null,
      2,
    ),
  );
})()
  .catch(async (e) => {
    console.error(e, errors);
    if (page)
      await page
        .screenshot({ path: path.join(out, "refinement3-failure.png") })
        .catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

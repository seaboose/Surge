// Real desktop journeys for grouped references; fixed holdout scores are not tuned here.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const root = path.resolve(__dirname, "../benchmarks/rt-iot2022/refinement-1");
const out = path.resolve(__dirname, "../verification/electron");
const files = fs.mkdtempSync(path.join(out, "refinement-"));
const entry = path.join(files, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(files, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
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
async function click(name) {
  if (name === "Open saved case") {
    await page
      .getByRole("button", { name: "Case library", exact: true })
      .click();
    await page
      .getByRole("dialog", { name: "Case library", exact: true })
      .waitFor();
    name = "Open case file";
  }
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
    .getByRole("button", { name: "Case library", exact: true })
    .waitFor();
  await check(
    "fresh holdout case reopens with exact scoring and grouped evidence",
    async () => {
      await dialog(path.join(root, "candidate.case.json"));
      await click("Open saved case");
      await click("Evaluate");
      await dialog(path.join(root, "holdout.labels.json"));
      await click("Import labels");
      await page
        .getByRole("button", { name: "False positive · 222", exact: true })
        .waitFor();
      await page
        .getByRole("button", { name: "Missed · 2", exact: true })
        .waitFor();
      assert.match(
        await page.locator(".evaluation-rates").innerText(),
        /Missed: 0.02% \(2\/9289\)/,
      );
      assert.match(
        await page.locator(".evaluation-rates").innerText(),
        /Recall: 99.98% \(9287\/9289\)/,
      );
      await click("Clear · 489");
      await page
        .getByRole("table", { name: "Evaluation records" })
        .locator("tbody tr")
        .first()
        .click();
      await page.waitForFunction(() =>
        document
          .querySelector(".evidence")
          ?.innerText.includes("Reference group:"),
      );
      assert.match(
        await page.locator(".evidence").innerText(),
        /proto = .*service = /s,
      );
      assert.match(
        await page.locator(".evidence").innerText(),
        /matched · \d+ reference records/,
      );
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(1100, 760),
      );
      await page.screenshot({
        path: path.join(out, "refinement-evidence.png"),
      });
    },
  );
  await check(
    "comparison uses actual group medians and keeps prior outcomes visible",
    async () => {
      const comparison = JSON.parse(
        fs.readFileSync(path.join(root, "holdout-comparison.json")),
      );
      const row = comparison.resolved_false_positives[0];
      await click("Compare");
      await dialog(path.join(root, "baseline.case.json"));
      await click("Choose case");
      await page
        .getByLabel("Changed records", { exact: true })
        .selectOption(String(row));
      await page.waitForFunction(() =>
        document
          .querySelector('[aria-label="Comparison"]')
          ?.innerText.includes("Reference group"),
      );
      const table = await page
        .getByRole("table", { name: "Comparison", exact: true })
        .innerText();
      assert.match(table, /No finding/);
      assert.match(table, /Review/);
      assert.match(table, /matched/);
      const state = await rpc("state");
      const rows = await rpc("comparison", { revision: state.revision, row });
      const group = rows.rows.find((r) => r.label === "Reference group");
      assert.ok(group.changed);
      await page.screenshot({
        path: path.join(out, "refinement-comparison.png"),
      });
    },
  );
  await check(
    "editable group mappings, warning drill-through and global fallback preserve gaps",
    async () => {
      await click("Data");
      assert.equal(
        await page.getByLabel("Reference group", { exact: true }).inputValue(),
        "proto",
      );
      assert.equal(
        await page.getByLabel("Also group by", { exact: true }).inputValue(),
        "service",
      );
      // Leave controls reachable when every numeric signal is unchecked.
      for (const field of [
        "flow_duration",
        "flow_pkts_per_sec",
        "fwd_pkts_payload.avg",
      ]) {
        await page.getByRole("checkbox", { name: field, exact: true }).click();
        await page.waitForFunction(
          () => !document.querySelector('.app[data-working="true"]'),
        );
        assert.equal(
          await page
            .getByRole("checkbox", { name: field, exact: true })
            .isChecked(),
          false,
        );
      }
      await page
        .getByLabel("Reference group", { exact: true })
        .selectOption("");
      await page.waitForFunction(
        () => !document.querySelector('.app[data-working="true"]'),
      );
      assert.deepEqual((await rpc("state")).config.reference_by, []);
      const source = path.join(files, "source.json"),
        ref = path.join(files, "ref.json"),
        policy = path.join(files, "policy.json");
      fs.writeFileSync(
        source,
        JSON.stringify([
          { kind: "new", x: 10 },
          { kind: null, x: 10 },
          { kind: "a", x: 10 },
        ]),
      );
      fs.writeFileSync(
        ref,
        JSON.stringify(
          Array.from({ length: 20 }, () => ({ kind: "a", x: 10 })),
        ),
      );
      fs.writeFileSync(
        policy,
        JSON.stringify({
          schema: "surge-policy-v1",
          settings: {
            features: ["x"],
            reference_by: ["kind"],
            event_id: null,
            session: null,
            time: null,
            time_format: "milliseconds",
            threshold: 6,
            rules: [],
          },
        }),
      );
      await dialog(source);
      await click("Import evidence");
      await dialog(ref);
      await click("Import reference");
      await dialog(policy);
      await click("Load policy");
      await page
        .getByRole("button", {
          name: /Check · 2 records have missing, unseen, or undersized reference groups/,
        })
        .click();
      await page
        .getByRole("table", { name: "Preview" })
        .locator("tbody tr")
        .first()
        .click();
      await page.waitForFunction(() =>
        document
          .querySelector(".pinned")
          ?.innerText.includes("Global profiles"),
      );
      await click("Analyze");
      const s = await rpc("state");
      assert.equal(s.summary.Unknown, 2);
      await page
        .getByRole("table", { name: "Results", exact: true })
        .locator("tbody tr")
        .first()
        .click();
      await page.waitForFunction(() =>
        document
          .querySelector(".evidence")
          ?.innerText.includes("global fallback"),
      );
      assert.match(await page.locator(".evidence").innerText(), /Unknown/);
      await page.screenshot({
        path: path.join(out, "refinement-fallback.png"),
      });
      assert.deepEqual(errors, []);
    },
  );
  fs.writeFileSync(
    path.join(out, "refinement-results.json"),
    JSON.stringify({ checks, errors }, null, 2),
  );
})()
  .catch(async (e) => {
    console.error(e, errors);
    if (page)
      await page
        .screenshot({ path: path.join(out, "refinement-failure.png") })
        .catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

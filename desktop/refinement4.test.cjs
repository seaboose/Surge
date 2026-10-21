// Retained-policy Wipro investigation. Development only; no holdout is opened.
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { _electron: electron } = require("playwright");
const root = path.resolve(__dirname, "../benchmarks/rt-iot2022");
const out = path.resolve(__dirname, "../verification/electron"),
  files = fs.mkdtempSync(path.join(out, "refinement4-development-"));
const entry = path.join(files, "entry.cjs"),
  savedCase = path.join(files, "wipro-development.case.json");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(files, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
let app, page, before;
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
  await page.getByRole("button", { name, exact: true }).click();
  await page.waitForFunction(() => !document.querySelector(".app.busy"));
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
async function report(args = {}) {
  const s = await rpc("state");
  return rpc("evaluation", { revision: s.revision, ...args });
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
    "retained policy reproduces development detections and all legitimate groups",
    async () => {
      await dialog(path.join(root, "refinement-1/development.json"));
      await click("Import data");
      await dialog(path.join(root, "reference.json"));
      await click("Import reference");
      await dialog(
        path.resolve(
          __dirname,
          "../policies/rt-iot2022-refinement-3.policy.json",
        ),
      );
      await click("Load policy");
      await click("Analyze");
      await dialog(savedCase, true);
      await click("Save case");
      await click("Evaluate");
      await dialog(path.join(root, "refinement-1/development.labels.json"));
      await click("Import labels");
      before = await report();
      assert.equal(before.summary.counts["False positive"], 175);
      assert.equal(before.summary.counts.Missed, 0);
      assert.equal(before.summary.counts.Unresolved, 0);
      for (const [name, n] of Object.entries({
        Wipro_bulb: 15,
        Thing_Speak: 104,
        MQTT_Publish: 56,
      }))
        assert.equal(
          before.groups.find((g) => g.group === name).counts["False positive"],
          n,
        );
    },
  );
  await check(
    "Wipro filter exposes every record and preserves sparse-reference warnings",
    async () => {
      await click("False positive · 175");
      await page
        .getByLabel("Group", { exact: true })
        .selectOption("Wipro_bulb");
      await page.waitForFunction(() =>
        document
          .querySelector(".evaluation")
          ?.innerText.includes("15 records · False positive · Wipro_bulb"),
      );
      const data = await report({
        outcome: "False positive",
        group: "Wipro_bulb",
      });
      assert.equal(data.total, 15);
      assert.equal(data.rows.length, 15);
      let sparse = 0;
      const s = await rpc("state");
      for (const record of data.rows) {
        const row = record.row;
        const tr = page
          .getByRole("table", { name: "Evaluation records" })
          .locator("tbody tr")
          .filter({
            has: page.locator("td:first-child", {
              hasText: new RegExp(`^${row}$`),
            }),
          });
        await tr.click();
        await page.waitForFunction(
          (row) =>
            document
              .querySelector(".evidence")
              ?.innerText.includes(`Record: ${row} · ID:`),
          row,
        );
        const evidence = await rpc("evidence", { revision: s.revision, row });
        assert.equal(evidence.status, "Review");
        assert.ok(evidence.groups.length);
        assert.ok(evidence.values.length);
        if (evidence.reference_group.mode === "global fallback") {
          sparse++;
          assert.ok(evidence.reference_group.reference_rows < 20);
          assert.ok(evidence.gaps.length);
          assert.ok(
            (await page.locator(".evidence").innerText()).includes(
              `global fallback · ${evidence.reference_group.reference_rows} reference records`,
            ),
          );
          await page.screenshot({
            path: path.join(
              out,
              "refinement4-development-sparse-reference.png",
            ),
          });
        }
      }
      assert.ok(sparse > 0);
      await page.screenshot({
        path: path.join(out, "refinement4-development-wipro.png"),
      });
    },
  );
  await check(
    "saved case and labels retain results after reopening with no replacement policy",
    async () => {
      await click("Data");
      await dialog(savedCase);
      await click("Open case");
      await click("Evaluate");
      await dialog(path.join(root, "refinement-1/development.labels.json"));
      await click("Import labels");
      const after = await report();
      assert.deepEqual(after.summary, before.summary);
      assert.deepEqual(after.groups, before.groups);
      assert.equal((await rpc("state")).config.threshold, 1.8);
      assert.equal(await page.locator("h1,h2,h3,header").count(), 0);
      assert.deepEqual(errors, []);
    },
  );
  fs.writeFileSync(
    path.join(out, "refinement4-results.json"),
    JSON.stringify(
      {
        checks,
        errors,
        scope:
          "Retained policy on development data only; no candidate promoted and no holdout opened",
      },
      null,
      2,
    ),
  );
})()
  .catch(async (e) => {
    console.error(e, errors);
    if (page)
      await page
        .screenshot({ path: path.join(out, "refinement4-failure.png") })
        .catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

// Replay the published cases through the real interface; dialogs select only demo files.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const folder = path.join(root, "demos/native");
const expected = JSON.parse(
  fs.readFileSync(path.join(folder, "expected.json"), "utf8"),
);
const out = path.join(root, "verification/electron");
fs.mkdirSync(out, { recursive: true });
const temp = fs.mkdtempSync(path.join(out, "demo-"));
const entry = path.join(temp, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(temp, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
let app;
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  app = await electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
  });
  const page = await app.firstWindow();
  page.setDefaultTimeout(15000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByRole("button", { name: "Our app", exact: true }).click();
  const call = (method, args = {}) =>
    page.evaluate(
      async ({ method, args }) => {
        const reply = await window.surge.request(method, args);
        if (!reply.ok) throw new Error(reply.error);
        return reply.value;
      },
      { method, args },
    );
  async function open(spec) {
    const data = page.getByRole("button", { name: "Data", exact: true });
    if (await data.isVisible()) await data.click();
    await app.evaluate(
      ({ dialog }, file) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [file],
        });
      },
      path.join(folder, spec.file),
    );
    await page.getByRole("button", { name: "Open case", exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector(".app")?.dataset.working === "false",
    );
    const state = await call("state");
    assert.equal(state.current.records, 4);
    for (const status of ["No finding", "Review", "Unknown"])
      assert.equal(
        state.summary[status],
        spec.outcomes.filter((s) => s === status).length,
      );
    for (let index = 0; index < 4; index++) {
      const evidence = await call("evidence", {
        revision: state.revision,
        row: index + 1,
      });
      assert.equal(evidence.status, spec.outcomes[index]);
      assert.equal(
        evidence.groups.find((g) => g.field === "Coverage").value,
        `${spec.readable_ranges[index]}/2 ranges read`,
      );
    }
  }
  for (const spec of expected.cases) await open(spec);
  await open(expected.cases.find((s) => s.file === "changed-code.case.json"));
  const findings = page.locator(".view:not([hidden])");
  await findings.getByRole("checkbox", { name: "Findings only" }).check();
  await findings.locator("tbody tr").first().click();
  await page
    .locator(".evidence")
    .getByText(/Code:.*Changed/)
    .waitFor();
  await page
    .locator(".evidence")
    .getByText(/2\/2 ranges read/)
    .waitFor();
  await page.getByText("Our app · Ready", { exact: true }).waitFor();
  assert.equal(await page.locator("h1,h2,h3").count(), 0);
  await page.screenshot({
    path: process.argv.includes("--screenshot")
      ? path.join(root, "docs/native-investigation.png")
      : path.join(out, "demo.png"),
  });
  assert.deepEqual(errors, []);
  console.log(
    "Five published demo cases passed desktop replay, expected outcomes and coverage checks.",
  );
})()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });

// Short, staged checks of the real desktop; uses only synthetic/owned evidence.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const stage = Number(process.argv[2] || 7);
const out = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(out, { recursive: true });
const temp = fs.mkdtempSync(path.join(out, `usability-${stage}-`));
const entry = path.join(temp, "entry.cjs");
const source = path.join(temp, "records.json");
const policy = path.join(temp, "policy.json");
fs.writeFileSync(
  policy,
  JSON.stringify({
    schema: "surge-policy-v1",
    settings: {
      features: [],
      session: null,
      event_id: "id",
      time: null,
      time_format: "milliseconds",
      threshold: 6,
      context: {},
      rules: [{ name: "Above limit", field: "value", op: "gt", value: 15 }],
    },
  }),
);
fs.writeFileSync(
  source,
  JSON.stringify([
    { id: "one", value: 10 },
    { id: "two", value: 20 },
  ]),
);
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(temp, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
let app, page, failure;
const started = Date.now();
const guard = setTimeout(() => {
  console.error("Usability check deadline exceeded");
  process.exit(2);
}, 90000);
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  app = await electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
  });
  page = await app.firstWindow();
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const ready = () =>
    page.waitForFunction(
      () => document.querySelector(".app")?.dataset.working === "false",
    );
  const click = async (name) => {
    if (
      name === "Start collection" &&
      !(await page.getByRole("button", { name, exact: true }).count())
    )
      name = "Start another capture";
    if (name === "Open saved case") {
      await page
        .getByRole("button", { name: "Case library", exact: true })
        .click();
      await page
        .getByRole("dialog", { name: "Case library", exact: true })
        .waitFor();
      name = "Open case file";
    }
    await page.getByRole("button", { name, exact: true }).click();
    await ready();
  };
  const call = (method, args = {}) =>
    page.evaluate(
      async ({ method, args }) => {
        const r = await window.surge.request(method, args);
        if (!r.ok) throw Error(r.error);
        return r.value;
      },
      { method, args },
    );
  await ready();
  const collect = "Try Demo";
  if (stage === 2) {
    await page.getByRole("heading", { name: "Surge" }).waitFor();
    for (const name of ["Import evidence", "Case library", collect])
      assert.equal(
        await page.getByRole("button", { name, exact: true }).count(),
        1,
      );
    await app.evaluate(({ dialog }) => {
      dialog.showOpenDialog = async () => ({ canceled: true, filePaths: [] });
    });
    await click("Import evidence");
    assert.equal((await call("state")).current, null);
  }
  await page.screenshot({ path: path.join(temp, "opening.png") });
  await click(collect);
  await page.locator(".demo-collection-details summary").click();
  await page
    .getByText(/Retains up to 500 samples, subject to the evidence size limit/)
    .waitFor();
  if (stage >= 4) {
    await require("./test-export-menu.cjs").revealExport(
      page,
      "Export captured records",
    );
    await page
      .getByRole("button", { name: "Inspect snapshot", exact: true })
      .waitFor();
    assert.equal(
      await page
        .getByRole("button", { name: "Export captured records", exact: true })
        .isDisabled(),
      true,
    );
    assert.equal(
      await page.getByRole("combobox", { name: "Build", exact: true }).count(),
      0,
    );
  }
  if (stage >= 4) await page.locator(".export-options summary").click();
  if (stage === 5) {
    assert.equal(await page.locator("button.primary:visible").count(), 1);
    assert.equal(
      await page.locator("button.primary:visible").innerText(),
      "Start collection",
    );
    assert.equal(
      await page
        .getByRole("button", { name: "Start collection" })
        .evaluate((e) => getComputedStyle(e).boxShadow),
      "none",
    );
  }
  if (stage === 6) {
    for (const zoom of [1, 1.5, 2]) {
      await app.evaluate(({ BrowserWindow }, zoom) => {
        const w = BrowserWindow.getAllWindows()[0];
        w.setSize(1100, 800);
        w.webContents.setZoomFactor(zoom);
      }, zoom);
      await page.waitForTimeout(150);
      const issues = await page.evaluate(() =>
        [...document.querySelectorAll("button")]
          .filter(
            (e) => e.checkVisibility() && e.scrollWidth > e.clientWidth + 3,
          )
          .map((e) => e.textContent),
      );
      assert.deepEqual(issues, [], `button clipping at ${zoom}`);
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 2,
        ),
      );
      await page.screenshot({ path: path.join(temp, `scale-${zoom}.png`) });
    }
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1),
    );
  }
  if (stage === 3) {
    await click("Start collection");
    await page.waitForFunction(async () => {
      const r = await window.surge.request("native_status", {});
      return r.value.capture.records >= 4;
    });
    await click("Inspect snapshot");
    const before = await call("state");
    assert.ok(before.inspected_capture.final_sequence > 0);
    await page.getByText(/Viewing snapshot/).waitFor();
    await page.getByText(/Newer samples available/).waitFor();
    assert.equal((await call("state")).current.sha256, before.current.sha256);
    await click("Stop collection");
    const stopped = await call("state");
    assert.equal(
      stopped.inspected_capture.final_sequence,
      stopped.capture.final_sequence,
    );
    await click("Start collection");
    await page.getByText(/Snapshot is from an earlier collection/).waitFor();
    assert.equal(await page.getByText(/Newer samples available/).count(), 0);
    await click("Stop collection");
  }
  if (stage === 7) {
    await click("Back");
    await app.evaluate(({ dialog }, file) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [file],
      });
    }, source);
    await click("Import evidence");
    await page
      .locator(".setup summary")
      .filter({ hasText: /^Options$/ })
      .click();
    await app.evaluate(({ dialog }, file) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [file],
      });
    }, policy);
    await click("Load policy");
    await click("Analyze");
    await page.getByText("What the results mean", { exact: true }).click();
    await page.getByText(/No finding.*does not prove/i).waitFor();
    await click("Compare");
    await page
      .getByText(/Compare this investigation with a saved case/)
      .waitFor();
    await click("Evaluate");
    await page
      .getByText(
        /Measure detection performance using independently assigned labels/,
      )
      .waitFor();
    await page.keyboard.press("Alt+5");
    await page
      .getByRole("button", { name: "Case details", exact: true })
      .waitFor();
    await page
      .getByText(
        /Source fingerprints, analysis settings and evidence provenance/,
      )
      .waitFor();
  }
  await page.screenshot({ path: path.join(temp, "completed.png") });
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ stage, status: "passed", artifacts: temp }));
})()
  .catch(async (e) => {
    console.error(e);
    failure = String(e);
    if (page)
      await page
        .screenshot({ path: path.join(temp, "failure.png") })
        .catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
    fs.writeFileSync(
      path.join(temp, "result.json"),
      JSON.stringify(
        {
          stage,
          status: failure ? "failed" : "passed",
          elapsed_ms: Date.now() - started,
          error: failure || null,
        },
        null,
        2,
      ),
    );
    clearTimeout(guard);
  });

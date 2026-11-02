// Real native captures enter through the ordinary desktop file dialog.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const captureRoot = path.join(root, "native/captures");
const captureFolder = JSON.parse(
  fs.readFileSync(path.join(captureRoot, "latest.json"), "utf8"),
).folder;
assert.match(captureFolder, /^run-[a-f0-9]{12}$/);
const out = path.join(root, "verification/electron");
fs.mkdirSync(out, { recursive: true });
const temp = fs.mkdtempSync(path.join(out, "native-"));
const entry = path.join(temp, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app,ipcMain}=require('electron');global.__delay={};const handle=ipcMain.handle.bind(ipcMain);ipcMain.handle=(channel,handler)=>handle(channel,async(event,method,args)=>{if(global.__delay[method])await new Promise(resolve=>setTimeout(resolve,global.__delay[method]));return handler(event,method,args);});app.setPath('userData',${JSON.stringify(path.join(temp, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
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
  page.on("pageerror", (e) => errors.push(e.message));
  for (const [file, expected] of [
    ["v1-memory-change", "Review"],
    ["v2-approved", "No finding"],
    ["v2-unapproved", "Review"],
    ["v1-secondary-change", "Review"],
    ["v1-unreadable", "Unknown"],
  ]) {
    const dataTab = page.getByRole("button", { name: "Data", exact: true });
    if (await dataTab.isVisible()) await dataTab.click();
    await app.evaluate(
      ({ dialog }, file) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [file],
        });
      },
      path.join(captureRoot, captureFolder, file + ".jsonl"),
    );
    await page
      .getByRole("button", { name: "Import evidence", exact: true })
      .click();
    if (file === "v1-memory-change")
      await app.evaluate(() => {
        global.__delay.analyze = 600;
      });
    await page.getByRole("button", { name: "Analyze", exact: true }).click();
    if (file === "v1-memory-change") {
      await page.waitForFunction(
        () => document.querySelector("fieldset.workspace")?.disabled === true,
      );
      await page.getByText(/Analyzing records/).waitFor();
    }
    await page.getByRole("button", { name: "Results", exact: true }).click();
    const evidence = await page.evaluate(async (file) => {
      const state = await window.surge.request("state", {});
      return await window.surge.request("evidence", {
        revision: state.value.revision,
        row: file === "v1-secondary-change" ? 4 : 3,
      });
    }, file);
    assert.equal(evidence.ok, true);
    assert.equal(evidence.value.status, expected);
    const coverage = evidence.value.groups.find((g) => g.field === "Coverage");
    assert.equal(
      coverage.value,
      expected === "Unknown" ? "1/2 ranges read" : "2/2 ranges read",
    );
    if (expected !== "No finding" && file !== "v2-unapproved") {
      await app.evaluate(() => {
        global.__delay.evidence = 600;
      });
      await page.getByRole("checkbox", { name: "Findings only" }).uncheck();
      await page.locator(".view:not([hidden]) tbody tr").first().click();
      await page
        .locator(".evidence")
        .getByText(/Code hash:/)
        .waitFor();
      await page
        .locator(".view:not([hidden]) tbody tr")
        .filter({ hasText: expected })
        .first()
        .click();
      await page
        .locator(".evidence")
        .getByText(/Loading record/)
        .waitFor();
      assert.equal(
        await page.locator(".evidence").getAttribute("aria-busy"),
        "true",
      );
      await page
        .locator(".evidence")
        .getByText(/Code hash:/)
        .waitFor();
      await page
        .locator(".evidence")
        .getByText(/Coverage:/)
        .waitFor();
      assert.ok(
        await page
          .locator(".evidence")
          .getByText(/Expected:/)
          .isVisible(),
      );
      if (expected === "Review") {
        assert.notEqual(evidence.value.groups[0].value, "Unavailable");
        assert.equal(
          await page.locator(".evidence").getAttribute("aria-busy"),
          "false",
        );
        await page
          .locator(".evidence")
          .getByText("Code: Changed", { exact: true })
          .waitFor();
        assert.equal(
          await page
            .locator(".evidence")
            .getByText(/memory_matches: false/)
            .isVisible(),
          false,
        );
        const code = evidence.value.groups.find((g) => g.field === "Code");
        assert.match(code.lines[0].details, /memory_matches: false/);
        await app.evaluate(({ dialog }) => {
          global.__delay.save = 600;
          dialog.showSaveDialog = async () => ({ canceled: true });
        });
        await require("./test-export-menu.cjs").revealExport(
          page,
          "Export case file",
        );
        await page
          .getByRole("button", { name: "Export case file", exact: true })
          .click();
        await page.getByText(/Saving case/).waitFor();
        assert.equal(
          await page.locator("fieldset.workspace").isDisabled(),
          false,
        );
        await page
          .getByRole("button", { name: "Case details", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Results", exact: true })
          .click();
        await page
          .getByText("Canceled. Your workspace is unchanged.", { exact: true })
          .waitFor();
        await page.screenshot({ path: path.join(out, "native-evidence.png") });
      } else {
        assert.equal(evidence.value.groups[0].value, "Unavailable");
      }
    }
  }
  assert.deepEqual(errors, []);
  console.log(
    "Native desktop checks passed: automatic mapping, changed bytes, approved update, and unavailable evidence.",
  );
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    await app?.close();
  });

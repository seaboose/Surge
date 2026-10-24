// Isolated real desktop, with owned case fixtures and native-dialog selections.
const { _electron } = require("playwright");
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const folder = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(folder, { recursive: true });
const temp = fs.mkdtempSync(path.join(folder, "case-library-"));
const entry = path.join(temp, "entry.cjs"),
  profile = path.join(temp, "profile");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(profile)});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
const source = path.resolve(
    __dirname,
    "../demos/native/changed-code.case.json",
  ),
  original = fs.readFileSync(source);
const exported = path.join(temp, "portable.case.json"),
  checks = [];
let app, page;
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
async function start() {
  app = await _electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
  });
  page = await app.firstWindow();
  page.setDefaultTimeout(10000);
  await page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
}
const call = (method, args = {}) =>
  page.evaluate(
    async ({ method, args }) => {
      const r = await window.surge.request(method, args);
      if (!r.ok) throw Error(r.error);
      return r.value;
    },
    { method, args },
  );
async function click(name, scope = page) {
  await scope.getByRole("button", { name, exact: true }).click();
  await page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
}
async function check(name, fn) {
  await fn();
  checks.push({ name, passed: true });
  console.log("PASS", name);
}
async function selectFile(file) {
  await app.evaluate(({ dialog }, file) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [file],
    });
  }, file);
}
(async () => {
  try {
    await start();
    await check("combined opening and keyboard focus", async () => {
      assert.equal(
        await page.getByRole("heading", { name: "Surge", exact: true }).count(),
        1,
      );
      for (const name of ["Import evidence", "Case library", "Try Demo"])
        assert.equal(
          await page.getByRole("button", { name, exact: true }).count(),
          1,
        );
      await page.keyboard.press("Tab");
      assert.equal(
        await page.locator(":focus").getAttribute("aria-label"),
        "Import evidence",
      );
      await page.screenshot({ path: path.join(temp, "opening.png") });
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setContentSize(720, 540),
      );
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
      );
      await page
        .getByRole("button", { name: "Try Demo", exact: true })
        .scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(temp, "opening-small.png") });
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setContentSize(1120, 740),
      );
    });
    if (process.argv.includes("--opening-only")) return;
    await check("import case into empty library", async () => {
      await click("Case library");
      await page.getByText(/No saved cases yet/).waitFor();
      await selectFile(source);
      await click("Import case");
      await page
        .getByRole("button", { name: "Open case", exact: true })
        .waitFor();
      assert.equal((await call("state")).current, null);
    });
    await check("open verified case", async () => {
      await click("Open case");
      assert.ok((await call("state")).summary);
    });
    await check("save a named independent snapshot", async () => {
      await click("Save a copy");
      await page
        .getByLabel("Case name", { exact: true })
        .fill("Investigation Alpha");
      await click("Save to library");
      assert.equal((await call("library_list")).entries.length, 2);
    });
    let id;
    await check("rename keeps case bytes intact", async () => {
      await click("Case library", page.getByRole("navigation"));
      let row = page
        .locator(".case-list li")
        .filter({ hasText: "Investigation Alpha" });
      id = (await call("library_list")).entries.find(
        (x) => x.name === "Investigation Alpha",
      ).id;
      const before = fs.readFileSync(
        path.join(profile, "cases", id, "case.json"),
      );
      await click("Rename", row);
      await row.getByLabel("New case name").fill("Investigation Beta");
      await click("Save name", row);
      await page
        .locator(".case-list li")
        .filter({ hasText: "Investigation Beta" })
        .getByRole("button", { name: "Rename", exact: true })
        .waitFor();
      assert.deepEqual(
        fs.readFileSync(path.join(profile, "cases", id, "case.json")),
        before,
      );
    });
    await check("export and import portable copy", async () => {
      await app.evaluate(({ dialog }, file) => {
        dialog.showSaveDialog = async () => ({
          canceled: false,
          filePath: file,
        });
      }, exported);
      await click(
        "Export case",
        page.locator(".case-list li").filter({ hasText: "Investigation Beta" }),
      );
      assert.deepEqual(
        fs.readFileSync(exported),
        fs.readFileSync(path.join(profile, "cases", id, "case.json")),
      );
      await selectFile(exported);
      await click("Import case");
      assert.equal((await call("library_list")).entries.length, 3);
      await page.screenshot({ path: path.join(temp, "library.png") });
    });
    await check(
      "delete confirmation cancellation and evidence preservation",
      async () => {
        const row = page
          .locator(".case-list li")
          .filter({ hasText: "Investigation Beta" });
        await app.evaluate(({ dialog }) => {
          dialog.showMessageBox = async () => ({ response: 0 });
        });
        await click("Delete case", row);
        assert.equal((await call("library_list")).entries.length, 3);
        await app.evaluate(({ dialog }) => {
          dialog.showMessageBox = async () => ({ response: 1 });
        });
        await click("Delete case", row);
        assert.equal((await call("library_list")).entries.length, 2);
        assert.deepEqual(fs.readFileSync(source), original);
        assert.ok(fs.existsSync(exported));
        assert.ok((await call("state")).summary);
      },
    );
    await check(
      "invalid import and renderer path rejection preserve state",
      async () => {
        const before = await call("state"),
          bad = path.join(temp, "invalid.case.json");
        fs.writeFileSync(bad, "{}");
        await selectFile(bad);
        await click("Import case");
        await page.getByRole("dialog", { name: "Check input" }).waitFor();
        assert.equal((await call("state")).revision, before.revision);
        assert.equal((await call("library_list")).entries.length, 2);
        await click("Close", page.getByRole("dialog", { name: "Check input" }));
        await assert.rejects(call("library_open", { id: "../original" }));
        await assert.rejects(call("library_import", { path: source }));
      },
    );
    await check("library persists across desktop restart", async () => {
      await app.close();
      app = null;
      await start();
      await click("Case library");
      assert.equal((await call("library_list")).entries.length, 2);
      await click(
        "Open case",
        page.locator(".case-list li").filter({ hasText: "portable" }),
      );
      assert.ok((await call("state")).summary);
    });
  } catch (error) {
    checks.push({ passed: false, error: error.stack });
    throw error;
  } finally {
    fs.writeFileSync(
      path.join(temp, "results.json"),
      JSON.stringify(checks, null, 2),
    );
    console.log("Evidence:", temp);
    if (app) await app.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

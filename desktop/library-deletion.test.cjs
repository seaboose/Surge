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
    await page.screenshot({ path: path.join(temp, "opening.png") });
    await click("Case library");
    await selectFile(source);
    await click("Import case");
    await click("Open case");
    const initial = await call("state");
    await check("canceled deletion retains membership", async () => {
      await click("Case library", page.getByRole("navigation"));
      await app.evaluate(({ dialog }) => {
        dialog.showMessageBox = async () => ({ response: 0 });
      });
      await click("Delete case");
      assert.equal(
        await page.getByText("Saved in library", { exact: true }).count(),
        1,
      );
      assert.equal((await call("library_list")).entries.length, 1);
    });
    await check(
      "opened deletion clears membership and preserves evidence",
      async () => {
        await app.evaluate(({ dialog }) => {
          dialog.showMessageBox = async () => ({ response: 1 });
        });
        await click("Delete case");
        assert.equal((await call("library_list")).entries.length, 0);
        assert.equal(
          await page.getByText("Saved in library", { exact: true }).count(),
          0,
        );
        assert.deepEqual(await call("state"), initial);
        await click("Close", page.getByRole("dialog"));
        await page.getByText(/Viewing saved case:/).waitFor();
        await page.screenshot({
          path: path.join(temp, "deleted-open-case.png"),
        });
      },
    );
    await check(
      "recently saved deletion clears stale reopen action",
      async () => {
        await click("Save a copy");
        await page
          .getByLabel("Case name", { exact: true })
          .fill("Deletion regression");
        await click("Save to library");
        assert.equal(
          await page.getByText("Saved in library", { exact: true }).count(),
          1,
        );
        await call("library_save", {
          name: "Unrelated copy",
          revision: (await call("state")).revision,
        });
        await click("Case library", page.getByRole("navigation"));
        await click(
          "Delete case",
          page.locator(".case-list li").filter({ hasText: "Unrelated copy" }),
        );
        assert.equal(
          await page.getByText("Saved in library", { exact: true }).count(),
          1,
        );
        await click("Delete case");
        await click("Close", page.getByRole("dialog"));
        assert.equal(
          await page.getByText("Saved in library", { exact: true }).count(),
          0,
        );
        assert.equal(
          await page
            .getByRole("button", { name: "Open saved case", exact: true })
            .count(),
          0,
        );
        assert.deepEqual((await call("state")).summary, initial.summary);
        assert.deepEqual(fs.readFileSync(source), original);
      },
    );
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

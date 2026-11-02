const path = require("node:path"),
  fs = require("node:fs"),
  assert = require("node:assert/strict");
const desktop = __dirname,
  { _electron } = require(path.join(desktop, "node_modules/playwright"));
const stage = Number(process.argv[2] || 7),
  out = path.resolve(desktop, "../verification/electron");
fs.mkdirSync(out, { recursive: true });
const dir = fs.mkdtempSync(path.join(out, `demo-flow-${stage}-`)),
  entry = path.join(dir, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(dir, "profile"))});require(${JSON.stringify(path.join(desktop, "main.cjs"))});`,
);
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  const app = await _electron.launch({
    executablePath: require(path.join(desktop, "node_modules/electron")),
    args: [entry],
    env,
  });
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(10000);
    const ready = () =>
      page.waitForFunction(
        () => document.querySelector(".app")?.dataset.working === "false",
      );
    const click = async (name) => {
      await page.getByRole("button", { name, exact: true }).click();
      await ready();
    };
    await ready();
    await click("Try Demo");
    assert.equal(
      await page.getByRole("region", { name: "Welcome to Surge" }).count(),
      0,
    );
    await click("Back to start");
    await page.getByRole("heading", { name: "Surge", exact: true }).waitFor();
    await click("Try Demo");
    if (stage >= 2) {
      assert.equal(
        await page.locator(".demo-guide").getAttribute("open"),
        null,
      );
      await page
        .getByText("Start collection to observe the included sample app.", {
          exact: true,
        })
        .waitFor();
      await page.locator(".demo-guide summary").click();
      await page.getByText(/No finding is the expected result/).waitFor();
      await page.locator(".demo-guide summary").click();
    }
    if (stage >= 3) {
      await click("Start collection");
      await page.waitForFunction(
        async () =>
          (await window.surge.request("native_status", {})).value.capture
            .samples >= 2,
      );
      await click("Inspect snapshot");
      await page
        .getByRole("button", { name: "Inspect newer snapshot", exact: true })
        .waitFor();
      await page
        .getByRole("region", { name: "Demo snapshot result" })
        .getByText(/Expected demo result: all 2 configured ranges match/)
        .waitFor();
      await click("Stop collection");
      if (stage >= 4)
        await page
          .getByText(
            "Collection stopped. The final snapshot is open and ready to save.",
            { exact: true },
          )
          .waitFor();
      if (stage >= 5) {
        assert.equal(
          await page
            .getByRole("button", { name: "Export case file", exact: true })
            .isVisible(),
          false,
        );
        await page
          .locator(".view:not([hidden]) .export-options summary")
          .click();
        for (const name of [
          "Export case file",
          "Export alerts",
          "Export captured records",
        ])
          await page.getByRole("button", { name, exact: true }).waitFor();
        await app.evaluate(
          ({ dialog }, file) => {
            dialog.showSaveDialog = async () => ({
              canceled: false,
              filePath: file,
            });
          },
          path.join(dir, "demo.case.json"),
        );
        await click("Export case file");
        assert.ok(fs.existsSync(path.join(dir, "demo.case.json")));
        assert.equal(
          await page
            .locator(".view:not([hidden]) .export-options")
            .getAttribute("open"),
          null,
        );
      }
      if (stage >= 6) {
        assert.ok(
          (
            await page
              .getByRole("button", { name: "Save case", exact: true })
              .getAttribute("class")
          ).includes("primary"),
        );
        assert.ok(
          !(
            (await page
              .getByRole("button", {
                name: "Start another capture",
                exact: true,
              })
              .getAttribute("class")) || ""
          ).includes("primary"),
        );
      }
      if (stage >= 7) {
        await click("Save case");
        assert.match(
          await page.getByLabel("Case name", { exact: true }).inputValue(),
          /^Demo investigation/,
        );
        await page
          .getByLabel("Case name", { exact: true })
          .fill("My first demo");
        await click("Save to library");
        await page
          .getByRole("region", { name: "Case saved" })
          .getByText("Saved “My first demo” to Case library.", { exact: true })
          .waitFor();
        await click("Open library");
        await page
          .locator(".case-list")
          .getByText("My first demo", { exact: true })
          .waitFor();
        await click("Close");
      }
    }
    await page.screenshot({ path: path.join(dir, "demo.png") });
    if (stage >= 7) {
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setContentSize(720, 540),
      );
      await app.evaluate(({ dialog }) => {
        dialog.showSaveDialog = async () => ({ canceled: true });
      });
      for (const name of [
        "Export case file",
        "Export alerts",
        "Export captured records",
      ]) {
        await page
          .locator(".view:not([hidden]) .export-options summary")
          .click();
        await click(name);
        assert.equal(
          await page
            .locator(".view:not([hidden]) .export-options")
            .getAttribute("open"),
          null,
        );
      }
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth + 2,
        ),
        false,
      );
      await page.screenshot({ path: path.join(dir, "small.png") });
      await page.locator(".view:not([hidden]) .export-options summary").click();
      await page.keyboard.press("Escape");
      assert.equal(
        await page
          .locator(".view:not([hidden]) .export-options")
          .getAttribute("open"),
        null,
      );
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setContentSize(1120, 740),
      );
    }
    if (stage >= 7) {
      await click("Start another capture");
      await page.waitForFunction(
        async () =>
          (await window.surge.request("native_status", {})).value.capture
            .samples >= 2,
      );
      await click("Inspect snapshot");
      await click("Save case");
      await page
        .getByText(/Collection is still running. This saves only the snapshot/)
        .waitFor();
      await click("Close");
      await click("Stop collection");
      await page.evaluate(async () => {
        const r = await window.surge.request("native_start", { build: "v1" });
        if (!r.ok) throw Error(r.error);
      });
      // Internal v1 start bypasses React; reload its initial state before
      // exercising controls that correctly disable an already-final snapshot.
      await page.reload();
      await ready();
      await page.waitForFunction(
        async () =>
          (await window.surge.request("native_status", {})).value.capture
            .samples >= 2,
      );
      await click("Inspect snapshot");
      const result = page.getByRole("region", { name: "Demo snapshot result" });
      await result.getByText(/Expected match not established/).waitFor();
      assert.ok(!(await result.innerText()).includes("Expected demo result:"));
      await click("Stop collection");
    }
    fs.writeFileSync(
      path.join(dir, "results.json"),
      JSON.stringify(
        {
          stage,
          status: "passed",
          checks:
            "Seven UX stages; live-save explanation; v1 unapproved evidence does not show success",
        },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ stage, status: "passed", artifacts: dir }));
  } finally {
    await app.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

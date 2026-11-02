const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { _electron } = require("playwright");
const stage = Number(process.argv[2] || 6),
  base = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(base, { recursive: true });
const dir = fs.mkdtempSync(path.join(base, `demo-polish-${stage}-`)),
  entry = path.join(dir, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(dir, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
let app, page;
const checks = [];
(async () => {
  try {
    const env = { ...process.env };
    delete env.ELECTRON_RUN_AS_NODE;
    app = await _electron.launch({
      executablePath: require("electron"),
      args: [entry],
      env,
    });
    page = await app.firstWindow();
    page.setDefaultTimeout(10000);
    const ready = () =>
      page.waitForFunction(
        () => document.querySelector(".app")?.dataset.working === "false",
      );
    const click = async (name) => {
      await page.getByRole("button", { name, exact: true }).click();
      await ready();
    };
    const state = () =>
      page.evaluate(
        async () => (await window.surge.request("state", {})).value,
      );
    await ready();
    await click("Try Demo");
    await click("Start collection");
    await page
      .locator(".demo-next")
      .getByText("Observations available—you can inspect now.", { exact: true })
      .waitFor();
    const available = (await state()).capture;
    assert.ok(available.samples > 0 && available.records > 0);
    checks.push("Readiness follows actual retained observations");
    if (stage >= 2) {
      await page
        .getByText(
          "Inspect while collecting, or stop to review the final snapshot.",
          { exact: true },
        )
        .waitFor();
      checks.push("Intermediate inspection is explicitly optional");
    }
    await click("Stop collection");
    const stopped = await state();
    assert.ok(stopped.summary);
    assert.equal(stopped.inspected_capture.capture_state, "stopped");
    await page
      .locator('table[aria-label="Results"] tbody tr')
      .first()
      .waitFor();
    if (stage >= 3) {
      assert.match(
        await page
          .locator('table[aria-label="Results"] tbody tr')
          .first()
          .innerText(),
        /Matched approved reference/,
      );
      checks.push("Normal native row explains the verified match");
    }
    if (stage >= 4) {
      assert.equal(
        await page
          .getByText("Priority keeps gaps visible. Exports use priority.", {
            exact: true,
          })
          .isVisible(),
        false,
      );
      await page.getByText("What the results mean", { exact: true }).click();
      await page
        .getByText("Priority keeps gaps visible. Exports use priority.", {
          exact: true,
        })
        .waitFor();
      await page.getByText("What the results mean", { exact: true }).click();
      checks.push("Secondary filter guidance is available in help");
    }
    await click("Save case");
    await page.getByLabel("Case name", { exact: true }).fill("Demo saved once");
    await click("Save to library");
    if (stage >= 5) {
      assert.doesNotMatch(
        await page.locator(".demo-next").innerText(),
        /Demo complete|saved case/,
      );
      assert.equal((await page.locator("footer").innerText()).trim(), "Ready.");
      await page
        .getByRole("region", { name: "Case saved" })
        .getByText(/already saved/)
        .waitFor();
      checks.push("One confirmation announces save; reopening is optional");
    }
    await click("Open saved case");
    assert.equal((await state()).inspected_capture, null);
    assert.equal(
      await page.getByRole("region", { name: "Demo app collection" }).count(),
      0,
    );
    if (stage >= 6) {
      await click("Save a copy");
      assert.equal(
        await page.getByLabel("Case name", { exact: true }).inputValue(),
        "Demo saved once — copy",
      );
      await page
        .getByLabel("Case name", { exact: true })
        .fill("My renamed copy");
      await click("Save to library");
      await click("Open saved case");
      await page
        .getByRole("region", { name: "Saved case" })
        .getByText("Viewing saved case: My renamed copy", { exact: true })
        .waitFor();
      assert.deepEqual((await state()).summary, stopped.summary);
      checks.push(
        "Copy has editable suggested name and preserves original evidence",
      );
    }
    await page.screenshot({ path: path.join(dir, "reopened.png") });
    fs.writeFileSync(
      path.join(dir, "results.json"),
      JSON.stringify({ stage, status: "passed", checks }, null, 2),
    );
    console.log(
      JSON.stringify({ stage, status: "passed", checks, artifacts: dir }),
    );
  } catch (e) {
    fs.writeFileSync(path.join(dir, "failure.txt"), e.stack);
    if (page)
      await page
        .screenshot({ path: path.join(dir, "failure.png") })
        .catch(() => {});
    throw e;
  } finally {
    if (app) await app.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

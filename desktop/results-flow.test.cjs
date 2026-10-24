const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { _electron } = require("playwright");
const stage = Number(process.argv[2] || 3),
  base = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(base, { recursive: true });
const dir = fs.mkdtempSync(path.join(base, `results-flow-${stage}-`)),
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
    if (stage >= 3) {
      assert.equal(
        (await page.locator("footer").innerText()).trim(),
        "Collecting.",
      );
      assert.equal(
        await page
          .getByText("Observations available—you can inspect now.", {
            exact: true,
          })
          .count(),
        1,
      );
      checks.push("Readiness appears once; footer reports operational status");
    }
    await click("Inspect snapshot");
    await page.locator(".results-table tbody tr").first().waitFor();
    if (stage >= 2) {
      await page
        .getByRole("button", { name: "Results", exact: true })
        .waitFor();
      assert.equal(
        await page
          .getByRole("button", { name: "Findings", exact: true })
          .count(),
        0,
      );
      await page.getByRole("table", { name: "Results", exact: true }).waitFor();
      await page.getByLabel("Findings only", { exact: true }).waitFor();
      await click("Data");
      await page.keyboard.press("Alt+2");
      await page
        .getByRole("button", { name: "Results", exact: true })
        .getAttribute("aria-current")
        .then((x) => assert.equal(x, "page"));
      checks.push(
        "Results labels and keyboard navigation agree; Findings only remains a filter",
      );
    }
    await click("Stop collection");
    const stopped = await state();
    assert.equal(
      await page
        .locator(".results-table tbody tr")
        .first()
        .locator("td")
        .nth(3)
        .innerText(),
      "Matched approved reference",
    );
    await page
      .getByRole("region", { name: "Record evidence" })
      .getByText(
        /matched its recorded approved reference for code and page protection/,
      )
      .waitFor();
    for (const size of [
      [1120, 740],
      [720, 540],
    ]) {
      await app.evaluate(
        ({ BrowserWindow }, size) =>
          BrowserWindow.getAllWindows()[0].setContentSize(...size),
        size,
      );
      const cell = page
        .locator(".results-table tbody tr")
        .first()
        .locator("td")
        .nth(2);
      await cell.scrollIntoViewIfNeeded();
      assert.equal(
        await cell.evaluate((el) => {
          const r = document.createRange();
          r.selectNodeContents(el);
          return r.getClientRects().length;
        }),
        1,
      );
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth + 2,
        ),
        false,
      );
    }
    checks.push(
      "Result stays on one line at normal and minimum size; detailed evidence remains accessible",
    );
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setContentSize(1120, 740),
    );
    await click("Save case");
    await page.getByLabel("Case name", { exact: true }).fill("Results review");
    await click("Save to library");
    await click("Open saved case");
    assert.equal((await state()).inspected_capture, null);
    assert.deepEqual((await state()).summary, stopped.summary);
    assert.equal(
      await page.getByRole("region", { name: "Demo app collection" }).count(),
      0,
    );
    await page.getByRole("region", { name: "Saved observations" }).waitFor();
    await page.screenshot({ path: path.join(dir, "reopened.png") });
    checks.push(
      "Reopened results retain verified evidence without live association",
    );
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

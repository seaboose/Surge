// Owned sample app, isolated library. Stages support a short check after each change.
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { _electron } = require("playwright");
const stage = Number(process.argv[2] || 6);
const base = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(base, { recursive: true });
const dir = fs.mkdtempSync(path.join(base, `saved-flow-${stage}-`));
const entry = path.join(dir, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(dir, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
const checks = [];
let app, page;
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  try {
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
    const click = async (name, scope = page) => {
      await scope.getByRole("button", { name, exact: true }).click();
      await ready();
    };
    const state = () =>
      page.evaluate(
        async () => (await window.surge.request("state", {})).value,
      );
    await ready();
    await click("Try Demo");
    if (stage >= 5)
      assert.match(await page.locator("footer").innerText(), /Demo ready/);
    await click("Start collection");
    await page.waitForFunction(
      async () =>
        (await window.surge.request("native_status", {})).value.capture
          .samples >= 2,
    );
    await click("Inspect snapshot");
    await page
      .getByRole("region", { name: "Demo snapshot result" })
      .getByText(/Expected demo result/)
      .waitFor();
    if (stage >= 4) {
      assert.match(
        await page
          .getByRole("button", { name: "Stop collection", exact: true })
          .getAttribute("class"),
        /primary/,
      );
      assert.doesNotMatch(
        (await page
          .getByRole("button", { name: "Inspect newer snapshot", exact: true })
          .getAttribute("class")) || "",
        /primary/,
      );
      checks.push(
        "Stop is primary after inspection; newer inspection is secondary",
      );
    }
    if (stage >= 5) {
      assert.match(await page.locator("footer").innerText(), /Collecting/);
      assert.equal(
        await page.locator('table[aria-label="Results"] caption').innerText(),
        "Observations",
      );
    }
    await click("Stop collection");
    if (stage >= 5) {
      assert.match(
        await page.locator("footer").innerText(),
        /Collection stopped/,
      );
      checks.push("Footer follows demo steps and table says Observations");
    }
    await click("Save case");
    await page
      .getByLabel("Case name", { exact: true })
      .fill("First demo review");
    await click("Save to library");
    await page.getByRole("region", { name: "Case saved" }).waitFor();
    const saved = await state();
    if (stage >= 6) {
      await click("Open saved case");
      checks.push("Save confirmation opens exact saved case directly");
    } else {
      await click("Open library");
      await click("Open case");
    }
    await page
      .locator('table[aria-label="Results"] tbody tr')
      .first()
      .waitFor();
    assert.equal(
      await page.getByLabel("Findings only", { exact: true }).isChecked(),
      false,
    );
    assert.equal(
      await page.locator('table[aria-label="Results"] tbody tr').count(),
      saved.summary.total,
    );
    await page.getByLabel("Findings only", { exact: true }).check();
    await click("Show all observations");
    await page
      .locator('table[aria-label="Results"] tbody tr')
      .first()
      .waitFor();
    assert.equal(
      await page.getByLabel("Findings only", { exact: true }).isChecked(),
      false,
    );
    await page.getByLabel("Search records").fill("no-such-owned-record");
    await page.getByLabel("Priority", { exact: true }).selectOption("Critical");
    await click("Show all observations");
    await page
      .locator('table[aria-label="Results"] tbody tr')
      .first()
      .waitFor();
    assert.equal(await page.getByLabel("Search records").inputValue(), "");
    assert.equal(
      await page.getByLabel("Priority", { exact: true }).inputValue(),
      "All",
    );
    checks.push(
      "Normal saved case opens with observations; empty-filter recovery clears all filters",
    );
    if (stage >= 2) {
      await page
        .getByRole("region", { name: "Saved case" })
        .getByText("Viewing saved case: First demo review", { exact: true })
        .waitFor();
      assert.equal(
        await page.getByRole("region", { name: "Demo app collection" }).count(),
        0,
      );
      assert.equal((await state()).inspected_capture, null);
      checks.push(
        "Reopen leaves demo panel and identifies saved case without runtime provenance",
      );
    }
    if (stage >= 3) {
      const result = page.getByRole("region", { name: "Saved observations" });
      await result.getByText(/all 2 configured ranges matched/).waitFor();
      assert.equal((await state()).saved_result.expected, true);
      await result.getByText(/Saved evidence only/).waitFor();
      checks.push(
        "Historical summary reflects verified approved evidence and limits scope",
      );
      const before = await state();
      await page.getByText("Previous demo capture", { exact: true }).click();
      await click("View demo capture");
      await page.getByText(/Saved case remains open below/).waitFor();
      await click("Start another capture");
      await click("Case library", page.getByRole("navigation"));
      await click("Open case");
      await page
        .getByText("Live demo capture is running separately.", { exact: true })
        .waitFor();
      const reopened = await state();
      assert.equal(reopened.capture.state, "running");
      assert.notEqual(reopened.capture.session_id, before.capture.session_id);
      assert.deepEqual(reopened.saved_result, before.saved_result);
      assert.deepEqual(reopened.summary, before.summary);
      assert.equal(reopened.inspected_capture, null);
      assert.equal(reopened.demo_result, null);
      assert.equal(
        await page.getByRole("region", { name: "Demo app collection" }).count(),
        0,
      );
      checks.push(
        "Concurrent capture stays separate and cannot change saved summary",
      );
    }
    await page.screenshot({ path: path.join(dir, "reopened.png") });
    if (stage >= 6) {
      await app.close();
      app = null;
      app = await _electron.launch({
        executablePath: require("electron"),
        args: [entry],
        env,
      });
      page = await app.firstWindow();
      page.setDefaultTimeout(10000);
      await ready();
      await click("Case library");
      await click("Open case");
      await page
        .getByRole("region", { name: "Saved observations" })
        .getByText(/all 2 configured ranges matched/)
        .waitFor();
      assert.equal((await state()).capture, null);
      assert.equal((await state()).inspected_capture, null);
      assert.deepEqual((await state()).summary, saved.summary);
      assert.equal(
        await page
          .getByRole("button", { name: "View demo capture", exact: true })
          .count(),
        0,
      );
      await page
        .locator('table[aria-label="Results"] tbody tr')
        .first()
        .waitFor();
      await page.screenshot({ path: path.join(dir, "reopened-fresh.png") });
      checks.push(
        "After app restart, case reopens with its verified observations and no collector",
      );
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setContentSize(720, 540),
      );
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth + 2,
        ),
        false,
      );
      await page
        .getByRole("button", { name: "Save a copy", exact: true })
        .scrollIntoViewIfNeeded();
      await page
        .locator('table[aria-label="Results"] tbody tr')
        .first()
        .scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(dir, "reopened-small.png") });
      checks.push(
        "Minimum window retains reachable observations without horizontal overflow",
      );
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setContentSize(1120, 740),
      );
      await click("Case library", page.getByRole("navigation"));
      await click("Rename");
      await page.getByLabel("New case name").fill("Renamed first demo");
      await click("Save name");
      await page
        .locator(".case-list")
        .getByText("Renamed first demo", { exact: true })
        .waitFor();
      await click("Close");
      await page
        .getByRole("region", { name: "Saved case" })
        .getByText("Viewing saved case: Renamed first demo", { exact: true })
        .waitFor();
      assert.deepEqual((await state()).summary, saved.summary);
      checks.push(
        "Renaming the open case updates its label without changing verified evidence",
      );
    }
    fs.writeFileSync(
      path.join(dir, "results.json"),
      JSON.stringify({ stage, status: "passed", checks }, null, 2),
    );
    console.log(
      JSON.stringify({ stage, status: "passed", checks, artifacts: dir }),
    );
  } catch (e) {
    fs.writeFileSync(path.join(dir, "failure.txt"), e.stack || String(e));
    if (page)
      await page
        .screenshot({ path: path.join(dir, "failure.png") })
        .catch(() => {});
    console.error(JSON.stringify({ stage, status: "failed", artifacts: dir }));
    throw e;
  } finally {
    if (app) await app.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

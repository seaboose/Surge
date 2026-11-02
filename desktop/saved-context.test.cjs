// Isolated owned demo: simulate an out-of-band stop, then edit/export a saved case.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { _electron } = require("playwright");
const base = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(base, { recursive: true });
const dir = fs.mkdtempSync(path.join(base, "saved-context-"));
const entry = path.join(dir, "entry.cjs");
fs.writeFileSync(
  entry,
  `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(dir, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);
const checks = [];
let app, page;
const ready = () =>
  page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
const call = (method, args = {}) =>
  page.evaluate(
    async ({ method, args }) => {
      const result = await window.surge.request(method, args);
      if (!result.ok) throw Error(result.error);
      return result.value;
    },
    { method, args },
  );
const click = async (name) => {
  await page.getByRole("button", { name, exact: true }).click();
  await ready();
};
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
    await ready();
    await click("Try Demo");
    await click("Start collection");
    await page.waitForFunction(
      async () =>
        (await window.surge.request("native_status", {})).value.capture
          .samples >= 2,
    );
    await click("Inspect snapshot");
    await page.getByRole("region", { name: "Demo snapshot result" }).waitFor();
    const inspected = (await call("state")).inspected_capture;
    assert.equal(inspected.capture_state, "running");
    const deadline = Date.now() + 10000;
    while (
      (await call("native_status")).capture.final_sequence <=
      inspected.final_sequence
    ) {
      assert.ok(
        Date.now() < deadline,
        "Timed out waiting for a newer owned sample",
      );
      await page.waitForTimeout(100);
    }
    // Do not pass this response through React. Its next status poll sees the
    // stopped collector while the displayed snapshot remains the older one.
    const stopped = await call("native_stop");
    fs.writeFileSync(
      path.join(dir, "stop-evidence.json"),
      JSON.stringify({ inspected, stopped }, null, 2),
    );
    assert.equal(stopped.capture.state, "stopped");
    assert.ok(stopped.capture.final_sequence > inspected.final_sequence);
    await page
      .locator(".demo-next")
      .getByText("Inspect the available evidence before saving a case.", {
        exact: true,
      })
      .waitFor();
    assert.doesNotMatch(
      await page.locator(".demo-next").innerText(),
      /final snapshot is open/i,
    );
    assert.doesNotMatch(
      (await page
        .getByRole("button", { name: "Save case", exact: true })
        .getAttribute("class")) || "",
      /primary/,
    );
    await page.screenshot({
      path: path.join(dir, "older-snapshot-after-stop.png"),
    });
    checks.push(
      "Out-of-band stop leaves earlier displayed snapshot explicitly non-final",
    );
    await click("Inspect snapshot");
    await page
      .locator(".demo-next")
      .getByText(
        "Collection stopped. The final snapshot is open and ready to save.",
        { exact: true },
      )
      .waitFor();
    const final = await call("state");
    assert.equal(final.inspected_capture.capture_state, "stopped");
    assert.equal(
      final.inspected_capture.final_sequence,
      final.capture.final_sequence,
    );
    assert.match(
      await page
        .getByRole("button", { name: "Save case", exact: true })
        .getAttribute("class"),
      /primary/,
    );
    checks.push(
      "Explicit final inspection matches stopped endpoint and enables save emphasis",
    );

    await click("Save case");
    await page
      .getByLabel("Case name", { exact: true })
      .fill("Original owned demo");
    await click("Save to library");
    await click("Open saved case");
    await page.getByRole("region", { name: "Saved case" }).waitFor();
    const originalState = await call("state");
    const originalPath = originalState.case_file.path;
    const originalBytes = fs.readFileSync(originalPath);
    const rules = [
      ...originalState.config.rules,
      {
        name: "Test review rule",
        field: "memory_status",
        op: "eq",
        value: "complete",
        priority: "Notice",
      },
    ];
    await click("Data");
    await page.getByText("Options", { exact: true }).click();
    await click("Edit rules");
    await page.getByLabel("Rules", { exact: true }).fill(JSON.stringify(rules));
    await click("Apply rules");
    await page
      .getByText("Working from saved case: Original owned demo", {
        exact: true,
      })
      .waitFor();
    assert.equal((await call("state")).saved_result, null);
    await click("Analyze");
    await page
      .getByRole("button", { name: "Save as new case", exact: true })
      .waitFor();
    assert.equal(
      await page.getByText("Saved in library", { exact: true }).count(),
      0,
    );
    assert.ok(
      (await call("state")).summary.Review > originalState.summary.Review,
    );
    const exported = path.join(dir, "edited-export.case.json");
    await app.evaluate(({ dialog }, file) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
    }, exported);
    await page.getByText("Export…", { exact: true }).click();
    await click("Export case file");
    assert.ok(fs.existsSync(exported));
    const context = page.getByRole("region", { name: "Saved case" });
    assert.match(
      await context.innerText(),
      /Working from saved case: Original owned demo/,
    );
    assert.match(
      await context.innerText(),
      /Workspace settings have changed\. The saved copy is unchanged\./,
    );
    assert.doesNotMatch(await context.innerText(), /Historical evidence/);
    assert.match(
      await page.locator("footer").innerText(),
      /Working from a saved case/,
    );
    assert.equal(
      await page.getByRole("region", { name: "Saved observations" }).count(),
      0,
    );
    assert.deepEqual(fs.readFileSync(originalPath), originalBytes);
    const exportedPayload = JSON.parse(
      fs.readFileSync(exported, "utf8"),
    ).payload;
    const originalPayload = JSON.parse(originalBytes.toString("utf8")).payload;
    assert.notDeepEqual(exportedPayload.config, originalPayload.config);
    assert.ok(
      exportedPayload.result.summary.Review >
        originalPayload.result.summary.Review,
    );
    await page.screenshot({
      path: path.join(dir, "edited-export-context.png"),
    });
    checks.push(
      "UI-edited case export retains original-case modification label and leaves library bytes unchanged",
    );
    const result = {
      status: "passed",
      checks,
      artifacts: dir,
      limitations: [
        "Out-of-band stop is simulated using the owned collector's stop request; the 10-minute timer was not waited out.",
      ],
    };
    fs.writeFileSync(
      path.join(dir, "results.json"),
      JSON.stringify(result, null, 2),
    );
    console.log(JSON.stringify(result));
  } catch (error) {
    fs.writeFileSync(
      path.join(dir, "failure.txt"),
      error.stack || String(error),
    );
    fs.writeFileSync(
      path.join(dir, "results.json"),
      JSON.stringify({ status: "failed", checks, artifacts: dir }, null, 2),
    );
    if (page)
      await page
        .screenshot({ path: path.join(dir, "failure.png") })
        .catch(() => {});
    console.error(JSON.stringify({ status: "failed", artifacts: dir }));
    throw error;
  } finally {
    if (app) await app.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

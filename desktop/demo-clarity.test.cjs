const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { _electron } = require("playwright");
const stage = Number(process.argv[2] || 6),
  base = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(base, { recursive: true });
const dir = fs.mkdtempSync(path.join(base, `demo-clarity-${stage}-`)),
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
    await click("Back to start");
    await page.getByRole("heading", { name: "Surge", exact: true }).waitFor();
    await click("Try Demo");
    await click("Start collection");
    await page.waitForFunction(
      async () =>
        (await window.surge.request("native_status", {})).value.capture
          .samples >= 2,
    );
    await click("Inspect snapshot");
    assert.equal(
      await page
        .getByRole("button", { name: "Hide demo controls", exact: true })
        .isDisabled(),
      true,
    );
    await click("Stop collection");
    const stopped = await state();
    if (stage >= 2) {
      assert.equal(
        await page
          .getByRole("button", { name: "Inspect snapshot", exact: true })
          .isDisabled(),
        true,
      );
      checks.push("Final snapshot does not request another inspection");
    }
    if (stage >= 5) {
      const counts = stopped.observation_counts;
      assert.ok(counts.samples >= 2);
      assert.equal(
        counts.observations,
        counts.samples * counts.ranges_per_sample,
      );
      await page
        .getByRole("region", { name: "Observation counts" })
        .getByText(new RegExp(`${counts.observations} range observations`))
        .waitFor();
      checks.push("Displayed count explanation matches inspected rows");
    }
    if (stage >= 6) {
      await page
        .getByRole("region", { name: "Record evidence" })
        .getByText(/This range matched its recorded approved reference/)
        .waitFor();
      await page
        .getByRole("region", { name: "Record evidence" })
        .getByText(/Code hash:/)
        .waitFor();
      checks.push("Plain explanation precedes accessible technical evidence");
    }
    await click("Hide demo controls");
    assert.equal(
      await page.getByRole("region", { name: "Demo app collection" }).count(),
      0,
    );
    await page
      .locator('table[aria-label="Results"] tbody tr')
      .first()
      .waitFor();
    checks.push("Navigation describes destination and retains investigation");
    await click("Save case");
    await page.getByLabel("Case name", { exact: true }).fill("Clarity review");
    await click("Save to library");
    await click("Open saved case");
    await page.getByRole("region", { name: "Saved observations" }).waitFor();
    if (stage >= 3) {
      assert.equal(
        await page
          .getByText(
            "Historical evidence · opening this case does not start a live check.",
            { exact: true },
          )
          .count(),
        0,
      );
      assert.equal(
        await page
          .getByRole("button", { name: "View demo capture", exact: true })
          .isVisible(),
        false,
      );
      await page.getByText("Previous demo capture", { exact: true }).click();
      await page
        .getByRole("button", { name: "View demo capture", exact: true })
        .waitFor();
      checks.push("Saved banner is concise and stopped capture is collapsed");
      await page.getByText("Previous demo capture", { exact: true }).click();
    }
    if (stage >= 4) {
      await page.getByText("Saved in library", { exact: true }).waitFor();
      await click("Save a copy");
      await page
        .getByRole("dialog", { name: "Save a copy", exact: true })
        .waitFor();
      await click("Close");
      checks.push("Unchanged saved case offers explicit independent copy");
    }
    if (stage >= 5)
      assert.deepEqual(
        (await state()).observation_counts,
        stopped.observation_counts,
      );
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

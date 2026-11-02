// Bounded real-Electron clarity checks; owned fixture and isolated profile only.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const mode = process.argv[2] || "sample";
assert.ok(["sample", "library", "evaluate", "all"].includes(mode));
const root = path.resolve(__dirname, ".."),
  base = path.join(root, "verification/qualification");
fs.mkdirSync(base, { recursive: true });
const dir = fs.mkdtempSync(path.join(base, "visual-clarity-"));
const profile = path.join(dir, "profile"),
  entry = path.join(dir, "entry.cjs");
const checks = [],
  errors = [],
  started = new Date().toISOString();
let app,
  page,
  active = "launch",
  outcome = "failed";
const hash = (file) =>
  crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const source = Object.fromEntries(
  ["src/main.jsx", "src/style.css", "dist/app.js", "dist/style.css"].map(
    (file) => [file, hash(path.join(__dirname, file))],
  ),
);
const ready = () =>
  page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
async function click(name, scope = page) {
  await scope.getByRole("button", { name, exact: true }).click();
  await ready();
}
async function check(name, run) {
  active = name;
  const evidence = await run();
  checks.push({ name, passed: true, evidence });
  console.log("PASS " + name);
}
const read = (method = "state") =>
  page.evaluate(async (method) => {
    const args = {};
    if (method !== "state") {
      const state = await window.surge.request("state", {});
      if (!state.ok) throw Error(state.error);
      args.revision = state.value.revision;
    }
    const response = await window.surge.request(method, args);
    if (!response.ok) throw Error(response.error);
    return response.value;
  }, method);
async function screenshot(name) {
  // Playwright's page-sized screenshot can crop Electron's physical viewport
  // when browser zoom is changed. Capture the actual rendered client surface.
  const png = await app.evaluate(async ({ BrowserWindow }) =>
    (await BrowserWindow.getAllWindows()[0].webContents.capturePage())
      .toPNG()
      .toString("base64"),
  );
  fs.writeFileSync(path.join(dir, name + ".png"), Buffer.from(png, "base64"));
}
async function help(label, prefix) {
  const button = page.getByRole("button", { name: label, exact: true });
  const panel = page.getByRole("note", {
    name: label,
    exact: true,
    includeHidden: true,
  });
  await check(prefix + " starts collapsed", async () => {
    await button.waitFor();
    assert.equal(await panel.count(), 1);
    assert.equal(await panel.isVisible(), false);
  });
  for (const zoom of [1, 1.25, 1.5]) {
    await check(prefix + " fits at zoom " + zoom, async () => {
      await app.evaluate(({ BrowserWindow }, zoom) => {
        const win = BrowserWindow.getAllWindows()[0];
        win.setSize(900, 700);
        win.webContents.setZoomFactor(zoom);
      }, zoom);
      await button.click();
      await panel.waitFor({ state: "visible" });
      const layout = await panel.evaluate((el) => {
        const rect = el.getBoundingClientRect();
        return {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: innerWidth,
          height: innerHeight,
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
          text: el.textContent.trim(),
          documentOverflow:
            document.documentElement.scrollWidth > innerWidth + 2,
        };
      });
      assert.ok(
        layout.left >= 0 &&
          layout.top >= 0 &&
          layout.right <= layout.width + 1 &&
          layout.bottom <= layout.height + 1,
        JSON.stringify(layout),
      );
      assert.ok(
        layout.scrollWidth <= layout.clientWidth + 2,
        "Help text must wrap",
      );
      assert.equal(layout.documentOverflow, false);
      assert.ok(layout.text.length > 20);
      await screenshot(prefix + "-zoom-" + zoom);
      await page.keyboard.press("Escape");
      assert.equal(await panel.isVisible(), false);
      assert.equal(
        await button.evaluate((el) => el === document.activeElement),
        true,
      );
      return layout;
    });
  }
  await check(prefix + " supports keyboard and outside dismissal", async () => {
    await button.focus();
    await page.keyboard.press("Enter");
    await panel.waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    assert.equal(await panel.isVisible(), false);
    assert.equal(
      await button.evaluate((el) => el === document.activeElement),
      true,
    );
    await page.keyboard.press("Space");
    await panel.waitFor({ state: "visible" });
    await page.mouse.click(2, 2);
    assert.equal(await panel.isVisible(), false);
  });
  await check(
    prefix + " supports keyboard access to full help text",
    async () => {
      await button.focus();
      await page.keyboard.press("Enter");
      await panel.waitFor({ state: "visible" });
      await page.keyboard.press("Tab");
      assert.equal(
        await panel.evaluate((el) => el === document.activeElement),
        true,
      );
      const layout = await panel.evaluate((el) => ({
        top: el.scrollTop,
        height: el.clientHeight,
        content: el.scrollHeight,
      }));
      if (layout.content > layout.height + 2) {
        await page.keyboard.press("PageDown");
        await page.waitForFunction((label) => {
          const panel = [...document.querySelectorAll(".info-panel")].find(
            (el) => el.getAttribute("aria-label") === label,
          );
          return panel.scrollTop > 0;
        }, label);
        assert.ok(await panel.evaluate((el) => el.scrollTop > 0));
        await screenshot(prefix + "-keyboard-scroll");
      }
      await page.keyboard.press("Escape");
      assert.equal(await panel.isVisible(), false);
      assert.equal(
        await button.evaluate((el) => el === document.activeElement),
        true,
      );
      return layout;
    },
  );
  await check(
    prefix + " dismisses safely when window size or zoom changes",
    async () => {
      await button.click();
      await panel.waitFor({ state: "visible" });
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(880, 680),
      );
      await panel.waitFor({ state: "hidden" });
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(900, 700),
      );
      await button.click();
      await panel.waitFor({ state: "visible" });
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1),
      );
      await panel.waitFor({ state: "hidden" });
    },
  );
}
(async () => {
  try {
    fs.writeFileSync(
      entry,
      `const {app}=require('electron');app.setPath('userData',${JSON.stringify(profile)});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
    );
    const env = { ...process.env };
    delete env.ELECTRON_RUN_AS_NODE;
    app = await require("playwright")._electron.launch({
      executablePath: require("electron"),
      args: [entry],
      env,
    });
    page = await app.firstWindow();
    page.setDefaultTimeout(10000);
    page.on("pageerror", (error) => errors.push(error.message));
    await ready();
    await screenshot("opening");
    await click("Case library");
    if (["library", "all"].includes(mode))
      await help("About case files", "case-files");
    const file = path.join(root, "demos/native/approved-update.case.json");
    const expected = JSON.parse(
      fs.readFileSync(path.join(root, "demos/native/expected.json"), "utf8"),
    ).cases.find((item) => item.file === path.basename(file));
    assert.equal(hash(file), expected.sha256);
    await app.evaluate(({ dialog }, file) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [file],
      });
    }, file);
    await click("Import case");
    const row = page
      .locator(".case-list li")
      .filter({ has: page.getByText("approved-update", { exact: true }) });
    await click("Open case", row);
    await page
      .getByRole("region", { name: "Saved observations", exact: true })
      .waitFor();
    await check(
      "Visible sample counts match verified saved evidence",
      async () => {
        const state = await read();
        assert.equal(state.inspected_capture, null);
        assert.equal(state.current.records, expected.outcomes.length);
        assert.equal(state.summary["No finding"], expected.outcomes.length);
        assert.equal(state.summary.Review, 0);
        assert.equal(state.summary.Unknown, 0);
        const counts = state.observation_counts;
        assert.ok(
          counts &&
            counts.samples > 0 &&
            counts.observations === expected.outcomes.length,
        );
        const visible = page.getByRole("region", {
          name: "Observation counts",
          exact: true,
        });
        await visible
          .getByText(
            `Viewed evidence: ${counts.samples} retained samples · ${counts.observations} range observations.`,
            { exact: true },
          )
          .waitFor();
        await screenshot("saved-evidence-counts");
        return {
          counts,
          summary: state.summary,
          saved_not_live: state.inspected_capture === null,
        };
      },
    );
    await help("About sample counts", "sample-counts");
    if (["evaluate", "all"].includes(mode)) {
      await page.keyboard.press("Alt+4");
      await ready();
      await help("Labeling guidance", "labeling");
    }
    if (mode === "all") {
      await page.keyboard.press("Alt+5");
      await ready();
      await check(
        "Case details start concise and preserve exact reader fields",
        async () => {
          const data = await read("details");
          const view = page.locator(".view:not([hidden]) .details");
          const settings = view.locator("details").filter({
            has: page.getByText("Analysis settings", { exact: true }),
          });
          const profiles = view.locator("details").filter({
            has: page.getByText("Numeric reference profiles", {
              exact: true,
            }),
          });
          await settings.locator("summary").waitFor();
          assert.equal(await settings.evaluate((el) => el.open), false);
          assert.equal(await profiles.evaluate((el) => el.open), false);
          assert.equal(await settings.locator("pre").isVisible(), false);
          assert.equal(await profiles.locator("pre").isVisible(), false);
          await view
            .getByText(`SHA-256: ${data.source.sha256}`, { exact: true })
            .waitFor();
          await view
            .getByText(
              "Constant references use 1% of the absolute median as scale, with a 1e-9 minimum.",
              { exact: true },
            )
            .waitFor();
          await view
            .getByText(
              "Imported records are unverified claims. Fingerprints do not prove who collected them.",
              { exact: true },
            )
            .waitFor();
          await screenshot("case-details-collapsed");
          await settings.locator("summary").click();
          assert.equal(
            await settings.locator("pre").innerText(),
            data.settings,
          );
          await profiles.locator("summary").click();
          assert.equal(
            await profiles.locator("pre").innerText(),
            data.profiles,
          );
          await screenshot("case-details-expanded");
          return {
            sha256: data.source.sha256,
            settings_equal: true,
            profiles_equal: true,
            summary: data.summary,
          };
        },
      );
    }
    await check("Original evidence and renderer remain intact", async () => {
      assert.equal(hash(file), expected.sha256);
      assert.deepEqual(errors, []);
      const after = Object.fromEntries(
        Object.keys(source).map((file) => [
          file,
          hash(path.join(__dirname, file)),
        ]),
      );
      assert.deepEqual(after, source, "Source/build changed during test");
    });
    outcome = "passed";
  } catch (error) {
    checks.push({ name: active, passed: false, error: error.stack });
    fs.writeFileSync(
      path.join(dir, "failure.txt"),
      error.stack || String(error),
    );
    if (page) await screenshot("failure").catch(() => {});
    console.error(error);
    process.exitCode = 1;
  } finally {
    if (app)
      await app.close().catch((error) => {
        checks.push({ name: "shutdown", passed: false, error: String(error) });
        process.exitCode = 1;
        outcome = "failed";
      });
    fs.writeFileSync(
      path.join(dir, "results.json"),
      JSON.stringify(
        {
          mode,
          status: outcome,
          started,
          finished: new Date().toISOString(),
          source,
          checks,
          renderer_errors: errors,
          limitations: [
            "Automated owned-fixture checks, not unfamiliar-human acceptance.",
            "Native file dialog is substituted to select the published owned case; real controls perform all actions.",
            "Same Windows host, Electron zoom and a small window; no OS display/account matrix or screen-reader certification.",
          ],
        },
        null,
        2,
      ),
    );
    console.log(JSON.stringify({ mode, status: outcome, artifacts: dir }));
  }
})();

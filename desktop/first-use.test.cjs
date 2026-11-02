// Same-host first-use rehearsal, not an unfamiliar-human usability study.
// Run sequentially: replay (before native build), unapproved (before approval),
// approved (after explicit approval of this exact local v2 build).
// Every action uses the interface; native dialogs select only owned fixtures.
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict"),
  crypto = require("node:crypto");
const mode = process.argv[2],
  root = path.resolve(__dirname, ".."),
  base = path.join(root, "verification/electron");
fs.mkdirSync(base, { recursive: true });
const dir = fs.mkdtempSync(path.join(base, "first-use-")),
  profile = path.join(dir, "profile"),
  entry = path.join(dir, "entry.cjs"),
  started = new Date().toISOString(),
  checks = [],
  errors = [];
let app,
  page,
  activeCheck = "initialization",
  outcome = "failed";
const ready = () =>
  page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
const click = async (name, scope = page) => {
  await scope.getByRole("button", { name, exact: true }).click();
  await ready();
};
// Read-only supplementary assertions. No bridge call starts capture or opens,
// imports, saves, or changes the evidence under test.
const read = (method) =>
  page.evaluate(async (method) => {
    const result = await window.surge.request(method, {});
    if (!result.ok) throw Error(result.error);
    return result.value;
  }, method);
async function check(name, fn) {
  activeCheck = name;
  const begin = Date.now();
  const evidence = await fn();
  checks.push({
    name,
    passed: true,
    milliseconds: Date.now() - begin,
    evidence,
  });
  console.log("PASS", name);
}
const digest = (file) =>
  crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
async function screenshot(name) {
  await page.screenshot({ path: path.join(dir, `${name}.png`) });
}
async function replay() {
  await check("Missing native build gives actionable guidance", async () => {
    assert.equal(
      fs.existsSync(path.join(root, "native/build/surge_owned_app.exe")),
      false,
    );
    await click("Try Demo");
    await click("Start collection");
    const dialog = page.getByRole("dialog", { name: "Check input" });
    await dialog
      .getByText("Build the owned app first. See native/README.md.", {
        exact: true,
      })
      .waitFor();
    assert.equal((await read("native_status")).capture, null);
    await screenshot("missing-native-build");
    await click("Close", dialog);
    await click("Back to start");
  });
  const published = JSON.parse(
    fs.readFileSync(path.join(root, "demos/native/expected.json"), "utf8"),
  );
  for (const spec of published.cases) {
    await check(`Import and inspect ${spec.file}`, async () => {
      const file = path.join(root, "demos/native", spec.file),
        name = spec.file.replace(/\.case\.json$/, "");
      assert.equal(digest(file), spec.sha256, "Published fixture fingerprint");
      await app.evaluate(({ dialog }, file) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [file],
        });
      }, file);
      await click("Case library");
      await click("Import case");
      const row = page
        .locator(".case-list li")
        .filter({ has: page.getByText(name, { exact: true }) });
      await click("Open case", row);
      await page.getByRole("region", { name: "Saved observations" }).waitFor();
      const current = await read("state");
      assert.equal(current.inspected_capture, null);
      assert.equal(current.current.records, spec.outcomes.length);
      const expected = Object.fromEntries(
        ["No finding", "Review", "Unknown"].map((status) => [
          status,
          spec.outcomes.filter((x) => x === status).length,
        ]),
      );
      for (const [status, count] of Object.entries(expected))
        assert.equal(current.summary[status], count);
      await page.getByLabel("Findings only", { exact: true }).uncheck();
      await page.waitForFunction(
        (expected) =>
          JSON.stringify(
            Array.from(
              document.querySelectorAll(".results-table tbody tr"),
              (row) => row.cells[2].innerText,
            ),
          ) === JSON.stringify(expected),
        spec.outcomes,
      );
      await page
        .getByText(
          `${spec.outcomes.length} shown / ${spec.outcomes.length} · ${expected.Review} need review · ${expected.Unknown} unknown`,
          { exact: true },
        )
        .waitFor();
      await page
        .getByRole("region", { name: "Saved observations" })
        .getByText(/no live check\./)
        .waitFor();
      assert.equal(
        await page.getByRole("region", { name: "Demo app collection" }).count(),
        0,
      );
      // Check the visible boundary explanation; this does not establish that
      // an unfamiliar user understands it.
      await page.locator(".view:not([hidden]) .result-guide summary").click();
      await page
        .getByText(/this does not prove whole-process integrity/)
        .waitFor();
      await screenshot(name);
      assert.equal(digest(file), spec.sha256, "Original fixture preserved");
      return {
        sha256: spec.sha256,
        expected,
        summary: current.summary,
        saved_result: current.saved_result,
      };
    });
  }
}
async function capture() {
  await check(`${mode} environment preconditions`, async () => {
    assert.ok(
      fs.existsSync(path.join(root, "native/build/surge_owned_app.exe")),
    );
    const registry = path.join(root, "native/baselines.json");
    if (mode === "unapproved") {
      assert.equal(
        fs.existsSync(registry),
        false,
        "Unapproved rehearsal requires no inherited registry",
      );
    } else
      assert.ok(
        fs.existsSync(registry),
        "Approve the exact owned v2 build explicitly before this mode",
      );
    return {
      executable_sha256: digest(
        path.join(root, "native/build/surge_owned_app.exe"),
      ),
      registry_sha256: fs.existsSync(registry) ? digest(registry) : null,
    };
  });
  await check(
    "Start and inspect through the visible demo controls",
    async () => {
      await click("Try Demo");
      await page
        .getByText(/The sample app runs separately by design/)
        .waitFor();
      await page.locator(".demo-guide summary").click();
      await page.getByText(/Only configured code ranges are checked/).waitFor();
      await page.locator(".demo-guide summary").click();
      await click("Start collection");
      await page.waitForFunction(
        async () =>
          (await window.surge.request("native_status", {})).value.capture
            ?.samples >= 2,
      );
      await click("Inspect snapshot");
      const current = await read("state"),
        region = page.getByRole("region", { name: "Demo snapshot result" });
      assert.ok(current.summary.total >= 4);
      assert.equal(current.summary.Unknown, 0);
      if (mode === "approved") {
        assert.equal(current.summary.Review, 0);
        assert.equal(current.summary["No finding"], current.summary.total);
        await region
          .getByText(
            "Expected demo result: all 2 configured ranges match the approved baseline.",
            { exact: true },
          )
          .waitFor();
        assert.equal(
          await page.getByLabel("Findings only", { exact: true }).isChecked(),
          false,
        );
        await page.locator(".results-table tbody tr").first().waitFor();
      } else {
        assert.equal(current.summary.Review, current.summary.total);
        assert.equal(current.summary["No finding"], 0);
        await region.getByText(/Expected match not established/).waitFor();
        assert.doesNotMatch(await region.innerText(), /Expected demo result:/);
      }
      await screenshot(`${mode}-snapshot`);
      return {
        summary: current.summary,
        demo_result: current.demo_result,
        inspected_capture: current.inspected_capture,
      };
    },
  );
  let final;
  await check("Stop opens the final snapshot", async () => {
    await click("Stop collection");
    await page
      .getByText(
        "Collection stopped. The final snapshot is open and ready to save.",
        { exact: true },
      )
      .waitFor();
    final = await read("state");
    assert.equal(final.inspected_capture.capture_state, "stopped");
    assert.equal((await read("native_status")).capture.state, "stopped");
    assert.equal(final.summary.Unknown, 0);
    assert.equal(
      final.summary[mode === "approved" ? "No finding" : "Review"],
      final.summary.total,
    );
    return {
      summary: final.summary,
      inspected_capture: final.inspected_capture,
    };
  });
  if (mode === "approved") {
    await check(
      "Save and reopen preserves evidence without a live claim",
      async () => {
        await click("Save case");
        await page
          .getByLabel("Case name", { exact: true })
          .fill("First-use approved sample");
        await click("Save to library");
        await page.getByRole("region", { name: "Case saved" }).waitFor();
        await click("Open saved case");
        const reopened = await read("state");
        assert.deepEqual(reopened.summary, final.summary);
        assert.equal(reopened.inspected_capture, null);
        assert.equal(
          await page
            .getByRole("region", { name: "Demo app collection" })
            .count(),
          0,
        );
        const saved = page.getByRole("region", { name: "Saved observations" });
        await saved
          .getByText(
            "Saved observations: all 2 configured ranges matched the recorded approved baseline.",
            { exact: true },
          )
          .waitFor();
        await saved.getByText(/no live check\./).waitFor();
        await screenshot("approved-saved-case");
        return {
          summary: reopened.summary,
          saved_result: reopened.saved_result,
          inspected_capture: reopened.inspected_capture,
        };
      },
    );
  }
}
(async () => {
  try {
    assert.ok(
      ["replay", "unapproved", "approved"].includes(mode),
      "Usage: node desktop/first-use.test.cjs replay|unapproved|approved",
    );
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
    page.setDefaultTimeout(15000);
    page.on("pageerror", (error) => errors.push(error.message));
    await ready();
    await check(
      "Fresh isolated profile opens at the start screen",
      async () => {
        await page
          .getByRole("heading", { name: "Surge", exact: true })
          .waitFor();
        for (const name of ["Try Demo", "Case library", "Import evidence"])
          await page.getByRole("button", { name, exact: true }).waitFor();
        assert.equal((await read("state")).current, null);
        assert.equal((await read("library_list")).entries.length, 0);
        await screenshot("opening");
      },
    );
    if (mode === "replay") await replay();
    else await capture();
    await check("No uncaught renderer errors", async () =>
      assert.deepEqual(errors, []),
    );
    activeCheck = "desktop shutdown";
    await app.close();
    app = null;
    outcome = "passed";
  } catch (error) {
    checks.push({ name: activeCheck, passed: false, error: error.stack });
    fs.writeFileSync(
      path.join(dir, "failure.txt"),
      error.stack || String(error),
    );
    if (page) await screenshot("failure").catch(() => {});
    process.exitCode = 1;
    console.error(error);
  } finally {
    if (app)
      await app.close().catch((error) => {
        checks.push({ name: "cleanup", passed: false, error: String(error) });
        process.exitCode = 1;
        outcome = "failed";
      });
    const report = {
      mode,
      status: outcome,
      started,
      finished: new Date().toISOString(),
      profile,
      checks,
      renderer_errors: errors,
      limitations: [
        "Automated same-host rehearsal, not an unfamiliar tester or another Windows installation.",
        "Native file dialogs are stubbed to select owned fixtures; shell dialog interaction is not tested.",
        "Read-only bridge assertions supplement visible controls; actions use actual interface buttons.",
        "Short bounded capture only; does not repeat endurance, wider fuzzing, or hostile-host validation.",
      ],
    };
    fs.writeFileSync(
      path.join(dir, "results.json"),
      JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify({ mode, status: outcome, artifacts: dir }));
  }
})();

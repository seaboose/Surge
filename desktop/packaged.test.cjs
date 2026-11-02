// Real packaged entry point; no generated main script or development Electron.
// Native dialogs select owned fixtures. Actions use UI; bridge reads are assertions.
"use strict";
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict"),
  crypto = require("node:crypto");
const config = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const checks = [],
  errors = [],
  began = Date.now();
let app,
  page,
  active = "launch",
  status = "failed",
  identity;
const digest = (file) =>
  crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const ready = () =>
  page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
const read = (method) =>
  page.evaluate(async (method) => {
    const r = await window.surge.request(method, {});
    if (!r.ok) throw Error(r.error);
    return r.value;
  }, method);
async function click(name, scope = page) {
  await scope.getByRole("button", { name, exact: true }).click();
  await ready();
}
async function selectFile(file, save = false) {
  await app.evaluate(
    ({ dialog }, { file, save }) => {
      if (save)
        dialog.showSaveDialog = async () => ({
          canceled: false,
          filePath: file,
        });
      else
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [file],
        });
    },
    { file, save },
  );
}
async function check(name, action) {
  active = name;
  const start = Date.now();
  const evidence = await bounded(
    action,
    30000,
    `30-second action limit: ${name}`,
  );
  checks.push({
    name,
    status: "passed",
    milliseconds: Date.now() - start,
    evidence,
  });
  console.log("PASS", name);
}
async function bounded(action, milliseconds, message) {
  let timer;
  try {
    return await Promise.race([
      action(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(Error(message)), milliseconds);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}
async function shot(name) {
  await page.screenshot({ path: path.join(config.output, `${name}.png`) });
}
const row = (name) =>
  page
    .locator(".case-list li")
    .filter({ has: page.getByText(name, { exact: true }) });
async function library() {
  await click("Case library", page.getByRole("navigation"));
}
async function save(name) {
  await click("Save case");
  await page.getByLabel("Case name", { exact: true }).fill(name);
  await click("Save to library");
  await page.getByRole("region", { name: "Case saved" }).waitFor();
  await click("Open saved case");
}
function assertSaved(state) {
  assert.equal(state.inspected_capture, null);
  assert.ok(state.summary?.total > 0);
}
function nativeProcesses() {
  const executable = path.join(
    config.application,
    "resources/app/native/build/surge_owned_app.exe",
  );
  const powershell = path.join(
    process.env.SystemRoot,
    "System32/WindowsPowerShell/v1.0/powershell.exe",
  );
  const command =
    "$OutputEncoding=[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding $false; Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $env:SURGE_OWNED_SAMPLE } | Select-Object ProcessId,ParentProcessId,ExecutablePath | ConvertTo-Json -Compress";
  const output = require("node:child_process")
    .execFileSync(powershell, ["-NoProfile", "-Command", command], {
      encoding: "utf8",
      timeout: 5000,
      windowsHide: true,
      env: { ...process.env, SURGE_OWNED_SAMPLE: executable },
    })
    .trim()
    .replace(/^\uFEFF/, "");
  const value = JSON.parse(output || "[]");
  return Array.isArray(value) ? value : [value];
}
async function demo(approved) {
  await click("Try Demo");
  await click("Start collection");
  await page.waitForFunction(
    async () =>
      (await window.surge.request("native_status", {})).value.capture
        ?.samples >= 2,
  );
  await click("Inspect snapshot");
  const current = await read("state");
  assert.ok(current.summary.total >= 4);
  assert.equal(current.summary.Unknown, 0);
  assert.equal(
    current.summary[approved ? "No finding" : "Review"],
    current.summary.total,
  );
  assert.equal(current.summary[approved ? "Review" : "No finding"], 0);
  const result = page.getByRole("region", { name: "Demo snapshot result" });
  if (approved) {
    await result
      .getByText(
        `Expected demo result: all ${config.sample_ranges} configured ranges match the approved baseline.`,
        { exact: true },
      )
      .waitFor();
    assert.equal(
      await page.getByLabel("Findings only", { exact: true }).isChecked(),
      false,
    );
  } else {
    await result.getByText(/Expected match not established/).waitFor();
    assert.doesNotMatch(await result.innerText(), /Expected demo result:/);
  }
  await shot(approved ? "demo-approved" : "approval-mismatch");
  const sample_running = nativeProcesses();
  assert.equal(sample_running.length, 1);
  assert.equal(sample_running[0].ParentProcessId, identity.runtime.workerPid);
  await click("Stop collection");
  const sample_stopped = nativeProcesses();
  assert.deepEqual(sample_stopped, []);
  const final = await read("state"),
    capture = (await read("native_status")).capture;
  assert.equal(capture.state, "stopped");
  assert.equal(final.inspected_capture.capture_state, "stopped");
  assert.equal(final.summary.Unknown, 0);
  assert.equal(
    final.summary[approved ? "No finding" : "Review"],
    final.summary.total,
  );
  return {
    summary: final.summary,
    inspected_capture: final.inspected_capture,
    capture,
    sample_running,
    sample_stopped,
  };
}
async function journey() {
  await check("fresh packaged opening", async () => {
    for (const name of ["Import evidence", "Case library", "Try Demo"])
      await page.getByRole("button", { name, exact: true }).waitFor();
    assert.equal((await read("state")).current, null);
    assert.equal((await read("library_list")).entries.length, 0);
    await shot("opening");
  });
  await check("raw import and declared field rule", async () => {
    await selectFile(config.raw_source);
    await click("Import evidence");
    const imported = await read("state");
    assert.equal(imported.current.sha256, config.raw_sha256);
    assert.equal(imported.current.records, 2);
    await page
      .locator(".setup details")
      .filter({ has: page.locator("summary", { hasText: /^Options$/ }) })
      .locator("summary")
      .click();
    await selectFile(config.policy);
    await click("Load policy");
    await click("Analyze");
    const actual = await read("state");
    assert.equal(actual.summary.total, 2);
    assert.equal(actual.summary.Review, 1);
    assert.equal(actual.summary["No finding"], 1);
    assert.equal(actual.summary.Unknown, 0);
    await shot("import-results");
    return { current: actual.current, summary: actual.summary };
  });
  let savedId, savedDigest;
  await check("save and reopen imported evidence", async () => {
    const before = (await read("state")).summary;
    await save("Package evidence");
    const after = await read("state");
    assertSaved(after);
    assert.deepEqual(after.summary, before);
    const entries = (await read("library_list")).entries;
    assert.equal(entries.length, 1);
    savedId = entries[0].id;
    savedDigest = digest(
      path.join(config.profile, "cases", savedId, "case.json"),
    );
    return { id: savedId, summary: after.summary, sha256: savedDigest };
  });
  await check("rename preserves case evidence", async () => {
    await library();
    const selected = row("Package evidence");
    await click("Rename", selected);
    await selected.getByLabel("New case name").fill("Renamed package evidence");
    await click("Save name", selected);
    await row("Renamed package evidence").waitFor();
    assert.equal(
      digest(path.join(config.profile, "cases", savedId, "case.json")),
      savedDigest,
    );
    return { id: savedId, sha256: savedDigest };
  });
  await check("export and independent import", async () => {
    await selectFile(config.exported, true);
    await click("Export case", row("Renamed package evidence"));
    assert.equal(digest(config.exported), savedDigest);
    await selectFile(config.exported);
    await click("Import case");
    const entries = (await read("library_list")).entries;
    assert.equal(entries.length, 2);
    assert.equal(new Set(entries.map((x) => x.id)).size, 2);
    return { entries, exported_sha256: digest(config.exported) };
  });
  await check("delete cancellation and original preservation", async () => {
    await app.evaluate(({ dialog }) => {
      dialog.showMessageBox = async () => ({ response: 0 });
    });
    await click("Delete case", row("Renamed package evidence"));
    assert.equal((await read("library_list")).entries.length, 2);
    await app.evaluate(({ dialog }) => {
      dialog.showMessageBox = async () => ({ response: 1 });
    });
    await click("Delete case", row("Renamed package evidence"));
    assert.equal((await read("library_list")).entries.length, 1);
    assert.equal(
      fs.existsSync(path.join(config.profile, "cases", savedId)),
      false,
    );
    assert.equal(digest(config.raw_source), config.raw_sha256);
    assert.equal(digest(config.exported), savedDigest);
    return {
      deleted_id: savedId,
      original_sha256: digest(config.raw_source),
      exported_sha256: digest(config.exported),
    };
  });
  await check("existing source-format case import", async () => {
    await selectFile(config.existing_case);
    await click("Import case");
    await click("Open case", row("existing-source"));
    const actual = await read("state");
    assertSaved(actual);
    for (const [key, value] of Object.entries(config.existing_summary))
      assert.equal(actual.summary[key], value);
    assert.equal(digest(config.existing_case), config.existing_sha256);
    return { summary: actual.summary, sha256: config.existing_sha256 };
  });
  await check("exact bundled demo approval and stopped capture", async () => {
    await click("Data", page.getByRole("navigation"));
    return demo(true);
  });
  await check("save demo as evidence with no live claim", async () => {
    const before = (await read("state")).summary;
    await save("Packaged approved sample");
    const current = await read("state");
    assertSaved(current);
    assert.deepEqual(current.summary, before);
    await page
      .getByRole("region", { name: "Saved observations" })
      .getByText(/no live check\./)
      .waitFor();
    assert.equal(
      await page.getByRole("region", { name: "Demo app collection" }).count(),
      0,
    );
    await shot("saved-demo");
    fs.writeFileSync(
      config.retained,
      JSON.stringify(
        { entries: (await read("library_list")).entries, demo_summary: before },
        null,
        2,
      ),
    );
    return { summary: current.summary, saved_result: current.saved_result };
  });
}
async function replacement() {
  const retained = JSON.parse(fs.readFileSync(config.retained, "utf8"));
  await check("replacement retains library identifiers and names", async () => {
    const entries = (await read("library_list")).entries;
    assert.deepEqual(
      entries
        .map(({ id, name }) => ({ id, name }))
        .sort((a, b) => a.id.localeCompare(b.id)),
      retained.entries
        .map(({ id, name }) => ({ id, name }))
        .sort((a, b) => a.id.localeCompare(b.id)),
    );
    await click("Case library");
    return { entries };
  });
  for (const name of [
    "portable",
    "existing-source",
    "Packaged approved sample",
  ]) {
    await check(`replacement reopens ${name}`, async () => {
      await click("Open case", row(name));
      const actual = await read("state");
      assertSaved(actual);
      if (name === "Packaged approved sample") {
        assert.deepEqual(actual.summary, retained.demo_summary);
        await page
          .getByRole("region", { name: "Saved observations" })
          .getByText(/no live check\./)
          .waitFor();
      } else {
        const expected =
          name === "portable"
            ? { total: 2, Review: 1, "No finding": 1, Unknown: 0 }
            : config.existing_summary;
        for (const [key, value] of Object.entries(expected))
          assert.equal(actual.summary[key], value);
      }
      assert.equal(
        await page.getByRole("region", { name: "Demo app collection" }).count(),
        0,
      );
      await shot(`reopened-${name.replaceAll(" ", "-")}`);
      await library();
      return {
        summary: actual.summary,
        inspected_capture: actual.inspected_capture,
      };
    });
  }
}
(async () => {
  try {
    assert.ok(["journey", "replacement", "mismatch"].includes(config.mode));
    while (!fs.existsSync(config.gate)) {
      if (Date.now() - began > 10000)
        throw Error("Owned supervisor launch gate timed out.");
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    const env = { ...config.app_env };
    await bounded(
      async () => {
        app = await require("playwright")._electron.launch({
          executablePath: config.executable,
          args:
            config.profile_mode === "ordinary"
              ? []
              : [`--user-data-dir=${config.profile}`],
          cwd: config.cwd,
          env,
          timeout: 30000,
          chromiumSandbox: true,
        });
        page = await app.firstWindow({ timeout: 30000 });
        page.setDefaultTimeout(30000);
        page.on("pageerror", (error) => errors.push(error.message));
        await ready();
      },
      30000,
      "30-second packaged startup limit exceeded",
    );
    await check("bundled runtime identity and renderer isolation", async () => {
      identity = await app.evaluate(({ app, BrowserWindow }) => ({
        runtime: app.surgeRuntimeIdentity,
        executable: process.execPath,
        pid: process.pid,
        app_name: app.getName(),
        profile: app.getPath("userData"),
        session_data: app.getPath("sessionData"),
        versions: process.versions,
        preferences:
          BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences(),
      }));
      assert.equal(
        path.resolve(identity.executable).toLowerCase(),
        path.resolve(config.executable).toLowerCase(),
      );
      assert.equal(
        path.resolve(identity.profile).toLowerCase(),
        path.resolve(config.profile).toLowerCase(),
      );
      assert.equal(identity.app_name, "surge-desktop");
      assert.equal(identity.runtime.packaged, true);
      assert.equal(identity.runtime.ready, true);
      assert.equal(identity.runtime.status, "ready");
      assert.equal(identity.runtime.pythonVersion, config.python_version);
      assert.equal(identity.versions.electron, config.electron_version);
      assert.equal(
        path.resolve(identity.session_data).toLowerCase(),
        path.resolve(config.profile).toLowerCase(),
      );
      for (const module of [
        "desktop_worker",
        "engine",
        "native_integrity",
        "native_stream",
      ])
        assert.equal(
          path
            .resolve(identity.runtime.backendModulePaths[module])
            .toLowerCase(),
          path
            .resolve(config.application, "resources/app", `${module}.py`)
            .toLowerCase(),
        );
      for (const [key, relative] of Object.entries({
        applicationRoot: "resources/app",
        pythonExecutable: "resources/python/python.exe",
        backendPath: "resources/app/desktop_worker.py",
        nativeExecutable: "resources/app/native/build/surge_owned_app.exe",
      }))
        assert.equal(
          path.resolve(identity.runtime[key]).toLowerCase(),
          path.resolve(config.application, relative).toLowerCase(),
          key,
        );
      assert.equal(identity.preferences.sandbox, true);
      assert.equal(identity.preferences.contextIsolation, true);
      assert.equal(identity.preferences.nodeIntegration, false);
      fs.writeFileSync(
        path.join(config.output, "process-identity.json"),
        JSON.stringify(identity, null, 2),
      );
      return identity;
    });
    if (config.mode === "journey") await journey();
    else if (config.mode === "replacement") await replacement();
    else
      await check("mismatched owned approval never becomes approved", () =>
        demo(false),
      );
    await check("no uncaught renderer errors", async () =>
      assert.deepEqual(errors, []),
    );
    active = "graceful shutdown";
    await bounded(
      () => app.close(),
      15000,
      "15-second shutdown limit exceeded",
    );
    app = null;
    checks.push({ name: active, status: "passed" });
    status = "passed";
  } catch (error) {
    checks.push({ name: active, status: "failed", error: error.stack });
    if (page) await shot("failure").catch(() => {});
    process.exitCode = 1;
    console.error(error);
  } finally {
    if (app)
      await bounded(
        () => app.close(),
        15000,
        "15-second cleanup limit exceeded",
      ).catch((error) => {
        checks.push({
          name: "cleanup",
          status: "failed",
          error: String(error),
        });
        status = "failed";
        process.exitCode = 1;
      });
    fs.writeFileSync(
      path.join(config.output, "results.json"),
      JSON.stringify(
        {
          schema: "surge-packaged-ui-v1",
          mode: config.mode,
          status,
          elapsed_seconds: (Date.now() - began) / 1000,
          identity,
          checks,
          renderer_errors: errors,
          limitations: [
            "Native dialogs select owned fixtures through main-process substitution.",
            "Playwright debugger attachment is test tooling; no developer runtime supplies the app worker.",
            "Automated bounded rehearsal, not unfamiliar-tester acceptance or native-dialog usability.",
          ],
        },
        null,
        2,
      ),
    );
  }
})();

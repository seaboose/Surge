// Real extracted application and game; developer Playwright is test tooling only.
// UI actions drive capture/reporting. Only native save-dialog destinations are stubbed.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");
const { _electron: electron } = require("playwright");
const config = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const checks = [],
  errors = [],
  trials = [];
const started = Date.now();
let app, page, identity, selected, investigationId;
let current = "launch",
  outcome = "failed";
const readJSON = (file) => JSON.parse(fs.readFileSync(file, "utf8"));
const hash = (file) =>
  crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const write = (name, value) =>
  fs.writeFileSync(
    path.join(config.output, name),
    JSON.stringify(value, null, 2),
  );
const workflow = () =>
  page.getByRole("navigation", { name: "Session workflow", exact: true });
const notebook = () =>
  page.getByLabel("Investigation notebook", { exact: true });
const rawRecord = () =>
  page
    .getByLabel("Selected evidence", { exact: true })
    .locator("details")
    .filter({ has: page.getByText("Raw source record", { exact: true }) })
    .locator("pre");
async function request(method, args = {}) {
  return page.evaluate(
    async ({ method, args }) => {
      const reply = await window.surge.request(method, args);
      if (!reply.ok) throw Error(reply.error);
      return reply.value;
    },
    { method, args },
  );
}
async function until(action, accept, seconds = 30) {
  const end = Date.now() + seconds * 1000;
  while (Date.now() < end) {
    const value = await action();
    if (accept(value)) return value;
    await delay(250);
  }
  throw Error(`Timed out: ${current}`);
}
async function check(name, action) {
  current = name;
  const began = Date.now();
  const evidence = await action();
  checks.push({
    name,
    status: "passed",
    milliseconds: Date.now() - began,
    evidence,
  });
  write("progress.json", { current, checks, trials });
  console.log("PASS", name);
}
async function stage(name) {
  const index =
    ["Play", "Record", "Review", "Explain", "Export"].indexOf(name) + 1;
  await workflow()
    .getByRole("button", { name: `${index} ${name}`, exact: true })
    .click();
}
async function disclose(scope, title) {
  const summary = scope
    .locator("summary")
    .filter({ hasText: new RegExp(`^${title}$`) });
  if ((await summary.locator("..").getAttribute("open")) === null)
    await summary.click();
}
async function screenshot(name) {
  await page.screenshot({
    path: path.join(config.output, `${name}.png`),
    timeout: 10000,
  });
}
function ownedProcesses() {
  return JSON.parse(
    execFileSync(
      config.verification_python,
      [
        "-I",
        "-B",
        config.process_inspector,
        "--application",
        config.application,
      ],
      { encoding: "utf8", windowsHide: true, timeout: 8000 },
    ),
  );
}
function recordingFiles(recordingId) {
  const folder = path.join(
    config.profile,
    "Survive",
    "SurgeRecordings",
    recordingId,
  );
  return Object.fromEntries(
    fs
      .readdirSync(folder)
      .filter((name) => fs.statSync(path.join(folder, name)).isFile())
      .map((name) => [name, hash(path.join(folder, name))]),
  );
}
async function exactSelection(expected) {
  await disclose(
    page.getByLabel("Selected evidence", { exact: true }),
    "Raw source record",
  );
  await until(
    async () => {
      try {
        return JSON.parse(await rawRecord().innerText());
      } catch {
        return null;
      }
    },
    (value) => value?.seq === expected.seq,
  );
  assert.deepEqual(JSON.parse(await rawRecord().innerText()), expected);
  const time = Number(
    await page
      .getByRole("slider", { name: "Game time", exact: true })
      .inputValue(),
  );
  assert(Math.abs(time - expected.elapsed_s) <= 0.000501);
}
async function round(mode, partial = false) {
  await stage("Play");
  await page
    .getByLabel("Participant alias", { exact: true })
    .fill("package-verification");
  await page.getByLabel("Input condition", { exact: true }).selectOption(mode);
  await page.getByLabel("Phase", { exact: true }).selectOption("practice");
  await page.getByLabel("Seed", { exact: true }).fill("1337");
  await page
    .getByRole("button", { name: "Play and record trial", exact: true })
    .click();
  const live = await until(
    () => request("survive_status", { after: 0 }),
    (value) =>
      value.capture?.state === "recording" && value.capture.records > 80,
    90,
  );
  const record = {
    mode,
    partial,
    trial_id: live.trial.trial_id,
    recording_id: live.capture.recording_id,
  };
  trials.push(record);
  write("owned-trials.json", trials);
  const folder = path.join(
    config.profile,
    "Survive",
    "StudyTrials",
    record.trial_id,
  );
  const manifest = readJSON(path.join(folder, "trial.json"));
  const processStart = readJSON(path.join(folder, "process-start.json"));
  const processes = ownedProcesses();
  const game = processes.find((item) => item.ProcessId === processStart.pid);
  assert(game, "Standalone game must be a live owned packaged process");
  assert.equal(game.ParentProcessId, identity.runtime.workerPid);
  assert.equal(
    path.resolve(game.ExecutablePath).toLowerCase(),
    path.resolve(config.game_executable).toLowerCase(),
  );
  assert.equal(
    path.resolve(manifest.command[0]).toLowerCase(),
    path.resolve(config.game_executable).toLowerCase(),
  );
  assert(
    !manifest.command.some((value) => /UnrealEditor|\.uproject$/i.test(value)),
  );
  assert(
    manifest.command.some((value) => value.startsWith("-SurviveSavedDir=")),
  );
  record.process = game;
  record.command = manifest.command;
  write(`${mode}${partial ? "-partial" : ""}-game-process.json`, record);
  await page
    .getByRole("button", { name: "Inspect live recording", exact: true })
    .click();
  await page.getByRole("button", { name: "Pause view", exact: true }).click();
  const pinned = await page
    .getByRole("slider", { name: "Game time", exact: true })
    .inputValue();
  const later = await until(
    () => request("survive_status", { after: 0 }),
    (value) => value.capture.records > live.capture.records + 30,
  );
  assert.equal(
    await page
      .getByRole("slider", { name: "Game time", exact: true })
      .inputValue(),
    pinned,
  );
  assert(later.capture.records > live.capture.records);
  if (partial) {
    await page
      .getByRole("button", { name: "Stop recording", exact: true })
      .click();
    const stopped = await until(
      () => request("survive_status", { after: 0 }),
      (value) => value.capture.state === "stopped",
    );
    assert.equal(stopped.trial.process_state, "running");
    assert.notEqual(stopped.capture.completion, "completed");
    record.partial_hashes = recordingFiles(record.recording_id);
  }
  const finished = await until(
    () => request("survive_status", { after: 0 }),
    (value) =>
      ["complete", "stopped", "failed"].includes(value.capture?.state) &&
      value.trial?.process_state === "exited",
    100,
  );
  const processResult = readJSON(path.join(folder, "process-result.json"));
  assert.equal(processResult.exit_code, 0);
  const saved = await request("survive_open", {
    recording_id: record.recording_id,
  });
  const dataRoot = path.join(config.profile, "Survive");
  const raw = fs.readFileSync(
    path.join(dataRoot, "Telemetry", `${saved.capture.session_id}.jsonl`),
  );
  const retained = fs.readFileSync(
    path.join(dataRoot, "SurgeRecordings", record.recording_id, "source.jsonl"),
  );
  const rows = raw.toString("utf8").trim().split("\n").map(JSON.parse);
  assert.equal(rows.at(-1).event, "run_end");
  assert.equal(rows.at(-1).elapsed_s, 60);
  assert.equal(
    saved.capture.source_sha256,
    crypto.createHash("sha256").update(retained).digest("hex"),
  );
  if (partial) {
    assert.equal(saved.capture.state, "stopped");
    assert.deepEqual(retained, raw.subarray(0, retained.length));
    assert(!retained.toString("utf8").includes('"event":"run_end"'));
    assert.deepEqual(
      recordingFiles(record.recording_id),
      record.partial_hashes,
    );
    assert.notEqual(saved.capture.analysis_state, "complete");
  } else {
    assert.equal(saved.capture.state, "complete");
    assert.deepEqual(raw, retained);
    const counts = saved.view.analysis.counts;
    assert(mode === "speed_probe" ? counts.Review > 0 : counts.Review === 0);
    record.counts = counts;
  }
  record.capture = saved.capture;
  record.final_source = rows.at(-1);
  record.files_sha256 = recordingFiles(record.recording_id);
  record.process_result = processResult;
  const report = await request("survive_report");
  const trial = report.trials.find(
    (value) => value.trial_id === record.trial_id,
  );
  assert.equal(trial.included_in_confusion, false);
  if (!partial) assert.equal(trial.source_association.state, "matched");
  write("owned-trials.json", trials);
  assert.equal(finished.trial.process_state, "exited");
  return record;
}
async function journey() {
  await check(
    "fresh isolated package has no developer recordings or reports",
    async () => {
      await page
        .getByRole("button", { name: "Survive sessions", exact: true })
        .click();
      assert.equal((await request("survive_sessions")).sessions.length, 0);
      assert.equal(
        (await request("survive_investigations")).investigations.length,
        0,
      );
      await screenshot("01-play");
    },
  );
  await check(
    "standalone legal scripted round records exact complete evidence",
    () => round("scripted"),
  );
  const violation = await checkRound();
  await check("exact finding links replay and raw evidence", async () => {
    await page
      .getByRole("button", { name: "Review this session", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Next review", exact: true })
      .click();
    await disclose(
      page.getByLabel("Selected evidence", { exact: true }),
      "Raw source record",
    );
    const resolved = await until(
      async () => {
        try {
          return {
            record: JSON.parse(await rawRecord().innerText()),
            time: Number(
              await page
                .getByRole("slider", { name: "Game time", exact: true })
                .inputValue(),
            ),
          };
        } catch {
          return null;
        }
      },
      (value) =>
        Number.isInteger(value?.record?.seq) &&
        Math.abs(value.record.elapsed_s - value.time) <= 0.000501,
    );
    selected = resolved.record;
    const source = fs
      .readFileSync(
        path.join(
          config.profile,
          "Survive",
          "SurgeRecordings",
          violation.recording_id,
          "source.jsonl",
        ),
        "utf8",
      )
      .trim()
      .split("\n")
      .map(JSON.parse);
    assert.deepEqual(
      selected,
      source.find((row) => row.seq === selected.seq),
    );
    await exactSelection(selected);
    await screenshot("02-review");
  });
  await check(
    "pinned evidence creates report and drafts survive navigation",
    async () => {
      await page
        .getByRole("button", {
          name: "Add selection to investigation",
          exact: true,
        })
        .click();
      await notebook()
        .getByLabel("New investigation title", { exact: true })
        .fill("Standalone Survive demonstration");
      await notebook()
        .getByLabel("New investigation author", { exact: true })
        .fill("package-verification");
      await notebook()
        .getByRole("button", {
          name: "Create and attach selected evidence",
          exact: true,
        })
        .click();
      await notebook().getByLabel("Evidence E1", { exact: true }).waitFor();
      investigationId = await notebook()
        .getByLabel("Saved investigation", { exact: true })
        .inputValue();
      const narratives = [
        [
          "Question",
          "Investigation question",
          "Does the controlled speed-change interval exceed its allowance?",
        ],
        [
          "Observations",
          "Observations",
          "The selected interval exceeds the reviewed movement allowance [E1].",
        ],
        [
          "Alternatives",
          "Hypotheses and alternatives",
          "Automated practice controls validate the pipeline; they do not identify human input or intent.",
        ],
        [
          "Conclusion",
          "Conclusion and limitations",
          "Review this mechanical interval [E1]. No general cheat-detection or human false-positive claim follows.",
        ],
        [
          "Next steps",
          "Next steps",
          "Collect independently labelled human practice sessions under comparable conditions.",
        ],
      ];
      for (const [tab, label, text] of narratives) {
        await notebook().getByRole("tab", { name: tab, exact: true }).click();
        await notebook()
          .getByRole("textbox", { name: label, exact: true })
          .fill(text);
      }
      for (const name of ["Play", "Record", "Review", "Explain", "Export"])
        await stage(name);
      assert(
        await notebook()
          .getByRole("button", {
            name: "Export investigation report",
            exact: true,
          })
          .isDisabled(),
      );
      await notebook()
        .getByRole("button", { name: "Edit report", exact: true })
        .click();
      for (const [tab, label, text] of narratives) {
        await notebook().getByRole("tab", { name: tab, exact: true }).click();
        assert.equal(
          await notebook()
            .getByRole("textbox", { name: label, exact: true })
            .inputValue(),
          text,
        );
      }
      await notebook()
        .getByLabel("Revision reason", { exact: true })
        .fill("Review controlled standalone package evidence");
      await notebook()
        .getByLabel("Investigation review status", { exact: true })
        .selectOption("reviewed");
      await notebook()
        .getByRole("button", { name: "Save revision", exact: true })
        .click();
      await notebook()
        .getByText("Saved · revision 3 of 3 · reviewed", { exact: true })
        .waitFor();
      await screenshot("03-explain");
    },
  );
  await check(
    "saved report exports exact evidence and citation restores the moment",
    async () => {
      await notebook()
        .getByRole("button", { name: "Continue to export", exact: true })
        .click();
      await app.evaluate(({ dialog }, destination) => {
        dialog.showSaveDialog = async () => ({
          canceled: false,
          filePath: destination,
        });
      }, config.export_path);
      await notebook()
        .getByRole("button", {
          name: "Export investigation report",
          exact: true,
        })
        .click();
      await notebook()
        .getByRole("status")
        .filter({ hasText: "Portable investigation report exported" })
        .waitFor();
      const html = fs.readFileSync(config.export_path, "utf8");
      const exported = await page.evaluate((text) => {
        const doc = new DOMParser().parseFromString(text, "text/html");
        return {
          scripts: doc.querySelectorAll("script").length,
          data: JSON.parse(
            doc.querySelector("#surge-investigation-json").textContent,
          ),
        };
      }, html);
      assert.equal(exported.scripts, 0);
      assert.equal(exported.data.document.investigation_id, investigationId);
      assert.deepEqual(exported.data.document.evidence[0].raw_record, selected);
      await screenshot("04-export");
      await disclose(notebook(), "Preview narrative");
      await notebook()
        .getByRole("button", { name: "Open evidence E1", exact: true })
        .first()
        .click();
      await page.getByLabel("Review workspace", { exact: true }).waitFor();
      await exactSelection(selected);
      assert.deepEqual(
        recordingFiles(violation.recording_id),
        violation.files_sha256,
      );
      write("retained-session.json", {
        investigationId,
        selected,
        recording: violation,
        export_sha256: hash(config.export_path),
      });
    },
  );
  await check(
    "stopping capture preserves partial evidence while standalone gameplay completes",
    () => round("scripted", true),
  );
}
async function checkRound() {
  let result;
  await check(
    "standalone controlled violation produces a reviewable finding",
    async () => {
      result = await round("speed_probe");
      return result;
    },
  );
  return result;
}
async function reopen() {
  const prior = readJSON(config.prior);
  await check(
    "replacement package reopens existing recordings and exact report revisions",
    async () => {
      await page
        .getByRole("button", { name: "Survive sessions", exact: true })
        .click();
      const sessions = (await request("survive_sessions")).sessions;
      assert.equal(sessions.length, 3);
      assert(
        sessions.some(
          (value) => value.recording_id === prior.recording.recording_id,
        ),
      );
      await stage("Explain");
      await notebook()
        .getByLabel("Saved investigation", { exact: true })
        .selectOption(prior.investigationId);
      await notebook().getByLabel("Evidence E1", { exact: true }).waitFor();
      await notebook()
        .getByRole("button", { name: "Open E1 in replay", exact: true })
        .click();
      await page.getByLabel("Review workspace", { exact: true }).waitFor();
      await exactSelection(prior.selected);
      assert.deepEqual(
        recordingFiles(prior.recording.recording_id),
        prior.recording.files_sha256,
      );
      await stage("Export");
      assert.equal(
        await notebook()
          .getByRole("button", {
            name: "Export investigation report",
            exact: true,
          })
          .isDisabled(),
        false,
      );
      await screenshot("05-reopened-report");
    },
  );
}
(async () => {
  try {
    assert(["journey", "reopen"].includes(config.mode));
    await until(
      async () => fs.existsSync(config.gate),
      (value) => value,
      10,
    );
    app = await electron.launch({
      executablePath: config.executable,
      args: [`--user-data-dir=${config.profile}`],
      cwd: config.cwd,
      env: config.app_env,
      chromiumSandbox: true,
      timeout: 30000,
    });
    page = await app.firstWindow();
    page.setDefaultTimeout(30000);
    page.on("pageerror", (error) => errors.push(error.message));
    await page.waitForFunction(
      () => document.querySelector(".app")?.dataset.working === "false",
    );
    await check(
      "application and Python use extracted runtimes with isolated renderer",
      async () => {
        identity = await app.evaluate(({ app, BrowserWindow }) => ({
          runtime: app.surgeRuntimeIdentity,
          executable: process.execPath,
          pid: process.pid,
          profile: app.getPath("userData"),
          preferences:
            BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences(),
        }));
        assert.equal(identity.runtime.packaged, true);
        assert.equal(identity.runtime.ready, true);
        assert.equal(
          path.resolve(identity.executable).toLowerCase(),
          path.resolve(config.executable).toLowerCase(),
        );
        assert.equal(
          path.resolve(identity.runtime.pythonExecutable).toLowerCase(),
          path
            .resolve(config.application, "resources/python/python.exe")
            .toLowerCase(),
        );
        assert.equal(
          path.resolve(identity.profile).toLowerCase(),
          path.resolve(config.profile).toLowerCase(),
        );
        assert.equal(identity.preferences.sandbox, true);
        assert.equal(identity.preferences.contextIsolation, true);
        assert.equal(identity.preferences.nodeIntegration, false);
        identity.developerTools = await app.evaluate(
          async ({ BrowserWindow }) => {
            const contents = BrowserWindow.getAllWindows()[0].webContents;
            let opened = false;
            const observe = () => {
              opened = true;
            };
            contents.on("devtools-opened", observe);
            try {
              contents.openDevTools({ mode: "detach" });
              await new Promise((resolve) => setTimeout(resolve, 1000));
              return {
                opened: opened || contents.isDevToolsOpened(),
                frontendCreated: Boolean(contents.devToolsWebContents),
              };
            } finally {
              contents.removeListener("devtools-opened", observe);
            }
          },
        );
        assert.deepEqual(identity.developerTools, {
          opened: false,
          frontendCreated: false,
        });
        assert.equal(
          fs.existsSync(
            path.join(
              config.application,
              "resources/app/desktop/developer-tools.cjs",
            ),
          ),
          false,
        );
        for (const name of ["app.js.map", "app.css.map", "style.css.map"])
          assert.equal(
            fs.existsSync(
              path.join(config.application, "resources/app/desktop/dist", name),
            ),
            false,
          );
        write("process-identity.json", identity);
        return identity;
      },
    );
    if (config.mode === "journey") await journey();
    else await reopen();
    await check(
      "no renderer exceptions and graceful owned shutdown",
      async () => {
        assert.deepEqual(errors, []);
        await app.close();
        app = null;
      },
    );
    outcome = "passed";
  } catch (error) {
    checks.push({ name: current, status: "failed", error: error.stack });
    console.error(error);
    if (page) await screenshot("failure").catch(() => {});
    process.exitCode = 1;
  } finally {
    if (app) await app.close().catch(() => {});
    write("results.json", {
      schema: "surge-survive-packaged-ui-v1",
      status: outcome,
      mode: config.mode,
      elapsed_seconds: (Date.now() - started) / 1000,
      checks,
      trials,
      renderer_errors: errors,
      limitations: [
        "Test tooling uses developer Playwright; application, Python and game come only from the extracted package.",
        "Native save dialogs select a dedicated output through main-process substitution.",
        "Automated practice sessions are not a human baseline or unfamiliar-user usability study.",
        "This host has development tools installed; clean-environment/path checks are not a fresh-machine acceptance test.",
      ],
    });
  }
})();

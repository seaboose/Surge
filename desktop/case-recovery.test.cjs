"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { fork } = require("node:child_process");
const { createHash, randomUUID } = require("node:crypto");

const ROOT = path.resolve(__dirname, "..");
const BOUNDS = Object.freeze({
  scenarios: 48,
  repeats: 2,
  child_ms: 5000,
  campaign_ms: 300000,
  logs_bytes: 10 * 1024 * 1024,
  fixtures_bytes: 64 * 1024 * 1024,
  input_bytes: 256 * 1024,
});
const VALID = JSON.stringify({
  schema: "surge-owned-recovery-fixture-v1",
  evidence: "bounded owned evidence ".repeat(3200),
});
const EXISTING =
  "Owned pre-existing destination; preserve these exact bytes.\n";
const sha256 = (data) => createHash("sha256").update(data).digest("hex");

const SCENARIOS = [
  ["save-success", "save", "none", "success"],
  ["save-partial-snapshot-ENOSPC", "save", "snapshot-error", "failure"],
  ["save-metadata-EACCES", "save", "metadata-permission", "failure"],
  ["save-publication-EACCES", "save", "publish-error", "failure"],
  ["save-interrupt-after-snapshot", "save", "kill-snapshot", "interrupted"],
  [
    "save-interrupt-before-publication",
    "save",
    "kill-prepublish",
    "interrupted",
  ],
  [
    "save-interrupt-after-publication",
    "save",
    "kill-postpublish",
    "interrupted",
    "published",
  ],
  ["import-success", "import", "none", "success"],
  ["import-invalid-input", "import", "invalid-input", "failure"],
  ["import-partial-copy-ENOSPC", "import", "partial-write", "failure"],
  ["import-zero-write", "import", "zero-write", "failure"],
  ["import-short-write", "import", "short-write", "success"],
  ["import-output-close-EIO", "import", "close-error", "failure"],
  ["import-verification-rejected", "import", "verify-error", "failure"],
  ["import-interrupt-partial-copy", "import", "kill-copy", "interrupted"],
  [
    "import-interrupt-during-validation",
    "import",
    "kill-validation",
    "interrupted",
  ],
  [
    "import-interrupt-before-publication",
    "import",
    "kill-prepublish",
    "interrupted",
  ],
  [
    "import-interrupt-after-publication",
    "import",
    "kill-postpublish",
    "interrupted",
    "published",
  ],
  ["rename-success", "rename", "none", "success"],
  ["rename-partial-temp-ENOSPC", "rename", "rename-partial", "failure"],
  ["rename-publication-EACCES", "rename", "publish-error", "failure"],
  [
    "rename-interrupt-partial-temp",
    "rename",
    "kill-rename-partial",
    "interrupted",
  ],
  [
    "rename-interrupt-before-publication",
    "rename",
    "kill-prepublish",
    "interrupted",
  ],
  [
    "rename-interrupt-after-publication",
    "rename",
    "kill-postpublish",
    "interrupted",
    "published",
  ],
  ["delete-unexpected-file-refused", "delete", "unexpected-file", "failure"],
  ["export-success", "export", "none", "success"],
  [
    "export-existing-destination-refused",
    "export",
    "existing-destination",
    "failure",
  ],
  ["export-partial-copy-ENOSPC", "export", "partial-write", "failure"],
  ["export-zero-write", "export", "zero-write", "failure"],
  ["export-short-write", "export", "short-write", "success"],
  ["export-output-close-EIO", "export", "close-error", "failure"],
  ["export-verification-rejected", "export", "verify-error", "failure"],
  ["export-interrupt-partial-copy", "export", "kill-copy", "interrupted"],
  [
    "export-interrupt-during-validation",
    "export",
    "kill-validation",
    "interrupted",
  ],
  [
    "export-interrupt-before-publication",
    "export",
    "kill-prepublish",
    "interrupted",
  ],
  [
    "export-interrupt-after-publication",
    "export",
    "kill-postpublish",
    "interrupted",
    "published",
  ],
  ["export-publication-EACCES", "export", "publish-error", "failure"],
  [
    "export-destination-publication-race",
    "export",
    "destination-race",
    "failure",
  ],
  [
    "export-post-publication-cleanup-EACCES",
    "export",
    "export-cleanup-error",
    "success",
  ],
  ["delete-success", "delete", "none", "success"],
  [
    "delete-interrupt-before-publication",
    "delete",
    "kill-prepublish",
    "interrupted",
  ],
  [
    "delete-interrupt-after-publication",
    "delete",
    "kill-postpublish",
    "interrupted",
    "published",
  ],
  [
    "delete-post-publication-cleanup-EACCES",
    "delete",
    "delete-cleanup-error",
    "success",
  ],
  ["restart-invalid-metadata", "corruption", "invalid-metadata", "success"],
  ["restart-invalid-case-body", "corruption", "invalid-body", "success"],
  ["import-publication-EACCES", "import", "publish-error", "failure"],
  [
    "export-verification-and-cleanup-failure",
    "export",
    "verify-cleanup-error",
    "failure",
  ],
  [
    "save-write-and-cleanup-failure",
    "save",
    "snapshot-cleanup-error",
    "failure",
  ],
].map(([name, kind, fault, expected, published]) => ({
  name,
  kind,
  fault,
  expected,
  published: published === "published",
}));

function expectedInjections(scenario) {
  const publication = ["save", "import"].includes(scenario.kind)
    ? "case"
    : scenario.kind === "rename"
      ? "name"
      : scenario.kind;
  const markers = {
    "snapshot-error": ["snapshot-partial-ENOSPC"],
    "snapshot-cleanup-error": [
      "snapshot-partial-ENOSPC",
      "save-cleanup-EACCES",
    ],
    "metadata-permission": ["metadata-EACCES"],
    "publish-error": [`${publication}-publication-EACCES`],
    "partial-write": ["partial-copy-ENOSPC"],
    "zero-write": ["zero-byte-write"],
    "short-write": ["short-byte-write"],
    "close-error": ["output-close-EIO"],
    "verify-error": ["verification-rejected"],
    "rename-partial": ["rename-temp-ENOSPC"],
    "destination-race": ["destination-created-immediately-before-publication"],
    "export-cleanup-error": ["export-cleanup-EACCES"],
    "delete-cleanup-error": ["delete-cleanup-EACCES"],
    "verify-cleanup-error": ["verification-rejected", "export-cleanup-EACCES"],
    "kill-snapshot": ["snapshot-written"],
    "kill-copy": ["partial-copy-persisted"],
    "kill-validation": ["verification-read-before-acceptance"],
    "kill-rename-partial": ["rename-partial-temp-written"],
    "kill-prepublish": [`${publication}-publication-before`],
    "kill-postpublish": [`${publication}-publication-after`],
  };
  return markers[scenario.fault] || [];
}

async function inventory(root, prefix = "") {
  const result = [];
  for (const entry of await fs.readdir(path.join(root, prefix), {
    withFileTypes: true,
  })) {
    const rel = path.join(prefix, entry.name);
    if (entry.isDirectory()) result.push(...(await inventory(root, rel)));
    else {
      assert.ok(
        entry.isFile(),
        "Fixtures must contain only regular files and directories.",
      );
      const data = await fs.readFile(path.join(root, rel));
      result.push({
        path: rel.replaceAll("\\", "/"),
        bytes: data.length,
        sha256: sha256(data),
      });
    }
  }
  return result.sort((a, b) => a.path.localeCompare(b.path));
}

async function writeJson(file, value) {
  await fs.writeFile(file, `${JSON.stringify(value, null, 2)}\n`, {
    flag: "wx",
  });
}

test(
  "bounded owned case-library interruption and recovery campaign",
  { timeout: BOUNDS.campaign_ms + 10000 },
  async () => {
    assert.equal(SCENARIOS.length, BOUNDS.scenarios);
    assert.equal(
      new Set(SCENARIOS.map((item) => item.name)).size,
      SCENARIOS.length,
    );
    assert.ok(Buffer.byteLength(VALID) <= BOUNDS.input_bytes);
    const started = Date.now();
    const attempt = path.join(
      ROOT,
      "verification",
      "qualification",
      `case-recovery-${new Date().toISOString().replaceAll(/[:.]/g, "-")}-${randomUUID().slice(0, 8)}`,
    );
    await fs.mkdir(path.join(attempt, "source"), { recursive: true });
    console.log(`Recovery evidence: ${attempt}`);
    const sourceFiles = [
      "desktop/case-library.cjs",
      "desktop/case-recovery.test.cjs",
      "desktop/case-recovery-child.cjs",
      "docs/case-recovery-acceptance.md",
    ];
    const sources = [];
    for (const file of sourceFiles) {
      const bytes = await fs.readFile(path.join(ROOT, file));
      await fs.mkdir(path.dirname(path.join(attempt, "source", file)), {
        recursive: true,
      });
      await fs.writeFile(path.join(attempt, "source", file), bytes, {
        flag: "wx",
      });
      sources.push({ path: file, bytes: bytes.length, sha256: sha256(bytes) });
    }
    await writeJson(path.join(attempt, "acceptance.json"), {
      schema: 1,
      recorded_before_execution: true,
      criteria_file: "source/docs/case-recovery-acceptance.md",
      bounds: BOUNDS,
      scenarios: SCENARIOS,
      sources,
      node: process.version,
      platform: process.platform,
    });

    let logBytes = 0;
    let ipcBytes = 0;
    let budgetError = null;
    const results = [];
    const runChild = async (folder, label, config) => {
      const configFile = path.join(folder, `${label}-config.json`);
      await writeJson(configFile, config);
      const stdout = [];
      const stderr = [];
      const messages = [];
      const launch = Date.now();
      const child = fork(
        path.join(__dirname, "case-recovery-child.cjs"),
        [configFile],
        {
          stdio: ["ignore", "pipe", "pipe", "ipc"],
          windowsHide: true,
          execArgv: [],
        },
      );
      let deadline = false;
      let interrupted = false;
      let childError = null;
      const stop = () => {
        if (!child.killed) child.kill("SIGKILL");
      };
      const timer = setTimeout(
        () => {
          deadline = true;
          stop();
        },
        Math.max(
          1,
          Math.min(
            BOUNDS.child_ms,
            BOUNDS.campaign_ms - (Date.now() - started),
          ),
        ),
      );
      for (const [stream, chunks] of [
        [child.stdout, stdout],
        [child.stderr, stderr],
      ]) {
        stream.on("data", (chunk) => {
          logBytes += chunk.length;
          if (logBytes + ipcBytes > BOUNDS.logs_bytes) {
            budgetError =
              "Campaign exceeded the 10 MiB combined raw/IPC-log budget.";
            stop();
          } else chunks.push(chunk);
        });
      }
      child.on("message", (message) => {
        ipcBytes += Buffer.byteLength(JSON.stringify(message));
        if (logBytes + ipcBytes > BOUNDS.logs_bytes) {
          budgetError =
            "Campaign exceeded the 10 MiB combined raw/IPC-log budget.";
          stop();
          return;
        }
        messages.push(message);
        if (message.type === "boundary") {
          if (
            config.mode !== "operate" ||
            config.scenario.expected !== "interrupted"
          ) {
            childError = "Unexpected persistence marker.";
          } else interrupted = true;
          stop();
        }
      });
      child.on("error", (error) => {
        childError = error.message;
      });
      const exit = await new Promise((resolve) =>
        child.on("close", (code, signal) => resolve({ code, signal })),
      );
      clearTimeout(timer);
      await fs.writeFile(
        path.join(folder, `${label}.stdout.log`),
        Buffer.concat(stdout),
        { flag: "wx" },
      );
      await fs.writeFile(
        path.join(folder, `${label}.stderr.log`),
        Buffer.concat(stderr),
        { flag: "wx" },
      );
      const record = {
        owned_pid: child.pid,
        elapsed_ms: Date.now() - launch,
        ...exit,
        deadline,
        interrupted,
        child_error: childError,
        messages,
        result: messages.find((item) => item.type === "result")?.result ?? null,
      };
      await writeJson(path.join(folder, `${label}-process.json`), record);
      return record;
    };

    for (let repeat = 1; repeat <= BOUNDS.repeats; repeat++) {
      for (const scenario of SCENARIOS) {
        if (budgetError || Date.now() - started >= BOUNDS.campaign_ms) {
          budgetError ||= "Campaign exceeded the 300-second deadline.";
          break;
        }
        const folder = path.join(attempt, `repeat-${repeat}`, scenario.name);
        const fixture = path.join(folder, "fixture");
        const targetId = randomUUID();
        const unrelatedId = randomUUID();
        const source = path.join(fixture, "original.json");
        const destination = path.join(fixture, "export.case.json");
        const targetDir = path.join(fixture, "cases", targetId);
        const unrelatedDir = path.join(fixture, "cases", unrelatedId);
        await fs.mkdir(targetDir, { recursive: true });
        await fs.mkdir(unrelatedDir, { recursive: true });
        for (const [dir, id, name] of [
          [targetDir, targetId, "Target"],
          [unrelatedDir, unrelatedId, "Unrelated"],
        ]) {
          await fs.writeFile(path.join(dir, "case.json"), VALID, {
            flag: "wx",
          });
          await writeJson(path.join(dir, "metadata.json"), {
            id,
            name,
            created: "2026-10-23T00:00:00.000Z",
          });
        }
        await fs.writeFile(
          source,
          scenario.fault === "invalid-input" ? "invalid owned input" : VALID,
          { flag: "wx" },
        );
        if (scenario.fault === "existing-destination")
          await fs.writeFile(destination, EXISTING, { flag: "wx" });
        if (scenario.fault === "unexpected-file")
          await fs.writeFile(
            path.join(targetDir, "unexpected.txt"),
            "Owned unexpected file: preserve me.",
            { flag: "wx" },
          );
        if (scenario.fault === "invalid-metadata")
          await fs.writeFile(path.join(targetDir, "metadata.json"), "{");
        if (scenario.fault === "invalid-body")
          await fs.writeFile(
            path.join(targetDir, "case.json"),
            "invalid owned case body",
          );
        const before = await inventory(fixture);
        const config = {
          mode: "operate",
          scenario,
          fixture,
          targetId,
          unrelatedId,
          source,
          destination,
          valid: VALID,
          existing: EXISTING,
        };
        const errors = [];
        const checks = [];
        let operation;
        let inspection;
        let after;
        try {
          operation = await runChild(folder, "operation", config);
          after = await inventory(fixture);
          const inspectFixture =
            scenario.kind === "rename"
              ? path.join(folder, "restart-copy")
              : fixture;
          if (scenario.kind === "rename")
            await fs.cp(fixture, inspectFixture, {
              recursive: true,
              errorOnExist: true,
              force: false,
            });
          inspection = await runChild(folder, "restart", {
            ...config,
            fixture: inspectFixture,
            mode: "inspect",
            recoverRename: scenario.kind === "rename",
          });
          const check = (name, action) => {
            try {
              action();
              checks.push({ name, status: "passed" });
            } catch (error) {
              errors.push({ check: name, message: error.message });
              checks.push({ name, status: "failed" });
            }
          };
          check("operation completed within the child deadline", () =>
            assert.equal(operation.deadline, false),
          );
          check("no child launch/runtime error", () =>
            assert.equal(operation.child_error, null),
          );
          check("expected operation result", () => {
            if (scenario.expected === "interrupted") {
              assert.equal(
                operation.interrupted,
                true,
                "The child must reach the acknowledged persistence boundary.",
              );
              assert.equal(
                operation.result,
                null,
                "A terminated operation must not report completion.",
              );
            } else {
              assert.equal(operation.code, 0);
              assert.equal(
                operation.result?.ok,
                scenario.expected === "success",
              );
            }
          });
          check("exact requested failures and controls were reached", () =>
            assert.deepEqual(
              [
                ...new Set(
                  operation.messages
                    .filter((item) => item.type === "injection")
                    .map((item) => item.name),
                ),
              ].sort(),
              expectedInjections(scenario).sort(),
            ),
          );
          const primaryCodes = {
            "snapshot-error": "ENOSPC",
            "snapshot-cleanup-error": "ENOSPC",
            "metadata-permission": "EACCES",
            "publish-error": "EACCES",
            "partial-write": "ENOSPC",
            "close-error": "EIO",
            "verify-error": "EINVAL",
            "verify-cleanup-error": "EINVAL",
            "rename-partial": "ENOSPC",
            "destination-race": "EEXIST",
            "existing-destination": "EEXIST",
            "invalid-input": "EINVAL",
          };
          if (primaryCodes[scenario.fault])
            check("primary operation error is preserved", () =>
              assert.equal(
                operation.result?.code,
                primaryCodes[scenario.fault],
              ),
            );
          check("fresh-process restart completed", () => {
            assert.equal(inspection.code, 0);
            assert.equal(inspection.deadline, false);
            assert.ok(inspection.result?.inspection);
          });
          const beforeMap = new Map(before.map((file) => [file.path, file]));
          const afterMap = new Map(after.map((file) => [file.path, file]));
          check("original imported evidence stayed byte-identical", () =>
            assert.deepEqual(
              afterMap.get("original.json"),
              beforeMap.get("original.json"),
            ),
          );
          for (const file of before.filter((item) =>
            item.path.startsWith(`cases/${unrelatedId}/`),
          ))
            check(
              `unrelated evidence unchanged: ${path.basename(file.path)}`,
              () => assert.deepEqual(afterMap.get(file.path), file),
            );
          const state = inspection.result;
          if (state?.inspection) {
            check("unrelated case reopened with exact bytes", () =>
              assert.equal(
                state.opened[unrelatedId]?.result?.evidence_hash,
                sha256(VALID),
              ),
            );
            let expectedCount = 2;
            const published =
              scenario.expected === "success" || scenario.published;
            if (["save", "import"].includes(scenario.kind) && published)
              expectedCount++;
            if (scenario.kind === "delete" && published) expectedCount--;
            if (scenario.fault === "invalid-metadata") expectedCount--;
            check("restart shows only expected published entries", () =>
              assert.equal(state.listed.entries.length, expectedCount),
            );
            check("restart unavailable count is accurate", () =>
              assert.equal(
                state.listed.unavailable,
                scenario.fault === "invalid-metadata" ? 1 : 0,
              ),
            );
            const expectedNames = ["Unrelated"];
            if (
              !(scenario.kind === "delete" && published) &&
              scenario.fault !== "invalid-metadata"
            )
              expectedNames.push(
                scenario.kind === "rename" && published ? "New name" : "Target",
              );
            if (["save", "import"].includes(scenario.kind) && published)
              expectedNames.push("New case");
            check("restart preserves expected case names", () =>
              assert.deepEqual(
                state.listed.entries.map((entry) => entry.name).sort(),
                expectedNames.sort(),
              ),
            );
            for (const entry of state.listed.entries) {
              check(
                `restart validates ${entry.id === targetId ? "target" : entry.id === unrelatedId ? "unrelated" : "new"} case`,
                () =>
                  assert.equal(
                    state.opened[entry.id]?.ok,
                    !(
                      scenario.fault === "invalid-body" && entry.id === targetId
                    ),
                  ),
              );
            }
            if (scenario.kind === "rename") {
              check("rename preserves complete expected name", () =>
                assert.equal(
                  state.listed.entries.find((entry) => entry.id === targetId)
                    ?.name,
                  published ? "New name" : "Target",
                ),
              );
              for (const action of ["open", "rename", "delete"])
                check(`rename recovery permits ${action}`, () =>
                  assert.equal(state.recovery?.[action]?.ok, true),
                );
              check("rename recovery removes only the requested case", () =>
                assert.deepEqual(
                  state.recovery.after.entries.map((entry) => entry.id),
                  [unrelatedId],
                ),
              );
            }
          }
          if (
            scenario.kind !== "delete" ||
            scenario.expected === "failure" ||
            (scenario.expected === "interrupted" && !scenario.published)
          )
            check("target evidence bytes preserved", () =>
              assert.deepEqual(
                afterMap.get(`cases/${targetId}/case.json`),
                beforeMap.get(`cases/${targetId}/case.json`),
              ),
            );
          if (
            scenario.kind !== "rename" &&
            !(
              scenario.kind === "delete" &&
              (scenario.expected === "success" || scenario.published)
            )
          )
            check("target metadata bytes are unchanged", () =>
              assert.deepEqual(
                afterMap.get(`cases/${targetId}/metadata.json`),
                beforeMap.get(`cases/${targetId}/metadata.json`),
              ),
            );
          if (scenario.kind === "export") {
            const exported = afterMap.get("export.case.json");
            if (
              ["existing-destination", "destination-race"].includes(
                scenario.fault,
              )
            )
              check("existing/racing destination never overwritten", () =>
                assert.equal(exported?.sha256, sha256(EXISTING)),
              );
            else if (scenario.expected === "success" || scenario.published)
              check("published export contains exact verified evidence", () =>
                assert.equal(exported?.sha256, sha256(VALID)),
              );
            else
              check(
                "failed/interrupted export has no final partial destination",
                () => assert.equal(exported, undefined),
              );
          }
          if (
            ["export-cleanup-error", "delete-cleanup-error"].includes(
              scenario.fault,
            )
          )
            check(
              "published operation accurately reports incomplete cleanup",
              () =>
                assert.match(
                  operation.result?.result?.message || "",
                  /cleanup.*incomplete|incomplete.*cleanup/i,
                ),
            );
          if (scenario.fault === "unexpected-file")
            check("unexpected files are preserved", () =>
              assert.deepEqual(
                afterMap.get(`cases/${targetId}/unexpected.txt`),
                beforeMap.get(`cases/${targetId}/unexpected.txt`),
              ),
            );
        } catch (error) {
          errors.push({
            check: "harness execution",
            message: error.stack || error.message,
          });
        }
        const semantic = {
          status: errors.length ? "failed" : "passed",
          operation_ok: operation?.result?.ok ?? null,
          operation_error_code: operation?.result?.code ?? null,
          deadline: operation?.deadline ?? null,
          interrupted: operation?.interrupted ?? null,
          injections:
            operation?.messages
              .filter((item) => item.type === "injection")
              .map((item) => item.name) ?? [],
          entry_names:
            inspection?.result?.listed?.entries
              .map((item) => item.name)
              .sort() ?? null,
          unavailable: inspection?.result?.listed?.unavailable ?? null,
          target_opens: inspection?.result?.opened?.[targetId]?.ok ?? null,
          export_sha256:
            after?.find((item) => item.path === "export.case.json")?.sha256 ??
            null,
          recovery: inspection?.result?.recovery
            ? Object.fromEntries(
                ["open", "rename", "delete"].map((action) => [
                  action,
                  inspection.result.recovery[action]?.ok,
                ]),
              )
            : null,
          failed_checks: errors.map((item) => item.check),
        };
        const result = {
          scenario: scenario.name,
          repeat,
          status: semantic.status,
          errors,
          checks,
          semantic,
          before,
          after,
          files: {
            operation: "operation-process.json",
            restart: "restart-process.json",
            interrupted_state: "fixture",
          },
        };
        await writeJson(path.join(folder, "result.json"), result);
        results.push(result);
        console.log(
          `${semantic.status.toUpperCase()} repeat ${repeat}: ${scenario.name}${errors.length ? ` (${errors.map((item) => item.check).join("; ")})` : ""}`,
        );
      }
    }
    const repeatability = SCENARIOS.map((scenario) => {
      const attempts = results.filter(
        (item) => item.scenario === scenario.name,
      );
      return {
        scenario: scenario.name,
        comparable: attempts.length === BOUNDS.repeats,
        identical:
          attempts.length === BOUNDS.repeats &&
          JSON.stringify(attempts[0].semantic) ===
            JSON.stringify(attempts[1].semantic),
      };
    });
    const allRetained = await inventory(attempt);
    const retained = allRetained.filter(
      (file) => !file.path.startsWith("source/"),
    );
    const retainedBytes = retained.reduce((sum, file) => sum + file.bytes, 0);
    if (retainedBytes > BOUNDS.fixtures_bytes)
      budgetError = "Attempt exceeded the 64 MiB retained-evidence budget.";
    if (Date.now() - started > BOUNDS.campaign_ms)
      budgetError ||= "Campaign exceeded the 300-second deadline.";
    const unchanged = [];
    for (const source of sources)
      unchanged.push({
        path: source.path,
        unchanged:
          sha256(await fs.readFile(path.join(ROOT, source.path))) ===
          source.sha256,
      });
    const failed = results.filter((item) => item.status !== "passed");
    const status =
      !failed.length &&
      !budgetError &&
      results.length === SCENARIOS.length * BOUNDS.repeats &&
      repeatability.every((item) => item.identical) &&
      unchanged.every((item) => item.unchanged)
        ? "passed"
        : "failed";
    const report = {
      schema: 1,
      status,
      started_utc: new Date(started).toISOString(),
      finished_utc: new Date().toISOString(),
      elapsed_ms: Date.now() - started,
      bounds: BOUNDS,
      named_scenarios: SCENARIOS.length,
      expected_executions: SCENARIOS.length * BOUNDS.repeats,
      completed_executions: results.length,
      passed_executions: results.length - failed.length,
      failed_executions: failed.length,
      unexecuted: SCENARIOS.length * BOUNDS.repeats - results.length,
      log_bytes: logBytes,
      ipc_log_bytes: ipcBytes,
      combined_log_bytes: logBytes + ipcBytes,
      retained_bytes_before_final_report: retainedBytes,
      retained_bytes_including_report_and_manifest: 0,
      budget_error: budgetError,
      sources,
      sources_unchanged: unchanged,
      repeatability,
      failures: failed.map(({ scenario, repeat, errors }) => ({
        scenario,
        repeat,
        errors,
      })),
      limitations: [
        "Owned simple exact-byte verifier; actual portable-case reader is a separate integration check.",
        "Process termination is not a power-loss or filesystem durability test.",
        "No real disk exhaustion, permission changes, external applications, network shares, or hostile concurrent writers.",
        "Unfamiliar-tester acceptance remains pending; broader T1/T2/T3 fuzzing remains unfinished.",
        "This local run does not qualify later changes on hosted Windows CI.",
      ],
    };
    let reportBytes;
    let manifestBytes;
    for (let settle = 0; settle < 8; settle++) {
      reportBytes = Buffer.from(`${JSON.stringify(report, null, 2)}\n`);
      manifestBytes = Buffer.from(
        `${JSON.stringify(
          [
            ...allRetained,
            {
              path: "report.json",
              bytes: reportBytes.length,
              sha256: sha256(reportBytes),
            },
          ].sort((a, b) => a.path.localeCompare(b.path)),
          null,
          2,
        )}\n`,
      );
      const total = retainedBytes + reportBytes.length + manifestBytes.length;
      if (total > BOUNDS.fixtures_bytes) {
        report.budget_error =
          "Attempt exceeded the 64 MiB retained-evidence budget, including its final report and manifest.";
        report.status = "failed";
      }
      if (report.retained_bytes_including_report_and_manifest === total) break;
      report.retained_bytes_including_report_and_manifest = total;
    }
    await fs.writeFile(path.join(attempt, "report.json"), reportBytes, {
      flag: "wx",
    });
    await fs.writeFile(
      path.join(attempt, "evidence-manifest.json"),
      manifestBytes,
      { flag: "wx" },
    );
    console.log(
      `Recovery result: ${report.status}; ${report.passed_executions}/${report.completed_executions} passed; report ${path.join(attempt, "report.json")}`,
    );
    assert.equal(
      report.status,
      "passed",
      `${failed.length} failed scenario executions; ${report.unexecuted} unexecuted. Preserved evidence: ${attempt}`,
    );
  },
);

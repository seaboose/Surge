// Runs all page families through their existing isolated data/IPC fixtures.
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const root = path.resolve(__dirname, "../verification/visual-release-20261028");
fs.mkdirSync(root, { recursive: true });
const output = fs.mkdtempSync(path.join(root, "audit-"));
const suites = process.argv.slice(2);
const requested = suites.length
  ? suites
  : [
      "library-ui.test.cjs",
      "parity.cjs",
      "evaluation.test.cjs",
      "survive.test.cjs",
      "investigations.test.cjs",
      "timeline-layout.test.cjs",
    ];
const allowed = new Set([
  "library-ui.test.cjs",
  "parity.cjs",
  "evaluation.test.cjs",
  "survive.test.cjs",
  "investigations.test.cjs",
  "timeline-layout.test.cjs",
]);
const results = [];
for (const suite of requested) {
  if (!allowed.has(suite)) throw Error("Unknown visual suite");
  const run = spawnSync(process.execPath, [path.join(__dirname, suite)], {
    cwd: __dirname,
    env: {
      ...process.env,
      SURGE_VISUAL_AUDIT: output,
      SURGE_UI_TEST_OUTPUT: output,
    },
    encoding: "utf8",
    windowsHide: true,
    timeout: 240000,
  });
  fs.writeFileSync(
    path.join(output, suite + ".log"),
    (run.stdout || "") + (run.stderr || ""),
  );
  results.push({
    suite,
    exit_code: run.status,
    error: run.error?.message || null,
  });
  console.log(suite, run.status === 0 ? "PASSED" : "FAILED");
  if (run.status !== 0) break;
}
const pages = fs
  .readdirSync(output)
  .filter((n) => n.endsWith(".json"))
  .map((n) => JSON.parse(fs.readFileSync(path.join(output, n), "utf8")))
  .filter((v) => v.samples);
const status =
  results.length === requested.length && results.every((r) => r.exit_code === 0)
    ? "passed"
    : "failed";
fs.writeFileSync(
  path.join(output, "report.json"),
  JSON.stringify(
    {
      status,
      results,
      pages: pages.map((v) => ({
        name: v.name,
        widths: v.samples.map((s) => s.width),
        issues: v.samples.flatMap((s) => s.issues),
      })),
      scope:
        "Actual renderer journeys at desktop, intermediate and minimum-width layouts. Functional fixtures are controlled, not human study data. Screenshots require visual review in addition to geometry assertions.",
    },
    null,
    2,
  ),
);
console.log(JSON.stringify({ status, output, pages: pages.length }));
process.exitCode = status === "passed" ? 0 : 1;

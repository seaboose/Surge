// Opt-in development-only layout audit used by existing functional journeys.
// It changes viewport size, never application data or production code.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

async function auditPage(app, page, name) {
  if (!process.env.SURGE_VISUAL_AUDIT) return;
  assert(/^[a-z0-9-]+$/.test(name));
  const output = path.resolve(process.env.SURGE_VISUAL_AUDIT);
  fs.mkdirSync(output, { recursive: true });
  const original = await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0].getContentSize(),
  );
  const scroll = await page.evaluate(() => ({
    workspace: document.querySelector(".survive-workspace")?.scrollTop || 0,
    main: document.querySelector("main")?.scrollTop || 0,
  }));
  const samples = [];
  try {
    for (const [width, height] of [
      [1360, 860],
      [900, 700],
      [720, 620],
    ]) {
      await app.evaluate(
        ({ BrowserWindow }, size) =>
          BrowserWindow.getAllWindows()[0].setContentSize(...size),
        [width, height],
      );
      await page.waitForFunction(
        ([requestedWidth, requestedHeight]) =>
          innerWidth === requestedWidth && innerHeight === requestedHeight,
        [width, height],
      );
      await page.waitForTimeout(180);
      const sample = await page.evaluate(() => {
        const issues = [],
          groups = [];
        const visible = (el) =>
          el.checkVisibility() && el.getBoundingClientRect().width > 0;
        for (const el of [
          document.documentElement,
          ...document.querySelectorAll(".survive-workspace"),
        ]) {
          if (visible(el) && el.scrollWidth > el.clientWidth + 2)
            issues.push("Horizontal page overflow: " + el.className);
        }
        for (const selector of [
          ".survive-workflow > button",
          ".investigation-section-tabs > button",
          ".opening-actions > button",
          ".app > nav > button",
          '.actions[aria-label="Comparison changes"] > button',
          '.actions[aria-label="Evaluation counts"] > button:not(:first-child)',
        ]) {
          const boxes = [...document.querySelectorAll(selector)]
            .filter(visible)
            .map((el) => {
              const r = el.getBoundingClientRect();
              return {
                text: el.textContent.trim().slice(0, 80),
                x: r.x,
                y: r.y,
                width: r.width,
                height: r.height,
              };
            });
          if (boxes.length < 2) continue;
          groups.push({ selector, boxes });
          for (const key of ["width", "height"]) {
            if (
              Math.max(...boxes.map((r) => r[key])) -
                Math.min(...boxes.map((r) => r[key])) >
              1
            )
              issues.push(`${selector}: unequal ${key}`);
          }
          if (
            selector.includes("section-tabs") ||
            selector.includes("workflow")
          ) {
            if (
              Math.max(...boxes.map((r) => r.y)) -
                Math.min(...boxes.map((r) => r.y)) >
              1
            )
              issues.push(`${selector}: misaligned top edges`);
          }
        }
        for (const el of document.querySelectorAll("button, summary")) {
          if (!visible(el)) continue;
          if (
            el.scrollWidth > el.clientWidth + 3 ||
            el.scrollHeight > el.clientHeight + 3
          )
            issues.push(
              "Clipped control text: " + el.textContent.trim().slice(0, 70),
            );
        }
        const launch = [
          ...document.querySelectorAll(
            ".survive-launch-fields input,.survive-launch-fields select,.survive-launch-fields > button",
          ),
        ]
          .filter(visible)
          .map((el) => {
            const r = el.getBoundingClientRect();
            return { x: r.x, y: r.y, width: r.width, height: r.height };
          });
        if (launch.length) {
          for (const key of ["width", "height"])
            if (
              Math.max(...launch.map((r) => r[key])) -
                Math.min(...launch.map((r) => r[key])) >
              1
            )
              issues.push("Launch controls: unequal " + key);
          groups.push({ selector: "launch controls", boxes: launch });
        }
        return { width: innerWidth, height: innerHeight, issues, groups };
      });
      samples.push(sample);
      await page.screenshot({
        path: path.join(output, `${name}-${width}.png`),
      });
    }
  } finally {
    await app.evaluate(
      ({ BrowserWindow }, size) =>
        BrowserWindow.getAllWindows()[0].setContentSize(...size),
      original,
    );
    await page.evaluate((value) => {
      const w = document.querySelector(".survive-workspace"),
        m = document.querySelector("main");
      if (w) w.scrollTop = value.workspace;
      if (m) m.scrollTop = value.main;
    }, scroll);
    await page.waitForTimeout(100);
  }
  fs.writeFileSync(
    path.join(output, `${name}.json`),
    JSON.stringify({ name, samples }, null, 2),
  );
  assert.deepEqual(
    samples.flatMap((s) => s.issues.map((issue) => `${s.width}: ${issue}`)),
    [],
    name,
  );
}
module.exports = { auditPage };

"use strict";
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { _electron: electron } = require("playwright");
const root = path.resolve(__dirname, "..");
const output = path.resolve(
  process.env.SURGE_UI_TEST_OUTPUT ||
    path.join(root, "verification/release-refinement-20261028"),
);
fs.mkdirSync(output, { recursive: true });
const folder = fs.mkdtempSync(path.join(output, "developer-inspector-"));
let app;
const checks = [],
  errors = [];
const record = (name) => {
  checks.push(name);
  console.log("PASS", name);
};
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
const build = (...args) =>
  execFileSync(process.execPath, [path.join(__dirname, "build.cjs"), ...args], {
    cwd: __dirname,
    windowsHide: true,
    timeout: 30000,
  });

(async () => {
  let status = "failed";
  try {
    build("--development");
    for (const name of ["app.js.map", "app.css.map", "style.css.map"]) {
      const map = JSON.parse(
        fs.readFileSync(path.join(__dirname, "dist", name), "utf8"),
      );
      assert.equal(map.sources.length, map.sourcesContent.length);
      assert(map.sources.some((source) => source.includes("src/")));
    }
    record("development maps contain readable original JSX and CSS");
    app = await electron.launch({
      executablePath: require("electron"),
      args: [
        __dirname,
        `--user-data-dir=${path.join(folder, "profile")}`,
        "--surge-test",
      ],
      env,
      cwd: root,
      chromiumSandbox: true,
      timeout: 30000,
    });
    const page = await app.firstWindow();
    page.on("pageerror", (error) => errors.push(error.message));
    await page
      .getByRole("button", { name: "Survive sessions", exact: true })
      .waitFor();
    const identity = await app.evaluate(({ BrowserWindow }) => {
      const win = BrowserWindow.getAllWindows()[0];
      return {
        title: win.getTitle(),
        preferences: win.webContents.getLastWebPreferences(),
      };
    });
    assert.equal(identity.title, "Surge — Test session");
    assert.equal(identity.preferences.nodeIntegration, false);
    assert.equal(identity.preferences.contextIsolation, true);
    assert.equal(identity.preferences.sandbox, true);
    record("source test title and renderer isolation remain intact");
    // Playwright's CDP key dispatch does not reach Windows menu accelerators.
    // Dispatch the same native before-input command handled by Ctrl+Shift+I;
    // the real Chromium inspector, DOM, CSS and source maps remain under test.
    await app.evaluate(({ BrowserWindow }) => {
      const contents = BrowserWindow.getAllWindows()[0].webContents;
      contents.emit(
        "before-input-event",
        { preventDefault() {} },
        {
          type: "keyDown",
          key: "I",
          control: true,
          shift: true,
          alt: false,
          meta: false,
        },
      );
    });
    await page.waitForTimeout(800);
    assert.equal(
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].webContents.isDevToolsOpened(),
      ),
      true,
    );
    record("source inspector command opens the real docked Chromium inspector");
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("DOM.enable");
    await cdp.send("CSS.enable");
    const document = await cdp.send("DOM.getDocument");
    const { nodeId } = await cdp.send("DOM.querySelector", {
      nodeId: document.root.nodeId,
      selector: "button",
    });
    assert(nodeId > 0);
    const original = await page
      .locator("button")
      .first()
      .evaluate((node) => getComputedStyle(node).backgroundColor);
    await cdp.send("CSS.setEffectivePropertyValueForNode", {
      nodeId,
      propertyName: "background-color",
      value: "rgb(113, 47, 141)",
    });
    await page.waitForFunction(
      () =>
        getComputedStyle(document.querySelector("button")).backgroundColor ===
        "rgb(113, 47, 141)",
    );
    assert.equal(
      await page
        .locator("button")
        .first()
        .evaluate((node) => getComputedStyle(node).backgroundColor),
      "rgb(113, 47, 141)",
    );
    record("inspector CSS protocol edits update the actual selected element");
    const box = await page.locator("button").first().boundingBox();
    await app.evaluate(
      ({ BrowserWindow }, box) =>
        BrowserWindow.getAllWindows()[0].webContents.inspectElement(
          Math.round(box.x + 8),
          Math.round(box.y + 8),
        ),
      box,
    );
    await page.waitForTimeout(400);
    // $0 is scoped to DevTools' own debugging session, not Playwright's CDP
    // session. Check the actual selected row in the visible inspector instead.
    const selected = await app.evaluate(async ({ BrowserWindow }) => {
      const tools =
        BrowserWindow.getAllWindows()[0].webContents.devToolsWebContents;
      return tools.executeJavaScript(`(() => {
        const rows = [];
        function visit(root) {
          for (const node of root.querySelectorAll('*')) {
            if (node.matches('[aria-selected="true"], .selected'))
              rows.push((node.innerText || node.textContent || '').slice(0, 2000));
            if (node.shadowRoot) visit(node.shadowRoot);
          }
        }
        visit(document);
        return rows.slice(0, 100);
      })()`);
    });
    fs.writeFileSync(
      path.join(folder, "inspected-selection.json"),
      JSON.stringify(selected, null, 2),
    );
    assert(selected.some((text) => /<button\b/.test(text)));
    record("Inspect element links the visible control to its DOM node");
    const sourceMaps = await app.evaluate(async ({ BrowserWindow }) => {
      const session = BrowserWindow.getAllWindows()[0].webContents.session;
      return Promise.all(
        ["app.js.map", "app.css.map", "style.css.map"].map(async (name) => {
          const response = await session.fetch("surge://app/" + name);
          return { name, status: response.status, map: await response.json() };
        }),
      );
    });
    assert(sourceMaps.every((item) => item.status === 200));
    assert(
      sourceMaps[0].map.sources.some((name) =>
        name.endsWith("SurviveWorkspace.jsx"),
      ),
    );
    assert(
      sourceMaps
        .slice(1)
        .every((item) =>
          item.map.sources.some((name) => name.endsWith(".css")),
        ),
    );
    record(
      "JSX and CSS source maps are served through fixed local asset routes",
    );
    await page.screenshot({ path: path.join(folder, "inspected-page.png") });
    await page.reload();
    await page
      .getByRole("button", { name: "Survive sessions", exact: true })
      .waitFor();
    assert.equal(
      await page
        .locator("button")
        .first()
        .evaluate((node) => getComputedStyle(node).backgroundColor),
      original,
    );
    record("temporary style experiment resets after reload");
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].webContents.closeDevTools(),
    );
    assert.deepEqual(errors, []);
    status = "passed";
  } catch (error) {
    console.error(error);
    errors.push(error.message);
    process.exitCode = 1;
  } finally {
    if (app) await app.close();
    build();
    for (const name of ["app.js.map", "app.css.map", "style.css.map"])
      assert.equal(fs.existsSync(path.join(__dirname, "dist", name)), false);
    const result = {
      status,
      checks,
      renderer_errors: errors,
      production_renderer_restored: true,
    };
    fs.writeFileSync(
      path.join(folder, "results.json"),
      JSON.stringify(result, null, 2),
    );
    console.log(JSON.stringify({ ...result, evidence: folder }));
  }
})();

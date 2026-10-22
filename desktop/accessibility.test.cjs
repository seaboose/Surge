const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const out = path.resolve(__dirname, "../verification/electron");
fs.mkdirSync(out, { recursive: true });
const temp = fs.mkdtempSync(path.join(out, "accessibility-"));
const source = path.join(temp, "records.json");
const policy = path.join(temp, "policy.json");
const long = "evidence_".repeat(35);
fs.writeFileSync(
  source,
  JSON.stringify([
    { id: "one", session: "session", reading: 80, message: "needle " + long },
    { id: "two", session: "session", reading: 90, message: "needle second" },
  ]),
);
fs.writeFileSync(
  policy,
  JSON.stringify({
    schema: "surge-policy-v1",
    settings: {
      features: [],
      session: "session",
      event_id: "id",
      time: null,
      time_format: "milliseconds",
      threshold: 6,
      context: { User: "message" },
      rules: [{ name: "Above limit", field: "reading", op: "gt", value: 70 }],
    },
  }),
);
let app, page;
const results = [];
async function ready() {
  await page.waitForFunction(
    () => document.querySelector(".app")?.dataset.working === "false",
  );
}
async function click(name) {
  await page.getByRole("button", { name, exact: true }).click();
  await ready();
}
async function importFile(file, name) {
  await app.evaluate(({ dialog }, file) => {
    dialog.showOpenDialog = async () => ({
      canceled: false,
      filePaths: [file],
    });
  }, file);
  await click(name);
}
async function fit(label) {
  const issues = await page.evaluate(() => {
    const bad = [];
    if (document.documentElement.scrollWidth > innerWidth + 2)
      bad.push("page horizontal overflow");
    const footer = document.querySelector("footer").getBoundingClientRect();
    if (footer.bottom > innerHeight + 2) bad.push("status outside viewport");
    for (const el of document.querySelectorAll(
      "button,summary,.evidence pre,.evidence p",
    )) {
      if (!el.checkVisibility()) continue;
      if (el.scrollWidth > el.clientWidth + 3)
        bad.push(`${el.tagName}: ${el.textContent.slice(0, 55)}`);
    }
    return bad;
  });
  assert.deepEqual(issues, [], label);
}
(async () => {
  for (const dpi of [1, 1.25, 1.5, 2]) {
    const entry = path.join(temp, `entry-${dpi}.cjs`);
    fs.writeFileSync(
      entry,
      `const {app}=require('electron');app.setPath('userData',${JSON.stringify(path.join(temp, `profile-${dpi}`))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
    );
    const env = { ...process.env };
    delete env.ELECTRON_RUN_AS_NODE;
    app = await electron.launch({
      executablePath: require("electron"),
      args: [`--force-device-scale-factor=${dpi}`, entry],
      env,
    });
    page = await app.firstWindow();
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await ready();
    await importFile(source, "Import data");
    await page
      .locator(".setup summary")
      .filter({ hasText: /^Options$/ })
      .press("Enter");
    await importFile(policy, "Load policy");
    await click("Analyze");
    await page.locator(".evidence .observed").waitFor();
    for (const text of [1, 1.5, 2]) {
      await page.evaluate((text) => {
        document.documentElement.style.fontSize = `${13 * text}px`;
      }, text);
      for (const zoom of [1, 2]) {
        await app.evaluate(
          ({ BrowserWindow }, zoom) =>
            BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(zoom),
          zoom,
        );
        await page.waitForTimeout(180);
        await fit(`dpi ${dpi}, text ${text}, zoom ${zoom}`);
        await page.keyboard.press("Alt+1");
        await page
          .getByRole("table", { name: "Preview", exact: true })
          .locator("tbody tr")
          .first()
          .focus();
        await page.keyboard.press("Enter");
        await page.getByLabel("Find in record", { exact: true }).fill("needle");
        const match = page.locator("mark.current-match").first();
        await match.waitFor();
        await match.focus();
        await page.keyboard.press("Enter");
        await click("Copy match");
        assert.equal(
          await app.evaluate(({ clipboard }) => clipboard.readText()),
          "needle",
        );
        await fit(`preview dpi ${dpi}, text ${text}, zoom ${zoom}`);
        // Tab through controls at large text; focused controls must scroll into view.
        for (let i = 0; i < 8; i++) {
          await page.keyboard.press("Tab");
          const valid = await page.evaluate(() => {
            const el = document.activeElement;
            const r = el.getBoundingClientRect();
            return (
              el === document.body ||
              (el.checkVisibility() &&
                r.bottom > 0 &&
                r.top < innerHeight &&
                r.right > 0 &&
                r.left < innerWidth)
            );
          });
          assert.equal(valid, true, "keyboard focus remains visible");
        }
        await page.keyboard.press("Alt+2");
        await page.locator(".evidence .observed").waitFor();
        results.push({
          dpi,
          text,
          zoom,
          viewport: await page.evaluate(() => ({
            width: innerWidth,
            height: innerHeight,
            dpr: devicePixelRatio,
          })),
        });
        if (text === 2 && zoom === 2)
          await page.screenshot({ path: path.join(out, `scaling-${dpi}.png`) });
      }
    }
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1),
    );
    await page.evaluate(() => {
      document.documentElement.style.fontSize = "13px";
    });
    await app.evaluate(({ BrowserWindow }) => {
      const wc = BrowserWindow.getAllWindows()[0].webContents;
      wc.sendInputEvent({
        type: "keyDown",
        keyCode: "=",
        modifiers: ["control"],
      });
      wc.sendInputEvent({
        type: "keyUp",
        keyCode: "=",
        modifiers: ["control"],
      });
    });
    await page.waitForTimeout(100);
    assert.ok(
      (await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].webContents.getZoomFactor(),
      )) > 1,
    );
    await app.evaluate(({ BrowserWindow }) => {
      const wc = BrowserWindow.getAllWindows()[0].webContents;
      wc.sendInputEvent({
        type: "keyDown",
        keyCode: "0",
        modifiers: ["control"],
      });
      wc.sendInputEvent({
        type: "keyUp",
        keyCode: "0",
        modifiers: ["control"],
      });
    });
    await page.waitForTimeout(100);
    assert.equal(
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].webContents.getZoomFactor(),
      ),
      1,
    );
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(720, 540),
    );
    await page.evaluate(() => {
      document.documentElement.style.fontSize = "26px";
    });
    for (const key of ["1", "2", "3", "4", "5"]) {
      await page.keyboard.press(`Alt+${key}`);
      await fit(`small window ${dpi}, view ${key}`);
    }
    await page.keyboard.press("Alt+2");
    await page.getByRole("region", { name: "Record evidence" }).focus();
    await page.keyboard.press("PageDown");
    const png = await app.evaluate(async ({ BrowserWindow }) =>
      (await BrowserWindow.getAllWindows()[0].webContents.capturePage())
        .toPNG()
        .toString("base64"),
    );
    fs.writeFileSync(
      path.join(out, `small-window-${dpi}.png`),
      Buffer.from(png, "base64"),
    );
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1360, 880),
    );
    await page.evaluate(() => {
      document.documentElement.style.fontSize = "13px";
    });
    await page.keyboard.press("Alt+1");
    await click("Edit rules");
    await page.keyboard.press("Escape");
    assert.equal(
      await page
        .getByRole("button", { name: "Edit rules", exact: true })
        .evaluate((el) => el === document.activeElement),
      true,
    );
    await page.keyboard.press("Alt+2");
    const rows = page
      .getByRole("table", { name: "Findings", exact: true })
      .locator("tbody tr");
    await rows.first().focus();
    await page.keyboard.press("ArrowDown");
    assert.equal(
      await rows.nth(1).evaluate((el) => el === document.activeElement),
      true,
    );
    const divider = page.getByRole("separator", { name: "Resize evidence" });
    await divider.focus();
    const before = Number(await divider.getAttribute("aria-valuenow"));
    await page.keyboard.press("ArrowRight");
    assert.equal(
      Number(await divider.getAttribute("aria-valuenow")),
      before + 2,
    );
    assert.deepEqual(errors, []);
    await app.close();
    app = null;
  }
  fs.writeFileSync(
    path.join(out, "accessibility-results.json"),
    JSON.stringify(
      {
        passed: results,
        notes:
          "Electron device scale and root text enlargement; not an OS settings or screen-reader certification.",
      },
      null,
      2,
    ),
  );
  console.log(
    `PASS ${results.length} display/text/zoom combinations, keyboard navigation, match copying, modal focus, row keys and resizing.`,
  );
})()
  .catch(async (e) => {
    console.error(e);
    if (page)
      await page
        .screenshot({ path: path.join(out, "accessibility-failure.png") })
        .catch(() => {});
    process.exitCode = 1;
  })
  .finally(async () => {
    await app?.close();
  });

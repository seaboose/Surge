"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { install, windowTitle } = require("./developer-tools.cjs");
const { options } = require("./build.cjs");

function fixture(packaged) {
  const listeners = new Map(),
    calls = [],
    templates = [];
  let opened = false;
  const app = { isPackaged: packaged, commandLine: { hasSwitch: () => false } };
  const win = {
    setMenu: (value) => calls.push(["menu", value]),
    webContents: {
      on: (name, callback) => listeners.set(name, callback),
      openDevTools: (args) => {
        opened = true;
        calls.push(["open", args]);
      },
      closeDevTools: () => {
        opened = false;
        calls.push(["close"]);
      },
      isDevToolsOpened: () => opened,
      inspectElement: (x, y) => calls.push(["inspect", x, y]),
    },
  };
  const Menu = {
    buildFromTemplate: (value) => {
      templates.push(value);
      return { popup: (args) => calls.push(["popup", args.window === win]) };
    },
  };
  const dialog = { showMessageBox: () => calls.push(["guide"]) };
  return { app, win, Menu, dialog, listeners, calls, templates };
}

test("packaged mode installs no developer menu, listeners or inspector", () => {
  const f = fixture(true);
  assert.equal(install(f.app, f.win, f), false);
  assert.deepEqual(f.calls, []);
  assert.equal(f.listeners.size, 0);
});

test("source inspector docks and captures native context coordinates before layout changes", () => {
  const f = fixture(false);
  assert.equal(install(f.app, f.win, f), true);
  f.listeners.get("context-menu")({}, { x: 50, y: 70 });
  f.templates.at(-1)[0].click();
  assert.deepEqual(f.calls.slice(-2), [
    ["inspect", 50, 70],
    ["open", { mode: "right", activate: true }],
  ]);
  let prevented = false;
  f.listeners.get("before-input-event")(
    {
      preventDefault: () => {
        prevented = true;
      },
    },
    { type: "keyDown", control: true, shift: true, alt: false, key: "I" },
  );
  assert.equal(prevented, true);
  assert.deepEqual(f.calls.at(-1), ["close"]);
});

test("source and explicit test titles distinguish them from the installed product", () => {
  assert.equal(windowTitle(fixture(false).app), "Surge — Development");
  assert.equal(
    windowTitle({
      commandLine: { hasSwitch: (name) => name === "surge-test" },
    }),
    "Surge — Test session",
  );
});

test("readable mapped builds are opt-in and production remains minified with no maps", () => {
  assert.equal(options().minify, true);
  assert.equal(options().sourcemap, false);
  assert.equal(options().sourcesContent, false);
  assert.equal(options().define["process.env.NODE_ENV"], '"production"');
  assert.equal(options(true).minify, false);
  assert.equal(options(true).sourcemap, "linked");
  assert.equal(options(true).sourcesContent, true);
  assert.equal(options(true).define["process.env.NODE_ENV"], '"development"');
});

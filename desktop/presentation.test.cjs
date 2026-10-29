"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  parsePresentation,
  resolvePresentation,
  revealWindow,
} = require("./presentation.cjs");

function display(scale = 1) {
  const area = { x: -1080, y: 0, width: 1080, height: 1872 };
  const calls = [];
  return {
    calls,
    getDisplayNearestPoint(point) {
      calls.push(["point", point]);
      return { workArea: area };
    },
    getDisplayMatching(rect) {
      calls.push(["rect", rect]);
      return { workArea: area };
    },
    dipToScreenRect(win, rect) {
      assert.equal(win, null);
      calls.push(["pixels", rect]);
      return Object.fromEntries(
        Object.entries(rect).map(([key, value]) => [
          key,
          Math.round(value * scale),
        ]),
      );
    },
  };
}

test("unconfigured launches preserve defaults and never inspect displays", () => {
  assert.equal(resolvePresentation(undefined, null), null);
  assert.deepEqual(resolvePresentation('{"hidden":true}', null), {
    hidden: true,
    window: null,
    game: null,
  });
});

test("presentation accepts only bounded trusted numeric launch options", () => {
  for (const value of [
    null,
    [],
    4,
    { hidden: 1 },
    { path: "C:/elsewhere" },
    { point: { x: 0, y: 0 }, rect: { x: 0, y: 0, width: 720, height: 540 } },
    { point: { x: true, y: 0 } },
    { point: { x: 0.5, y: 0 } },
    { point: { x: 100001, y: 0 } },
    { point: { x: 0, y: 0, shell: true } },
    { rect: { x: 0, y: 0, width: 719, height: 540 } },
    { rect: { x: 0, y: 0, width: 720, height: 16385 } },
  ])
    assert.throws(() => parsePresentation(JSON.stringify(value)));
  assert.throws(() => parsePresentation("{"));
  assert.throws(() => parsePresentation(" ".repeat(513)));
});

test("selected portrait display contains Surge and converts game bounds to pixels", () => {
  const screen = display(1.25);
  const value = resolvePresentation(
    '{"point":{"x":-540,"y":936},"hidden":true}',
    screen,
    "win32",
  );
  assert.deepEqual(value.window, { x: -1064, y: 16, width: 1048, height: 880 });
  assert.deepEqual(screen.calls[1], [
    "pixels",
    { x: -1044, y: 48, width: 1008, height: 567 },
  ]);
  assert.deepEqual(value.game, { x: -1305, y: 60, width: 1260, height: 709 });
  assert.equal(value.hidden, true);
});

test("explicit rectangles clamp inside the selected work area", () => {
  const screen = display();
  const value = resolvePresentation(
    '{"rect":{"x":-9000,"y":9000,"width":1600,"height":2200}}',
    screen,
    "linux",
  );
  assert.deepEqual(value.window, {
    x: -1080,
    y: 32,
    width: 1048,
    height: 1840,
  });
  assert.equal(value.hidden, false);
  assert.equal(screen.calls.length, 1);
});

test("hidden mode suppresses initial display and second-instance focus", () => {
  const calls = [];
  const win = {
    isMinimized: () => true,
    restore: () => calls.push("restore"),
    show: () => calls.push("show"),
    focus: () => calls.push("focus"),
  };
  revealWindow(win, { hidden: true });
  revealWindow(win, { hidden: true }, true);
  assert.deepEqual(calls, []);
  revealWindow(win, null);
  revealWindow(win, null, true);
  assert.deepEqual(calls, ["show", "restore", "show", "focus"]);
});

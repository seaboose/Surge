"use strict";

// Trusted launch configuration only. Never exposed through renderer IPC.
function parsePresentation(raw) {
  if (raw === undefined) return null;
  if (typeof raw !== "string" || raw.length > 512)
    throw new Error("SURGE_PRESENTATION must be a bounded JSON object.");
  let value;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("SURGE_PRESENTATION must contain valid JSON.");
  }
  const object = (item) =>
    item && typeof item === "object" && !Array.isArray(item);
  if (
    !object(value) ||
    Object.keys(value).some(
      (key) => !["point", "rect", "hidden"].includes(key),
    ) ||
    ("hidden" in value && typeof value.hidden !== "boolean") ||
    ("point" in value && "rect" in value)
  )
    throw new Error("Invalid launch presentation options.");
  for (const key of ["point", "rect"]) {
    if (!(key in value)) continue;
    const fields = key === "point" ? ["x", "y"] : ["x", "y", "width", "height"];
    const bounds = value[key];
    if (
      !object(bounds) ||
      Object.keys(bounds).length !== fields.length ||
      fields.some((field) => !Number.isInteger(bounds[field])) ||
      Math.abs(bounds.x) > 100000 ||
      Math.abs(bounds.y) > 100000 ||
      (key === "rect" &&
        (bounds.width < 720 ||
          bounds.height < 540 ||
          bounds.width > 16384 ||
          bounds.height > 16384))
    )
      throw new Error("Invalid launch presentation coordinates.");
  }
  return value;
}

function resolvePresentation(raw, screen, platform = process.platform) {
  const value = parsePresentation(raw);
  if (!value) return null;
  const result = { hidden: value.hidden === true, window: null, game: null };
  if (!value.point && !value.rect) return result;
  const display = value.point
    ? screen.getDisplayNearestPoint(value.point)
    : screen.getDisplayMatching(value.rect);
  const area = display.workArea;
  if (area.width < 720 || area.height < 540)
    throw new Error("The selected display is too small for Surge.");
  const width = Math.min(
    value.rect?.width || 1360,
    Math.max(720, area.width - 32),
  );
  const height = Math.min(
    value.rect?.height || 880,
    Math.max(540, area.height - 32),
  );
  const clamp = (n, low, high) => Math.min(high, Math.max(low, n));
  result.window = {
    x: clamp(
      value.rect?.x ?? area.x + Math.floor((area.width - width) / 2),
      area.x,
      area.x + area.width - width,
    ),
    y: clamp(
      value.rect?.y ?? area.y + 16,
      area.y,
      area.y + area.height - height,
    ),
    width,
    height,
  };
  const gameWidth =
    Math.floor(
      Math.min(1280, area.width - 64, ((area.height - 96) * 16) / 9) / 16,
    ) * 16;
  const game = {
    x: area.x + Math.floor((area.width - gameWidth) / 2),
    y: area.y + 48,
    width: gameWidth,
    height: (gameWidth * 9) / 16,
  };
  // Electron uses DIP; Unreal's launch coordinates/resolution use screen pixels.
  result.game =
    platform === "win32" ? screen.dipToScreenRect(null, game) : game;
  return result;
}

function revealWindow(win, presentation, focus = false) {
  if (!win || presentation?.hidden) return;
  if (focus && win.isMinimized()) win.restore();
  win.show();
  if (focus) win.focus();
}

module.exports = { parsePresentation, resolvePresentation, revealWindow };

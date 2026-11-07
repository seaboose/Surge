export const PREFERENCE_KEY = "surge.preferences.v1";
export const DEFAULT_PREFERENCES = Object.freeze({
  version: 1,
  reduceMotion: null,
  openLatestCase: false,
});

export function parsePreferences(text) {
  if (text === null) return { ...DEFAULT_PREFERENCES };
  const value = JSON.parse(text);
  if (
    !value ||
    value.version !== 1 ||
    ![null, true, false].includes(value.reduceMotion) ||
    typeof value.openLatestCase !== "boolean"
  )
    throw new Error("Invalid preferences");
  return {
    version: 1,
    reduceMotion: value.reduceMotion,
    openLatestCase: value.openLatestCase,
  };
}

export function newestCase(entries) {
  return [...(Array.isArray(entries) ? entries : [])]
    .filter(
      (entry) =>
        entry &&
        typeof entry.id === "string" &&
        entry.id &&
        typeof entry.created === "string" &&
        Number.isFinite(Date.parse(entry.created)),
    )
    .sort(
      (a, b) => b.created.localeCompare(a.created) || a.id.localeCompare(b.id),
    )[0];
}

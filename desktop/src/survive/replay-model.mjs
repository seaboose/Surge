export const PROFILE = "survive-lucian-practice-v1";
export const ACTIVE = new Set(["waiting", "recording"]);
export const POINTS = new Set([
  "run_start",
  "sample",
  "ability_start",
  "ability_end",
  "run_end",
]);
export const number = (value, digits = 2) =>
  Number.isFinite(value) ? value.toFixed(digits) : "Unavailable";
export const pretty = (value) => String(value || "").replaceAll("_", " ");

export function lastAt(rows, time) {
  let left = 0,
    right = rows.length;
  while (left < right) {
    const mid = (left + right) >> 1;
    if (rows[mid].elapsed_s <= time + 1e-9) left = mid + 1;
    else right = mid;
  }
  return left > 0 ? rows[left - 1] : null;
}

export function viewRows(snapshot) {
  const merged = new Map();
  for (const row of snapshot?.view?.samples || [])
    merged.set(row.seq, {
      ...row,
      event: "sample",
      detail: "",
      related_id: "",
    });
  for (const row of snapshot?.view?.events || []) merged.set(row.seq, row);
  for (const row of snapshot?.records || []) merged.set(row.seq, row);
  return [...merged.values()].sort((a, b) => a.seq - b.seq);
}

export function lastViewTime(value) {
  return Math.max(
    value?.capture?.source_elapsed_s || 0,
    value?.view?.samples?.at(-1)?.elapsed_s || 0,
    value?.view?.events?.at(-1)?.elapsed_s || 0,
    value?.records?.at(-1)?.elapsed_s || 0,
  );
}

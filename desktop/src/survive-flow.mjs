// Presentation projections only: these never become detector inputs.
export const MARKER_FILTERS = {
  hits: "Hits",
  dashes: "Dashes",
  blinks: "Blinks",
  findings: "Findings",
  gaps: "Missing data",
  commands: "Commands",
  threats: "Threats",
};

export function eventCategory(row) {
  if (row.event === "threat_hit") return "hits";
  if (row.event.startsWith("ability_") && row.detail === "dash")
    return "dashes";
  if (row.event.startsWith("ability_") && row.detail === "blink")
    return "blinks";
  if (row.event.startsWith("command_")) return "commands";
  if (row.event.startsWith("threat_")) return "threats";
  return "capture";
}

export function timelineMarkers(
  events,
  constraints,
  points,
  truncated = false,
) {
  const result = events
    .filter((r) => r.event !== "sample")
    .map((row) => ({
      id: `event-${row.seq}`,
      category: eventCategory(row),
      time: row.elapsed_s,
      seq: row.seq,
      row,
      label: [row.event.replaceAll("_", " "), row.detail]
        .filter(Boolean)
        .join(" · "),
    }));
  for (const rule of constraints) {
    if (!["Review", "Unknown"].includes(rule.status)) continue;
    result.push({
      id: `rule-${rule.event_id}`,
      category: rule.status === "Review" ? "findings" : "gaps",
      time: rule.elapsed_s,
      seq: rule.end_seq,
      constraint: rule,
      label:
        rule.status === "Review"
          ? "Review"
          : `Unknown coverage · ${rule.coverage || "unavailable"}`,
    });
  }
  // A bounded display may omit valid samples; do not invent source gaps from it.
  if (!truncated)
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1],
        b = points[i];
      if (b.elapsed_s - a.elapsed_s > 0.15)
        result.push({
          id: `gap-${a.seq}-${b.seq}`,
          category: "gaps",
          time: b.elapsed_s,
          start: a.elapsed_s,
          seq: b.seq,
          row: b,
          label: `Unobserved position interval ${(b.elapsed_s - a.elapsed_s).toFixed(3)} s`,
        });
    }
  return result.sort((a, b) => a.time - b.time || a.seq - b.seq);
}

export const TIMELINE_LANES = [
  "Commands",
  "Mobility",
  "Threats",
  "Hits",
  "Findings",
  "Coverage",
];

export function markerLane(marker) {
  return (
    {
      commands: 0,
      dashes: 1,
      blinks: 1,
      threats: 2,
      hits: 3,
      findings: 4,
      gaps: 5,
      capture: 5,
    }[marker.category] ?? 5
  );
}

export function clampTimelineRange(range, duration) {
  const end = Number.isFinite(duration) && duration > 0 ? duration : 0.001;
  const minimum = Math.min(0.25, end);
  if (
    !Array.isArray(range) ||
    range.length !== 2 ||
    !range.every(Number.isFinite)
  )
    return [0, end];
  let first = Math.max(0, Math.min(end, Math.min(...range)));
  let last = Math.max(0, Math.min(end, Math.max(...range)));
  if (last - first < minimum) {
    const center = (first + last) / 2;
    first = Math.max(0, Math.min(end - minimum, center - minimum / 2));
    last = first + minimum;
  }
  return [first, last];
}

export function zoomTimelineRange(range, factor, duration, anchor) {
  const [start, end] = clampTimelineRange(range, duration);
  const total = clampTimelineRange(null, duration)[1];
  if (!Number.isFinite(factor) || factor <= 0) return [start, end];
  const middle =
    Number.isFinite(anchor) && anchor >= start && anchor <= end
      ? anchor
      : (start + end) / 2;
  const width = Math.min(total, (end - start) * factor);
  const first = Math.max(0, Math.min(total - width, middle - width / 2));
  return clampTimelineRange([first, first + width], total);
}

export function markerOverlapsRange(marker, range) {
  if (Number.isFinite(marker.start))
    return marker.time >= range[0] && marker.start <= range[1];
  return marker.time >= range[0] && marker.time <= range[1];
}

// Clustering changes only the drawn targets; every exact marker remains selectable.
export function clusterTimelineMarkers(markers, range, width, separation = 24) {
  const span = Math.max(0.001, range[1] - range[0]);
  const scale = Math.max(1, width) / span;
  const ordered = markers
    .filter((r) => markerOverlapsRange(r, range))
    .slice()
    .sort(
      (a, b) =>
        markerLane(a) - markerLane(b) ||
        a.time - b.time ||
        a.seq - b.seq ||
        a.id.localeCompare(b.id),
    );
  const groups = [];
  for (const marker of ordered) {
    const position = Math.max(range[0], Math.min(range[1], marker.time));
    const prior = groups.at(-1);
    if (
      prior &&
      prior.lane === markerLane(marker) &&
      (position - prior.lastPosition) * scale < separation
    ) {
      prior.items.push(marker);
      prior.lastPosition = position;
      prior.time = (prior.firstPosition + position) / 2;
      if (marker.category === "gaps") prior.category = "gaps";
    } else
      groups.push({
        id: marker.id,
        lane: markerLane(marker),
        time: position,
        firstPosition: position,
        lastPosition: position,
        category: marker.category,
        items: [marker],
      });
  }
  return groups;
}

export function timelineOverview(markers, duration, count = 60) {
  const total = Number.isFinite(duration) && duration > 0 ? duration : 0.001;
  const size = Math.max(1, Math.min(120, Math.floor(count) || 1));
  const buckets = Array.from({ length: size }, (_, i) => ({
    start: (i / size) * total,
    end: ((i + 1) / size) * total,
    count: 0,
    reviews: 0,
    unknown: 0,
  }));
  for (const marker of markers) {
    const index = Math.max(
      0,
      Math.min(size - 1, Math.floor((marker.time / total) * size)),
    );
    buckets[index].count++;
    if (marker.category === "findings") buckets[index].reviews++;
    if (marker.category === "gaps") buckets[index].unknown++;
  }
  return buckets;
}

export function sessionSummary(snapshot) {
  const capture = snapshot?.capture;
  const summary = snapshot?.view?.summary;
  const counts = snapshot?.view?.analysis?.counts;
  const complete = capture?.analysis_state === "complete" && summary;
  const threats = Array.isArray(summary?.threats) ? summary.threats : null;
  const fraction = summary?.run_quality?.supported_sample_interval_fraction;
  return {
    duration: complete
      ? summary.simulation_duration_s
      : capture?.source_elapsed_s,
    hits:
      complete && threats
        ? threats.filter((r) => r.outcome === "hit").length
        : null,
    avoided:
      complete && threats
        ? threats.filter(
            (r) =>
              r.outcome === "expired" &&
              r.geometric_initial_threat_without_terrain === true,
          ).length
        : null,
    coverage:
      complete && Number.isFinite(fraction) && fraction >= 0 && fraction <= 1
        ? fraction * 100
        : null,
    reviews:
      capture?.analysis_state === "complete" ? (counts?.Review ?? null) : null,
    unknown:
      capture?.analysis_state === "complete" ? (counts?.Unknown ?? null) : null,
    completion:
      capture?.completion ||
      (["stopped", "failed", "complete"].includes(capture?.state)
        ? "Not observed / partial"
        : "In progress"),
  };
}

export function advanceReplay(time, deltaSeconds, rate, duration) {
  if (
    ![time, deltaSeconds, rate, duration].every(Number.isFinite) ||
    deltaSeconds < 0 ||
    rate <= 0 ||
    duration < 0
  )
    return time;
  return Math.min(duration, Math.max(0, time) + deltaSeconds * rate);
}

export function recordingPresentation(
  capture,
  updateAge = 0,
  requestFailed = false,
) {
  if (!capture) return { label: "Recorder idle", tone: "neutral" };
  const active = ["waiting", "recording"].includes(capture.state);
  if (active && (requestFailed || updateAge > 3))
    return { label: "Recorder status unavailable", tone: "unknown" };
  if (capture.finalizing)
    return { label: "Finalizing recording", tone: "pending" };
  if (capture.state === "waiting")
    return { label: "Armed · waiting for game", tone: "pending" };
  if (capture.state === "recording") {
    if (
      capture.health?.error ||
      capture.health?.parse_errors ||
      capture.health?.sequence_gaps ||
      (capture.health?.stale_s ?? 0) + updateAge > 3
    )
      return { label: "Recording · check receipt health", tone: "unknown" };
    return { label: "Recording · receiving game data", tone: "recording" };
  }
  if (capture.state === "complete" && capture.analysis_state === "complete")
    return { label: "Recording saved · ready to review", tone: "verified" };
  return { label: "Partial or unavailable evidence", tone: "unknown" };
}

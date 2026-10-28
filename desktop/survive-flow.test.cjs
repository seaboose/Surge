const assert = require("node:assert/strict");
const { test, before } = require("node:test");
let flow;
before(async () => {
  flow = await import("./src/survive-flow.mjs");
});

function snapshot(overrides = {}) {
  return {
    capture: {
      state: "complete",
      analysis_state: "complete",
      source_elapsed_s: 60,
      elapsed_s: 88,
      completion: "completed",
      ...overrides.capture,
    },
    view: {
      analysis: { counts: { Review: 0, Unknown: 0, "No finding": 9 } },
      summary: {
        simulation_duration_s: 60,
        run_quality: { supported_sample_interval_fraction: 0 },
        threats: [],
      },
      ...overrides.view,
    },
  };
}

test("session summary separates game duration from recorder time and preserves measured zero", () => {
  assert.deepEqual(flow.sessionSummary(snapshot()), {
    duration: 60,
    hits: 0,
    avoided: 0,
    coverage: 0,
    reviews: 0,
    unknown: 0,
    completion: "completed",
  });
});

test("missing and unfinished summaries cannot turn unavailable observations into clean zeros", () => {
  for (const state of ["pending", "unavailable"]) {
    const value = flow.sessionSummary(
      snapshot({ capture: { analysis_state: state, source_elapsed_s: 17 } }),
    );
    assert.equal(value.duration, 17);
    for (const name of ["hits", "avoided", "coverage", "reviews", "unknown"])
      assert.equal(value[name], null, name);
  }
  const unavailable = flow.sessionSummary(
    snapshot({ view: { summary: null, analysis: { counts: null } } }),
  );
  for (const name of ["hits", "avoided", "coverage", "reviews", "unknown"])
    assert.equal(unavailable[name], null, name);
  for (const fraction of [-0.1, 1.1, NaN, Infinity, null, "1"]) {
    assert.equal(
      flow.sessionSummary(
        snapshot({
          view: {
            summary: {
              run_quality: { supported_sample_interval_fraction: fraction },
            },
          },
        }),
      ).coverage,
      null,
    );
  }
});

test("terminal recordings without a game end never display in progress", () => {
  for (const state of ["stopped", "failed"]) {
    const value = flow.sessionSummary(
      snapshot({
        capture: { state, completion: null, analysis_state: "unavailable" },
      }),
    );
    assert(!/in progress/i.test(value.completion), state);
    assert(
      /partial|not observed|unavailable/i.test(value.completion),
      value.completion,
    );
  }
  assert.match(
    flow.sessionSummary(
      snapshot({
        capture: {
          state: "recording",
          completion: null,
          analysis_state: "pending",
        },
      }),
    ).completion,
    /in progress/i,
  );
});

test("avoided threat counts require initially threatening geometry and an expired outcome", () => {
  const threats = [
    { outcome: "expired", geometric_initial_threat_without_terrain: true },
    { outcome: "expired", geometric_initial_threat_without_terrain: false },
    { outcome: "expired", geometric_initial_threat_without_terrain: null },
    { outcome: "hit", geometric_initial_threat_without_terrain: true },
    { outcome: "hit", geometric_initial_threat_without_terrain: false },
    { outcome: "blocked", geometric_initial_threat_without_terrain: true },
    { outcome: "cancelled", geometric_initial_threat_without_terrain: true },
  ];
  const value = flow.sessionSummary(
    snapshot({
      view: {
        summary: { threats, simulation_duration_s: 60 },
        analysis: { counts: { Review: 2, Unknown: 3 } },
      },
    }),
  );
  assert.equal(value.avoided, 1);
  assert.equal(value.hits, 2);
  assert.equal(value.reviews, 2);
  assert.equal(value.unknown, 3);
});

test("timeline markers retain exact records at tied timestamps and rule endpoints", () => {
  const first = {
    seq: 8,
    elapsed_s: 1.23456789,
    event: "threat_hit",
    detail: "circle_aimed",
  };
  const second = {
    seq: 9,
    elapsed_s: first.elapsed_s,
    event: "ability_start",
    detail: "dash",
  };
  const blink = {
    seq: 10,
    elapsed_s: 2,
    event: "ability_start",
    detail: "blink",
  };
  const review = {
    event_id: "9:walking",
    end_seq: 9,
    elapsed_s: first.elapsed_s,
    status: "Review",
  };
  const unknown = {
    event_id: "10:walking",
    end_seq: 10,
    elapsed_s: 2,
    status: "Unknown",
    coverage: "insufficient",
  };
  const markers = flow.timelineMarkers(
    [second, first, blink, { seq: 11, elapsed_s: 3, event: "sample" }],
    [
      review,
      unknown,
      { event_id: "other", end_seq: 11, elapsed_s: 3, status: "No finding" },
    ],
    [],
  );
  assert.equal(markers.length, 5);
  assert.equal(markers[0].seq, 8);
  assert.equal(markers[0].row, first);
  assert.equal(markers[0].time, first.elapsed_s);
  assert.equal(markers.find((m) => m.category === "dashes").row, second);
  assert.equal(markers.find((m) => m.category === "blinks").row, blink);
  assert.equal(
    markers.find((m) => m.category === "findings").constraint,
    review,
  );
  assert.equal(markers.find((m) => m.category === "gaps").constraint, unknown);
  assert.equal(new Set(markers.map((m) => m.id)).size, markers.length);
});

test("position gaps do not arise from omitted display items while measured Unknown remains visible", () => {
  const points = [
    { seq: 0, elapsed_s: 0 },
    { seq: 4, elapsed_s: 0.151 },
    { seq: 5, elapsed_s: 0.16 },
  ];
  const unknown = {
    event_id: "gap",
    end_seq: 4,
    elapsed_s: 0.151,
    status: "Unknown",
  };
  const complete = flow.timelineMarkers([], [unknown], points, false);
  assert.equal(complete.filter((m) => Number.isFinite(m.start)).length, 1);
  const gap = complete.find((m) => Number.isFinite(m.start));
  assert.equal(gap.start, 0);
  assert.equal(gap.time, 0.151);
  assert.equal(gap.row, points[1]);
  const bounded = flow.timelineMarkers([], [unknown], points, true);
  assert.equal(bounded.length, 1);
  assert.equal(bounded[0].constraint, unknown);
});

test("replay progression respects rate, duration and clock boundaries", () => {
  assert.equal(flow.advanceReplay(10, 2, 0.5, 60), 11);
  assert.equal(flow.advanceReplay(10, 2, 2, 60), 14);
  assert.equal(flow.advanceReplay(59, 2, 2, 60), 60);
  assert.equal(flow.advanceReplay(60, 1, 1, 60), 60);
  assert.equal(flow.advanceReplay(10, 0, 1, 60), 10);
  assert.equal(flow.advanceReplay(0, 1, 1, 0), 0);
  for (const args of [
    [10, -1, 1, 60],
    [10, 1, 0, 60],
    [10, 1, -1, 60],
    [10, 1, 1, -1],
    [10, Infinity, 1, 60],
    [10, 1, NaN, 60],
  ])
    assert.equal(flow.advanceReplay(...args), 10);
});

test("recorder health distinguishes client freshness, received data age and saved evidence", () => {
  assert.equal(flow.recordingPresentation(null).label, "Recorder idle");
  assert.equal(
    flow.recordingPresentation({ state: "waiting" }).tone,
    "pending",
  );
  assert.match(
    flow.recordingPresentation({ state: "recording", finalizing: true }).label,
    /Finalizing/,
  );
  const recording = {
    state: "recording",
    health: { stale_s: 0, parse_errors: 0, sequence_gaps: 0 },
  };
  assert.equal(flow.recordingPresentation(recording, 3).tone, "recording");
  assert.match(
    flow.recordingPresentation(recording, 3.01).label,
    /status unavailable/,
  );
  assert.match(
    flow.recordingPresentation(recording, 0, true).label,
    /status unavailable/,
  );
  assert.match(
    flow.recordingPresentation({ ...recording, health: { stale_s: 4 } }).label,
    /receipt health/,
  );
  assert.match(
    flow.recordingPresentation({ ...recording, health: { parse_errors: 1 } })
      .label,
    /receipt health/,
  );
  assert.match(
    flow.recordingPresentation({ ...recording, health: { sequence_gaps: 1 } })
      .label,
    /receipt health/,
  );
  assert.equal(
    flow.recordingPresentation(
      { state: "stopped", analysis_state: "unavailable" },
      100,
      true,
    ).tone,
    "unknown",
  );
  assert.equal(
    flow.recordingPresentation(
      { state: "complete", analysis_state: "complete" },
      100,
    ).tone,
    "verified",
  );
});

test("timeline ranges clamp reversed, empty, invalid and edge selections without losing bounds", () => {
  assert.deepEqual(flow.clampTimelineRange([20, 10], 60), [10, 20]);
  assert.deepEqual(flow.clampTimelineRange([-5, 70], 60), [0, 60]);
  assert.deepEqual(flow.clampTimelineRange([60, 60], 60), [59.75, 60]);
  assert.deepEqual(flow.clampTimelineRange([0, 0], 60), [0, 0.25]);
  assert.deepEqual(flow.clampTimelineRange([0, 1], 0.1), [0, 0.1]);
  for (const range of [null, [], [NaN, 10], [0, Infinity], ["1", 2]])
    assert.deepEqual(flow.clampTimelineRange(range, 60), [0, 60]);
  assert.deepEqual(flow.clampTimelineRange(null, NaN), [0, 0.001]);
});

test("timeline zoom preserves a valid window at recording boundaries and never edits source times", () => {
  const range = [0, 8];
  assert.deepEqual(flow.zoomTimelineRange(range, 0.5, 60, 0), [0, 4]);
  assert.deepEqual(flow.zoomTimelineRange([52, 60], 2, 60, 60), [44, 60]);
  assert.deepEqual(flow.zoomTimelineRange([10, 18], 0.5, 60, 14), [12, 16]);
  assert.deepEqual(flow.zoomTimelineRange([10, 18], -1, 60, 14), [10, 18]);
  assert.deepEqual(range, [0, 8]);
});

test("gaps crossing a zoom window remain visible even when their endpoint is outside", () => {
  const gap = { start: 2, time: 9, category: "gaps", seq: 270, id: "g" };
  assert.equal(flow.markerOverlapsRange(gap, [3, 5]), true);
  assert.equal(flow.markerOverlapsRange(gap, [10, 12]), false);
  assert.equal(flow.markerOverlapsRange({ time: 9 }, [3, 5]), false);
  const group = flow.clusterTimelineMarkers([gap], [3, 5], 800)[0];
  assert.equal(group.time, 5);
  assert.equal(group.items[0], gap);
  assert.equal(gap.time, 9);
});

test("dense marker clusters preserve every exact event and keep separate lanes distinct", () => {
  const values = [
    { id: "a", time: 1, seq: 1, category: "findings" },
    { id: "b", time: 1, seq: 2, category: "findings" },
    { id: "c", time: 1.02, seq: 3, category: "findings" },
    { id: "hit", time: 1, seq: 4, category: "hits" },
    { id: "late", time: 9, seq: 5, category: "findings" },
  ];
  const before = JSON.stringify(values),
    groups = flow.clusterTimelineMarkers(values, [0, 10], 500);
  assert.deepEqual(
    groups.map((g) => g.items.length),
    [1, 3, 1],
  );
  assert.equal(groups.flatMap((g) => g.items).length, values.length);
  assert.equal(
    new Set(groups.flatMap((g) => g.items).map((m) => m.id)).size,
    values.length,
  );
  assert.equal(groups.find((g) => g.items.length === 3).items[1], values[1]);
  assert.equal(JSON.stringify(values), before);
});

test("overview buckets retain all counts and distinguish findings from unsupported evidence", () => {
  const markers = [
    { time: 0, category: "capture" },
    { time: 1, category: "findings" },
    { time: 5, category: "gaps" },
    { time: 60, category: "findings" },
  ];
  const buckets = flow.timelineOverview(markers, 60, 60);
  assert.equal(buckets.length, 60);
  assert.equal(
    buckets.reduce((n, b) => n + b.count, 0),
    4,
  );
  assert.equal(
    buckets.reduce((n, b) => n + b.reviews, 0),
    2,
  );
  assert.equal(
    buckets.reduce((n, b) => n + b.unknown, 0),
    1,
  );
  assert.equal(buckets[59].reviews, 1);
  assert.equal(flow.timelineOverview(markers, 60, 500).length, 120);
});

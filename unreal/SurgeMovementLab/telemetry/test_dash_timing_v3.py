"""Synthetic dash evidence boundaries; these do not exercise Unreal gameplay."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_v3 import derive
from test_v3 import row, encode


def capture(points, *, duration=.32, distance=425., end_time=None, ended=True,
            completion="completed", end_delta=1 / 60):
    start_time = 1. if end_time is None else end_time - duration
    rows = [row(0), row(start_time, "ability_start", movement_mode="dash", detail="dash", related_id="d1")]
    for elapsed, x, extra in points:
        rows.append(row(start_time + elapsed, x=x, movement_mode="dash", **extra))
    if ended:
        rows.append(row(start_time + duration, "ability_end", x=distance, detail="dash", related_id="d1",
                        movement_mode="walking", delta_s=end_delta))
    return encode(rows, completion=completion)


def constraints(raw, name):
    return [record for record in derive(raw) if record["constraint"] == name]


class DashTimingTests(unittest.TestCase):
    def test_reference_speed_and_frame_quantized_duration_are_supported(self):
        points = [(i * .04, i * .04 * 1350, {}) for i in range(1, 8)]
        raw = capture(points)
        speed = constraints(raw, "dash_displacement")
        duration = constraints(raw, "dash_duration")
        self.assertEqual(len(speed), 6)
        self.assertTrue(all(0 < r["constraint_ratio"] <= 1 for r in speed + duration))
        self.assertAlmostEqual(duration[0]["allowed"], 425 / 1350 + 1 / 60 + .001)

    def test_speed_violation_is_detected_within_legal_total_range(self):
        raw = capture([(.04, 50, {}), (.08, 250, {}), (.12, 400, {})], duration=.16)
        self.assertLessEqual(constraints(raw, "dash_range")[0]["constraint_ratio"], 1)
        self.assertTrue(any(r["constraint_ratio"] > 1 for r in constraints(raw, "dash_displacement")))

    def test_overlong_dash_is_independent_of_legal_displacement(self):
        points = [(i * .04, 425 * i * .04 / .6, {}) for i in range(1, 15)]
        raw = capture(points, duration=.6)
        self.assertTrue(all(r["constraint_ratio"] <= 1 for r in constraints(raw, "dash_displacement")))
        self.assertGreater(constraints(raw, "dash_duration")[0]["constraint_ratio"], 1)

    def test_wall_stop_may_be_shorter_than_minimum_requested_distance(self):
        raw = capture([(.02, 20, {}), (.04, 40, {})], duration=.08, distance=50)
        for name in ("dash_range", "dash_displacement", "dash_duration"):
            self.assertTrue(all(r["constraint_ratio"] <= 1 for r in constraints(raw, name)))

    def test_gap_cannot_pass_speed_or_duration(self):
        raw = capture([(.04, 40, {}), (.28, 250, {})])
        self.assertIsNone(constraints(raw, "dash_displacement")[0]["constraint_ratio"])
        self.assertIsNone(constraints(raw, "dash_duration")[0]["constraint_ratio"])

    def test_state_change_or_large_tick_is_unknown(self):
        for extra in ({"movement_mode": "blink"}, {"delta_s": .2}):
            # Build this explicit row separately to avoid duplicate mode kwargs.
            points = [row(1.04, x=40, movement_mode="dash"), row(1.08, x=80, movement_mode="dash")]
            points[1].update(extra)
            raw = encode([row(0), row(1, "ability_start", movement_mode="dash", detail="dash", related_id="d1"),
                          *points, row(1.1, "ability_end", x=90, detail="dash", related_id="d1")])
            self.assertIsNone(constraints(raw, "dash_displacement")[0]["constraint_ratio"])
            self.assertIsNone(constraints(raw, "dash_duration")[0]["constraint_ratio"])

    def test_transition_only_and_run_boundary_durations_are_unknown(self):
        raw = capture([], duration=.1, distance=50)
        self.assertEqual(constraints(raw, "dash_displacement"), [])
        self.assertIsNone(constraints(raw, "dash_duration")[0]["constraint_ratio"])
        raw = capture([(.02, 20, {}), (.04, 40, {})], duration=.08, distance=50, end_time=60)
        duration = constraints(raw, "dash_duration")[0]
        self.assertIsNone(duration["constraint_ratio"])
        self.assertIn("censored", duration["coverage"])

    def test_unfinished_partial_activation_is_unknown_and_terminal_marker_last(self):
        raw = capture([(.04, 40, {}), (.08, 80, {})], ended=False, completion="restart")
        duration = constraints(raw, "dash_duration")[0]
        self.assertIsNone(duration["constraint_ratio"])
        self.assertIn("unfinished", duration["coverage"])
        self.assertEqual(derive(raw)[-1]["constraint"], "run_completion")

    def test_order_and_ids_remain_compatible_and_payload_cannot_redefine_limits(self):
        points = [(.04, 40, {"a": 999999, "b": 999999}), (.08, 240, {"a": 999999, "b": 999999})]
        records = derive(capture(points, duration=.1, distance=250))
        self.assertEqual([r["end_seq"] for r in records], sorted(r["end_seq"] for r in records))
        self.assertEqual(len({r["event_id"] for r in records}), len(records))
        speed = next(r for r in records if r["constraint"] == "dash_displacement")
        self.assertAlmostEqual(speed["allowed"], 1350 * .04 + 5)
        self.assertGreater(speed["constraint_ratio"], 1)
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        import engine
        import json
        policy = json.loads(Path(__file__).with_name("survive-policy.json").read_text())
        data = engine.parse_bytes("\n".join(json.dumps(r) for r in records).encode(), "dash-v3.jsonl")
        result = engine.analyze(data, None, policy)
        self.assertTrue(any(r["status"] == "Review" for r in result["records"]))


if __name__ == "__main__":
    unittest.main()

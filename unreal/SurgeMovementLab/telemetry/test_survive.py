"""Synthetic Survive contract checks; no Unreal execution is implied."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dodge_window import dodge_window_seconds
from prepare_v2 import derive


def row(t, event="sample", x=0, y=0, detail="", related_id="", mode="walking"):
    return dict(schema="survive-v2", session_id="b" * 32, seq=0, elapsed_s=t,
                event=event, x_cm=x, y_cm=y, z_cm=100, movement_mode=mode,
                related_id=related_id, detail=detail, a=0, b=0, c=0, d=0,
                source_x_cm=0, source_y_cm=0, velocity_x_cm_s=0, velocity_y_cm_s=0)


def capture(rows, completion="completed"):
    rows = [row(0, "run_start")] + rows + [row(60, "run_end", detail=completion, mode="ended")]
    return ("\n".join(json.dumps(dict(r, seq=i)) for i, r in enumerate(rows)) + "\n").encode()


def ability(t, end_t, kind, key, start_x, end_x):
    return [row(t, "ability_start", x=start_x, detail=kind, related_id=key, mode=kind),
            row(end_t, "ability_end", x=end_x, detail=kind, related_id=key, mode="walking")]


class SurviveTests(unittest.TestCase):
    def test_legal_dash_and_blink_are_not_walking_violations(self):
        rows = [row(0), row(.04, x=24)] + ability(.05, .23, "dash", "d1", 24, 374)
        rows += [row(.24, x=374), row(.28, x=398)]
        rows += ability(.29, .29, "blink", "b1", 398, 848) + [row(.32, x=848), row(.36, x=872)]
        result = derive(capture(rows))
        self.assertFalse(any(r["constraint_ratio"] is not None and r["constraint_ratio"] > 1 for r in result))
        self.assertTrue(any(r["constraint_ratio"] is None for r in result))

    def test_blink_between_walking_endpoints_is_unknown_for_walking(self):
        result = derive(capture([row(0)] + ability(.01, .01, "blink", "b1", 0, 450) + [row(.04, x=450)]))
        walk = next(r for r in result if r["constraint"] == "walking_displacement")
        self.assertIsNone(walk["constraint_ratio"])

    def test_actual_excess_range_cooldown_and_speed_create_findings(self):
        rows = [row(0), row(.04, x=80)] + ability(.05, .23, "dash", "d1", 80, 700)
        rows += ability(.3, .48, "dash", "d2", 700, 1050)
        findings = {r["constraint"] for r in derive(capture(rows)) if (r["constraint_ratio"] or 0) > 1}
        self.assertEqual(findings, {"walking_displacement", "dash_range", "dash_cooldown"})

    def test_hitch_and_partial_run_produce_unknowns(self):
        result = derive(capture([row(0), row(.8, x=480)], completion="capture_limit"))
        self.assertTrue(all(r["constraint_ratio"] is None for r in result))

    def test_lifecycle_missing_tail_labels_and_mutable_limits(self):
        raw = capture([row(0), row(.04, x=80)])
        for bad in (b"\n".join(raw.splitlines()[:-1]),
                    raw.replace(b'"seq": 1', b'"seq": 8'),
                    raw.replace(b'"a": 0', b'"label": true, "a": 0'),
                    capture(ability(.1, .2, "dash", "same", 0, 350) + ability(.3, .4, "dash", "same", 350, 700))):
            with self.assertRaises(ValueError):
                derive(bad)
        # Payload claims cannot increase the reviewed walking cap.
        self.assertGreater(derive(raw.replace(b'"a": 0', b'"a": 99999'))[0]["constraint_ratio"], 1)

    def test_surge_compatibility(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        import engine
        records = derive(capture([row(0), row(.04, x=24), row(.08, x=104), row(.8, x=200)]))
        data = engine.parse_bytes("\n".join(json.dumps(r) for r in records).encode(), "survive.jsonl")
        policy = json.loads(Path(__file__).with_name("survive-policy.json").read_text())
        result = engine.analyze(data, None, policy)
        self.assertEqual([r["status"] for r in result["records"]], ["No finding", "Review", "Unknown", "Unknown"])

    def test_missing_head_tail_and_entire_trajectory_are_unknown(self):
        result = derive(capture([row(1), row(1.04, x=24)]))
        gaps = {r["constraint"] for r in result if r["constraint_ratio"] is None}
        self.assertEqual(gaps, {"capture_start_gap", "capture_end_gap"})
        result = derive(capture(ability(.1, .28, "dash", "d1", 0, 350)))
        self.assertTrue(any(r["coverage"] == "no trajectory samples retained" for r in result))

    def test_adapted_calibration_and_limits(self):
        args = dict(cast_delay_s=.25, distance_cm=900, projectile_speed_cm_s=1200,
                    player_radius_cm=42, projectile_radius_cm=20, walk_speed_cm_s=600)
        self.assertAlmostEqual(dodge_window_seconds(**args), 1 - 62 / 600)
        self.assertLess(dodge_window_seconds(**dict(args, distance_cm=400)), dodge_window_seconds(**args))
        with self.assertRaises(ValueError):
            dodge_window_seconds(**dict(args, walk_speed_cm_s=0))


if __name__ == "__main__":
    unittest.main()

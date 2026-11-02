"""Synthetic evidence/geometry checks; never represented as Unreal playtests."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_v3 import derive, load_profile, load_rows
from audit_v3 import summarize, segment_distance
from analyze_v3 import build_bundle


def row(t, event="sample", x=0, y=0, **extra):
    result = dict(schema="survive-v3", session_id="c" * 32, seq=0, elapsed_s=t,
                  event=event, x_cm=x, y_cm=y, z_cm=90, movement_mode="walking",
                  related_id="", detail="", a=0, b=0, c=0, d=0,
                  source_x_cm=0, source_y_cm=0, velocity_x_cm_s=0, velocity_y_cm_s=0,
                  server_tick=int(t * 60 + .00001), delta_s=1 / 60, monotonic_s=t,
                  profile_id="survive-lucian-practice-v1", path_radius_cm=41,
                  hit_radius_cm=65, visual_radius_cm=50, threat_x_cm=0, threat_y_cm=0,
                  nearest_clearance_cm=0, clearance_valid=False, baseline_threat="unknown")
    result.update(extra)
    return result


def encode(rows, completion="completed"):
    data = [row(0, "run_start", detail="fixed_seed", a=1337, b=.5, c=60, d=3)]
    data += sorted(rows, key=lambda r: r["elapsed_s"])
    data += [row(60, "run_end", detail=completion, movement_mode="ended")]
    return ("\n".join(json.dumps(dict(r, seq=i), allow_nan=False) for i, r in enumerate(data)) + "\n").encode()


def nominal_capture():
    def player_y(t):
        return min(200., max(0., (t - .5) * 335))
    rows = [row(i / 30, y=player_y(i / 30)) for i in range(1801)]
    threat = dict(detail="projectile_aimed", related_id="p1", a=0, b=0, c=70, d=1200,
                  source_x_cm=-900, source_y_cm=0, velocity_x_cm_s=1200, velocity_y_cm_s=0,
                  baseline_threat="yes")
    rows += [row(.5, "threat_warning", y=0, threat_x_cm=-900, **threat),
             row(.75, "threat_fire", y=player_y(.75), threat_x_cm=-900, **threat),
             row(.75 + 1300 / 1200, "threat_expired", y=200, threat_x_cm=400,
                 nearest_clearance_cm=65, clearance_valid=True, **threat)]
    return encode(rows)


class V3Tests(unittest.TestCase):
    def test_nominal_profile_trajectory_and_exposure(self):
        raw = nominal_capture()
        profile = load_profile()
        summary = summarize(load_rows(raw, profile), profile)
        self.assertEqual(summary["attack_strata"]["projectile_aimed"]["geometric_initial_threat"], 1)
        self.assertEqual(summary["attack_strata"]["projectile_aimed"]["expired"], 1)
        self.assertAlmostEqual(summary["threats"][0]["sampled_nearest_clearance_cm"], 65, places=5)
        self.assertGreater(summary["threats"][0]["sampled_flight_coverage"], .99)
        self.assertEqual(summary["audit_issues"], [])
        self.assertFalse(any((r["constraint_ratio"] or 0) > 1 for r in derive(raw)))

    def test_incoming_profile_cannot_select_limits(self):
        raw = nominal_capture()
        with self.assertRaises(ValueError):
            derive(raw.replace(b"survive-lucian-practice-v1", b"survive-lucian-reference-v1"))
        with self.assertRaises(ValueError):
            derive(raw.replace(b'"hit_radius_cm": 65', b'"hit_radius_cm": 1'))

    def test_source_labels_clock_and_unknown_fields_rejected(self):
        raw = nominal_capture()
        for bad in (raw.replace(b'"seq": 1,', b'"seq": 1, "truth": true,', 1),
                    raw.replace(b'"monotonic_s": 0.03333333333333333', b'"monotonic_s": -1', 1),
                    raw.replace(b'"server_tick": 2', b'"server_tick": true', 1)):
            with self.assertRaises(ValueError):
                derive(bad)

    def test_fixed_profile_speed_and_mobility(self):
        rows = [row(0), row(.04, x=30)]  # 750/s exceeds the frozen335 envelope.
        rows += [row(.1, "ability_start", detail="dash", related_id="d1", x=30, movement_mode="dash"),
                 row(.1 + 425 / 1350, "ability_end", detail="dash", related_id="d1", x=455)]
        records = derive(encode(rows))
        self.assertGreater(records[0]["constraint_ratio"], 1)
        self.assertLessEqual(next(r for r in records if r["constraint"] == "dash_range")["constraint_ratio"], 1)

    def test_impossible_threat_lifecycle_and_tracking_rejected(self):
        raw = nominal_capture()
        profile = load_profile()
        rows = load_rows(raw, profile)
        no_fire = [r for r in rows if r["event"] != "threat_fire"]
        with self.assertRaises(ValueError):
            summarize(no_fire, profile)
        changed = [dict(r, velocity_x_cm_s=1100) if r["event"] == "threat_fire" else r for r in rows]
        with self.assertRaises(ValueError):
            summarize(changed, profile)

    def test_circle_pressure_is_not_pure_reaction_failure(self):
        common = dict(detail="circle_aimed", related_id="a1", a=0, b=0, c=250, d=.75, baseline_threat="yes")
        rows = [row(0), row(1), row(1, "threat_warning", **common),
                row(1.75, "threat_fire", **common),
                row(1.75, "threat_hit", nearest_clearance_cm=-315, clearance_valid=True, **common), row(60)]
        profile = load_profile()
        summary = summarize(load_rows(encode(rows), profile), profile)
        self.assertFalse(summary["threats"][0]["ideal_walking_escape_possible_without_terrain"])
        self.assertEqual(summary["threats"][0]["minimum_circle_escape_cm"], 315)

    def test_threat_profile_geometry_and_unrelated_gap(self):
        profile = load_profile()
        rows = load_rows(nominal_capture(), profile)
        bad = [dict(r, c=1) if r["event"].startswith("threat_") else r for r in rows]
        with self.assertRaises(ValueError):
            summarize(bad, profile)
        # An unrelated late gap must not mask an incorrect early-flight clearance.
        changed = [dict(r, nearest_clearance_cm=1000) if r["event"] == "threat_expired" else r
                   for r in rows if not (10 < r["elapsed_s"] < 12)]
        summary = summarize(changed, profile)
        self.assertEqual(summary["threats"][0]["clearance_consistency"], "review_geometry_or_sampling")
        # A gap during this threat cannot be called a successful consistency check.
        partial = [r for r in rows if not (.9 < r["elapsed_s"] < 1.2)]
        summary = summarize(partial, profile)
        self.assertEqual(summary["threats"][0]["clearance_consistency"], "partial_sampling_unavailable")

    def test_exclusive_bundle_and_replayable_snapshots(self):
        raw = nominal_capture()
        test_root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(dir=test_root) as temp:
            self.assertTrue(Path(temp).resolve().is_relative_to(test_root))
            output = Path(temp) / "run"
            build_bundle(raw, output, profile_id="survive-lucian-practice-v1", source_kind="synthetic-fixture", phase="development")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["source_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(manifest["policy_sha256"], hashlib.sha256((output / "profile.json").read_bytes()).hexdigest())
            for name, expected in manifest["bundle_sha256"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
            with self.assertRaises(FileExistsError):
                build_bundle(raw, output, profile_id="survive-lucian-practice-v1", source_kind="synthetic-fixture", phase="development")
            self.assertEqual((output / "source.jsonl").read_bytes(), raw)

    def test_bundle_binds_offline_replay_and_exporter(self):
        raw = nominal_capture()
        test_root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(dir=test_root) as temp:
            self.assertTrue(Path(temp).resolve().is_relative_to(test_root))
            output = Path(temp) / "with-replay"
            build_bundle(raw, output, profile_id="survive-lucian-practice-v1", source_kind="synthetic-fixture",
                         phase="development", include_replay=True)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["replay"]["profile_sha256"], manifest["profile_sha256"])
            self.assertEqual(hashlib.sha256((output / "replay.html").read_bytes()).hexdigest(),
                             manifest["bundle_sha256"]["replay.html"])
            self.assertEqual(manifest["analysis_settings_sha256"], manifest["bundle_sha256"]["policy.json"])
            self.assertEqual(set(manifest["replay_exporter_sha256"]), {"render_replay.py", "replay-template.html"})

    def test_relative_segment_handles_between_frame_crossing(self):
        self.assertEqual(segment_distance((0, 0), (-100, 0), (100, 0)), 0)
        self.assertEqual(segment_distance((0, 0), (0, 200), (100, 200)), 200)

    def test_blocked_terminal_does_not_replay_through_wall(self):
        profile = load_profile()
        rows = [row(i / 30) for i in range(1801)]
        common = dict(detail="projectile_aimed", related_id="wall", a=0, b=0, c=70, d=1200,
                      source_x_cm=-900, velocity_x_cm_s=1200, baseline_threat="yes")
        rows += [row(.5, "threat_warning", threat_x_cm=-900, **common),
                 row(.75, "threat_fire", threat_x_cm=-900, **common),
                 row(1.27, "threat_blocked", threat_x_cm=-300, nearest_clearance_cm=165, clearance_valid=True, **common)]
        summary = summarize(load_rows(encode(rows), profile), profile)
        self.assertAlmostEqual(summary["threats"][0]["sampled_nearest_clearance_cm"], 165)
        self.assertTrue(any("pass-through" in issue for issue in summary["audit_issues"]))

    def test_restart_retains_unknown_and_current_surge_compatibility(self):
        raw = encode([row(0), row(.04, x=30)], completion="restart")
        records = derive(raw)
        self.assertEqual(records[-1]["run_completion"], "restart")
        self.assertIsNone(records[-1]["constraint_ratio"])
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        import engine
        policy = json.loads(Path(__file__).with_name("survive-policy.json").read_text())
        data = engine.parse_bytes("\n".join(json.dumps(r) for r in records).encode(), "v3.jsonl")
        result = engine.analyze(data, None, policy)
        self.assertEqual(result["records"][0]["status"], "Review")
        self.assertEqual(result["records"][-1]["status"], "Unknown")


if __name__ == "__main__":
    unittest.main()

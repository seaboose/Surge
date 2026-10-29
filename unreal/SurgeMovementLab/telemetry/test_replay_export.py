"""Synthetic export/coverage/security tests, not Unreal playtest evidence."""
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_v3
from render_replay import (
    MAX_BYTES, build_model, build_points, export_replay, player_at,
    projectile_at, render_model, script_json,
)

PROFILE = "survive-lucian-practice-v1"


def row(t, event="sample", x=0, y=0, **extra):
    result = dict(schema="survive-v3", session_id="d" * 32, seq=0, elapsed_s=t,
                  event=event, x_cm=x, y_cm=y, z_cm=90, movement_mode="walking",
                  related_id="", detail="", a=0, b=0, c=0, d=0,
                  source_x_cm=0, source_y_cm=0, velocity_x_cm_s=0, velocity_y_cm_s=0,
                  server_tick=int(t * 1000), delta_s=.01, monotonic_s=t,
                  profile_id=PROFILE, path_radius_cm=41, hit_radius_cm=65,
                  visual_radius_cm=50, threat_x_cm=0, threat_y_cm=0,
                  nearest_clearance_cm=0, clearance_valid=False, baseline_threat="unknown")
    result.update(extra)
    return result


def encode(rows=None, end=.2):
    rows = [row(0), row(.1, x=33.5)] if rows is None else rows
    all_rows = [row(0, "run_start", detail="fixed_seed", a=1337, b=.5, c=60, d=3)]
    all_rows += sorted(rows, key=lambda r: r["elapsed_s"])
    all_rows += [row(end, "run_end", detail="disconnect", movement_mode="ended")]
    return ("\n".join(json.dumps(dict(r, seq=i), allow_nan=False) for i, r in enumerate(all_rows)) + "\n").encode()


def embedded_data(html):
    match = re.search(r'<script id="capture-data" type="application/json">([\s\S]*?)</script>', html)
    return json.loads(match.group(1))


class ReplayExportTests(unittest.TestCase):
    def test_exclusive_export_exact_source_and_profile_hashes(self):
        raw = encode()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            self.assertTrue(Path(temp).resolve().is_relative_to(Path(__file__).resolve().parent))
            output = Path(temp) / "replay.html"
            metadata = export_replay(raw, output, profile_id=PROFILE, source_kind="synthetic-fixture")
            html = output.read_text(encoding="utf-8")
            model = embedded_data(html)
            self.assertEqual(metadata["source_sha256"], hashlib.sha256(raw).hexdigest())
            profile_raw = (prepare_v3.PROFILE_ROOT / (PROFILE + ".json")).read_bytes()
            self.assertEqual(model["profile_sha256"], hashlib.sha256(profile_raw).hexdigest())
            self.assertEqual(model["source_kind_operator_asserted"], "synthetic-fixture")
            self.assertEqual(model["authenticity"], "not_attested")
            with self.assertRaises(FileExistsError):
                export_replay(raw, output, profile_id=PROFILE)
            self.assertEqual(output.read_text(encoding="utf-8"), html)

    def test_explicit_profile_and_malformed_profile_rejected_before_output(self):
        raw = encode()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            self.assertTrue(Path(temp).resolve().is_relative_to(Path(__file__).resolve().parent))
            output = Path(temp) / "never.html"
            for bad in ("unknown", "survive-lucian-reference-v1"):
                with self.assertRaises(ValueError):
                    export_replay(raw, output, profile_id=bad)
                self.assertFalse(output.exists())
            malformed = {"schema": "survive-reference-profile-v1", "id": PROFILE,
                         "movement": {"walk_speed_cm_s": "fast"}}
            (Path(temp) / (PROFILE + ".json")).write_text(json.dumps(malformed))
            with patch.object(prepare_v3, "PROFILE_ROOT", Path(temp)):
                with self.assertRaises(ValueError):
                    export_replay(raw, output, profile_id=PROFILE)
            self.assertFalse(output.exists())

    def test_bounds_schema_and_operator_assertion_validation(self):
        for raw in (b"x" * (MAX_BYTES + 1), encode().replace(b'"seq": 1', b'"seq": 9', 1),
                    encode().replace(b'"seq": 1', b'"seq": 1, "truth": true', 1)):
            with self.assertRaises(ValueError):
                build_model(raw, profile_id=PROFILE)
        with self.assertRaises(ValueError):
            build_model(encode(), profile_id=PROFILE, source_kind="verified-authentic")

    def test_script_termination_payload_remains_inert_and_exact(self):
        hostile = '</script><img src=x onerror="alert(1)">&'
        raw = encode([row(0), row(.05, "command_request", detail=hostile), row(.1, x=20)])
        model = build_model(raw, profile_id=PROFILE)
        html = render_model(model)
        self.assertNotIn(hostile, html)
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertEqual(embedded_data(html)["rows"][2]["detail"], hostile)
        escaped = script_json({"text": "<>&\u2028\u2029"})
        self.assertEqual(json.loads(escaped), {"text": "<>&\u2028\u2029"})
        self.assertTrue(all(ch not in escaped for ch in "<>&\u2028\u2029"))

    def test_template_like_data_is_not_replaced(self):
        marker = "__SURVIVE_SCRIPT_SHA256__"
        model = build_model(encode([row(0), row(.05, "command_request", detail=marker), row(.1)]), profile_id=PROFILE)
        self.assertEqual(embedded_data(render_model(model))["rows"][2]["detail"], marker)

    def test_offline_csp_matches_exact_static_script_and_style(self):
        html = render_model(build_model(encode(), profile_id=PROFILE))
        self.assertIn("connect-src 'none'", html)
        self.assertIn("default-src 'none'", html)
        for kind, element_id in (("script", "replay-code"), ("style", "replay-style")):
            block = re.search('<' + kind + ' id="' + element_id + '">([\\s\\S]*?)</' + kind + '>', html).group(1)
            digest = base64.b64encode(hashlib.sha256(block.encode()).digest()).decode()
            self.assertIn("'sha256-" + digest + "'", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("fetch(", html)

    def test_blink_gap_and_unsupported_modes_are_not_interpolated(self):
        rows = [row(0), row(.1, x=10),
                row(.2, "ability_start", x=20, detail="blink", related_id="b1", movement_mode="blink"),
                row(.2, "ability_end", x=420, detail="blink", related_id="b1", movement_mode="blink"),
                row(.3, x=430), row(.6, x=450), row(.7, x=470, movement_mode="other")]
        model = build_model(encode(rows, end=.8), profile_id=PROFILE)
        points = model["points"]
        self.assertAlmostEqual(player_at(points, .05)["x"], 5)
        self.assertEqual(player_at(points, .199)["x"], 10)
        self.assertEqual(player_at(points, .2)["x"], 420)
        self.assertEqual(player_at(points, .25)["x"], 420)
        self.assertEqual(player_at(points, .45)["x"], 430)
        self.assertIn("unobserved gap", player_at(points, .45)["coverage"])
        self.assertEqual(player_at(points, .65)["x"], 450)
        self.assertIn("unsupported", player_at(points, .65)["coverage"])

    def test_projectile_uses_actual_fire_time_and_blocked_endpoint(self):
        threat = dict(detail="projectile_aimed", related_id="p1", a=0, b=0, c=70, d=1200,
                      source_x_cm=-900, velocity_x_cm_s=1200, baseline_threat="yes")
        rows = [row(0), row(.1), row(.2, "threat_warning", threat_x_cm=-900, **threat),
                row(.45, "threat_fire", threat_x_cm=-900, **threat),
                row(1, "threat_blocked", threat_x_cm=-500, **threat)]
        model = build_model(encode(rows, end=1.1), profile_id=PROFILE)
        flight = model["threats"][0]
        self.assertIsNone(projectile_at(flight, .4))
        self.assertAlmostEqual(projectile_at(flight, .55)[0], -780)
        self.assertAlmostEqual(projectile_at(flight, .9)[0], -500)
        self.assertEqual(flight["max_distance"], 400)


if __name__ == "__main__":
    unittest.main()

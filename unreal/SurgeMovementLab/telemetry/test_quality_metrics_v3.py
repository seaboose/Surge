"""Synthetic descriptive-quality checks; no engine, reaction-time or accuracy claim."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_v3 import summarize
from prepare_v3 import load_profile, load_rows
from test_v3 import row, nominal_capture


def capture(events, duration=2., completion="disconnect", monotonic_duration=None):
    records = [row(0, "run_start", a=1337, b=.5, c=60, d=3)]
    records += sorted(events, key=lambda r: r["elapsed_s"])
    records += [row(duration, "run_end", detail=completion, movement_mode="ended",
                    monotonic_s=duration if monotonic_duration is None else monotonic_duration)]
    return ("\n".join(json.dumps(dict(r, seq=i)) for i, r in enumerate(records)) + "\n").encode()


def circle(t, event, threat_id, **extra):
    return row(t, event, related_id=threat_id, detail="circle_aimed", c=250, d=.75,
               baseline_threat="yes", **extra)


class QualityMetricsTests(unittest.TestCase):
    def summarize(self, raw):
        profile = load_profile()
        return summarize(load_rows(raw, profile), profile)

    def test_complete_sampling_coverage_uses_observed_span(self):
        quality = self.summarize(nominal_capture())["run_quality"]
        self.assertTrue(quality["complete_round"])
        self.assertAlmostEqual(quality["observed_sample_hz_over_span"], 30.)
        self.assertAlmostEqual(quality["supported_sample_interval_s"], 60.)
        self.assertAlmostEqual(quality["supported_sample_interval_fraction"], 1.)
        self.assertEqual(quality["gap_over_150ms_s"], 0.)
        self.assertEqual(quality["leading_unsampled_s"], 0.)
        self.assertEqual(quality["trailing_unsampled_s"], 0.)

    def test_gap_partial_run_and_unsampled_tail_are_explicit(self):
        raw = capture([row(0), row(.1), row(.4), row(.5)], duration=1., completion="restart")
        quality = self.summarize(raw)["run_quality"]
        self.assertFalse(quality["complete_round"])
        self.assertAlmostEqual(quality["supported_sample_interval_s"], .2)
        self.assertAlmostEqual(quality["supported_sample_interval_fraction"], .2)
        self.assertAlmostEqual(quality["gap_over_150ms_s"], .3)
        self.assertAlmostEqual(quality["trailing_unsampled_s"], .5)
        self.assertAlmostEqual(quality["observed_sample_hz_over_span"], 6.)

    def test_no_samples_and_zero_monotonic_span_do_not_invent_coverage(self):
        raw = capture([row(.2, "command_stop", detail="stop", monotonic_s=0)], monotonic_duration=0)
        quality = self.summarize(raw)["run_quality"]
        self.assertEqual(quality["supported_sample_interval_fraction"], 0.)
        self.assertIsNone(quality["observed_sample_hz_over_span"])
        self.assertIsNone(quality["leading_unsampled_s"])
        self.assertIsNone(quality["trailing_unsampled_s"])
        self.assertIsNone(quality["simulation_per_monotonic_second"])
        self.assertIsNone(quality["sample_monotonic_interval_s"]["max"])

    def test_monotonic_cadence_is_separate_from_simulation_cadence(self):
        raw = capture([row(0), row(.1, monotonic_s=.2), row(.2, monotonic_s=.4)],
                      duration=.2, monotonic_duration=.4)
        quality = self.summarize(raw)["run_quality"]
        self.assertAlmostEqual(quality["simulation_per_monotonic_second"], .5)
        self.assertAlmostEqual(quality["sample_monotonic_interval_s"]["p50"], .2)

    def test_overlapping_warnings_share_a_command_without_causal_assignment(self):
        raw = capture([row(.35), row(.45, x=16.75),
                       circle(.5, "threat_warning", "a", x=33.5),
                       circle(.6, "threat_warning", "b", x=67),
                       row(.7, "command_grant", detail="move", x=100.5),
                       circle(1., "threat_cancelled", "a"),
                       circle(1.1, "threat_cancelled", "b")])
        a, b = [r["command_after_warning"] for r in self.summarize(raw)["threats"]]
        self.assertAlmostEqual(a["latency_simulation_s"], .2)
        self.assertAlmostEqual(b["latency_simulation_s"], .1)
        self.assertEqual(a["command_seq"], b["command_seq"])
        self.assertEqual(a["other_active_threats_at_warning"], 0)
        self.assertEqual(b["other_active_threats_at_warning"], 1)
        self.assertEqual(a["other_active_threats_at_command"], 1)
        self.assertEqual(b["other_active_threats_at_command"], 1)
        self.assertEqual(a["prewarning_motion"]["status"], "observed_displacement")
        self.assertAlmostEqual(a["prewarning_motion"]["displacement_cm"], 16.75)

    def test_denied_stopped_or_after_terminal_commands_do_not_count(self):
        raw = capture([row(.4), circle(.5, "threat_warning", "a"),
                       row(.6, "command_denied", detail="unreachable"), row(.7, "command_stop", detail="stop"),
                       circle(.8, "threat_cancelled", "a"), row(.9, "command_grant", detail="move")])
        command = self.summarize(raw)["threats"][0]["command_after_warning"]
        self.assertEqual(command["status"], "none_before_threat_terminal")
        self.assertIsNone(command["latency_simulation_s"])
        self.assertEqual(command["prewarning_motion"]["status"], "no_observed_displacement")

    def test_same_timestamp_uses_record_order_and_capture_end_censors_absence(self):
        raw = capture([row(.4), row(.5, "command_grant", detail="move"),
                       circle(.5, "threat_warning", "a")], completion="disconnect")
        command = self.summarize(raw)["threats"][0]["command_after_warning"]
        self.assertEqual(command["status"], "none_before_capture_end")
        self.assertIsNone(command["command_seq"])
        raw = capture([row(.4), circle(.5, "threat_warning", "a"),
                       row(.5, "command_grant", detail="move"), circle(.8, "threat_cancelled", "a")])
        command = self.summarize(raw)["threats"][0]["command_after_warning"]
        self.assertEqual(command["status"], "observed")
        self.assertEqual(command["latency_simulation_s"], 0.)

    def test_motion_context_excludes_gap_and_blink_discontinuity(self):
        for events in ([row(.1), circle(.5, "threat_warning", "a")],
                       [row(.4), row(.45, "ability_start", detail="blink", related_id="b", movement_mode="blink"),
                        row(.45, "ability_end", detail="blink", related_id="b", x=100),
                        circle(.5, "threat_warning", "a", x=100)]):
            raw = capture(events + [circle(.8, "threat_cancelled", "a")])
            motion = self.summarize(raw)["threats"][0]["command_after_warning"]["prewarning_motion"]
            self.assertEqual(motion["status"], "unavailable")
            self.assertIsNone(motion["displacement_cm"])

    def test_accepted_dash_or_blink_is_visible_before_the_next_move_command(self):
        for kind in ("dash", "blink"):
            with self.subTest(kind=kind):
                end = .8 if kind == "dash" else .6
                raw = capture([row(.4), circle(.5, "threat_warning", "a"),
                               row(.55, "ability_denied", detail=kind + ":cooldown", related_id="denied"),
                               row(.6, "ability_grant", detail=kind, related_id="accepted"),
                               row(.6, "ability_start", detail=kind, related_id="accepted", movement_mode=kind),
                               row(end, "ability_end", detail=kind, related_id="accepted"),
                               row(.85, "command_stop", detail="stop"),
                               row(.9, "command_grant", detail="move"), circle(1.2, "threat_cancelled", "a")])
                threat = self.summarize(raw)["threats"][0]
                action = threat["action_after_warning"]
                self.assertEqual(action["action_kind"], kind)
                self.assertEqual(action["action_event"], "ability_grant")
                self.assertAlmostEqual(action["latency_simulation_s"], .1)
                self.assertAlmostEqual(threat["command_after_warning"]["latency_simulation_s"], .4)
                self.assertEqual(action["other_active_threats_at_action"], 0)
                self.assertLess(action["action_seq"], threat["command_after_warning"]["command_seq"])

    def test_stop_is_an_action_and_actions_after_terminal_are_censored(self):
        raw = capture([row(.4), row(.5, "command_stop", detail="stop"),
                       circle(.5, "threat_warning", "a"), row(.6, "command_stop", detail="stop"),
                       row(.7, "command_grant", detail="move"), circle(.8, "threat_cancelled", "a")])
        action = self.summarize(raw)["threats"][0]["action_after_warning"]
        self.assertEqual(action["action_kind"], "stop")
        self.assertAlmostEqual(action["latency_simulation_s"], .1)
        raw = capture([row(.4), circle(.5, "threat_warning", "a"),
                       row(.6, "ability_denied", detail="dash:cooldown", related_id="d"),
                       circle(.8, "threat_cancelled", "a"), row(.9, "command_stop", detail="stop")])
        action = self.summarize(raw)["threats"][0]["action_after_warning"]
        self.assertEqual(action["status"], "none_before_threat_terminal")
        self.assertIsNone(action["latency_simulation_s"])
        self.assertIsNone(action["action_kind"])


if __name__ == "__main__":
    unittest.main()

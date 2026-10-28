"""Independent geometric checks of descriptive budgets, never detector rules."""
import math
import unittest

from audit_v3 import summarize
from prepare_v3 import load_profile, load_rows
from test_v3 import encode, row


class OpportunityModelTests(unittest.TestCase):
    def summary(self, *, distance=900, lateral=0, pattern="projectile_aimed", fire_delay=.25):
        common = dict(detail=pattern, related_id="p1", a=0, b=0, c=70, d=1200,
                      source_x_cm=-distance, velocity_x_cm_s=1200, baseline_threat="unknown")
        raw = encode([row(.5, "threat_warning", y=lateral, threat_x_cm=-distance, **common),
                      row(.5 + fire_delay, "threat_fire", y=lateral, threat_x_cm=-distance, **common),
                      row(.5 + fire_delay + 1300 / 1200, "threat_expired", y=lateral,
                          threat_x_cm=1300 - distance, **common)])
        profile = load_profile()
        return summarize(load_rows(raw, profile), profile)

    def test_best_heading_is_tangent_and_differs_from_perpendicular(self):
        summary = self.summary()
        threat = summary["threats"][0]
        budget = threat["nominal_centered_best_heading_budget_s"]
        theta = math.radians(threat["nominal_best_heading_degrees_from_projectile_forward"])
        self.assertAlmostEqual(budget, .5970149253731343)
        self.assertAlmostEqual(math.degrees(theta), 73.789524923099)
        # Independent relative-motion closest approach after starting at budget.
        def closest_distance(start):
            relative = (900 - 1200 * (start - .25), 0.)
            velocity = (335 * math.cos(theta) - 1200, 335 * math.sin(theta))
            tau = -sum(a * b for a, b in zip(relative, velocity)) / sum(v * v for v in velocity)
            self.assertGreater(tau, 0)
            self.assertLessEqual(1200 * (start + tau - .25), 1300)
            return math.hypot(*(a + tau * b for a, b in zip(relative, velocity)))
        self.assertAlmostEqual(closest_distance(budget), 135)
        self.assertGreater(closest_distance(budget - .001), 135)
        self.assertLess(closest_distance(budget + .001), 135)
        perpendicular = .25 + 900 / 1200 - 135 * math.sqrt(1 / 335 ** 2 + 1 / 1200 ** 2)
        self.assertAlmostEqual(budget - perpendicular, .015408543188331625)
        self.assertEqual(summary["schema"], "survive-run-summary-v2")
        self.assertEqual(summary["opportunity_model_version"], "nominal-walk-v2")
        self.assertEqual(threat["ideal_centered_perpendicular_window_s"], budget)
        self.assertEqual(summary["legacy_opportunity_field_aliases"]["ideal_centered_perpendicular_window_s"],
                         "nominal_centered_best_heading_budget_s")

    def test_noncentered_random_unexposed_and_endcap_models_are_unavailable(self):
        cases = [dict(lateral=1), dict(pattern="projectile_random"), dict(lateral=200), dict(distance=1350)]
        for case in cases:
            with self.subTest(case=case):
                threat = self.summary(**case)["threats"][0]
                self.assertIsNone(threat["nominal_centered_best_heading_budget_s"])
                self.assertIsNone(threat["nominal_walking_escape_possible_without_terrain"])
                self.assertIsNone(threat["nominal_best_heading_degrees_from_projectile_forward"])
                self.assertTrue(threat["nominal_model_unavailable_reason"])
        # The endcap can expose the player even though the formula is unavailable.
        self.assertTrue(self.summary(distance=1350)["threats"][0]["geometric_initial_threat_without_terrain"])

    def test_projectile_budget_uses_nominal_delay_not_observed_late_fire(self):
        threat = self.summary(fire_delay=.5)["threats"][0]
        self.assertEqual(threat["nominal_warning_delay_s"], .25)
        self.assertEqual(threat["observed_warning_to_fire_s"], .5)
        self.assertAlmostEqual(threat["nominal_centered_best_heading_budget_s"], .5970149253731343)

    def circle(self, x=0):
        common = dict(detail="circle_aimed", related_id="c1", a=0, b=0, c=250, d=.75,
                      baseline_threat="unknown")
        raw = encode([row(1, "threat_warning", x=x, **common), row(2, "threat_fire", x=x, **common),
                      row(2, "threat_expired", x=x, **common)])
        profile = load_profile()
        return summarize(load_rows(raw, profile), profile)["threats"][0]

    def test_centered_circle_has_negative_nominal_budget_despite_late_fire(self):
        threat = self.circle()
        self.assertAlmostEqual(threat["nominal_circle_walk_delay_budget_s"], .75 - 315 / 335)
        self.assertFalse(threat["nominal_walking_escape_possible_without_terrain"])
        self.assertEqual(threat["nominal_warning_delay_s"], .75)
        self.assertEqual(threat["observed_warning_to_fire_s"], 1)
        self.assertIsNone(threat["nominal_model_unavailable_reason"])

    def test_unexposed_circle_does_not_become_an_escape_opportunity(self):
        threat = self.circle(x=400)
        self.assertFalse(threat["geometric_initial_threat_without_terrain"])
        self.assertEqual(threat["minimum_circle_escape_cm"], 0)
        self.assertIsNone(threat["nominal_circle_walk_delay_budget_s"])
        self.assertIsNone(threat["nominal_walking_escape_possible_without_terrain"])
        self.assertTrue(threat["nominal_model_unavailable_reason"])


if __name__ == "__main__":
    unittest.main()

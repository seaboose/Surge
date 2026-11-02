"""Independent threshold-refinement checks; synthetic inputs, no holdout reads."""

import json
import math
import unittest

import engine
import evaluation
from desktop_worker import Workspace


def data(rows, name):
    return engine.parse_bytes(json.dumps(rows).encode(), name)


class ThresholdRefinementSecurityTests(unittest.TestCase):
    def setUp(self):
        self.reference = data([dict(kind="a", x=x, y=10) for x in [-1, 0, 1] * 7], "reference.json")
        self.config = dict(
            features=["x", "y"],
            reference_by=["kind"],
            event_id=None,
            session=None,
            time=None,
            time_format="milliseconds",
            threshold=1.5,
            rules=[],
        )

    def test_increasing_threshold_only_removes_numeric_flags_and_rules_still_fire(self):
        current = data(
            [
                dict(kind="a", x=1.6 * 1.4826, y=10, rule_value="hit"),
                dict(kind="a", x=2 * 1.4826, y=10, rule_value="miss"),
                dict(kind="a", x=-2 * 1.4826, y=10, rule_value="miss"),
                dict(kind="a", x=0, y=10, rule_value="miss"),
            ],
            "current.json",
        )
        config = dict(
            self.config,
            rules=[dict(name="Explicit signal", field="rule_value", op="eq", value="hit")],
        )
        before = engine.analyze(current, self.reference, config)
        after = engine.analyze(current, self.reference, dict(config, threshold=1.8))
        self.assertEqual(
            [r["status"] for r in after["records"]], ["Review", "Review", "Review", "No finding"]
        )
        self.assertEqual([e["kind"] for e in after["records"][0]["evidence"]], ["rule"])
        self.assertEqual(before["profiles"], after["profiles"])
        self.assertEqual(before["group_profiles"], after["group_profiles"])
        for old, new in zip(before["records"], after["records"]):
            self.assertEqual(old["scores"], new["scores"])
            self.assertLessEqual(
                {e["field"] for e in new["evidence"] if e["kind"] == "deviation"},
                {e["field"] for e in old["evidence"] if e["kind"] == "deviation"},
            )

    def test_raised_threshold_never_turns_missing_evidence_into_clear(self):
        current = data(
            [
                dict(kind="a", x=1.6 * 1.4826, y=None),
                dict(kind="unknown", x=0, y=10),
                dict(kind="a", x=None, y=10),
            ],
            "gaps.json",
        )
        before = engine.analyze(current, self.reference, self.config)
        after = engine.analyze(current, self.reference, dict(self.config, threshold=1.8))
        self.assertEqual(before["records"][0]["status"], "Review")
        self.assertEqual([r["status"] for r in after["records"]], ["Unknown"] * 3)
        self.assertTrue(all(r["gaps"] for r in after["records"]))
        labels = evaluation.template(current)
        labels["provenance"].update(
            author="Security fixture",
            method="Synthetic known truth",
            partition="Synthetic",
            purpose="synthetic",
        )
        for label in labels["labels"]:
            label.update(
                truth="target" if label["row"] == 1 else "legitimate",
                group="fixture",
                note="Synthetic check",
            )
        report = evaluation.evaluate(
            current,
            self.reference,
            dict(self.config, threshold=1.8),
            after,
            dict(document=labels, file=dict(name="synthetic.labels.json", sha256="synthetic")),
        )
        self.assertEqual(report["summary"]["counts"]["Missed"], 1)
        self.assertEqual(report["summary"]["counts"]["Unresolved"], 2)

    def test_worker_preserves_float_boundary_and_rejects_nonfinite_policy(self):
        # Decimal multiplication rounds just below the score boundary here;
        # its next representable float is above. Never round scores for decisions.
        boundary = 1.8 * 1.4826
        current = data(
            [
                dict(kind="a", x=math.nextafter(boundary, math.inf), y=10),
                dict(kind="a", x=boundary, y=10),
            ],
            "boundary.json",
        )
        ws = Workspace()
        ws.current = current
        ws.reference = self.reference
        ws.dispatch(
            "configure",
            dict(revision=ws.revision, config=dict(self.config, threshold="1.8"), rules_text="[]"),
        )
        ws.dispatch("analyze", dict(revision=ws.revision))
        self.assertEqual([r["status"] for r in ws.result["records"]], ["Review", "No finding"])
        self.assertEqual(ws.result["records"][0]["evidence"][0]["threshold"], 1.8)
        evidence = ws.dispatch("evidence", dict(revision=ws.revision, row=1))
        self.assertIn("Review at: 1.8", evidence["groups"][0]["lines"][0]["text"])
        for threshold in [math.nan, math.inf, -math.inf, True, 0, 101]:
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                engine.validate_config(
                    dict(self.config, threshold=threshold), current, self.reference
                )


if __name__ == "__main__":
    unittest.main()

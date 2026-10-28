"""Generic policy regression checks independent of benchmark test labels."""

import json
from pathlib import Path
import tempfile
import unittest
import engine
import workflow


def data(rows, name="source.json"):
    return engine.parse_bytes(json.dumps(rows).encode(), name)


class PolicyRefinementTests(unittest.TestCase):
    def setUp(self):
        self.reference = data(
            [dict(kind="a", value=x, noise=x) for x in [8, 9, 10, 11, 12] * 4], "ref.json"
        )
        self.source = data(
            [
                dict(kind="a", value=12.5, noise=10),
                dict(kind="a", value=10, noise=100),
                dict(kind="a", value=100, noise=10),
            ]
        )
        self.old = dict(
            features=["value", "noise"],
            reference_by=["kind"],
            event_id=None,
            session=None,
            time=None,
            time_format="milliseconds",
            threshold=2,
            rules=[],
        )
        self.new = dict(self.old, features=["value"], threshold=1.5)

    def test_fractional_threshold_and_selected_signals_have_exact_evidence(self):
        before = engine.analyze(self.source, self.reference, self.old)
        after = engine.analyze(self.source, self.reference, self.new)
        self.assertEqual(
            [r["status"] for r in before["records"]], ["No finding", "Review", "Review"]
        )
        self.assertEqual(
            [r["status"] for r in after["records"]], ["Review", "No finding", "Review"]
        )
        self.assertEqual(after["records"][0]["evidence"][0]["threshold"], 1.5)
        self.assertAlmostEqual(after["records"][0]["scores"]["value"], 2.5 / 1.4826)
        self.assertNotIn("noise", after["records"][1]["scores"])
        self.assertNotIn("noise", after["group_profiles"]['["a"]']["profiles"])

    def test_selected_missing_value_and_unseen_group_remain_unknown(self):
        source = data([dict(kind="a", value=None, noise=10), dict(kind="new", value=10, noise=10)])
        result = engine.analyze(source, self.reference, self.new)
        self.assertEqual([r["status"] for r in result["records"]], ["Unknown", "Unknown"])
        self.assertTrue(all(r["gaps"] for r in result["records"]))

    def test_policy_and_case_preserve_fractional_threshold_and_old_case(self):
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).parent / "verification/temporary-test-files"
        ) as folder:
            root = Path(folder)
            workflow.save_policy(root / "policy.json", self.source, self.reference, self.new)
            self.assertEqual(
                workflow.load_policy(root / "policy.json", self.source, self.reference), self.new
            )
            for label, config in [("old", self.old), ("new", self.new)]:
                result = engine.analyze(self.source, self.reference, config)
                engine.save_case(
                    root / f"{label}.json", self.source, self.reference, config, result
                )
                self.assertEqual(
                    engine.open_case(root / f"{label}.json"),
                    (self.source, self.reference, config, result),
                )

    def test_rules_remain_independent_of_removed_numeric_signal(self):
        config = dict(
            self.new, rules=[dict(name="Explicit condition", field="noise", op="gt", value=50)]
        )
        result = engine.analyze(self.source, self.reference, config)
        record = result["records"][1]
        self.assertEqual(record["status"], "Review")
        self.assertEqual(record["evidence"][0]["kind"], "rule")
        self.assertEqual(record["evidence"][0]["field"], "noise")


if __name__ == "__main__":
    unittest.main()

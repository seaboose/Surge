"""Synthetic checks of holdout acceptance; never open actual holdout inputs."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluation
from evaluate_refinement2 import compare_reports


def report(outcomes):
    records = []
    for i, (truth, outcome) in enumerate(outcomes, 1):
        status = (
            "Unknown"
            if outcome == "Unresolved"
            else "Review" if outcome in ("Detected", "False positive") else "Clear"
        )
        records.append(dict(row=i, truth=truth, outcome=outcome, status=status))
    return dict(records=records, groups=[], summary=evaluation.summarize(records))


def compare(old, new):
    source = [dict(flow_duration="10") for _ in old]
    labels = dict(labels=[dict(truth=t) for t, _ in old])
    return compare_reports(report(old), report(new), source, labels, 5)


class HoldoutAcceptanceTests(unittest.TestCase):
    def test_rejects_detection_swap_even_if_aggregate_misses_unchanged(self):
        old = [("legitimate", "False positive"), ("target", "Detected"), ("target", "Missed")]
        new = [("legitimate", "Clear"), ("target", "Missed"), ("target", "Detected")]
        result = compare(old, new)
        self.assertFalse(result["accepted"])
        self.assertTrue(result["gates"]["misses_not_higher"])
        self.assertEqual(result["new_misses"], [2])

    def test_rejects_false_positive_reduction_from_abstention(self):
        result = compare([("legitimate", "False positive")], [("legitimate", "Unresolved")])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["resolved_false_positives"], [])
        self.assertEqual(result["unknown_counts"]["candidate"], 1)

    def test_accepts_clear_improvement_and_counts_edge_cases(self):
        result = compare(
            [("legitimate", "False positive"), ("target", "Detected")],
            [("legitimate", "Clear"), ("target", "Detected")],
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["long_duration"]["baseline"]["false_positives"], 1)
        self.assertEqual(result["long_duration"]["candidate"]["false_positives"], 0)

    def test_rejects_unchanged_false_positive_count(self):
        same = [("legitimate", "False positive"), ("target", "Detected")]
        self.assertFalse(compare(same, same)["accepted"])

    def test_rejects_unpaired_truth_or_source_rows(self):
        with self.assertRaisesRegex(ValueError, "same records"):
            compare([("legitimate", "False positive")], [("target", "Detected")])


if __name__ == "__main__":
    unittest.main()

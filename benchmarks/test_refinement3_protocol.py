"""Synthetic acceptance and replay checks; no holdout records or labels read."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluation
import evaluate_refinement3 as protocol
from prepare_refinement3 import PRIOR
from prepare_rt_iot2022 import sha


def report(outcomes):
    records = []
    for i, (group, truth, outcome) in enumerate(outcomes, 1):
        status = (
            "Unknown"
            if outcome == "Unresolved"
            else "Review" if outcome in ("Detected", "False positive") else "No finding"
        )
        records.append(dict(row=i, group=group, truth=truth, outcome=outcome, status=status))
    names = sorted({r["group"] for r in records})
    return dict(
        records=records,
        summary=evaluation.summarize(records),
        groups=[
            dict(group=g, **evaluation.summarize([r for r in records if r["group"] == g]))
            for g in names
        ],
    )


def compare(old, new):
    source = [dict(flow_duration="10") for _ in old]
    labels = dict(labels=[dict(truth=t) for _, t, _ in old])
    return protocol.compare_reports(report(old), report(new), source, labels, 5)


T = "Thing_Speak"
L = "legitimate"


class SubgroupAcceptanceTests(unittest.TestCase):
    def test_accepts_targeted_reduction_and_unchanged_detections(self):
        result = compare(
            [(T, L, "False positive"), ("attack", "target", "Detected")],
            [(T, L, "Clear"), ("attack", "target", "Detected")],
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["long_duration"]["baseline"]["false_positives"], 1)
        self.assertEqual(result["resolved_false_positives"], [1])

    def test_rejects_missing_targeted_group(self):
        result = compare([("other", L, "False positive")], [("other", L, "Clear")])
        self.assertFalse(result["accepted"])
        self.assertFalse(result["gates"]["targeted_subgroup_present"])

    def test_rejects_overall_reduction_without_targeted_reduction(self):
        old = [(T, L, "False positive"), ("other", L, "False positive")]
        new = [(T, L, "False positive"), ("other", L, "Clear")]
        result = compare(old, new)
        self.assertTrue(result["gates"]["false_positives_lower"])
        self.assertFalse(result["gates"]["targeted_subgroup_false_positives_lower"])
        self.assertFalse(result["accepted"])

    def test_rejects_any_legitimate_subgroup_false_positive_regression(self):
        old = [(T, L, "False positive"), (T, L, "False positive"), ("other", L, "Clear")]
        new = [(T, L, "Clear"), (T, L, "Clear"), ("other", L, "False positive")]
        result = compare(old, new)
        self.assertTrue(result["gates"]["false_positives_lower"])
        self.assertFalse(result["gates"]["no_legitimate_subgroup_false_positive_regression"])
        self.assertFalse(result["accepted"])

    def test_rejects_moving_unknown_to_another_group_even_if_total_unchanged(self):
        old = [(T, L, "False positive"), (T, L, "Unresolved"), ("other", L, "Clear")]
        new = [(T, L, "Clear"), (T, L, "Clear"), ("other", L, "Unresolved")]
        result = compare(old, new)
        self.assertTrue(result["gates"]["legitimate_unresolved_not_higher"])
        self.assertFalse(result["gates"]["no_legitimate_subgroup_unresolved_regression"])
        self.assertFalse(result["accepted"])

    def test_rejects_detection_swap_with_same_total_misses(self):
        old = [
            (T, L, "False positive"),
            ("attack", "target", "Detected"),
            ("attack", "target", "Missed"),
        ]
        new = [(T, L, "Clear"), ("attack", "target", "Missed"), ("attack", "target", "Detected")]
        result = compare(old, new)
        self.assertTrue(result["gates"]["misses_not_higher"])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["new_misses"], [2])

    def test_rejects_abstention_as_false_positive_improvement(self):
        result = compare([(T, L, "False positive")], [(T, L, "Unresolved")])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["resolved_false_positives"], [])

    def test_rejects_unpaired_truth_and_group_denominators(self):
        with self.assertRaisesRegex(ValueError, "same records"):
            compare([(T, L, "False positive")], [(T, "target", "Detected")])
        old = report([(T, L, "False positive")])
        new = report([(T, L, "Clear")])
        new["groups"][0]["legitimate"] = 2
        with self.assertRaisesRegex(ValueError, "denominators"):
            protocol.compare_reports(
                old, new, [dict(flow_duration="10")], dict(labels=[dict(truth=L)]), 5
            )

    def test_previous_holdout_is_excluded(self):
        self.assertIn("refinement-2/holdout.json", PRIOR)
        self.assertIn("refinement-1/holdout.json", PRIOR)
        self.assertIn("refinement-1/development.json", PRIOR)

    def test_changed_development_labels_rejected(self):
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1] / "verification/temporary-test-files"
        ) as folder:
            root = Path(folder)
            out = root / "out"
            out.mkdir()
            (root / "refinement-1").mkdir()
            (root / "source.zip").write_bytes(b"synthetic archive")
            (root / "refinement-1/development.labels.json").write_bytes(b"changed")
            plan = dict(
                prior_files={},
                baseline_files={},
                archive_sha256=sha(b"synthetic archive"),
                development_labels_sha256=sha(b"original"),
            )
            (out / "plan.json").write_text(json.dumps(plan))
            with (
                patch.object(protocol, "ROOT", root),
                patch.object(protocol, "OUT", out),
                patch.object(protocol, "PLAN_SHA", sha((out / "plan.json").read_bytes())),
            ):
                with self.assertRaisesRegex(ValueError, "Development labels changed"):
                    protocol.verify_plan()

    def test_mismatched_candidate_rejected_before_snapshot(self):
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1] / "verification/temporary-test-files"
        ) as folder:
            root = Path(folder)
            out = root / "out"
            out.mkdir()
            (root / "verification").mkdir()
            (out / "candidate.policy.json").write_text(
                json.dumps(dict(schema="surge-policy-v1", settings={"threshold": 1.8}))
            )
            (out / "development-selection.json").write_text(
                json.dumps(dict(policy_sha256="different", selected={"threshold": 1.8}))
            )
            (root / "verification/refinement3-security-review.json").write_text("{}")
            with (
                patch.object(protocol, "APP", root),
                patch.object(protocol, "OUT", out),
                patch.object(protocol, "verify_plan", return_value={}),
            ):
                with self.assertRaisesRegex(ValueError, "differs from development selection"):
                    protocol.freeze()
            self.assertFalse((out / "candidate-source").exists())

    def test_spent_holdout_rejected_before_selection(self):
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1] / "verification/temporary-test-files"
        ) as folder:
            root = Path(folder)
            (root / "freeze.json").write_text("{}")
            (root / "holdout-opened.json").write_text('{"spent":true}')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with (
                patch.object(protocol, "OUT", root),
                patch.object(
                    protocol,
                    "verify_freeze",
                    return_value=({}, dict(candidate_policy_sha256="synthetic")),
                ),
                patch.object(protocol, "selection") as selected,
            ):
                with self.assertRaises(FileExistsError):
                    protocol.evaluate()
                selected.assert_not_called()
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})


if __name__ == "__main__":
    unittest.main()

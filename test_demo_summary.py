"""Fail-closed wording for inspected demo observations; synthetic rows only."""

import copy
import unittest
from desktop_worker import demo_summary


class DemoSummaryTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            dict(
                memory_status="complete",
                baseline_approved=True,
                memory_matches=True,
                protection_matches=True,
                module_sha256="owned",
                range_name=name,
                range_rva=i,
            )
            for i, name in enumerate(("one", "two"))
        ]
        self.summary = {"No finding": 2, "Review": 0, "Unknown": 0, "rows_with_gaps": 0}

    def test_complete_matching_evidence(self):
        self.assertEqual(
            demo_summary(self.rows, self.summary),
            dict(expected=True, ranges=2, review=0, unknown=0),
        )

    def test_missing_unapproved_changed_or_unreadable_evidence(self):
        for key, value in (
            ("baseline_approved", False),
            ("memory_matches", False),
            ("protection_matches", False),
            ("memory_matches", None),
            ("memory_status", "unreadable"),
        ):
            with self.subTest(key=key, value=value):
                rows = copy.deepcopy(self.rows)
                rows[0][key] = value
                self.assertFalse(demo_summary(rows, self.summary)["expected"])

    def test_health_gaps_and_non_normal_results_block_success(self):
        self.assertFalse(
            demo_summary([*self.rows, {"stream_health": True}], self.summary)["expected"]
        )
        for key in ("Review", "Unknown", "rows_with_gaps"):
            self.assertFalse(demo_summary(self.rows, {**self.summary, key: 1})["expected"])

    def test_empty_or_inconsistent_summary_cannot_succeed(self):
        self.assertFalse(demo_summary([], self.summary)["expected"])
        self.assertFalse(demo_summary(self.rows, {})["expected"])
        self.assertFalse(demo_summary(self.rows, {**self.summary, "No finding": 1})["expected"])

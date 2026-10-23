import unittest
from desktop_worker import observation_counts, native_observation_explanation
from native_integrity import SCHEMA


class CountTests(unittest.TestCase):
    def test_counts_rows_not_ranges_times_latest_sequence(self):
        rows = [dict(session_id="a", stream_sequence=n) for n in (8, 8, 12, 12)]
        self.assertEqual(
            observation_counts(rows),
            dict(samples=2, observations=4, notices=0, ranges_per_sample=2),
        )

    def test_mixed_samples_sessions_and_health_are_explicit(self):
        rows = [
            dict(session_id="a", stream_sequence=1),
            dict(session_id="b", stream_sequence=1),
            dict(session_id="b", stream_sequence=1),
            dict(stream_health=True),
        ]
        self.assertEqual(
            observation_counts(rows),
            dict(samples=2, observations=3, notices=1, ranges_per_sample=None),
        )

    def test_no_stream_counts_are_invented(self):
        for rows in ([], [dict(stream_health=True)], [dict(phase="before")]):
            self.assertIsNone(observation_counts(rows))


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(
            schema=SCHEMA,
            memory_status="complete",
            baseline_approved=True,
            memory_matches=True,
            protection_matches=True,
        )

    def test_match_and_rule_review_are_both_explained(self):
        text = native_observation_explanation(self.row, "Review")
        self.assertIn("matched its recorded approved reference", text)
        self.assertIn("flags this record for review", text)

    def test_nonmatching_states_never_claim_match(self):
        for fields, expected in (
            (dict(memory_status="failed"), "could not be read"),
            (dict(baseline_approved=False), "no recorded approved reference"),
            (dict(memory_matches=False), "code differed"),
            (dict(protection_matches=False), "page protection differed"),
            (dict(memory_matches=None), "does not establish"),
            (dict(stream_health=True), "not a code-range observation"),
        ):
            with self.subTest(fields=fields):
                text = native_observation_explanation(dict(self.row, **fields), "Unknown")
                self.assertIn(expected, text)
                self.assertNotIn("matched its recorded", text)

    def test_collection_limits_and_generic_records(self):
        self.assertIn(
            "missing or incomplete",
            native_observation_explanation(dict(self.row, stream_final_dropped=1), "No finding"),
        )
        self.assertIsNone(native_observation_explanation(dict(reading=2), "No finding"))


if __name__ == "__main__":
    unittest.main()

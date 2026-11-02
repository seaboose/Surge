import unittest
from desktop_findings import short_reason
from native_integrity import SCHEMA


class NativeReasonTests(unittest.TestCase):
    def setUp(self):
        self.record = dict(status="No finding", gaps=[], evidence=[])
        self.raw = dict(
            schema=SCHEMA,
            memory_status="complete",
            baseline_approved=True,
            memory_matches=True,
            protection_matches=True,
        )

    def test_success_requires_complete_approved_match(self):
        self.assertEqual(
            short_reason(self.record, self.raw), "Matched approved reference"
        )
        for fields in (
            dict(memory_status="failed"),
            dict(baseline_approved=False),
            dict(memory_matches=False),
            dict(protection_matches=False),
            dict(memory_matches=None),
            dict(stream_health=True),
        ):
            with self.subTest(fields=fields):
                self.assertNotIn(
                    "matched approved", short_reason(self.record, dict(self.raw, **fields)).lower()
                )

    def test_custom_rules_and_gaps_keep_precedence(self):
        record = dict(
            self.record,
            status="Review",
            evidence=[dict(kind="rule", name="Custom", field="memory_status", operator="eq")],
        )
        self.assertEqual(short_reason(record, self.raw), "memory_status matches rule")
        self.assertEqual(
            short_reason(dict(self.record, gaps=["missing"]), self.raw), "Input needs attention"
        )
        self.assertEqual(
            short_reason(dict(self.record, status="Unknown"), self.raw), "Comparison inconclusive"
        )

    def test_generic_data_keeps_generic_explanation(self):
        self.assertEqual(
            short_reason(self.record, dict(value=1)), "No configured condition matched"
        )


if __name__ == "__main__":
    unittest.main()

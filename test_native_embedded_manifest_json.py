"""Embedded declarations use the same unambiguous JSON policy as outer evidence."""
import copy
import json
import unittest

import engine
import native_integrity as native
from test_native_manifest_security import versioned_capture


class EmbeddedManifestJsonTests(unittest.TestCase):
    def setUp(self):
        capture = versioned_capture()
        registry = native.approve(capture, dict(schema=native.BASELINE_SCHEMA, entries=[]),
                                   "Owned duplicate-key regression fixture")
        self.rows = native.convert(capture, registry)

    def analyze(self, rows, fmt):
        raw = (engine.canonical(rows) if fmt == "json" else
               "\n".join(engine.canonical(row) for row in rows) + "\n").encode()
        data = engine.parse_bytes(raw, "fixture." + fmt)
        return engine.analyze(data, None, native.default_policy(data))

    def test_valid_manifest_json_remains_accepted_in_both_encodings(self):
        for fmt in ("json", "jsonl"):
            with self.subTest(fmt=fmt):
                self.assertEqual(self.analyze(self.rows, fmt)["summary"]["No finding"], 6)

    def test_duplicate_integrity_manifest_keys_are_rejected(self):
        for first in ("surge-integrity-manifest-v1", "contradictory-schema"):
            rows = copy.deepcopy(self.rows)
            for row in rows:
                row["integrity_manifest"] = ('{"schema":' + json.dumps(first) + ','
                                             + row["integrity_manifest"][1:])
            for fmt in ("json", "jsonl"):
                with self.subTest(first=first, fmt=fmt), self.assertRaises(ValueError):
                    self.analyze(rows, fmt)

    def test_duplicate_range_manifest_keys_are_rejected(self):
        name = json.loads(self.rows[0]["range_manifest"])[0]["range_name"]
        for first in (name, "ContradictoryRange"):
            rows = copy.deepcopy(self.rows)
            for row in rows:
                row["range_manifest"] = ('[{"range_name":' + json.dumps(first) + ','
                                         + row["range_manifest"][2:])
            for fmt in ("json", "jsonl"):
                with self.subTest(first=first, fmt=fmt), self.assertRaises(ValueError):
                    self.analyze(rows, fmt)


if __name__ == "__main__":
    unittest.main()

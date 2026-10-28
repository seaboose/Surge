"""Focused end-to-end check for the paired synthetic replay showcase."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_showcase import LOCAL, PROFILE, create_showcase
from prepare_v3 import load_profile, load_rows


class ShowcaseTests(unittest.TestCase):
    def test_paired_showcase_preserves_unknowns_and_is_replayable(self):
        LOCAL.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=LOCAL) as parent:
            output = Path(parent) / "paired"
            receipt = create_showcase(output)
            self.assertTrue(receipt["not_unreal_evidence"])
            legal, changed = receipt["cases"]
            self.assertNotIn("Review", legal["counts"])
            self.assertGreater(legal["counts"]["Unknown"], 0)
            self.assertEqual(changed["counts"]["Review"], 3)
            for item in receipt["cases"]:
                self.assertEqual(item["audit_issues"], [])
                self.assertTrue(item["reopen_matches"])
                directory = output / item["scenario"]
                rows = load_rows((directory / "source.jsonl").read_bytes(), load_profile(PROFILE))
                self.assertEqual(sum(r["event"] == "sample" for r in rows), 1801)
                self.assertEqual(sum(r["event"] == "ability_start" and r["detail"] == "dash" for r in rows), 5)
                self.assertEqual(sum(r["event"] == "ability_start" and r["detail"] == "blink" for r in rows), 3)
                self.assertEqual(sum(r["event"] == "threat_warning" for r in rows), 6)
                self.assertFalse(any(r["clearance_valid"] for r in rows))
                manifest = json.loads((directory / "manifest.json").read_text())
                self.assertEqual(manifest["source_kind_operator_asserted"], "synthetic-fixture")
                self.assertEqual(manifest["authenticity"], "not_attested")
                self.assertIn("replay.html", manifest["bundle_sha256"])
                # Fixture labels are external; strict raw validation forbids
                # unknown/truth fields rather than trusting generator prose.
                self.assertNotIn(b"synthetic", (directory / "source.jsonl").read_bytes())
            changed_rows = [json.loads(line) for line in (output / "dash-speed-change" / "surge.jsonl").read_text().splitlines()]
            reviews = [r for r in changed_rows if r["constraint_ratio"] is not None and r["constraint_ratio"] > 1]
            self.assertTrue(all(r["constraint"] == "dash_displacement" for r in reviews))
            with self.assertRaises(FileExistsError):
                create_showcase(output)


if __name__ == "__main__":
    unittest.main()

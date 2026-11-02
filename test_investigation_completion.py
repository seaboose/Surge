"""Clock semantics, provenance, and investigation summaries across real cases."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import engine
from desktop_worker import Workspace
from evidence_labels import time_label


class InvestigationCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            dir=Path(__file__).parent / "verification/temporary-test-files"
        )
        self.root = Path(self.temp.name)
        self.ws = Workspace()
        self.data = self.root / "events.json"
        self.data.write_text(
            json.dumps(
                [
                    dict(id="A", session="one", time=800, reading=20, flag=0),
                    dict(id="B", session="one", time=900, reading=10, flag=1),
                ]
            )
        )
        ref = self.root / "reference.json"
        ref.write_text(json.dumps([dict(reading=x) for x in [8, 9, 10, 11, 12]]))
        self.ws.dispatch("import", dict(role="current", path=str(self.data)))
        self.ws.dispatch("import", dict(role="reference", path=str(ref)))
        self.config = dict(
            features=["reading"],
            session="session",
            event_id="id",
            time="time",
            time_format="milliseconds",
            time_origin="elapsed",
            threshold=6,
            rules=[dict(name="Flag", field="flag", op="eq", value=1)],
        )
        self.configure(self.config)

    def tearDown(self):
        self.temp.cleanup()

    def call(self, method, **args):
        return self.ws.dispatch(method, dict(revision=self.ws.revision, **args))

    def configure(self, config):
        self.call("configure", config=config, rules_text=json.dumps(config["rules"]))
        self.call("analyze")

    def test_changed_counts_target_only_the_corresponding_records(self):
        self.configure(dict(self.config, threshold=10))
        previous = self.root / "previous.case.json"
        self.call("save", path=str(previous))
        self.configure(self.config)
        value = self.call("compare", path=str(previous))
        self.assertEqual(value["counts"]["Result"], 1)
        self.assertEqual([r for r, kinds in value["changes"] if "Result" in kinds.split(", ")], [1])
        rows = {r["label"]: r for r in self.call("comparison", row=1)["rows"]}
        self.assertEqual(
            (rows["Result"]["current"], rows["Result"]["previous"]), ("Review", "No finding")
        )
        self.assertEqual(rows["reading · observed"]["current"], "20")
        self.assertEqual(rows["reading · condition"]["previous"], "Not matched")
        self.call("compare", path=str(previous))
        other = self.root / "other.case.json"
        source = engine.parse_bytes(b'[{"reading":30,"flag":1}]', "other.json")
        config = dict(self.config, session=None, event_id=None, time=None)
        result = engine.analyze(source, self.ws.reference, config)
        engine.save_case(other, source, self.ws.reference, config, result)
        compared = self.call("compare", path=str(other))
        self.assertFalse(compared["paired"])
        self.assertEqual(compared["changes"], [])
        self.assertEqual(compared["counts"]["Result"], 0)

    def test_case_identity_tracks_saved_bytes_and_failed_replacement_is_atomic(self):
        path = self.root / "current.case.json"
        saved = self.call("save", path=str(path))["case_file"]
        self.assertEqual(saved["path"], str(path.resolve()))
        self.assertEqual(saved["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        value = self.call("compare", path=str(path))
        self.assertEqual(value["cases"], [saved, saved])
        self.assertEqual(value["provenance"][0]["paths"]["current"], str(self.data.resolve()))
        self.configure(dict(self.config, threshold=7))
        self.assertTrue(self.ws.snapshot()["case_file"]["modified"])
        self.call("compare", path=str(path))
        old_previous = self.ws.previous_file.copy()
        bad = self.root / "bad.case.json"
        bad.write_text("{}")
        with self.assertRaises(ValueError):
            self.call("compare", path=str(bad))
        self.assertEqual(self.ws.previous_file, old_previous)
        reopened = Workspace()
        reopened.dispatch("open", dict(path=str(path)))
        self.assertEqual(reopened.current_case, saved)
        self.assertEqual(reopened.source_paths, dict(current=None, reference=None))
        self.assertNotIn("path", json.loads(path.read_text())["payload"]["current"])

    def test_explicit_clock_roundtrip_and_legacy_unknown(self):
        self.assertIn("Elapsed time · 800 ms", self.call("evidence", row=1)["time"])
        self.configure(dict(self.config, time_origin="unix"))
        self.assertIn("1970-01-01T00:00:00.800000 UTC", self.call("evidence", row=1)["time"])
        path = self.root / "unix.case.json"
        self.call("save", path=str(path))
        opened = engine.open_case(path)
        self.assertEqual(opened[2]["time_origin"], "unix")
        self.assertIn(
            "Absolute time", time_label(opened[3]["records"][0], opened[2], opened[0].rows[0])
        )
        legacy = {k: v for k, v in self.config.items() if k != "time_origin"}
        self.configure(legacy)
        self.assertIn("origin not specified", self.call("evidence", row=1)["time"])
        iso = engine.parse_bytes(
            b'[{"when":"2026-10-20T08:30:00.123456-07:00","flag":1}]', "iso.json"
        )
        config = dict(
            legacy, features=[], session=None, event_id=None, time="when", time_format="iso8601"
        )
        result = engine.analyze(iso, None, config)
        label = time_label(result["records"][0], config, iso.rows[0])
        self.assertIn("15:30:00.123456 UTC", label)
        self.assertIn("-07:00", label)

    def test_invalid_clock_and_out_of_range_epoch_are_rejected(self):
        revision = self.ws.revision
        with self.assertRaises(ValueError):
            self.configure(dict(self.config, time_origin="guessed"))
        self.assertEqual(self.ws.revision, revision)
        for value in (-1, 1e99):
            with self.assertRaises(ValueError):
                engine._timestamp(value, "seconds", "unix")

    def test_rule_only_records_have_no_numeric_evidence_and_values_are_grouped(self):
        rows = self.call("findings", hide=False)["rows"]
        self.assertTrue(rows[0]["numeric_evidence"])
        self.assertFalse(rows[1]["numeric_evidence"])
        self.assertEqual(rows[1]["reason"], "flag matches rule")
        config = copy.deepcopy(self.config)
        config["rules"].append(dict(name="Response limit", field="reading", op="gt", value=19))
        self.configure(config)
        groups = self.call("evidence", row=1)["groups"]
        reading = [g for g in groups if g["field"] == "reading"]
        self.assertEqual(len(reading), 1)
        self.assertEqual(reading[0]["value"], "20")
        self.assertEqual(len(reading[0]["lines"]), 2)
        self.assertIn("reference range", self.call("findings")["rows"][0]["reason"])


if __name__ == "__main__":
    unittest.main()

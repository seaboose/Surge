"""Check presentation meaning: changes, missing evidence, and stale comparisons."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import comparison
import engine
from evidence_labels import time_label, source_label
from test_workbench import dataset, config, reference


def case(source, settings):
    baseline = reference() if settings["features"] else None
    return source, baseline, settings, engine.analyze(source, baseline, settings)


class ComparisonTests(unittest.TestCase):
    def test_drill_through_explains_matched_and_unmatched_conditions(self):
        source = dataset([{"reading": 18}, {"reading": 100}])
        current, previous = case(source, config(threshold=3)), case(source, config(threshold=6))
        self.assertEqual(comparison.changed_records(current, previous)[0][0], 1)
        rows = {r.label: r for r in comparison.record_rows(current, previous, 1)}
        self.assertEqual(
            (rows["Result"].current, rows["Result"].previous), ("Review", "No finding")
        )
        self.assertEqual(
            (rows["reading · condition"].current, rows["reading · condition"].previous),
            ("Matched", "Not matched"),
        )
        self.assertEqual(rows["reading · observed"].current, "18")
        self.assertFalse(rows["reading · observed"].changed)
        with self.assertRaises(ValueError):
            comparison.record_rows(current, case(dataset([{"reading": 1}]), config()), 1)

    def test_priority_only_and_reason_only_changes_are_included(self):
        source = dataset([{"reading": 18}, {"reading": None}])
        rule = dict(name="High", field="reading", op="gt", value=10, priority="Warning")
        current = case(source, config(features=[], rules=[rule]))
        previous = case(source, config(features=[], rules=[dict(rule, priority="Critical")]))
        self.assertEqual(comparison.changed_records(current, previous), [(1, "Priority")])
        rows = {r.label: r for r in comparison.record_rows(current, previous, 1)}
        self.assertIn("Priority: Warning", rows["High"].current)
        self.assertIn("Priority: Critical", rows["High"].previous)
        previous = case(source, config(features=[], rules=[dict(rule, value=15)]))
        self.assertEqual(comparison.changed_records(current, previous), [(1, "Reasons")])
        rows = {r.label: r for r in comparison.record_rows(current, previous, 2)}
        self.assertEqual(rows["Result"].current, "Unknown")
        self.assertIn("Unavailable", rows["High"].current)
        self.assertIn("input unavailable", rows["Gaps"].current)

    def test_pairing_uses_source_position_when_identity_mapping_changes(self):
        source = dataset([{"reading": 18, "id": "custom", "session": "second"}])
        current = case(source, config(threshold=3, event_id="id", session="session"))
        previous = case(source, config(threshold=6))
        rows = {r.label: r for r in comparison.record_rows(current, previous, 1)}
        self.assertEqual((rows["Record ID"].current, rows["Record ID"].previous), ("custom", "1"))
        self.assertEqual(rows["Source record"].current, rows["Source record"].previous)

    def test_same_evidence_changed_threshold_and_outcomes(self):
        source = dataset([{"reading": 18}, {"reading": None}])
        note, rows = comparison.rows(
            case(source, config(threshold=6)), case(source, config(threshold=3))
        )
        lookup = {row.label: row for row in rows}
        self.assertIn("1 changed outcomes", note)
        self.assertEqual((lookup["Threshold"].current, lookup["Threshold"].previous), ("6", "3"))
        self.assertTrue(lookup["Needs review"].changed)
        self.assertFalse(lookup["Unknown"].changed)
        self.assertFalse(lookup["Data fingerprint"].changed)

    def test_different_files_do_not_pair_records(self):
        note, _ = comparison.rows(
            case(dataset([{"reading": 18}]), config()), case(dataset([{"reading": 100}]), config())
        )
        self.assertIn("Record outcomes are not paired", note)
        self.assertNotIn("changed outcomes", note)

    def test_rules_align_by_name_and_preserve_types_and_missing_values(self):
        source = dataset([{"reading": 7}])
        rules = [
            dict(name="Text rule", field="reading", op="eq", value="7"),
            dict(name="Extra rule", field="reading", op="eq", value=7),
        ]
        previous = [dict(name="Text rule", field="reading", op="eq", value=7, priority="Critical")]
        note, rows = comparison.rows(
            case(source, config(features=[], rules=rules)),
            case(source, config(features=[], rules=previous)),
        )
        lookup = {r.label: r for r in rows}
        self.assertEqual(
            (lookup["Text rule · value"].current, lookup["Text rule · value"].previous),
            ('"7"', "7"),
        )
        self.assertTrue(lookup["Text rule · value"].changed)
        self.assertEqual(lookup["Extra rule · value"].previous, "Not present")
        self.assertIn("1 changed priorities", note)
        self.assertTrue(comparison.equivalent(6, 6.0))
        self.assertFalse(comparison.equivalent(True, 1))


class InspectorTests(unittest.TestCase):
    def setUp(self):
        from app import Workbench

        self.window = Workbench(start_hidden=True)
        self.window.withdraw()

    def tearDown(self):
        self.window.destroy()

    def show(self, source, settings):
        win = self.window
        win.current, win.reference, win.run_config, win.result = case(source, settings)
        win._render_findings()
        return win.detail.get("1.0", "end")

    def test_trigger_precedes_context_and_raw_values_are_available(self):
        text = self.show(
            dataset([{"reading": 100, "actor": "sam", "extra": "retained"}]),
            config(context={"User": "actor"}),
        )
        self.assertLess(text.index("reading: 100"), text.index("User:"))
        self.assertIn("Reference median: 10", text)
        self.assertNotIn("retained", text)
        self.window.show_values.set(True)
        self.window._inspect()
        self.assertIn('extra: "retained"', self.window.detail.get("1.0", "end"))
        self.assertIn("not a safe limit", text)

    def test_unknown_explains_gap_before_metadata(self):
        text = self.show(dataset([{"reading": None}]), config())
        self.assertTrue(text.startswith("Cannot fully assess"))
        self.assertLess(text.index("numeric value unavailable"), text.index("Source:"))
        self.assertNotIn("crossed", text)

    def test_comparison_refreshes_after_reanalysis_and_clears_stale_values(self):
        win = self.window
        source = dataset([{"reading": 18}])
        self.show(source, config(threshold=6))
        win.previous = case(source, config(threshold=3))
        win._render_comparison()
        win.differences_only.set(True)
        win._render_comparison()
        self.assertTrue(win.comparison.rows)
        self.assertTrue(all(row.changed for row in win.comparison.rows))
        win._changed()
        self.assertEqual(win.comparison.rows, [])
        win.result, win.run_config = win.previous[3], copy.deepcopy(win.previous[2])
        win._render_comparison()
        self.assertEqual(win.comparison.rows, [])
        self.assertIn("0 changed outcomes", win.comparison_note.get())

    def test_changed_record_action_selection_and_invalidation(self):
        win = self.window
        source = dataset([{"reading": 18}, {"reading": 20}])
        self.show(source, config(threshold=3))
        win.previous = case(source, config(threshold=9))
        win._render_comparison()
        win.changed_records_button.invoke()
        self.assertTrue(win.compare_records)
        self.assertEqual(win.changed_list.get_children(), ("1", "2"))
        win.changed_list.selection_set("2")
        win._inspect_comparison()
        lookup = {r.label: r for r in win.comparison.rows}
        self.assertEqual(lookup["reading · observed"].current, "20")
        self.assertEqual(lookup["Source record"].current, "2")
        self.assertIn("incoming.json", win.comparison.source_cells[0].cget("text"))
        self.assertIn(source.digest[:12], win.comparison.source_cells[0].cget("text"))
        self.assertIn("disabled", win.changes_filter.state())
        win.settings_button.invoke()
        self.assertFalse(win.compare_records)
        self.assertNotIn("disabled", win.changes_filter.state())
        win.changed_records_button.invoke()
        win._changed()
        self.assertEqual(win.changed_list.get_children(), ())
        self.assertEqual(win.comparison.rows, [])
        self.assertIn("disabled", win.changed_records_button.state())

    def test_different_and_unchanged_cases_disable_drill_through(self):
        win = self.window
        source = dataset([{"reading": 18}])
        self.show(source, config())
        for old in (case(source, config()), case(dataset([{"reading": 100}]), config())):
            win.previous = old
            win.compare_records = True
            win._render_comparison()
            self.assertFalse(win.compare_records)
            self.assertIn("disabled", win.changed_records_button.state())
            self.assertEqual(win.changed_list.get_children(), ())

    def test_inspector_time_and_provenance_after_case_roundtrip(self):
        source = dataset([{"reading": 100, "when": "2026-10-20T08:30:00.123456-07:00"}])
        settings = config(time="when", time_format="iso8601")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "time.case.json"
            engine.save_case(path, *case(source, settings))
            win = self.window
            win.current, win.reference, win.run_config, win.result = engine.open_case(path)
            win._render_findings()
            text = win.detail.get("1.0", "end")
            self.assertIn("2026-10-20T15:30:00.123456 UTC", text)
            self.assertIn('From when: "2026-10-20T08:30:00.123456-07:00"', text)
            self.assertIn("source record 1", text)
            win.show_values.set(True)
            win._inspect()
            self.assertIn(source.digest, win.detail.get("1.0", "end"))

    def test_split_preference_roundtrip_and_invalid_file_fallback(self):
        from app import Workbench

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "layout.json"
            with patch("app.UI_STATE", path):
                path.write_text(json.dumps({"split": 0.61}), encoding="utf-8")
                other = Workbench(start_hidden=True)
                try:
                    other.withdraw()
                    self.assertEqual(other._split_ratio, 0.61)
                finally:
                    other.destroy()
                path.write_text('{"split": false}', encoding="utf-8")
                other = Workbench(start_hidden=True)
                try:
                    other.withdraw()
                    self.assertEqual(other._split_ratio, 0.5)
                finally:
                    other.destroy()


class TimeLabelTests(unittest.TestCase):
    def test_numeric_units_do_not_invent_clock_origin(self):
        for format, value, unit in (("seconds", 1.25, "s"), ("milliseconds", 1250, "ms")):
            source = dataset([{"reading": 100, "clock": value}])
            settings = config(time="clock", time_format=format)
            record = case(source, settings)[3]["records"][0]
            label = time_label(record, settings, source.rows[0])
            self.assertIn(f"{value} {unit}", label)
            self.assertIn("origin not specified", label)
            self.assertNotIn("UTC", label)
            self.assertEqual(record["time_ms"], 1250)

    def test_unmapped_and_missing_time_are_distinct(self):
        self.assertEqual(time_label({"time_ms": None}, config(), {}), "Not mapped")
        self.assertIn("Unavailable", time_label({"time_ms": None}, config(time="clock"), {}))
        source = dataset([{"reading": 1}])
        self.assertIn(source.name, source_label(source))
        self.assertIn(source.digest[:12], source_label(source))


if __name__ == "__main__":
    unittest.main(verbosity=2)

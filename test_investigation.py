"""Search and compact evidence must preserve investigation meaning."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import engine
import investigation
import workflow
from test_workbench import config, dataset
from test_presentation import case


def input_case():
    source = dataset(
        [
            {"id": "event-[9]", "session": "Round A", "actor": "Straße", "reading": 100},
            {"id": "event-10", "session": "Round B", "actor": 42, "reading": 10},
            {"id": "event-11", "session": "Round B", "actor": "Lee", "reading": None},
        ]
    )
    rule = dict(name="High reading", field="reading", op="gt", value=50)
    settings = config(event_id="id", session="session", context={"User": "actor"}, rules=[rule])
    return case(source, settings)


class SearchTests(unittest.TestCase):
    def test_ids_sessions_users_and_rules_are_literal_case_insensitive(self):
        source, _, settings, result = input_case()
        index = investigation.search_index(source, settings, result)
        for query, expected in (
            (" EVENT-[9] ", [1]),
            ("round b", [2, 3]),
            ("STRASSE", [1]),
            ("42", [2]),
            ("high reading", [1, 3]),
            (".*", []),
            ("not present", []),
            ("", [1, 2, 3]),
            ("   ", [1, 2, 3]),
        ):
            with self.subTest(query=query):
                self.assertEqual(
                    [row for row, values in index.items() if investigation.matches(values, query)],
                    expected,
                )
        # The configured rule must not match every record, or a quiet record
        # would appear to have triggered it. Missing rule input remains searchable.
        self.assertFalse(investigation.matches(index[2], "high reading"))
        self.assertFalse(investigation.matches(index[1], "event-[9] round a"))

    def test_unmapped_user_is_not_guessed_from_a_column_name(self):
        source, _, settings, result = input_case()
        settings = dict(settings, context={})
        index = investigation.search_index(source, settings, result)
        self.assertFalse(investigation.matches(index[1], "straße"))
        source = dataset([{"reading": 100, "user": "alex"}])
        settings = config()
        result = case(source, settings)[3]
        index = investigation.search_index(source, settings, result)
        self.assertFalse(investigation.matches(index[1], "alex"))
        self.assertTrue(investigation.matches(index[1], "1"))


class InvestigationUITests(unittest.TestCase):
    def setUp(self):
        from app import Workbench

        self.win = Workbench()
        self.win.withdraw()
        self.win.current, self.win.reference, self.win.run_config, self.win.result = input_case()
        self.win._render_findings()

    def tearDown(self):
        self.win.destroy()

    def search(self, query):
        self.win.search.set(query)
        self.win._render_findings()
        return self.win.findings.get_children()

    def test_search_reports_hidden_gaps_and_distinguishes_empty_results(self):
        self.assertEqual(self.search("event-[9]"), ("1",))
        self.assertIn("1 record with gaps hidden", self.win.filter_note.cget("text"))
        self.assertIn("1 shown / 3", self.win.summary_label.cget("text"))
        self.assertEqual(self.search("event-10"), ())
        self.assertIn("No records match this search", self.win.detail.get("1.0", "end"))
        self.assertNotIn("No configured condition matched.", self.win.detail.get("1.0", "end"))
        self.win.only_leads.set(False)
        self.win._render_findings()
        self.assertEqual(self.win.findings.get_children(), ("2",))
        self.assertIn("No configured condition matched.", self.win.detail.get("1.0", "end"))

    def test_matching_gaps_survive_priority_and_selection_stays_on_visible_record(self):
        self.win.findings.selection_set("3")
        self.assertEqual(self.search("high reading"), ("1", "3"))
        self.assertEqual(self.win.findings.selection(), ("3",))
        self.win.minimum_priority.set("Critical")
        self.win._render_findings()
        self.assertEqual(self.win.findings.get_children(), ("3",))
        self.assertIn("Cannot fully assess", self.win.detail.get("1.0", "end"))
        self.win.clear_search_button.invoke()
        self.assertEqual(self.win.search.get(), "")
        self.assertEqual(self.win.findings.selection(), ("3",))

    def test_search_does_not_change_results_case_or_exports(self):
        win = self.win
        original = copy.deepcopy(win.result)
        self.search("not present")
        self.assertEqual(win.result, original)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "all.case.json"
            engine.save_case(path, win.current, win.reference, win.run_config, win.result)
            self.assertEqual(len(engine.open_case(path)[3]["records"]), 3)
            path = Path(tmp) / "alerts.jsonl"
            workflow.export_alerts(path, win.current, win.reference, win.run_config, win.result)
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([r["row"] for r in records[1:]], [1, 3])

    def test_new_results_replace_search_index_and_invalidated_results_clear_inspector(self):
        self.search("event-[9]")
        win = self.win
        win.current, win.reference, win.run_config, win.result = case(
            dataset([{"reading": 100}]), config()
        )
        win._render_findings()
        self.assertEqual(win.findings.get_children(), ())
        win._clear_search()
        self.assertEqual(win.findings.get_children(), ("1",))
        win._changed()
        self.assertEqual(win._search_index, {})
        self.assertEqual(win.findings.get_children(), ())
        self.assertNotIn("reading: 100", win.detail.get("1.0", "end"))

    def test_typing_updates_list_after_short_delay_and_enter_flushes_pending_search(self):
        win = self.win
        win.search.set("Lee")
        win.after(220, win.quit)
        win.mainloop()
        self.assertEqual(win.findings.get_children(), ("3",))
        self.assertIsNone(win._search_timer)
        win.search.set("event-[9]")
        win._render_findings()
        self.assertIsNone(win._search_timer)
        self.assertEqual(win.findings.get_children(), ("1",))

    def test_inspector_groups_same_field_and_keeps_all_reasons(self):
        win = self.win
        source = dataset([{"reading": "100", "second": 100}])
        baseline = dataset(
            [{"reading": x, "second": x} for x in [8, 9, 10, 11, 12]], "reference.json"
        )
        settings = config(
            features=["reading", "second"],
            rules=[
                dict(name="Upper", field="reading", op="gt", value=50),
                dict(name="Limit", field="reading", op="ge", value=75),
            ],
        )
        win.current, win.reference, win.run_config = source, baseline, settings
        win.result = engine.analyze(source, baseline, settings)
        win._render_findings()
        text = win.detail.get("1.0", "end")
        self.assertEqual(text.count('reading: "100"'), 1)
        self.assertEqual(text.count("Matched: Upper"), 1)
        self.assertEqual(text.count("Matched: Limit"), 1)
        self.assertIn("greater than 50", text)
        self.assertIn("at least 75", text)
        self.assertEqual(text.count("not a safe limit"), 1)
        self.assertNotIn("Scale:", text)
        self.assertNotIn("Method:", text)
        win.show_details.set(True)
        win._inspect()
        text = win.detail.get("1.0", "end")
        self.assertIn("Used as number: 100", text)
        self.assertIn("Method: median absolute deviation", text)
        self.assertIn(baseline.digest, text)
        win.show_values.set(True)
        win._inspect()
        self.assertIn(source.digest, win.detail.get("1.0", "end"))

    def test_rule_only_and_unknown_records_do_not_show_reference_explanations(self):
        win = self.win
        settings = dict(win.run_config, features=[])
        win.reference = None
        win.run_config = settings
        win.result = engine.analyze(win.current, None, settings)
        win.show_details.set(True)
        win._render_findings()
        text = win.detail.get("1.0", "end")
        self.assertIn("Matched: High reading", text)
        self.assertNotIn("Reference", text)
        win.findings.selection_set("3")
        win._inspect()
        text = win.detail.get("1.0", "end")
        self.assertTrue(text.startswith("Cannot fully assess"))
        self.assertIn("High reading: rule input unavailable", text)
        self.assertNotIn("Reference", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

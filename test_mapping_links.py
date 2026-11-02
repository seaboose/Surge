"""Warnings must point to exact source rows without changing evidence or analysis."""

import copy
import unittest

import engine
import mapping_checks
from test_workbench import config, dataset, reference


def find(report, group, contains):
    return next(note for note in report.groups[group] if contains in note.text)


class MappingTargetTests(unittest.TestCase):
    def test_all_affected_positions_survive_the_three_record_summary(self):
        source = dataset([{"reading": 10}] * 105 + [{"reading": None}] * 205)
        note = find(
            mapping_checks.check(source, reference(), config()), "features", "missing or nonnumeric"
        )
        self.assertEqual(note.source, "current")
        self.assertEqual(note.fields, ("reading",))
        self.assertEqual(note.rows, tuple(range(106, 311)))

    def test_duplicates_and_backward_times_include_context_not_unrelated_sessions(self):
        source = dataset(
            [
                {"session": "a", "id": "one", "clock": 4, "reading": 1},
                {"session": "b", "id": "one", "clock": 9, "reading": 2},
                {"session": "a", "id": "one", "clock": 3, "reading": 3},
                {"session": "a", "id": "three", "clock": 2, "reading": 4},
            ]
        )
        report = mapping_checks.check(
            source, reference(), config(session="session", event_id="id", time="clock")
        )
        duplicate = find(report, "event_id", "Repeated IDs")
        self.assertEqual((duplicate.rows, duplicate.related), ((3,), (1,)))
        self.assertEqual(duplicate.fields, ("id", "session"))
        backward = find(report, "time", "move backward")
        self.assertEqual((backward.rows, backward.related), ((3, 4), (1,)))

    def test_reference_and_source_warnings_are_separate(self):
        source = dataset([{"reading": 1}, {"reading": None}])
        ref = dataset([{"reading": 2}] * 5 + [{"reading": None}], "baseline.json")
        report = mapping_checks.check(source, ref, config())
        note = find(report, "features", "Reference 'reading' uses")
        self.assertEqual((note.source, note.rows, note.fields), ("reference", (6,), ("reading",)))
        shortage = find(
            mapping_checks.check(source, dataset([{"reading": 1}] * 4), config()),
            "features",
            "needs at least 5",
        )
        self.assertEqual((shortage.source, shortage.rows), ("reference", None))

    def test_rule_context_identity_and_missing_field_targets(self):
        source = dataset(
            [
                {"reading": 10, "id": "one", "action": "", "user": None},
                {"reading": 11, "id": "", "action": "ok", "user": "two"},
            ]
        )
        report = mapping_checks.check(
            source,
            reference(),
            config(
                event_id="id",
                context={"User": "user"},
                rules=[dict(name="Present", field="action", op="eq", value="ok")],
            ),
        )
        self.assertEqual(find(report, "event_id", "invalid").rows, (2,))
        self.assertEqual(find(report, "rules", "unavailable").fields, ("action",))
        self.assertEqual(find(report, "context", "missing").rows, (1,))
        absent = find(
            mapping_checks.check(source, dataset([{"other": 2}]), config()), "features", "has no"
        )
        self.assertEqual(
            (absent.source, absent.fields, absent.rows), ("reference", ("reading",), None)
        )

    def test_settings_without_records_are_not_fake_links(self):
        report = mapping_checks.check(dataset([{"reading": 1}]), None, config(threshold="bad"))
        self.assertIsNone(find(report, "threshold", "Enter").source)
        self.assertIsNone(find(report, "features", "Add a reference").source)


class MappingLinkUITests(unittest.TestCase):
    def setUp(self):
        from app import Workbench

        self.win = Workbench(start_hidden=True)
        self.win.withdraw()

    def tearDown(self):
        self.win.destroy()

    def setup_data(self, source, ref=None, cfg=None):
        win = self.win
        win.current, win.reference = source, ref or reference()
        win._refresh_data()
        win._apply_config(cfg or config())

    def open(self, group, contains):
        report = self.win.mapping_report
        note = find(report, group, contains)
        self.win._open_mapping_preview(note, report)
        return note

    def test_preview_paging_reaches_every_affected_record_and_restores_default(self):
        win = self.win
        self.setup_data(dataset([{"reading": 10}] * 105 + [{"reading": None}] * 205))
        self.open("features", "missing or nonnumeric")
        self.assertEqual(win.preview.get_children(), tuple(str(i) for i in range(106, 206)))
        self.assertEqual(win.preview.selection(), ("106",))
        self.assertEqual(win._preview_fields[0], "reading")
        self.assertEqual(win.preview.heading("field_0")["text"], "→ reading")
        win.preview_next.invoke()
        self.assertEqual(win.preview.get_children()[0], "206")
        win.preview_next.invoke()
        self.assertEqual(win.preview.get_children(), ("306", "307", "308", "309", "310"))
        self.assertIn("disabled", win.preview_next.state())
        win.preview_previous.invoke()
        self.assertEqual(win.preview.get_children()[0], "206")
        win.preview_back.invoke()
        self.assertIsNone(win._preview_note)
        self.assertEqual(len(win.preview.get_children()), 100)
        self.assertEqual(win.preview.get_children()[0], "1")
        self.assertEqual(win.preview_actions.winfo_manager(), "")

    def test_reference_preview_names_source_and_distinguishes_missing_null_and_empty(self):
        win = self.win
        ref = dataset(
            [{"reading": 2}] * 5 + [{"reading": None}, {"reading": ""}, {"other": 0}],
            "reference-only.json",
        )
        self.setup_data(dataset([{"reading": 100}]), ref)
        self.open("features", "Reference 'reading' uses")
        self.assertEqual(win.preview.get_children(), ("6", "7", "8"))
        self.assertIn("Reference · reference-only.json", win.preview_note.cget("text"))
        self.assertEqual(
            [win.preview.item(i, "values")[0] for i in ("6", "7", "8")], ["null", '""', "Missing"]
        )
        win.preview_back.invoke()
        self.assertIn("Incoming", win.preview_note.cget("text"))
        self.assertEqual(win.preview.item("1", "values")[0], "100")

    def test_missing_reference_field_is_visible_as_missing_for_each_record(self):
        win = self.win
        self.setup_data(
            dataset([{"reading": 1}]), dataset([{"other": 2}, {"other": 3}], "other.json")
        )
        self.open("features", "has no")
        self.assertEqual(win._preview_fields[:2], ["reading", "other"])
        self.assertEqual(
            [win.preview.item(i, "values")[0] for i in ("1", "2")], ["Missing", "Missing"]
        )

    def test_duplicate_preview_marks_original_as_related_and_selects_duplicate(self):
        win = self.win
        self.setup_data(
            dataset([{"reading": 1, "id": "a"}, {"reading": 2, "id": "a"}]),
            cfg=config(event_id="id"),
        )
        self.open("event_id", "Repeated IDs")
        self.assertEqual(win.preview.item("1", "text"), "1 · related")
        self.assertEqual(win.preview.selection(), ("2",))
        self.assertIn("1 affected · 1 related", win.preview_note.cget("text"))

    def test_clicks_and_enter_use_individual_warnings_and_preserve_results(self):
        win = self.win
        self.setup_data(
            dataset([{"reading": None, "other": 1}, {"reading": 1, "other": None}]),
            dataset([{"reading": i, "other": i + 10} for i in range(6)], "ref.json"),
            config(features=["reading", "other"]),
        )
        win.result = engine.analyze(win.current, win.reference, win.config())
        win.run_config = win.config()
        before = copy.deepcopy(
            (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        win.deiconify()
        win.update()
        widgets = [
            widget
            for widget in win.mapping_note_widgets["features"]
            if "missing or nonnumeric" in widget.cget("text")
        ]
        widgets[0].event_generate("<Button-1>")
        win.update()
        self.assertEqual((win.preview.get_children(), win._preview_fields[0]), (("1",), "reading"))
        widgets[1].focus_force()
        win.update()
        widgets[1].event_generate("<Return>")
        win.update()
        self.assertEqual((win.preview.get_children(), win._preview_fields[0]), (("2",), "other"))
        self.assertEqual(
            before, (win.current, win.reference, win.config(), win.result, win.run_config)
        )

    def test_mapping_and_source_changes_clear_drillthrough_and_reject_stale_callbacks(self):
        win = self.win
        self.setup_data(dataset([{"reading": None}, {"reading": 1}]))
        old_report = win.mapping_report
        note = self.open("features", "missing or nonnumeric")
        win.threshold.set("7")
        self.assertIsNone(win._preview_note)
        win._open_mapping_preview(note, old_report)
        self.assertIsNone(win._preview_note)
        self.open("features", "missing or nonnumeric")
        win.current = dataset([{"reading": 4}])
        win._refresh_data()
        self.assertIsNone(win._preview_note)
        self.assertEqual(win.preview.get_children(), ("1",))


if __name__ == "__main__":
    unittest.main(verbosity=2)

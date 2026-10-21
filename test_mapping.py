"""Mapping checks must match detector behavior without rewriting evidence."""

import copy
import unittest
from unittest.mock import patch

import engine
import mapping_checks
from test_workbench import config, dataset, reference


def text(report, group):
    return "\n".join(note.text for note in report.groups.get(group, []))


def visible_text(win, group):
    return "\n".join(widget.cget("text") for widget in win.mapping_note_widgets[group])


class MappingTests(unittest.TestCase):
    def test_optional_mappings_explain_defaults_without_blocking(self):
        source = dataset([{"reading": 1}])
        report = mapping_checks.check(source, reference(), config())
        self.assertFalse(report.blocked)
        self.assertIn("one session", text(report, "session"))
        self.assertIn("positions", text(report, "event_id"))
        self.assertIn("file order", text(report, "time"))

    def test_collisions_mark_each_affected_role(self):
        report = mapping_checks.check(
            dataset([{"reading": 1}]),
            reference(),
            config(session="reading", event_id="reading", time="reading"),
        )
        self.assertTrue(report.blocked)
        for group in ("features", "session", "event_id", "time"):
            self.assertIn("also used", text(report, group))

    def test_invalid_identity_and_time_records_are_located(self):
        source = dataset(
            [
                {"id": "a", "session": "s", "clock": 0, "reading": 1},
                {"id": "", "session": None, "clock": -1, "reading": 2},
                {"id": False, "session": "s", "clock": "bad", "reading": 3},
            ]
        )
        cfg = config(session="session", event_id="id", time="clock")
        report = mapping_checks.check(source, reference(), cfg)
        self.assertTrue(report.blocked)
        self.assertIn("Records 2, 3", text(report, "event_id"))
        self.assertIn("Record 2", text(report, "session"))
        self.assertIn("Records 2, 3", text(report, "time"))
        with self.assertRaises(ValueError):
            engine.analyze(source, reference(), cfg)

    def test_duplicate_ids_use_selected_session_and_report_both_positions(self):
        source = dataset(
            [
                {"session": "one", "id": "a", "reading": 1},
                {"session": "two", "id": "a", "reading": 2},
            ]
        )
        cfg = config(event_id="id", session="session")
        self.assertFalse(mapping_checks.check(source, reference(), cfg).blocked)
        cfg["session"] = None
        report = mapping_checks.check(source, reference(), cfg)
        self.assertIn("Record 2 repeats record 1", text(report, "event_id"))
        self.assertTrue(report.blocked)

    def test_time_format_and_backwards_time_match_engine(self):
        source = dataset(
            [
                {"clock": "2026-10-20T01:00:00Z", "reading": 1},
                {"clock": "2026-10-20T00:00:00Z", "reading": 2},
            ]
        )
        cfg = config(time="clock", time_format="iso8601")
        report = mapping_checks.check(source, reference(), cfg)
        self.assertFalse(report.blocked)
        self.assertIn("move backward", text(report, "time"))
        result = engine.analyze(source, reference(), cfg)
        self.assertTrue(result["records"][1]["gaps"])
        cfg["time_format"] = "seconds"
        self.assertTrue(mapping_checks.check(source, reference(), cfg).blocked)
        source = dataset([{"clock": "2026-10-20T01:00:00", "reading": 1}])
        cfg["time_format"] = "iso8601"
        self.assertTrue(mapping_checks.check(source, reference(), cfg).blocked)

    def test_reference_missing_field_and_minimum_values_block(self):
        source = dataset([{"reading": 1}])
        for ref in (None, dataset([{"other": 2}]), dataset([{"reading": 2}] * 4), source):
            self.assertTrue(mapping_checks.check(source, ref, config()).blocked)
        report = mapping_checks.check(
            source, dataset([{"reading": 2}] * 5 + [{"reading": None}]), config()
        )
        self.assertFalse(report.blocked)
        self.assertIn("5/6", text(report, "features"))

    def test_all_rows_checked_and_missing_measurements_remain_warnings(self):
        source = dataset([{"reading": 10}] * 100 + [{"reading": None}, {"reading": "bad"}])
        before = copy.deepcopy(source.rows)
        report = mapping_checks.check(source, reference(), config())
        self.assertFalse(report.blocked)
        self.assertIn("100/102", text(report, "features"))
        self.assertIn("Records 101, 102", text(report, "features"))
        self.assertEqual(source.rows, before)
        self.assertTrue(engine.analyze(source, reference(), config())["records"][100]["gaps"])

    def test_rule_and_context_fields_get_named_warnings(self):
        source = dataset([{"action": None, "user": ""}, {"action": "blocked", "user": "one"}])
        cfg = config(
            features=[],
            rules=[dict(name="Blocked", field="action", op="eq", value="blocked")],
            context={"User": "user"},
        )
        report = mapping_checks.check(source, None, cfg)
        self.assertFalse(report.blocked)
        self.assertIn("'action'", text(report, "rules"))
        self.assertIn("'user'", text(report, "context"))
        cfg["context"]["User"] = "absent"
        self.assertTrue(mapping_checks.check(source, None, cfg).blocked)

    def test_invalid_threshold_and_absent_fields_stay_actionable(self):
        source = dataset([{"reading": 1}])
        cfg = config(threshold="bad", session="absent")
        report = mapping_checks.check(source, reference(), cfg)
        self.assertTrue(report.blocked)
        self.assertIn("1 to 100", text(report, "threshold"))
        self.assertIn("'absent'", text(report, "session"))


class MappingUITests(unittest.TestCase):
    def setUp(self):
        from app import Workbench

        self.win = Workbench()
        self.win.withdraw()
        self.win.current = dataset(
            [{"reading": 10, "id": "one", "clock": 0}, {"reading": None, "id": "one", "clock": 1}]
        )
        self.win.reference = reference()
        self.win._refresh_data()
        self.win._apply_config(config(event_id="id", time="clock"))

    def tearDown(self):
        self.win.destroy()

    def test_inline_errors_disable_analyze_and_shortcut_cannot_bypass(self):
        win = self.win
        self.assertIn("Repeated IDs", visible_text(win, "event_id"))
        self.assertIn("disabled", win.run_button.state())
        self.assertNotIn("disabled", win.data_actions["Save policy"].state())
        with patch.object(win, "_job") as job:
            win._run()
            job.assert_not_called()
        win.event_id.set("Not mapped")
        self.assertNotIn("disabled", win.run_button.state())
        self.assertIn("Check", visible_text(win, "features"))
        self.assertIn("can continue", win.setup_hint.cget("text"))

    def test_reference_and_time_changes_refresh_notes_and_cache(self):
        win = self.win
        first = win.mapping_report
        win._sync_data_controls()
        self.assertIs(win.mapping_report, first)
        win.event_id.set("Not mapped")
        win.time_format.set("iso8601")
        self.assertIn("invalid", visible_text(win, "time"))
        win.time_format.set("seconds")
        self.assertIn("valid times", visible_text(win, "time"))
        win.reference = dataset([{"reading": 1}] * 4)
        win._refresh_data()
        self.assertIn("needs at least 5", visible_text(win, "features"))
        self.assertIn("disabled", win.run_button.state())

    def test_mapping_scroll_and_keyboard_focus_keep_controls_reachable(self):
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        win.update()
        self.assertGreater(win.mapping_frame.winfo_height(), win.mapping_canvas.winfo_height())
        win.rules_button.focus_force()
        win.update()
        top = win.rules_button.winfo_rooty()
        self.assertGreaterEqual(top, win.mapping_canvas.winfo_rooty())
        self.assertLess(top, win.mapping_canvas.winfo_rooty() + win.mapping_canvas.winfo_height())
        win.mapping_canvas.yview_moveto(0)
        win.update()
        self.assertAlmostEqual(win.mapping_canvas.yview()[0], 0, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

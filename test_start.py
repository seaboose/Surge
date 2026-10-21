"""Entry actions and progressive setup must follow real application state."""

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import engine
from test_workbench import config, dataset, reference
from test_presentation import case


class StartTests(unittest.TestCase):
    def setUp(self):
        from app import Workbench

        self.win = Workbench()
        self.win.withdraw()

    def tearDown(self):
        self.win.destroy()

    def finish(self):
        end = time.monotonic() + 8
        while self.win.busy and time.monotonic() < end:
            self.win.update()
            time.sleep(0.01)
        self.assertFalse(self.win.busy)

    def test_start_has_two_entry_actions_and_no_setup_or_navigation(self):
        win = self.win
        self.assertEqual(win.empty_data.winfo_manager(), "pack")
        self.assertEqual(win.data_setup.winfo_manager(), "")
        self.assertEqual(win.rail.winfo_manager(), "")
        self.assertNotIn("disabled", win.start_import.state())
        self.assertNotIn("disabled", win.start_open.state())
        self.assertIn("disabled", win.run_button.state())
        for page in ("Findings", "Compare", "Health"):
            win.show_page(page)
            self.assertEqual(win.active_page, "Data")
        win._focus_search()
        self.assertEqual(win.active_page, "Data")

    def test_canceled_entry_actions_leave_start_unchanged(self):
        with patch("app.filedialog.askopenfilename", return_value="") as dialog:
            self.win.start_import.invoke()
            self.win.start_open.invoke()
        self.assertEqual(dialog.call_count, 2)
        self.assertIsNone(self.win.current)
        self.assertFalse(self.win.busy)
        self.assertEqual(self.win.data_setup.winfo_manager(), "")

    def test_real_import_reveals_setup_without_choosing_signals(self):
        win = self.win
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text(json.dumps([{"reading": 100, "clock": 10}]), encoding="utf-8")
            with patch("app.filedialog.askopenfilename", return_value=str(path)):
                win.start_import.invoke()
                self.finish()
        self.assertEqual(win.empty_data.winfo_manager(), "")
        self.assertEqual(win.data_setup.winfo_manager(), "pack")
        self.assertEqual(win.rail.winfo_manager(), "pack")
        self.assertEqual(win.features.curselection(), ())
        self.assertEqual(win.numeric_setup.winfo_manager(), "pack")
        self.assertEqual(win.time_setup.winfo_manager(), "")
        self.assertEqual(win.threshold_setup.winfo_manager(), "")
        self.assertIn("disabled", win.run_button.state())
        self.assertIn("Choose values", win.setup_hint.cget("text"))
        self.assertEqual(len(win.preview.get_children()), 1)

    def test_numeric_and_time_controls_follow_mapping_and_keep_values(self):
        win = self.win
        win.current = dataset([{"reading": 100, "clock": 10}])
        win._refresh_data()
        win.time.set("clock")
        win.time_format.set("seconds")
        self.assertEqual(win.time_setup.winfo_manager(), "pack")
        win.time.set("Not mapped")
        self.assertEqual(win.time_setup.winfo_manager(), "")
        win.time.set("clock")
        self.assertEqual(win.time_format.get(), "seconds")
        position = list(win.features.get(0, "end")).index("reading")
        win.features.selection_set(position)
        win._changed()
        self.assertEqual(win.threshold_setup.winfo_manager(), "pack")
        self.assertIn("Add a reference", win.setup_hint.cget("text"))
        self.assertIn("disabled", win.run_button.state())
        win.reference = reference()
        win._refresh_data()
        self.assertNotIn("disabled", win.run_button.state())
        win.threshold.set("bad")
        self.assertIn("disabled", win.run_button.state())
        win.features.selection_clear(0, "end")
        win._changed()
        self.assertEqual(win.threshold_setup.winfo_manager(), "pack")  # Error remains editable.
        win.threshold.set("8")
        self.assertEqual(win.threshold_setup.winfo_manager(), "")
        win.features.selection_set(position)
        win._changed()
        self.assertEqual(win.threshold.get(), "8")
        self.assertNotIn("disabled", win.run_button.state())

    def test_text_only_rule_setup_needs_no_numeric_controls(self):
        win = self.win
        win.current = dataset([{"action": "blocked", "id": "one"}])
        win._refresh_data()
        self.assertEqual(win.numeric_setup.winfo_manager(), "")
        self.assertEqual(win.threshold_setup.winfo_manager(), "")
        self.assertIn("Add a rule", win.setup_hint.cget("text"))
        win.rules = [dict(name="Blocked", field="action", op="eq", value="blocked")]
        win._changed()
        self.assertNotIn("disabled", win.run_button.state())
        win.run_button.invoke()
        self.finish()
        self.assertEqual(win.active_page, "Findings")
        self.assertEqual(win.result["summary"]["Review"], 1)
        self.assertNotIn("disabled", win.navigation["Compare"].state())

    def test_open_case_restores_controls_and_goes_directly_to_findings(self):
        win = self.win
        source = dataset([{"reading": 100, "clock": 10}])
        saved = case(source, config(time="clock", time_format="seconds"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved.case.json"
            engine.save_case(path, *saved)
            with patch("app.filedialog.askopenfilename", return_value=str(path)):
                win.start_open.invoke()
                self.finish()
        self.assertEqual(win.active_page, "Findings")
        self.assertEqual(win.empty_data.winfo_manager(), "")
        self.assertEqual(win.config(), saved[2])
        self.assertEqual(win.time_setup.winfo_manager(), "pack")
        self.assertEqual(win.threshold_setup.winfo_manager(), "pack")
        self.assertEqual(win.result, saved[3])
        win.threshold.set("7")
        self.assertIsNone(win.result)
        self.assertEqual(win.active_page, "Data")
        self.assertIn("disabled", win.navigation["Findings"].state())

    def test_failed_import_preserves_empty_or_loaded_state(self):
        win = self.win
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text("{invalid", encoding="utf-8")
            for loaded in (False, True):
                if loaded:
                    win.current = dataset([{"reading": 100}])
                    win._refresh_data()
                before = win.current
                with (
                    patch("app.filedialog.askopenfilename", return_value=str(path)),
                    patch.object(win, "_show_import_error") as error,
                ):
                    win._load("current")
                    self.finish()
                    error.assert_called_once()
                self.assertIs(win.current, before)
                self.assertEqual(win.data_setup.winfo_manager(), "pack" if loaded else "")
                self.assertNotIn("disabled", win.start_import.state())

    def test_entry_buttons_disable_during_load_and_recover(self):
        gate = threading.Event()
        win = self.win

        def load():
            gate.wait(4)
            return dataset([{"reading": 10}])

        try:
            win._job("current", load)
            self.assertIn("disabled", win.start_import.state())
            self.assertIn("disabled", win.start_open.state())
        finally:
            gate.set()
            self.finish()
        self.assertEqual(win.data_setup.winfo_manager(), "pack")
        self.assertNotIn("disabled", win.data_actions["Import data"].state())


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Full preview values must retain source identity and the active mapping warning."""

import copy
import json
import time
import unittest
from unittest.mock import patch
import tkinter as tk

import engine
from test_workbench import config, dataset, reference
from test_mapping_links import find


class PreviewValuesTests(unittest.TestCase):
    def setUp(self):
        from app import Workbench

        self.win = Workbench()
        self.win.withdraw()

    def tearDown(self):
        self.win.destroy()

    def load(self, rows, ref=None, cfg=None):
        win = self.win
        win.current, win.reference = dataset(rows), ref or reference()
        win._refresh_data()
        win._apply_config(cfg or config())

    def select(self, index):
        self.win.preview.selection_set(str(index))
        self.win.preview.focus(str(index))
        self.win.preview.event_generate("<<TreeviewSelect>>")
        self.win.update()

    def contents(self):
        return self.win.preview_values.get("1.0", "end-1c")

    def open_warning(self, group, part):
        report = self.win.mapping_report
        note = find(report, group, part)
        self.win._open_mapping_preview(note, report)
        self.win.update()
        return note

    def test_normal_preview_selection_shows_full_unicode_values_from_source(self):
        value = "start\n" + "猫🙂x" * 800 + "\tEND"
        self.load([{"reading": 10, "payload": value}, {"reading": 11, "payload": "next"}])
        win = self.win
        self.assertIn("…", win.preview.item("1", "values")[1])
        self.select(1)
        self.assertIn(json.dumps(value, ensure_ascii=False), self.contents())
        self.assertIn("Record 1", win.preview_record_label.cget("text"))
        self.assertEqual(win.preview_values.cget("state"), "disabled")
        self.assertEqual(len(win.preview_split.panes()), 2)
        win.preview_values.tag_add("sel", "1.0", "end-1c")
        self.assertTrue(win.preview_values.tag_ranges("sel"))
        self.assertEqual(win.preview_warning.winfo_manager(), "")
        self.select(2)
        self.assertIn('"next"', self.contents())
        self.assertNotIn("END", self.contents())

    def test_null_empty_absent_boolean_and_numbers_remain_distinct(self):
        self.load(
            [
                {
                    "reading": 10,
                    "null_value": None,
                    "empty": "",
                    "boolean": False,
                    "number": 0,
                    "text": "null",
                    "nested": {"text": "0"},
                },
                {"reading": 11, "absent": "present only here"},
            ]
        )
        self.select(1)
        output = self.contents()
        for text in (
            "null_value\nnull\n",
            'empty\n""\n',
            "absent\nMissing\n",
            "boolean\nfalse\n",
            "number\n0\n",
            'text\n"null"\n',
            'nested.text\n"0"\n',
        ):
            self.assertIn(text, output)

    def test_warning_stays_pinned_while_full_values_scroll_and_selection_changes(self):
        self.load(
            [
                {"reading": None, "payload": "a" * 4096},
                {"reading": 10},
                {"reading": None, "payload": "b" * 4096},
            ]
        )
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        win.update()
        note = self.open_warning("features", "missing or nonnumeric")
        self.select(3)
        self.assertIn('"' + "b" * 4096 + '"', self.contents())
        win.preview_values.yview_moveto(1)
        win.update()
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertTrue(win.preview_warning.winfo_viewable())
        self.assertLess(win.preview_warning.winfo_rooty(), win.preview_values.winfo_rooty())
        self.assertGreater(win.preview_values.winfo_height(), 40)
        self.assertIs(win._preview_note, note)

    def test_reference_and_related_records_keep_correct_source_labels(self):
        ref = dataset(
            [{"reading": 1}] * 5 + [{"reading": None, "payload": "reference-only"}], "baseline.json"
        )
        self.load(
            [{"reading": 10, "id": "same"}, {"reading": 11, "id": "same"}],
            ref,
            config(event_id="id"),
        )
        self.open_warning("features", "Reference 'reading' uses")
        self.assertIn('"reference-only"', self.contents())
        self.assertIn(
            "Reference · baseline.json · Record 6", self.win.preview_record_label.cget("text")
        )
        note = self.open_warning("event_id", "Repeated IDs")
        self.select(1)
        self.assertIn(
            "Incoming · incoming.json · Record 1 · related",
            self.win.preview_record_label.cget("text"),
        )
        self.assertEqual(self.win.preview_warning.cget("text"), note.text)
        self.assertNotIn("reference-only", self.contents())

    def test_paging_back_and_mapping_changes_do_not_leave_stale_values(self):
        self.load(
            [{"reading": 10, "payload": "valid"}]
            + [{"reading": None, "payload": f"record-{i}"} for i in range(2, 205)]
        )
        win = self.win
        self.open_warning("features", "missing or nonnumeric")
        self.assertIn('"record-2"', self.contents())
        win.preview_next.invoke()
        win.update()
        self.assertIn('"record-102"', self.contents())
        self.assertNotIn('"record-2"', self.contents())
        win.preview_back.invoke()
        win.update()
        self.assertEqual(self.contents(), "")
        self.assertEqual(len(win.preview_split.panes()), 1)
        self.open_warning("features", "missing or nonnumeric")
        win.threshold.set("7")
        win.update()
        self.assertEqual(self.contents(), "")
        self.assertIsNone(win._preview_note)

    def test_source_replacement_and_selection_clear_remove_old_inspection(self):
        self.load([{"reading": 10, "payload": "old"}])
        self.select(1)
        self.win.preview.selection_remove("1")
        self.win.update()
        self.assertEqual(self.contents(), "")
        self.select(1)
        self.win.current = dataset([{"reading": 20, "payload": "new"}])
        # Even a queued selection event cannot read the previous source.
        self.win._inspect_preview()
        self.assertEqual(self.contents(), "")
        self.win._refresh_data()
        self.select(1)
        self.assertIn('"new"', self.contents())
        self.assertNotIn('"old"', self.contents())

    def test_real_row_click_and_keyboard_selection_preserve_analysis_and_settings(self):
        self.load([{"reading": 10, "payload": "first"}, {"reading": 11, "payload": "second"}])
        win = self.win
        win.result = engine.analyze(win.current, win.reference, win.config())
        win.run_config = win.config()
        before = copy.deepcopy(
            (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        win.deiconify()
        win.update()
        x, y, width, height = win.preview.bbox("1")
        win.preview.event_generate("<Button-1>", x=x + 20, y=y + height // 2)
        win.preview.event_generate("<ButtonRelease-1>", x=x + 20, y=y + height // 2)
        win.update()
        self.assertIn('"first"', self.contents())
        win.preview.focus_force()
        win.preview.event_generate("<Down>")
        win.update()
        self.assertIn('"second"', self.contents())
        self.assertEqual(
            before, (win.current, win.reference, win.config(), win.result, win.run_config)
        )

    def test_record_navigation_crosses_pages_and_preserves_evidence(self):
        self.load(
            [{"reading": None, "payload": f"value-{i}"} for i in range(1, 206)] + [{"reading": 10}]
        )
        win = self.win
        before = copy.deepcopy(
            (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        note = self.open_warning("features", "missing or nonnumeric")
        self.assertTrue(win.preview_record_previous.instate(["disabled"]))
        self.assertEqual(win.preview_record_position.cget("text"), "1 of 205 affected")
        self.select(100)
        win.preview_record_next.invoke()
        win.update()
        self.assertEqual(win._preview_page, 1)
        self.assertEqual(win.preview.selection(), ("101",))
        self.assertIn('"value-101"', self.contents())
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        win.preview_record_previous.invoke()
        win.update()
        self.assertEqual(win._preview_page, 0)
        self.assertEqual(win.preview.selection(), ("100",))
        win.preview_next.invoke()
        win.preview_next.invoke()
        self.select(205)
        self.assertTrue(win.preview_record_next.instate(["disabled"]))
        win._preview_record_step(1)
        self.assertEqual(win.preview.selection(), ("205",))
        self.assertEqual(win.preview_record_position.cget("text"), "205 of 205 affected")
        self.assertEqual(
            before, (win.current, win.reference, win.config(), win.result, win.run_config)
        )

    def test_related_records_are_skipped_in_both_directions(self):
        self.load(
            [{"reading": 10, "id": "a"}] * 99
            + [{"reading": 10, "id": "b"}, {"reading": 10, "id": "b"}],
            cfg=config(event_id="id"),
        )
        win = self.win
        self.open_warning("event_id", "Repeated IDs")
        self.assertEqual(win.preview_record_position.cget("text"), "1 of 99 affected")
        self.select(99)
        win.preview_record_next.invoke()
        win.update()
        self.assertEqual(win._preview_page, 1)
        self.assertEqual(win.preview.selection(), ("101",))
        win.preview_record_previous.invoke()
        win.update()
        self.assertEqual(win.preview.selection(), ("99",))
        self.select(100)
        self.assertEqual(win.preview_record_position.cget("text"), "Related · 99 affected")
        win.preview_record_previous.invoke()
        win.update()
        self.assertEqual(win.preview.selection(), ("99",))
        self.select(100)
        win.preview_record_next.invoke()
        win.update()
        self.assertEqual(win.preview.selection(), ("101",))

    def test_reference_navigation_and_single_record_boundaries(self):
        self.load(
            [{"reading": 10}],
            dataset(
                [{"reading": 10}] * 5
                + [{"reading": None, "payload": "first"}, {"reading": None, "payload": "last"}],
                "reference.json",
            ),
        )
        win = self.win
        note = self.open_warning("features", "Reference 'reading' uses")
        win.preview_record_next.invoke()
        win.update()
        self.assertIn(
            "Reference · reference.json · Record 7", win.preview_record_label.cget("text")
        )
        self.assertIn('"last"', self.contents())
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertTrue(win.preview_record_next.instate(["disabled"]))
        self.load([{"reading": None}, {"reading": 10}])
        self.open_warning("features", "missing or nonnumeric")
        self.assertEqual(win.preview_record_position.cget("text"), "1 of 1 affected")
        for button in (win.preview_record_previous, win.preview_record_next):
            self.assertTrue(button.instate(["disabled"]))

    def test_navigation_clears_and_rejects_replaced_sources_or_warnings(self):
        self.load([{"reading": None}, {"reading": None}, {"reading": 10}])
        win = self.win
        self.open_warning("features", "missing or nonnumeric")
        win.current = dataset(
            [{"reading": None}, {"reading": None}, {"reading": 10}], "replacement.json"
        )
        win._preview_record_step(1)
        self.assertEqual(win.preview.selection(), ("1",))
        win._refresh_data()
        self.open_warning("features", "missing or nonnumeric")
        win.mapping_report = None
        win._preview_record_step(1)
        self.assertEqual(win.preview.selection(), ("1",))
        win._reset_preview()
        self.select(1)
        self.assertEqual(win.preview_record_actions.winfo_manager(), "")
        self.assertEqual(win.preview_record_position.cget("text"), "")

    def test_navigation_and_warning_stay_visible_at_minimum_size(self):
        self.load([{"reading": None, "payload": "long value " * 300}] * 2 + [{"reading": 10}])
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        note = self.open_warning("features", "missing or nonnumeric")
        win.preview_record_next.invoke()
        win.update()
        win.preview_values.yview_moveto(1)
        win.update()
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertTrue(win.preview_warning.winfo_viewable())
        self.assertTrue(win.preview_record_next.winfo_viewable())
        self.assertLess(win.preview_record_actions.winfo_rooty(), win.preview_values.winfo_rooty())
        self.assertGreater(win.preview_values.winfo_height(), 40)

    def test_copy_full_value_and_record_preserves_types_and_evidence(self):
        value = '猫🙂\\quoted"\n\t' * 250 + "\0END"
        self.load(
            [
                {
                    "reading": None,
                    "payload": value,
                    "empty": "",
                    "flag": False,
                    "number": 0,
                    "literal": "null",
                    "nested": {"key": "value"},
                },
                {"reading": 10, "absent": 1},
            ]
        )
        win = self.win
        note = self.open_warning("features", "missing or nonnumeric")
        before = copy.deepcopy(
            (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        # Intercept clipboard writes so tests never replace the user's clipboard.
        with (
            patch.object(win, "clipboard_clear") as clear,
            patch.object(win, "clipboard_append") as append,
        ):
            for field in ("payload", "empty", "flag", "number", "literal", "reading", "nested.key"):
                win.preview_copy_field.set(field)
                win.preview_field_choice.event_generate("<<ComboboxSelected>>")
                win.update()
                win.preview_copy_value.invoke()
                self.assertEqual(json.loads(append.call_args.args[0]), win.current.rows[0][field])
                self.assertEqual(
                    type(json.loads(append.call_args.args[0])), type(win.current.rows[0][field])
                )
                self.assertEqual(win.status.get(), "Value copied as JSON.")
            win.preview_copy_record.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), win.current.rows[0])
            self.assertNotIn("absent", json.loads(append.call_args.args[0]))
            self.assertEqual(clear.call_count, 8)
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertEqual(
            before, (win.current, win.reference, win.config(), win.result, win.run_config)
        )

    def test_copy_missing_field_does_not_touch_clipboard(self):
        self.load([{"reading": 10}, {"reading": 11, "other": None}])
        win = self.win
        self.select(1)
        win.preview_copy_field.set("other")
        win._preview_field_changed()
        self.assertTrue(win.preview_copy_value.instate(["disabled"]))
        with (
            patch.object(win, "clipboard_clear") as clear,
            patch.object(win, "clipboard_append") as append,
        ):
            win._copy_preview(False)
            clear.assert_not_called()
            append.assert_not_called()
        self.select(2)
        self.assertFalse(win.preview_copy_value.instate(["disabled"]))
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append") as append:
            win.preview_copy_value.invoke()
            self.assertEqual(append.call_args.args[0], "null")

    def test_copy_tracks_page_navigation_reference_and_related_records(self):
        self.load(
            [{"reading": 10, "id": "same", "payload": f"row-{i}"} for i in range(1, 103)],
            dataset(
                [{"reading": 10}] * 5 + [{"reading": None, "payload": "reference"}], "ref.json"
            ),
            config(event_id="id"),
        )
        win = self.win
        self.open_warning("event_id", "Repeated IDs")
        win.preview_copy_field.set("payload")
        self.select(100)
        win.preview_record_next.invoke()
        win.update()
        self.assertEqual(win.preview_copy_field.get(), "payload")
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append") as append:
            win.preview_copy_value.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), "row-101")
            win.preview_previous.invoke()
            self.select(1)
            win.preview_copy_record.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), win.current.rows[0])
            self.assertIn("related", win.preview_record_label.cget("text"))
            self.open_warning("features", "Reference 'reading' uses")
            win.preview_copy_record.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), win.reference.rows[5])

    def test_copy_rejects_stale_source_warning_and_cleared_selection(self):
        for change in ("source", "warning", "selection"):
            with self.subTest(change=change):
                self.load([{"reading": None}, {"reading": 10}])
                win = self.win
                self.open_warning("features", "missing or nonnumeric")
                if change == "source":
                    win.current = dataset([{"reading": 5}])
                elif change == "warning":
                    win.mapping_report = None
                else:
                    win.preview.selection_remove(*win.preview.selection())
                with (
                    patch.object(win, "clipboard_clear") as clear,
                    patch.object(win, "clipboard_append") as append,
                ):
                    win._copy_preview(True)
                    clear.assert_not_called()
                    append.assert_not_called()
                self.assertEqual(win.preview_copy_actions.winfo_manager(), "")
                self.assertTrue(win.preview_copy_record.instate(["disabled"]))

    def test_clipboard_failure_is_visible_without_losing_warning(self):
        self.load([{"reading": None}, {"reading": 10}])
        win = self.win
        note = self.open_warning("features", "missing or nonnumeric")
        with (
            patch.object(win, "clipboard_clear", side_effect=tk.TclError("busy")),
            patch.object(win, "clipboard_append") as append,
        ):
            win.preview_copy_record.invoke()
            append.assert_not_called()
        self.assertEqual(win.status.get(), "Could not copy. Try again.")
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertEqual(win.preview.selection(), ("1",))
        with (
            patch.object(win, "clipboard_clear"),
            patch.object(win, "clipboard_append", side_effect=tk.TclError("busy")),
        ):
            win.preview_copy_value.invoke()
        self.assertEqual(win.status.get(), "Could not copy. Try again.")

    def test_copy_controls_and_warning_remain_visible_when_values_scroll(self):
        self.load([{"reading": None, "payload": "long " * 700}, {"reading": 10}])
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        note = self.open_warning("features", "missing or nonnumeric")
        win.preview_copy_field.set("payload")
        win.preview_field_choice.event_generate("<<ComboboxSelected>>")
        win.update()
        win.preview_values.yview_moveto(1)
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append"):
            win.preview_copy_value.invoke()
        win.update()
        for widget in (
            win.preview_warning,
            win.preview_field_choice,
            win.preview_copy_value,
            win.preview_copy_record,
        ):
            self.assertTrue(widget.winfo_viewable())
            self.assertLess(widget.winfo_rooty(), win.preview_values.winfo_rooty())
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertGreater(win.preview_values.winfo_height(), 40)
        self.assertLessEqual(
            win.preview_copy_record.winfo_rootx() + win.preview_copy_record.winfo_width(),
            win.preview_values_pane.winfo_rootx() + win.preview_values_pane.winfo_width(),
        )

    def test_record_search_names_full_values_case_unicode_and_literal_punctuation(self):
        self.load(
            [
                {
                    "reading": None,
                    "Payload": "prefix " * 300 + "猫 END.[x]",
                    "user": "Straße",
                    "other": "unrelated",
                },
                {"reading": 10},
            ]
        )
        win = self.win
        note = self.open_warning("features", "missing or nonnumeric")
        for query, fields in (
            ("payLOAD", ["Payload"]),
            ("end.[X]", ["Payload"]),
            ("猫", ["Payload"]),
            ("STRASSE", ["user"]),
            (".*", []),
        ):
            with self.subTest(query=query):
                win.preview_search.set(query)
                win.update()
                self.assertEqual(win._preview_visible_fields, fields)
                self.assertEqual(
                    win.preview_search_count.cget("text"), f"{len(fields)} of 4 fields"
                )
                self.assertEqual(win.preview_warning.cget("text"), note.text)
                if fields:
                    self.assertIn(
                        json.dumps(win.current.rows[0][fields[0]], ensure_ascii=False),
                        self.contents(),
                    )
                else:
                    self.assertEqual(self.contents(), "No matching fields.")
        win.preview_search_clear.invoke()
        self.assertEqual(len(win._preview_visible_fields), 4)
        self.assertIn('"unrelated"', self.contents())

    def test_record_search_keeps_types_and_missing_fields_explicit(self):
        self.load(
            [
                {
                    "reading": 10,
                    "empty": "",
                    "null_value": None,
                    "flag": False,
                    "zero": 0,
                    "text": "null",
                    "nested": {"name": "a\nb"},
                },
                {"reading": 11, "absent": "elsewhere"},
            ]
        )
        self.select(1)
        win = self.win
        for query, fields in (
            ("null", ["null_value", "text"]),
            ('""', ["empty"]),
            ("false", ["flag"]),
            ("missing", ["absent"]),
            ("nested.name", ["nested.name"]),
            (r"a\nb", ["nested.name"]),
        ):
            win.preview_search.set(query)
            self.assertEqual(win._preview_visible_fields, fields)
        win.preview_search.set("absent")
        self.assertTrue(win.preview_copy_value.instate(["disabled"]))
        self.assertIn("Missing", self.contents())

    def test_record_search_and_copy_do_not_change_evidence_or_record_scope(self):
        self.load([{"reading": None, "payload": "visible", "extra": "keep me"}, {"reading": 10}])
        win = self.win
        self.open_warning("features", "missing or nonnumeric")
        before = copy.deepcopy(
            (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        win.preview_search.set("payload")
        self.assertEqual(tuple(win.preview_field_choice.cget("values")), ("payload",))
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append") as append:
            win.preview_copy_value.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), "visible")
            win.preview_search.set("no matches")
            self.assertTrue(win.preview_copy_value.instate(["disabled"]))
            win.preview_copy_record.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), win.current.rows[0])
        self.assertEqual(
            before, (win.current, win.reference, win.config(), win.result, win.run_config)
        )

    def test_record_search_follows_selection_and_pages_then_resets_for_new_source(self):
        self.load(
            [{"reading": None, "payload": f"row-{i}"} for i in range(1, 102)] + [{"reading": 10}],
            dataset([{"reading": 10}] * 5 + [{"reading": None, "ref": "only"}], "ref.json"),
        )
        win = self.win
        self.open_warning("features", "missing or nonnumeric")
        win.preview_search.set("row-101")
        self.assertEqual(win._preview_visible_fields, [])
        self.select(100)
        win.preview_record_next.invoke()
        win.update()
        self.assertEqual(win.preview_search.get(), "row-101")
        self.assertEqual(win._preview_visible_fields, ["payload"])
        self.assertIn('"row-101"', self.contents())
        self.open_warning("features", "Reference 'reading' uses")
        self.assertEqual(win.preview_search.get(), "")
        win.preview_search.set("only")
        self.assertEqual(win._preview_visible_fields, ["ref"])
        win.threshold.set("7")
        win.update()
        self.assertEqual(win.preview_search.get(), "")
        self.assertEqual(win.preview_search_actions.winfo_manager(), "")
        self.assertEqual(self.contents(), "")

    def test_record_search_rejects_stale_source_or_warning(self):
        for change in ("source", "warning", "selection"):
            with self.subTest(change=change):
                self.load([{"reading": None, "payload": "old"}, {"reading": 10}])
                win = self.win
                self.open_warning("features", "missing or nonnumeric")
                if change == "source":
                    win.current = dataset([{"reading": 20, "payload": "new"}])
                elif change == "warning":
                    win.mapping_report = None
                else:
                    win.preview.selection_remove(*win.preview.selection())
                win.preview_search.set("old")
                self.assertEqual(self.contents(), "")
                self.assertEqual(win.preview_search_actions.winfo_manager(), "")

    def test_record_search_keyboard_clear_and_pinned_warning_at_minimum_size(self):
        self.load([{"reading": None, "payload": "long " * 700}, {"reading": 10}])
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        note = self.open_warning("features", "missing or nonnumeric")
        win.preview_search_entry.focus_force()
        win.preview_search_entry.insert(0, "payload")
        win.update()
        self.assertIs(win.focus_get(), win.preview_search_entry)
        win.preview_values.yview_moveto(1)
        win.update()
        for widget in (win.preview_warning, win.preview_search_entry, win.preview_search_count):
            self.assertTrue(widget.winfo_viewable())
            self.assertLess(widget.winfo_rooty(), win.preview_values.winfo_rooty())
        self.assertGreater(win.preview_values.winfo_height(), 40)
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        win.preview_search_entry.event_generate("<Escape>")
        win.update()
        self.assertEqual(win.preview_search.get(), "")
        self.assertEqual(win._preview_visible_fields, ["reading", "payload"])

    def test_match_highlights_exact_unicode_spans_in_names_and_full_values(self):
        self.load(
            [
                {"reading": None, "Straße": "🙂Straße " + "x" * 500 + " STRASSE", "other": "ßß"},
                {"reading": 10},
            ]
        )
        win = self.win
        self.open_warning("features", "missing or nonnumeric")
        win.preview_search.set("strasse")
        self.assertEqual(
            [win.preview_values.get(a, b) for _, a, b in win._preview_matches],
            ["Straße", "Straße", "STRASSE"],
        )
        self.assertEqual(len(win.preview_values.tag_ranges("search_match")), 6)
        self.assertEqual(win.preview_match_count.cget("text"), "1 of 3 matches")
        win.preview_search.set("s")
        actual = [win.preview_values.get(a, b) for _, a, b in win._preview_matches]
        self.assertEqual(actual.count("ß"), 4)  # Name, value, and the two standalone characters.
        win.preview_search.set("🙂")
        self.assertEqual([win.preview_values.get(a, b) for _, a, b in win._preview_matches], ["🙂"])

    def test_match_navigation_boundaries_and_copy_target_preserve_record(self):
        self.load([{"reading": None, "a": "hit hit", "b": "hit", "other": "keep"}, {"reading": 10}])
        win = self.win
        note = self.open_warning("features", "missing or nonnumeric")
        before = copy.deepcopy(
            (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        win.preview_search.set("hit")
        self.assertTrue(win.preview_match_previous.instate(["disabled"]))
        win.preview_match_next.invoke()
        self.assertEqual(win.preview_match_count.cget("text"), "2 of 3 matches")
        win.preview_match_next.invoke()
        self.assertTrue(win.preview_match_next.instate(["disabled"]))
        self.assertEqual(win.preview_copy_field.get(), "b")
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append") as append:
            win.preview_copy_value.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), "hit")
            win.preview_copy_record.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), win.current.rows[0])
        win._preview_match_step(1)
        self.assertEqual(win._preview_match_index, 2)
        win.preview_match_previous.invoke()
        self.assertEqual(win._preview_match_index, 1)
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertEqual(
            before, (win.current, win.reference, win.config(), win.result, win.run_config)
        )

    def test_match_reset_on_query_page_source_and_stale_navigation(self):
        self.load([{"reading": None, "payload": "hit hit"}] * 101 + [{"reading": 10}])
        win = self.win
        self.open_warning("features", "missing or nonnumeric")
        self.select(100)
        win.preview_search.set("hit")
        win.preview_match_next.invoke()
        win.preview_record_next.invoke()
        win.update()
        self.assertEqual(win.preview.selection(), ("101",))
        self.assertEqual(win.preview_match_count.cget("text"), "1 of 2 matches")
        win.preview_search.set("missing")
        self.assertEqual(win.preview_match_count.cget("text"), "No matches")
        self.assertEqual(win.preview_values.tag_ranges("search_match"), ())
        for button in (win.preview_match_previous, win.preview_match_next):
            self.assertTrue(button.instate(["disabled"]))
        win.preview_search.set("hit")
        win.current = dataset([{"reading": 10, "payload": "new"}])
        win._preview_match_step(1)
        self.assertEqual(win._preview_matches, [])
        self.assertEqual(win.preview_match_actions.winfo_manager(), "")
        self.assertEqual(self.contents(), "")

    def test_missing_and_json_escape_matches_keep_display_and_types(self):
        self.load(
            [
                {"reading": 10, "payload": "a\nb\nc", "null_value": None},
                {"reading": 11, "absent": "elsewhere"},
            ]
        )
        self.select(1)
        win = self.win
        win.preview_search.set(r"\n")
        self.assertEqual(
            [win.preview_values.get(a, b) for _, a, b in win._preview_matches], [r"\n", r"\n"]
        )
        win.preview_search.set("Missing")
        self.assertEqual(
            [win.preview_values.get(a, b) for _, a, b in win._preview_matches], ["Missing"]
        )
        self.assertTrue(win.preview_copy_value.instate(["disabled"]))
        win.preview_search.set("")
        self.assertEqual(win._preview_matches, [])
        self.assertEqual(win.preview_values.tag_ranges("search_current"), ())
        self.assertEqual(win.preview_match_actions.winfo_manager(), "")

    def focus_for_keyboard(self, widget):
        # Window activation and queued focus events must settle before a key is
        # generated. Retry readiness only, never the key or its expected result.
        deadline = time.monotonic() + 1.0
        while True:
            self.win.update()
            widget.focus_force()
            self.win.update()
            if widget.winfo_viewable() and self.win.focus_get() is widget:
                return
            if time.monotonic() >= deadline:
                self.fail(f"Keyboard target not ready: focus={self.win.focus_get()}, "
                          f"viewable={widget.winfo_viewable()}")
            time.sleep(0.01)

    def test_match_keyboard_with_pending_focus_transfer(self):
        entry = self.win.preview_search_entry
        original = entry.focus_force
        pending = True

        def request_focus():
            nonlocal pending
            original()
            if pending:
                pending = False
                self.win.after_idle(self.win.preview.focus_set)

        with patch.object(entry, "focus_force", side_effect=request_focus):
            self.test_match_keyboard_scroll_and_warning_visible_at_minimum_size()

    def test_match_keyboard_scroll_and_warning_visible_at_minimum_size(self):
        self.load([{"reading": None, "payload": "hit " + "x " * 1400 + "hit"}, {"reading": 10}])
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        note = self.open_warning("features", "missing or nonnumeric")
        win.preview_search.set("hit")
        self.focus_for_keyboard(win.preview_search_entry)
        win.preview_search_entry.event_generate("<F3>")
        win.update()
        self.assertEqual(win._preview_match_index, 1)
        _, start, _ = win._preview_matches[1]
        self.assertIsNotNone(win.preview_values.bbox(start))
        self.assertIs(win.focus_get(), win.preview_search_entry)
        for widget in (win.preview_warning, win.preview_match_next, win.preview_match_count):
            self.assertTrue(widget.winfo_viewable())
            self.assertLess(widget.winfo_rooty(), win.preview_values.winfo_rooty())
        self.assertGreater(win.preview_values.winfo_height(), 40)
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.focus_for_keyboard(win.preview_search_entry)
        win.preview_search_entry.event_generate("<Shift-F3>")
        win.update()
        self.assertEqual(win._preview_match_index, 0)

    def click_match(self, number, offset=0):
        win = self.win
        index = win.preview_values.index(f"{win._preview_matches[number][1]}+{offset}c")
        win.preview_values.see(index)
        win.update()
        x, y, width, height = win.preview_values.bbox(index)
        point = (x + max(1, width // 2), y + height // 2)
        win.preview_values.focus_force()
        win.preview_values.event_generate("<Button-1>", x=point[0], y=point[1])
        win.preview_values.event_generate("<ButtonRelease-1>", x=point[0], y=point[1])
        win.update()
        return point

    def test_click_match_selects_its_field_and_copies_complete_value(self):
        self.load(
            [{"reading": None, "first": "hit", "second": "before hit after"}, {"reading": 10}]
        )
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        note = self.open_warning("features", "missing or nonnumeric")
        before = copy.deepcopy(
            (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        win.preview_search.set("hit")
        win.update()
        with (
            patch.object(win, "clipboard_clear") as clear,
            patch.object(win, "clipboard_append") as append,
        ):
            self.click_match(1, 1)
            clear.assert_not_called()
            append.assert_not_called()
            self.assertEqual(win.preview_match_count.cget("text"), "2 of 2 matches")
            self.assertEqual(win.preview_copy_field.get(), "second")
            self.assertEqual(
                tuple(map(str, win.preview_values.tag_ranges("search_current"))),
                win._preview_matches[1][1:],
            )
            win.preview_copy_value.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), "before hit after")
            win.preview_copy_record.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), win.current.rows[0])
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertTrue(win.preview_warning.winfo_viewable())
        self.assertEqual(
            before, (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        win.preview_values.event_generate("<Shift-F3>")
        win.update()
        self.assertEqual(win._preview_match_index, 0)

    def test_click_wrapped_unicode_and_name_matches_hits_exact_occurrence(self):
        self.load([{"reading": 10, "Straße": "🙂 " + "x " * 1200 + "Straße"}])
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        self.select(1)
        win.preview_search.set("strasse")
        win.update()
        self.click_match(1, 4)
        self.assertEqual(win._preview_match_index, 1)
        self.assertEqual(win.preview_copy_field.get(), "Straße")
        self.click_match(0, 1)
        self.assertEqual(win._preview_match_index, 0)
        win.preview_search.set("🙂")
        win.update()
        self.click_match(0)
        self.assertEqual(win._preview_match_index, 0)
        self.assertEqual(win.preview_values.get(*win._preview_matches[0][1:]), "🙂")

    def test_blank_space_and_plain_text_do_not_select_nearest_match(self):
        self.load([{"reading": 10, "a": "hit", "b": "hit tail"}])
        win = self.win
        win.deiconify()
        self.select(1)
        win.preview_search.set("hit")
        win.update()
        text = win.preview_values
        _, start, end = win._preview_matches[1]
        text.see(start)
        win.update()
        x, y, _, height = text.bbox(start)
        for px, py in ((text.winfo_width() - 22, y + height // 2), (2, y + height // 2)):
            text.event_generate("<Button-1>", x=px, y=py)
            text.event_generate("<ButtonRelease-1>", x=px, y=py)
            win.update()
            self.assertEqual(win._preview_match_index, 0)
            self.assertEqual(win.preview_copy_field.get(), "a")
        x, y, width, height = text.bbox(end)
        text.event_generate("<Button-1>", x=x + width // 2, y=y + height // 2)
        win.update()
        self.assertEqual(win._preview_match_index, 0)
        self.assertIsNone(win._preview_match_at(x + width // 2, y + height // 2))

    def test_clicked_match_preserves_drag_selection_and_cursor_feedback(self):
        self.load([{"reading": 10, "payload": "hit tail"}])
        win = self.win
        win.deiconify()
        self.select(1)
        win.preview_search.set("hit")
        win.update()
        text = win.preview_values
        start = win._preview_matches[0][1]
        x, y, width, height = text.bbox(start)
        point = (x + 1, y + height // 2)
        text.event_generate("<Motion>", x=point[0], y=point[1])
        self.assertEqual(text.cget("cursor"), "hand2")
        text.event_generate("<Button-1>", x=point[0], y=point[1])
        end_x, end_y, _, end_height = text.bbox(f"{start}+7c")
        text.event_generate("<B1-Motion>", x=end_x, y=end_y + end_height // 2)
        text.event_generate("<ButtonRelease-1>", x=end_x, y=end_y + end_height // 2)
        win.update()
        self.assertTrue(text.tag_ranges("sel"))
        self.assertIn("hit", text.get("sel.first", "sel.last"))
        text.event_generate("<Leave>")
        self.assertEqual(text.cget("cursor"), "xterm")

    def test_click_rejects_stale_source_and_missing_field_stays_uncopyable(self):
        self.load([{"reading": None}, {"reading": 10, "absent": "value"}])
        win = self.win
        win.deiconify()
        self.open_warning("features", "missing or nonnumeric")
        win.preview_search.set("Missing")
        win.update()
        point = self.click_match(0)
        self.assertEqual(win.preview_copy_field.get(), "absent")
        self.assertTrue(win.preview_copy_value.instate(["disabled"]))
        win.current = dataset([{"reading": 10}])
        win.preview_values.event_generate("<Button-1>", x=point[0], y=point[1])
        win.update()
        self.assertEqual(self.contents(), "")
        self.assertEqual(win._preview_matches, [])
        self.assertTrue(win.preview_copy_value.instate(["disabled"]))

    def test_copy_match_uses_clicked_original_text_while_value_keeps_full_field(self):
        self.load(
            [{"reading": None, "a": "Straße", "b": "before 🙂STRASSE after"}, {"reading": 10}]
        )
        win = self.win
        win.deiconify()
        win.geometry("1100x760")
        note = self.open_warning("features", "missing or nonnumeric")
        before = copy.deepcopy(
            (win.current, win.reference, win.config(), win.result, win.run_config)
        )
        win.preview_search.set("strasse")
        win.update()
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append") as append:
            win.preview_copy_match.invoke()
            self.assertEqual(append.call_args.args[0], "Straße")
            self.click_match(1)
            win.preview_values.tag_add("sel", "1.0", "end-1c")
            win.preview_copy_match.invoke()
            self.assertEqual(append.call_args.args[0], "STRASSE")
            self.assertEqual(win.status.get(), "Match copied as displayed text.")
            win.preview_copy_value.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), "before 🙂STRASSE after")
            win.preview_copy_record.invoke()
            self.assertEqual(json.loads(append.call_args.args[0]), win.current.rows[0])
        self.assertEqual(win.preview_warning.cget("text"), note.text)
        self.assertTrue(win.preview_warning.winfo_viewable())
        self.assertTrue(win.preview_copy_match.winfo_viewable())
        self.assertLessEqual(
            win.preview_copy_match.winfo_rootx() + win.preview_copy_match.winfo_width(),
            win.preview_values_pane.winfo_rootx() + win.preview_values_pane.winfo_width(),
        )
        self.assertEqual(
            before, (win.current, win.reference, win.config(), win.result, win.run_config)
        )

    def test_copy_match_names_escapes_emoji_and_displayed_missing_marker(self):
        self.load([{"reading": 10, "Straße": "🙂a\nb"}, {"reading": 11, "absent": "elsewhere"}])
        win = self.win
        self.select(1)
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append") as append:
            for query, expected in (
                ("strasse", "Straße"),
                ("🙂", "🙂"),
                (r"\n", r"\n"),
                ("missing", "Missing"),
            ):
                win.preview_search.set(query)
                win.preview_copy_match.invoke()
                self.assertEqual(append.call_args.args[0], expected)
            self.assertTrue(win.preview_copy_value.instate(["disabled"]))
            self.assertFalse(win.preview_copy_match.instate(["disabled"]))

    def test_copy_match_empty_clear_and_stale_context_do_not_touch_clipboard(self):
        for change in ("no_match", "clear", "source", "warning", "selection"):
            with self.subTest(change=change):
                self.load([{"reading": None, "payload": "hit"}, {"reading": 10}])
                win = self.win
                self.open_warning("features", "missing or nonnumeric")
                win.preview_search.set("hit")
                if change == "no_match":
                    win.preview_search.set("no such text")
                elif change == "clear":
                    win.preview_search.set("")
                elif change == "source":
                    win.current = dataset([{"reading": 10}])
                elif change == "warning":
                    win.mapping_report = None
                else:
                    win.preview.selection_remove(*win.preview.selection())
                with (
                    patch.object(win, "clipboard_clear") as clear,
                    patch.object(win, "clipboard_append") as append,
                ):
                    win._copy_preview_match()
                    clear.assert_not_called()
                    append.assert_not_called()
                self.assertTrue(win.preview_copy_match.instate(["disabled"]))

    def test_copy_match_follows_navigation_pages_and_reference(self):
        self.load(
            [{"reading": None, "payload": "hit HIT"}] * 100
            + [{"reading": None, "payload": "HiT"}, {"reading": 10}],
            dataset([{"reading": 10}] * 5 + [{"reading": None, "payload": "hIt"}], "ref.json"),
        )
        win = self.win
        self.open_warning("features", "missing or nonnumeric")
        self.select(100)
        win.preview_search.set("hit")
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append") as append:
            win.preview_match_next.invoke()
            win.preview_copy_match.invoke()
            self.assertEqual(append.call_args.args[0], "HIT")
            win.preview_record_next.invoke()
            win.update()
            win.preview_copy_match.invoke()
            self.assertEqual(append.call_args.args[0], "HiT")
            self.open_warning("features", "Reference 'reading' uses")
            win.preview_search.set("hit")
            win.preview_copy_match.invoke()
            self.assertEqual(append.call_args.args[0], "hIt")

    def test_copy_match_clipboard_error_keeps_selection_and_warning(self):
        self.load([{"reading": None, "payload": "hit HIT"}, {"reading": 10}])
        win = self.win
        note = self.open_warning("features", "missing or nonnumeric")
        win.preview_search.set("hit")
        win.preview_match_next.invoke()
        for failing_method in ("clipboard_clear", "clipboard_append"):
            with (
                patch.object(win, "clipboard_clear"),
                patch.object(win, "clipboard_append"),
                patch.object(win, failing_method, side_effect=tk.TclError("busy")),
            ):
                win.preview_copy_match.invoke()
            self.assertEqual(win.status.get(), "Could not copy. Try again.")
            self.assertEqual(win._preview_match_index, 1)
            self.assertEqual(win.preview_warning.cget("text"), note.text)
        with patch.object(win, "clipboard_clear"), patch.object(win, "clipboard_append") as append:
            win.preview_copy_match.invoke()
            self.assertEqual(append.call_args.args[0], "HIT")


if __name__ == "__main__":
    unittest.main(verbosity=2)

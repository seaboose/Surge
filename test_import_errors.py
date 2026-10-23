"""Import diagnostics must locate problems without silently dropping evidence."""

import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import engine
from import_errors import ImportFailure
from test_workbench import config, dataset, reference


class ImportErrorTests(unittest.TestCase):
    def test_larger_native_manifest_allowance_is_narrow_and_bounded(self):
        native = {"schema": "surge-native-integrity-v1"}
        for name, limit in (("range_manifest", 16384), ("integrity_manifest", 32768)):
            data = engine.parse_bytes(
                json.dumps([{**native, name: "x" * limit}]).encode(), "native.json"
            )
            self.assertEqual(len(data.rows[0][name]), limit)
            self.failure(json.dumps([{**native, name: "x" * (limit + 1)}]))
            self.failure(json.dumps([{name: "x" * 4097}]))
            self.failure(json.dumps([{**native, "nested": {name: "x" * 4097}}]))
        self.failure(json.dumps([{**native, "ordinary": "x" * 4097}]))

    def failure(self, text, name="source.json"):
        with self.assertRaises(ImportFailure) as raised:
            engine.parse_bytes(text.encode("utf-8"), name)
        return raised.exception

    def test_nested_fields_and_multiple_records_are_located(self):
        error = self.failure(
            json.dumps([{"id": "valid"}, {"client": {"values": [1]}}, {"reading": 1e101}, 7])
        )
        self.assertEqual(
            [(x.record, x.field) for x in error.issues],
            [(2, "client.values"), (3, "reading"), (4, None)],
        )
        self.assertIn("Convert arrays", error.issues[0].message)
        self.assertIn("No records were added", str(error))

    def test_jsonl_blank_lines_and_syntax_use_physical_lines(self):
        error = self.failure('\n{"x": 1}\n\n{"x": }\n{"nested":{"x":[]}}\n', "source.jsonl")
        self.assertEqual(
            [(x.record, x.line, x.field) for x in error.issues],
            [(2, 4, None), (3, 5, "nested.x")],
        )
        self.assertEqual(error.issues[0].column, 7)

    def test_json_syntax_has_line_column_without_guessing_a_record(self):
        error = self.failure('[\n {"x": 1},\n {"x": }\n]')
        issue = error.issues[0]
        self.assertEqual((issue.record, issue.line, issue.column), (None, 3, 8))
        self.assertIn("later records were not checked", issue.message)

    def test_duplicate_json_keys_retain_record_and_field(self):
        for body in (
            '[{"ok":1},{"client":{"x":1,"x":2}}]',
            '{"events":[{"ok":1},{"client":{"x":1,"x":2}}]}',
        ):
            issue = self.failure(body).issues[0]
            self.assertEqual((issue.record, issue.field), (2, "client.x"))
            self.assertIn("Duplicate JSON key", issue.message)
        issue = self.failure('{"records":[],"records":[]}').issues[0]
        self.assertEqual(issue.field, "records")

    def test_nonfinite_numbers_and_flattened_collisions_are_located(self):
        error = self.failure('[{"x":NaN},{"x":Infinity},{"a":{"b":1},"a.b":2}]')
        self.assertEqual(
            [(i.record, i.field) for i in error.issues], [(1, "x"), (2, "x"), (3, "a.b")]
        )
        reverse = self.failure('[{"a.b":2,"a":{"b":1}}]').issues[0]
        self.assertEqual(reverse.field, "a.b")

    def test_csv_multiline_values_and_blank_lines_keep_record_positions(self):
        error = self.failure('id,note\none,"two\nlines"\n\nbad\nthree,ok,extra\n', "source.csv")
        self.assertEqual([(x.record, x.line) for x in error.issues], [(2, 5), (3, 6)])
        self.assertIn("Expected 2 values; found 1", error.issues[0].message)
        self.assertIn("cannot be determined reliably", error.issues[0].message)
        valid = engine.parse_bytes(b'id,note\none,"two\nlines"\n', "source.csv")
        self.assertEqual(valid.rows[0]["note"], "two\nlines")

    def test_csv_headers_and_unclosed_quotes_are_located(self):
        issue = self.failure("x,x\n1,2", "source.csv").issues[0]
        self.assertEqual((issue.line, issue.field), (1, "x"))
        self.assertIn("Columns 1 and 2", issue.message)
        issue = self.failure('id,note\none,"unfinished\n', "source.csv").issues[0]
        self.assertEqual(issue.record, 1)
        self.assertIn("Parsing stopped", issue.message)
        issue = self.failure("id,\none,two", "source.csv").issues[0]
        self.assertEqual((issue.line, issue.field), (1, ""))

    def test_diagnostics_are_bounded_and_do_not_echo_record_values(self):
        secret = "PRIVATE-RECORD-CONTENT"
        error = self.failure(json.dumps([{"long": secret * 300}] * 25))
        self.assertEqual(len(error.issues), 20)
        self.assertTrue(error.stopped)
        self.assertNotIn(secret, str(error))
        self.assertIn("more may remain", str(error))
        key = "\npretend status\t" + "a" * 120
        error = self.failure(json.dumps([{key: "private"}]))
        self.assertIn("\\npretend status\\t", str(error))
        self.assertNotIn("\npretend status\t", str(error))

    def test_depth_field_count_encoding_and_io_errors_have_repair_hints(self):
        deep = {"x": 1}
        for _ in range(6):
            deep = {"child": deep}
        self.assertIn("Reduce nesting", self.failure(json.dumps([deep])).issues[0].message)
        fields = {f"f{i}": i for i in range(65)}
        self.assertEqual(self.failure(json.dumps([fields])).issues[0].field, "f64")
        error = self.failure(json.dumps([{f"f{i}": i} for i in range(65)]))
        self.assertEqual((error.issues[0].record, error.issues[0].field), (65, "f64"))
        with self.assertRaises(ImportFailure) as raised:
            engine.parse_bytes(b"x\n\xff", "bad.csv")
        self.assertIn("byte 3", str(raised.exception))
        with patch("pathlib.Path.open", side_effect=PermissionError):
            with self.assertRaises(ImportFailure) as raised:
                engine.load_dataset("unreadable.csv")
        self.assertIn("permission", str(raised.exception))

    def test_limits_and_valid_source_identity_remain_unchanged(self):
        with patch("engine.MAX_ROWS", 2):
            for name, text in (
                ("x.json", '[{"x":1},{"x":2},{"x":3}]'),
                ("x.csv", "x\n1\n2\n3"),
                ("x.jsonl", '{"x":1}\n{"x":2}\n{"x":}'),
            ):
                self.assertIn("10,000 records", str(self.failure(text, name)))
        raw = '\ufeff{"records":[{"client":{"x":1},"empty":null}]}'.encode()
        source = engine.parse_bytes(raw, "source.json")
        self.assertEqual(source.rows, ({"client.x": 1, "empty": None},))
        self.assertEqual(source.text.encode(), raw)
        self.assertEqual(source.digest, engine.sha(raw))


class ImportDialogTests(unittest.TestCase):
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

    def test_failed_reference_keeps_current_evidence_and_results_then_retry_works(self):
        win = self.win
        win.current, win.reference = dataset([{"reading": 100}]), reference()
        win._refresh_data()
        win._apply_config(config())
        win.result = engine.analyze(win.current, win.reference, win.config())
        win.run_config = win.config()
        before = win.current, win.reference, win.result, win.run_config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference.json"
            path.write_text('[{"reading":[]}]')
            with (
                patch("app.filedialog.askopenfilename", return_value=str(path)),
                patch.object(win, "_show_import_error") as report,
            ):
                win._load("reference")
                self.finish()
                error, role = report.call_args.args
                self.assertEqual(role, "reference")
                self.assertEqual(error.issues[0].field, "reading")
                for old, new in zip(
                    before, (win.current, win.reference, win.result, win.run_config)
                ):
                    self.assertIs(old, new)
                path.write_text(
                    '[{"reading":1},{"reading":2},{"reading":3},{"reading":4},{"reading":5}]'
                )
                win._load("reference")
                self.finish()
            self.assertIsNone(win.result)
            self.assertEqual(len(win.reference.rows), 5)

    def test_error_view_is_selectable_scrollable_and_closes(self):
        self.win.deiconify()
        self.win.update()
        try:
            engine.parse_bytes(b'[{"sensor":{"values":[]}}]', "input.json")
        except ImportFailure as error:
            dialog = self.win._show_import_error(error, "current")
        body, actions = dialog.winfo_children()
        dialog.geometry("520x320")
        dialog.update()
        self.assertTrue(actions.winfo_viewable())
        self.assertGreater(actions.winfo_height(), 20)
        self.assertLessEqual(actions.winfo_y() + actions.winfo_height(), dialog.winfo_height())
        text = next(w for w in body.winfo_children() if isinstance(w, tk.Text))
        self.assertIn("Record 1", text.get("1.0", "end"))
        self.assertIn("sensor.values", text.get("1.0", "end"))
        self.assertEqual(text.cget("state"), "disabled")
        text.tag_add("sel", "1.0", "1.end")
        self.assertTrue(text.tag_ranges("sel"))
        self.assertTrue(text.cget("yscrollcommand"))
        actions.winfo_children()[0].invoke()
        self.assertFalse(dialog.winfo_exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

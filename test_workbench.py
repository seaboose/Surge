"""Independent generated inputs exercise adapters, evidence, and UI wiring.

These are test fixtures only; the application ships with no dataset or findings.
"""

import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import engine

ROOT = Path(__file__).resolve().parent
TEMP = ROOT / "verification" / "temporary-test-files"
TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP)


def dataset(rows, name="incoming.json"):
    return engine.parse_bytes(json.dumps(rows).encode(), name)


def config(**changes):
    value = dict(
        features=["reading"],
        session=None,
        event_id=None,
        time=None,
        time_format="milliseconds",
        threshold=6,
        rules=[],
    )
    value.update(changes)
    return value


def reference():
    return dataset([{"reading": v} for v in [8, 9, 10, 11, 12, 9, 10, 11]], "reference.json")


class EngineTests(unittest.TestCase):
    def test_independent_unseen_sources_use_selected_values(self):
        for field, center in [("latency", 20), ("temperature", 300)]:
            baseline = dataset([{field: center + d} for d in [-2, -1, 0, 1, 2]])
            incoming = engine.parse_bytes(
                f"{field}\n{center}\n{center + 100}\n".encode(), "arbitrary.csv"
            )
            result = engine.analyze(incoming, baseline, config(features=[field]))
            self.assertEqual([r["status"] for r in result["records"]], ["No finding", "Review"])
            self.assertEqual(result["records"][1]["evidence"][0]["field"], field)

    def test_csv_jsonl_and_nested_json(self):
        for raw, name in [
            (b"proc.name,value\nworker,12\n", "source.csv"),
            (b'{"proc":{"name":"worker"},"value":12}\n', "source.jsonl"),
            (b'{"events":[{"proc":{"name":"worker"},"value":12}]}', "source.json"),
        ]:
            data = engine.parse_bytes(raw, name)
            self.assertEqual(data.rows[0]["proc.name"], "worker")
            self.assertEqual(engine.number(data.rows[0]["value"]), 12)

    def test_malformed_and_colliding_inputs_rejected(self):
        for raw, name in [
            (b"a,a\n1,2", "bad.csv"),
            (b"a,b\n1", "bad.csv"),
            (b'{"x":1,"x":2}', "bad.jsonl"),
            (b'[{"x":NaN}]', "bad.json"),
            (b'[{"a":{"b":1},"a.b":2}]', "bad.json"),
            (b'[{"a.b":2,"a":{"b":1}}]', "bad.json"),
            (b'[{"x":[1,2]}]', "bad.json"),
        ]:
            with self.subTest(name=name, raw=raw), self.assertRaises(ValueError):
                engine.parse_bytes(raw, name)

    def test_bounds_refuse_truncation(self):
        with patch.object(engine, "MAX_BYTES", 10), self.assertRaises(ValueError):
            engine.parse_bytes(b"a\n1234567890", "big.csv")
        with patch.object(engine, "MAX_ROWS", 2), self.assertRaises(ValueError):
            engine.parse_bytes(b"a\n1\n2\n3", "big.csv")

    def test_rules_work_without_numeric_baseline(self):
        data = dataset([{"operation": "read"}, {"operation": "upload"}, {"other": 1}])
        rule = dict(name="External transfer", field="operation", op="eq", value="upload")
        result = engine.analyze(data, None, config(features=[], rules=[rule]))
        self.assertEqual(
            [r["status"] for r in result["records"]], ["No finding", "Review", "Unknown"]
        )
        self.assertIsNone(result["records"][1]["max_deviation"])

    def test_numeric_rule_and_typed_equality(self):
        data = engine.parse_bytes(b"value\n7\n20\n", "values.csv")
        rule = dict(name="Bound", field="value", op="gt", value=10)
        result = engine.analyze(data, None, config(features=[], rules=[rule]))
        self.assertEqual(result["summary"]["Review"], 1)
        rule.update(op="eq", value=7)
        self.assertEqual(
            engine.analyze(data, None, config(features=[], rules=[rule]))["summary"]["Review"], 0
        )

    def test_numeric_equality_matches_json_numbers_but_not_booleans(self):
        data = dataset([{"value": 7}, {"value": 7.0}, {"value": True}, {"value": "7"}])
        rule = dict(name="Numeric equality", field="value", op="eq", value=7.0)
        result = engine.analyze(data, None, config(features=[], rules=[rule]))
        self.assertEqual(result["summary"]["Review"], 2)
        rule["value"] = float("nan")
        with self.assertRaises(ValueError):
            engine.analyze(data, None, config(features=[], rules=[rule]))

    def test_missing_values_are_unknown_and_gaps_stay_visible_with_findings(self):
        data = dataset([{"reading": None}, {"reading": 100}, {"reading": "unknown"}])
        result = engine.analyze(data, reference(), config())
        self.assertEqual(result["summary"]["Unknown"], 2)
        self.assertEqual(result["summary"]["rows_with_gaps"], 2)
        self.assertEqual(result["summary"]["Review"], 1)

    def test_metadata_and_labels_do_not_automatically_enter_features(self):
        data = dataset(
            [
                {"reading": 10, "label": "attack", "session": "a"},
                {"reading": 100, "label": "legitimate", "session": "b"},
            ]
        )
        result = engine.analyze(data, reference(), config(session="session"))
        self.assertEqual([r["status"] for r in result["records"]], ["No finding", "Review"])
        self.assertEqual(set(result["profiles"]), {"reading"})
        with self.assertRaises(ValueError):
            engine.analyze(data, reference(), config(session="reading"))

    def test_duplicate_ids_are_scoped_to_session(self):
        rows = [{"reading": 10, "s": s, "id": "one"} for s in ["a", "b"]]
        engine.analyze(dataset(rows), reference(), config(session="s", event_id="id"))
        rows[1]["s"] = "a"
        with self.assertRaises(ValueError):
            engine.analyze(dataset(rows), reference(), config(session="s", event_id="id"))

    def test_time_units_sessions_and_clock_reversal(self):
        data = dataset(
            [
                {"reading": 10, "s": "a", "t": 2},
                {"reading": 10, "s": "b", "t": 0},
                {"reading": 10, "s": "a", "t": 1},
            ]
        )
        result = engine.analyze(
            data, reference(), config(session="s", time="t", time_format="seconds")
        )
        self.assertEqual([r["time_ms"] for r in result["records"]], [2000, 0, 1000])
        self.assertEqual(result["summary"]["Unknown"], 1)

    def test_iso_requires_timezone(self):
        data = dataset([{"reading": 10, "t": "2026-10-20T12:00:00Z"}])
        self.assertIsNotNone(
            engine.analyze(data, reference(), config(time="t", time_format="iso8601"))["records"][
                0
            ]["time_ms"]
        )
        data = dataset([{"reading": 10, "t": "2026-10-20T12:00:00"}])
        with self.assertRaises(ValueError):
            engine.analyze(data, reference(), config(time="t", time_format="iso8601"))

    def test_reference_is_required_and_incoming_never_changes_profile(self):
        with self.assertRaises(ValueError):
            engine.analyze(dataset([{"reading": 100}]), None, config())
        result = engine.analyze(dataset([{"reading": 1000000}]), reference(), config())
        self.assertEqual(result["profiles"]["reading"]["center"], 10)
        with self.assertRaises(ValueError):
            engine.analyze(reference(), reference(), config())

    def test_constant_reference_discloses_tolerance(self):
        baseline = dataset([{"reading": 100}] * 5)
        result = engine.analyze(dataset([{"reading": 101}, {"reading": 120}]), baseline, config())
        self.assertEqual(result["profiles"]["reading"]["method"], "relative tolerance")
        self.assertEqual([r["status"] for r in result["records"]], ["No finding", "Review"])

    def test_unsupported_rules_and_thresholds_rejected(self):
        for value in [float("nan"), 0, 101, True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                engine.analyze(dataset([{"reading": 11}]), reference(), config(threshold=value))
        with self.assertRaises(ValueError):
            engine.analyze(
                dataset([{"reading": 11}]),
                None,
                config(
                    features=[],
                    rules=[dict(name="x", field="reading", op="eval", value="__import__")],
                ),
            )

    def test_case_reopens_recomputes_and_preserves_source_without_execution(self):
        data, baseline, settings = dataset([{"reading": 100}]), reference(), config()
        result = engine.analyze(data, baseline, settings)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            engine.save_case(path, data, baseline, settings, result)
            reopened = engine.open_case(path)
            self.assertEqual(reopened, (data, baseline, settings, result))
            with self.assertRaises(FileExistsError):
                engine.save_case(path, data, baseline, settings, result)
            self.assertEqual(engine.open_case(path)[3], result)

    def test_modified_conclusion_rejected_even_with_rehashed_case(self):
        data, settings = dataset([{"reading": 100}]), config()
        result = engine.analyze(data, reference(), settings)
        doc = engine.case_document(data, reference(), settings, result)
        doc["payload"]["result"]["records"][0]["status"] = "No finding"
        doc["payload_sha256"] = engine.sha(engine.canonical(doc["payload"]).encode())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(ValueError):
                engine.open_case(path)

    def test_stale_results_cannot_be_exported(self):
        data, settings = dataset([{"reading": 100}]), config()
        result = engine.analyze(data, reference(), settings)
        result["summary"]["Review"] = 0
        with self.assertRaises(ValueError):
            engine.case_document(data, reference(), settings, result)

    def test_utf8_bom_and_non_ascii_roundtrip(self):
        data = engine.parse_bytes("\ufeffreading,note\n100,café\n".encode(), "café.csv")
        settings = config()
        result = engine.analyze(data, reference(), settings)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            engine.save_case(path, data, reference(), settings, result)
            self.assertEqual(engine.open_case(path)[0], data)


class DesktopTests(unittest.TestCase):
    def test_field_rule_form_applies_a_user_defined_condition(self):
        from app import Workbench
        from tkinter import ttk

        window = Workbench(start_hidden=True)
        window.withdraw()
        try:
            window.current = dataset([{"reading": 3}, {"reading": 90}])
            window._refresh_data()
            window._rules_dialog()
            dialog = next(w for w in window.winfo_children() if w.winfo_class() == "Toplevel")

            def descendants(parent):
                for child in parent.winfo_children():
                    yield child
                    yield from descendants(child)

            widgets = list(descendants(dialog))
            entries = [
                w for w in widgets if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)
            ]
            entries[0].insert(0, "Review high reading")
            entries[1].insert(0, "50")
            next(
                w for w in widgets if isinstance(w, ttk.Button) and w.cget("text") == "Add rule"
            ).invoke()
            next(
                w for w in widgets if isinstance(w, ttk.Button) and w.cget("text") == "Apply rules"
            ).invoke()
            self.assertEqual(
                window.rules,
                [dict(name="Review high reading", field="reading", op="gt", value=50.0)],
            )
            result = engine.analyze(window.current, None, window.config())
            self.assertEqual(result["summary"]["Review"], 1)
        finally:
            window.destroy()

    def test_desktop_mapping_analysis_case_comparison_and_invalidation(self):
        from app import Workbench

        window = Workbench(start_hidden=True)
        window.withdraw()
        try:
            window.current = dataset([{"reading": 100, "id": "one"}, {"reading": 10, "id": "two"}])
            window.reference = reference()
            window._refresh_data()
            window.features.selection_set(0)
            window.event_id.set("id")
            window._run()
            deadline = time.monotonic() + 8
            while window.busy and time.monotonic() < deadline:
                window.update()
                time.sleep(0.02)
            self.assertFalse(window.busy)
            self.assertEqual(window.result["summary"]["Review"], 1)
            self.assertEqual(len(window.findings.get_children()), 1)
            self.assertIn("100", window.detail.get("1.0", "end"))
            window.previous = (window.current, window.reference, window.run_config, window.result)
            window._render_comparison()
            self.assertIn("Same incoming evidence", window.comparison_note.get())
            self.assertTrue(window.comparison.rows)
            window.threshold.set("8")
            self.assertIsNone(window.result)
            self.assertEqual(str(window.export_button.cget("state")), "disabled")
            self.assertEqual(window.comparison.rows, [])
        finally:
            window.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)

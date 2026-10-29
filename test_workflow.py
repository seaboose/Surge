"""Workflow checks use arbitrary generated data, never product presets."""

import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import engine
import workflow
from test_workbench import config, dataset, reference


def sample():
    source = dataset(
        [
            {"action": "read", "actor": "sam"},
            {"action": "copy", "actor": "lee"},
            {"action": "copy"},
            {"actor": "missing action"},
        ]
    )
    settings = config(
        features=[],
        context={"User": "actor"},
        rules=[
            dict(name="Any copy", field="action", op="eq", value="copy", priority="Warning"),
            dict(
                name="Investigate copy", field="action", op="eq", value="copy", priority="Critical"
            ),
        ],
    )
    return source, settings


class WorkflowTests(unittest.TestCase):
    def test_policy_roundtrip_no_source_records_and_reuse(self):
        source, settings = sample()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            workflow.save_policy(path, source, None, settings)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("sam", raw)
            self.assertNotIn("source_record", raw)
            other = dataset([{"action": "copy", "actor": "new user"}], "another.json")
            loaded = workflow.load_policy(path, other, None)
            self.assertEqual(loaded, settings)
            self.assertEqual(engine.analyze(other, None, loaded)["summary"]["Review"], 1)
            with self.assertRaises(FileExistsError):
                workflow.save_policy(path, source, None, settings)
            self.assertEqual(path.read_text(encoding="utf-8"), raw)

    def test_invalid_policy_is_bounded_and_rejected(self):
        source, settings = sample()
        invalid = [
            '{"schema":"surge-policy-v1","schema":"surge-policy-v1","settings":{}}',
            json.dumps({"schema": "surge-policy-v1", "settings": settings, "command": "anything"}),
            json.dumps(
                {
                    "schema": "surge-policy-v1",
                    "settings": {**settings, "context": {"User": "absent"}},
                }
            ),
            json.dumps(
                {
                    "schema": "surge-policy-v1",
                    "settings": {
                        **settings,
                        "rules": [
                            dict(
                                name="invalid",
                                field="action",
                                op="eq",
                                value="copy",
                                priority="Urgent",
                            )
                        ],
                    },
                }
            ),
            json.dumps({"schema": "surge-policy-v1", "settings": {**settings, "features": [{}]}}),
            "!!python/object/apply:os.system ['not executable']",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            for content in invalid:
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ValueError):
                    workflow.load_policy(path, source, None)
            with patch.object(workflow, "MAX_POLICY", 5), self.assertRaises(ValueError):
                workflow.load_policy(path, source, None)

    def test_priorities_preserve_gaps_and_do_not_change_detection(self):
        source, settings = sample()
        result = engine.analyze(source, None, settings)
        self.assertEqual(
            [workflow.priority(r, settings) for r in result["records"]],
            [None, "Critical", "Critical", None],
        )
        self.assertEqual(
            [r["row"] for r in result["records"] if workflow.visible(r, settings, "Critical")],
            [2, 3, 4],
        )
        low = copy.deepcopy(settings)
        for rule in low["rules"]:
            rule["priority"] = "Notice"
        low_result = engine.analyze(source, None, low)
        self.assertEqual(low_result, result)
        self.assertEqual(
            [r["row"] for r in result["records"] if workflow.visible(r, low, "Critical")], [4]
        )
        # No context inference: missing actor is explicit and does not invent an identity.
        self.assertIsNone(workflow.context_values(source.rows[2], settings)["User"]["value"])
        numeric = engine.analyze(dataset([{"reading": 1000000}]), reference(), config())
        self.assertEqual(workflow.priority(numeric["records"][0], config()), "Notice")

    def test_case_persists_policy_and_context_and_legacy_results(self):
        source, settings = sample()
        result = engine.analyze(source, None, settings)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            engine.save_case(path, source, None, settings, result)
            restored = engine.open_case(path)
            self.assertEqual(restored, (source, None, settings, result))
        # Existing settings still produce the original result structure.
        legacy = config(
            features=[], rules=[dict(name="copy", field="action", op="eq", value="copy")]
        )
        legacy_result = engine.analyze(source, None, legacy)
        self.assertNotIn("priority", legacy_result["records"][1])
        self.assertEqual(workflow.priority(legacy_result["records"][1], legacy), "Notice")

    def test_export_routes_by_priority_preserves_provenance_and_refuses_overwrite(self):
        source, settings = sample()
        result = engine.analyze(source, None, settings)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alerts.jsonl"
            self.assertEqual(
                workflow.export_alerts(path, source, None, settings, result, "Critical"), 3
            )
            raw = path.read_bytes()
            lines = [json.loads(line) for line in raw.splitlines()]
            self.assertEqual(lines[0]["source"]["sha256"], source.digest)
            self.assertEqual(lines[0]["settings"], settings)
            self.assertEqual([a["row"] for a in lines[1:]], [2, 3, 4])
            self.assertEqual(lines[1]["context"]["User"], {"field": "actor", "value": "lee"})
            self.assertEqual(lines[-1]["status"], "Unknown")
            self.assertTrue(lines[-1]["gaps"])
            with self.assertRaises(FileExistsError):
                workflow.export_alerts(path, source, None, settings, result, "All")
            self.assertEqual(path.read_bytes(), raw)
            with patch.object(engine, "MAX_CASE", 100), self.assertRaises(ValueError):
                workflow.export_alerts(Path(tmp) / "large.jsonl", source, None, settings, result)
            self.assertFalse((Path(tmp) / "large.jsonl").exists())
            stale = copy.deepcopy(result)
            stale["records"][1]["status"] = "No finding"
            with self.assertRaises(ValueError):
                workflow.export_alerts(Path(tmp) / "stale.jsonl", source, None, settings, stale)

    def test_failed_output_removes_only_the_new_partial_file(self):
        source, settings = sample()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new.json"
            real_open = Path.open

            class FailingFile:
                def __enter__(self):
                    self.file = real_open(path, "xb")
                    return self

                def write(self, raw):
                    self.file.write(raw[:2])
                    raise OSError("simulated full disk")

                def __exit__(self, *_):
                    self.file.close()

            with patch.object(Path, "open", return_value=FailingFile()), self.assertRaises(OSError):
                workflow.save_policy(path, source, None, settings)
            self.assertFalse(path.exists())


class DesktopWorkflowTests(unittest.TestCase):
    @staticmethod
    def finish(window):
        deadline = time.monotonic() + 8
        while window.busy and time.monotonic() < deadline:
            window.update()
            time.sleep(0.01)
        if window.busy:
            raise AssertionError("Background operation did not finish")

    def test_policy_load_filter_context_export_and_failed_load_retains_state(self):
        from app import Workbench

        window = Workbench(start_hidden=True)
        window.withdraw()
        try:
            source, settings = sample()
            window.current = source
            window._refresh_data()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "policy.json"
                workflow.save_policy(path, source, None, settings)
                with patch("app.filedialog.askopenfilename", return_value=str(path)):
                    window._load_policy()
                    self.finish(window)
                self.assertEqual(window.config(), settings)
                window._run()
                self.finish(window)
                window.minimum_priority.set("Critical")
                window._render_findings()
                self.assertEqual(window.findings.get_children(), ("2", "3", "4"))
                self.assertIn('User: "lee" (from actor)', window.detail.get("1.0", "end"))
                export = Path(tmp) / "alerts.jsonl"
                with patch("app.filedialog.asksaveasfilename", return_value=str(export)):
                    window._export_alerts()
                    self.finish(window)
                self.assertEqual(len(export.read_text(encoding="utf-8").splitlines()), 4)
                previous = copy.deepcopy(window.result)
                path.write_text('{"schema":"wrong"}', encoding="utf-8")
                with (
                    patch("app.filedialog.askopenfilename", return_value=str(path)),
                    patch("app.messagebox.showerror") as error,
                ):
                    window._load_policy()
                    self.finish(window)
                    error.assert_called_once()
                self.assertEqual(window.config(), settings)
                self.assertEqual(window.result, previous)
                # Applying a new policy invalidates conclusions and disables case export.
                window._apply_config(settings)
                self.assertIsNone(window.result)
                self.assertEqual(str(window.export_button.cget("state")), "disabled")
        finally:
            window.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Parity and hostile-input checks at the new desktop's real Python boundary."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import comparison
import desktop_worker as desktop
import engine
import workflow


class DesktopTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).parent / "verification" / "temporary-test-files"
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.root = Path(self.temp.name)
        self.ws = desktop.Workspace()
        self.rows = [
            {
                "id": i,
                "session": "a",
                "time": i * 1000,
                "reading": 10 if i % 2 else 80,
                "user": "Straße 😀",
                "message": '<img src=x onerror="alert(1)">',
                "large": 9007199254740993,
            }
            for i in range(1, 206)
        ]
        self.rows[100]["reading"] = None
        self.rows[150].pop("reading")
        self.load("current", self.rows)
        self.load("reference", [{"reading": x} for x in [8, 9, 10, 11, 12]])
        self.config = dict(
            features=["reading"],
            session="session",
            event_id="id",
            time="time",
            time_format="milliseconds",
            threshold=6,
            context={"User": "user"},
            rules=[dict(name="Bound", field="reading", op="gt", value=70, priority="Critical")],
        )
        self.call("configure", config=self.config, rules_text=json.dumps(self.config["rules"]))

    def tearDown(self):
        self.temp.cleanup()

    def load(self, role, rows):
        path = self.root / f"{role}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return self.ws.dispatch("import", dict(role=role, path=str(path)))

    def call(self, method, **args):
        return self.ws.dispatch(method, dict(revision=self.ws.revision, **args))

    def test_exact_analysis_case_policy_export_parity(self):
        expected = engine.analyze(self.ws.current, self.ws.reference, self.config)
        self.call("analyze")
        self.assertEqual(self.ws.result, expected)
        case = self.root / "new.case.json"
        self.call("save", path=str(case))
        opened = engine.open_case(case)
        self.assertEqual(opened[3], expected)
        second = desktop.Workspace()
        second.dispatch("open", {"path": str(case)})
        self.assertEqual(second.result, expected)
        policy = self.root / "new.policy.json"
        self.call("policy_save", path=str(policy))
        self.assertEqual(workflow.load_policy(policy, *opened[:2]), self.config)

        alerts = self.root / "alerts.jsonl"
        self.call("alerts", path=str(alerts), minimum="Critical")
        records = [json.loads(x) for x in alerts.read_text(encoding="utf-8").splitlines()][1:]
        self.assertTrue(any(r["row"] == 101 and r["gaps"] for r in records))
        with self.assertRaises(FileExistsError):
            self.call("save", path=str(case))
        modified = json.loads(case.read_text(encoding="utf-8"))
        modified["payload"]["result"]["records"][0]["status"] = "Review"
        case.write_text(json.dumps(modified), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "integrity"):
            second.dispatch("open", {"path": str(case)})
        self.assertEqual(second.result, expected)

    def test_library_snapshot_and_verification_leave_workspace_unchanged(self):
        self.call("analyze")
        before = copy.deepcopy(self.ws.snapshot())
        target = self.root / "library.case.json"
        self.call("library_snapshot", path=str(target))
        self.assertEqual(self.ws.snapshot(), before)
        self.assertEqual(engine.open_case(target)[3], self.ws.result)
        self.assertEqual(
            self.ws.dispatch("library_verify", {"path": str(target)}), {"verified": True}
        )
        self.assertEqual(self.ws.snapshot(), before)
        with self.assertRaises(ValueError):
            self.ws.dispatch(
                "library_snapshot",
                {"path": str(self.root / "stale.json"), "revision": self.ws.revision - 1},
            )
        self.assertFalse((self.root / "stale.json").exists())
        target.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.ws.dispatch("library_verify", {"path": str(target)})
        self.assertEqual(self.ws.snapshot(), before)

    def test_warnings_pages_related_sources_and_navigation(self):
        note = next(
            i
            for i, n in enumerate(self.ws.notes)
            if n["source"] == "current" and n["rows"] and 101 in n["rows"]
        )
        preview = self.call("preview", note=note)
        self.assertIn(101, [r["row"] for r in preview["rows"]])
        self.assertEqual(preview["marked"], ["reading"])
        self.assertEqual(self.call("record_step", note=note, row=101, step=1)["row"], 151)
        self.assertEqual(self.call("record_step", note=note, row=151, step=1)["row"], None)
        normal = self.call("preview", page=2)
        self.assertEqual([r["row"] for r in normal["rows"]], list(range(201, 206)))
        self.assertLessEqual(len(normal["rows"]), 100)

    def test_full_values_unicode_missing_and_exact_copy(self):
        inspected = self.call("inspect", source="current", row=1, query="STRASSE")
        self.assertEqual(inspected["matches"][0]["text"], "Straße")
        self.assertEqual(
            self.call("copy", source="current", row=1, query="STRASSE", scope="match", match=0)[
                "text"
            ],
            "Straße",
        )
        self.assertEqual(
            self.call("copy", source="current", row=1, scope="value", field="large")["text"],
            "9007199254740993",
        )
        copied = self.call("copy", source="current", row=1, scope="record")["text"]
        self.assertEqual(json.loads(copied), self.rows[0])
        emoji = self.call("inspect", source="current", row=1, query="😀")["matches"][0]
        self.assertEqual(emoji["text"], "😀")
        self.assertEqual(
            self.call("copy", source="current", row=151, query="Missing", scope="match", match=0)[
                "text"
            ],
            "Missing",
        )
        with self.assertRaises(ValueError):
            self.call("copy", source="current", row=151, scope="value", field="reading")

    def test_search_filters_chart_and_inspector_do_not_mutate_evidence(self):
        self.call("analyze")
        before = copy.deepcopy(self.ws.result)
        for query in ["STRASSE", "a", "Bound", "2", "not found"]:
            page = self.call("findings", query=query, minimum="Critical")
            self.assertLessEqual(len(page["rows"]), 100)
        self.assertEqual(self.call("findings", query="not found")["hidden_gaps"], 2)
        points = self.call("chart", width=300, row=2)
        self.assertEqual(points["selected"]["value"], "80")
        self.assertLessEqual(len(points["points"]), 221)
        self.assertEqual(self.call("chart_step", row=100, step=1)["row"], 102)
        found = self.call("findings", query="not found", reveal=205, locate=205)
        self.assertEqual([r["row"] for r in found["rows"]], [205])
        self.assertIn("origin not specified", self.call("evidence", row=2)["time"])
        self.assertEqual(self.ws.result, before)

    def test_comparison_exact_and_stale_operations_rejected(self):
        self.call("analyze")
        old = self.root / "old.json"
        self.call("save", path=str(old))
        changed = dict(self.config, threshold=60)
        self.call("configure", config=changed, rules_text="[]")
        self.call("analyze")
        view = self.call("compare", path=str(old))
        self.assertTrue(view["paired"])
        self.assertTrue(view["changes"])
        row = view["changes"][0][0]
        actual = self.call("comparison", row=row)
        expected = comparison.record_rows(self.ws.case(), self.ws.previous, row)
        self.assertEqual(actual["rows"], [desktop.asdict(r) for r in expected])
        rev = self.ws.revision
        self.call("configure", config=self.config, rules_text=json.dumps(self.config["rules"]))
        self.assertIsNone(self.ws.previous)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.ws.dispatch("copy", dict(revision=rev, row=1, scope="record"))

    def test_bad_import_and_rules_are_transactional(self):
        before = self.ws.snapshot()
        invalid = self.root / "invalid.jsonl"
        invalid.write_text('{"reading": [1,2]}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Record 1"):
            self.ws.dispatch("import", dict(role="current", path=str(invalid)))
        self.assertEqual(self.ws.snapshot(), before)
        with self.assertRaises(ValueError):
            self.call("configure", config=self.config, rules_text='[{"command":"calc.exe"}]')
        self.assertEqual(self.ws.snapshot(), before)
        with self.assertRaises(ValueError):
            self.call("copy", row=1, source="../../", scope="record")

    def test_reference_warning_uses_reference_values_and_missing_field(self):
        self.load("reference", [{"other": i} for i in range(6)])
        note = next(i for i, n in enumerate(self.ws.notes) if n["source"] == "reference")
        preview = self.call("preview", note=note)
        self.assertEqual(preview["source"], "reference")
        self.assertEqual(preview["fields"][0], "reading")
        inspected = self.call("inspect", note=note, source="reference", row=1, query="Missing")
        self.assertEqual(inspected["matches"][0]["text"], "Missing")
        self.assertFalse(inspected["has_previous"])
        self.assertTrue(inspected["has_next"])
        with self.assertRaises(ValueError):
            self.call("inspect", note=note, source="current", row=1)

    def test_related_originals_not_counted_as_affected(self):
        rows = copy.deepcopy(self.rows)
        rows[1]["id"] = 1
        self.load("current", rows)
        self.call("configure", config=self.config, rules_text=json.dumps(self.config["rules"]))
        note = next(i for i, n in enumerate(self.ws.notes) if n["related"])
        preview = self.call("preview", note=note)
        self.assertEqual(preview["affected"], 1)
        self.assertTrue(preview["rows"][0]["related"])
        inspected = self.call("inspect", note=note, source="current", row=1)
        self.assertTrue(inspected["related"])
        self.assertEqual(self.call("record_step", note=note, row=1, step=1)["row"], 2)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.call("analyze")

    def test_all_file_adapters_and_rules_only_remain_available(self):
        for name, raw in [
            ("any.csv", "action\nread\nwrite\n"),
            ("any.jsonl", '{"action":"read"}\n{"action":"write"}\n'),
            ("any.ndjson", '{"action":"read"}\n{"action":"write"}\n'),
            ("any.json", '[{"action":"read"},{"action":"write"}]'),
        ]:
            with self.subTest(name=name):
                file = self.root / name
                file.write_text(raw, encoding="utf-8")
                self.ws.dispatch("import", dict(role="current", path=str(file)))
                rules = [dict(name="Write", field="action", op="eq", value="write")]
                config = dict(desktop.default_config(), rules=rules)
                self.call("configure", config=config, rules_text=json.dumps(rules))
                self.call("analyze")
                self.assertEqual(
                    [r["status"] for r in self.ws.result["records"]], ["No finding", "Review"]
                )
                self.assertEqual(self.call("chart", width=400)["points"], [])

    def test_different_source_comparison_cannot_pair_records(self):
        self.call("analyze")
        old = self.root / "old.json"
        self.call("save", path=str(old))
        rows = copy.deepcopy(self.rows)
        rows[0]["reading"] = 11
        self.load("current", rows)
        self.call("configure", config=self.config, rules_text=json.dumps(self.config["rules"]))
        self.call("analyze")
        comparison = self.call("compare", path=str(old))
        self.assertFalse(comparison["paired"])
        self.assertEqual(comparison["changes"], [])
        with self.assertRaisesRegex(ValueError, "cannot be paired"):
            self.call("comparison", row=1)

    def test_dense_search_bounds_highlights_but_keeps_every_value_and_match(self):
        rows = [{f"field{i}": "a" * 4096 for i in range(64)}]
        self.load("current", rows)
        first = self.call("inspect", row=1, query="a")
        self.assertEqual(first["match_total"], 64 * 4096)
        self.assertEqual(len(first["matches"]), 200)
        self.assertEqual(sum(len(f["spans"]) for f in first["fields"]), 200)
        self.assertEqual({f["field"]: json.loads(f["value"]) for f in first["fields"]}, rows[0])
        self.assertLess(len(json.dumps(first)), 400_000)
        last = first["match_total"] - 1
        with patch.object(
            desktop.record_search, "match_spans", side_effect=AssertionError("Repeated search")
        ):
            end = self.call("inspect", row=1, query="a", match=last)
            self.assertEqual(end["matches"][-1]["index"], last)
            self.assertEqual(
                self.call("copy", row=1, query="a", scope="match", match=last)["text"], "a"
            )
        with self.assertRaises(ValueError):
            self.call("copy", row=1, query="a", scope="match", match=last + 1)
        self.load("current", [{"field": "different"}])
        self.assertEqual(self.call("inspect", row=1, query="a")["match_total"], 0)

    def test_chart_reuses_points_and_invalidates_after_analysis_or_settings(self):
        self.call("analyze")
        with patch.object(desktop.chart, "points", wraps=desktop.chart.points) as points:
            before = self.call("chart", width=300, row=2)
            after = self.call("chart", width=300, row=3)
            self.assertEqual(points.call_count, 1)
            self.assertEqual(before["points"], after["points"])
            self.assertNotEqual(before["selected"], after["selected"])
            self.call("chart", width=400)
            self.assertEqual(points.call_count, 2)
            self.call("analyze")
            self.call("chart", width=400)
            self.assertEqual(points.call_count, 3)
            self.call("configure", config=dict(self.config, threshold=60), rules_text="[]")
            self.call("analyze")
            self.call("chart", width=400)
            self.assertEqual(points.call_count, 4)

    def test_comparison_caches_summary_without_reusing_wrong_record_or_case(self):
        self.call("analyze")
        old = self.root / "old.json"
        self.call("save", path=str(old))
        self.call("configure", config=dict(self.config, threshold=60), rules_text="[]")
        self.call("analyze")
        with patch.object(
            comparison, "changed_records", wraps=comparison.changed_records
        ) as changed:
            self.call("compare", path=str(old))
            for row in (2, 4, 6):
                view = self.call("comparison", row=row)
                self.assertEqual(
                    view["rows"],
                    [
                        desktop.asdict(r)
                        for r in comparison.record_rows(self.ws.case(), self.ws.previous, row)
                    ],
                )
            self.assertEqual(changed.call_count, 1)
            self.call("compare", path=str(old))
            self.assertEqual(changed.call_count, 2)
            self.call("analyze")
            self.call("comparison")
            self.assertEqual(changed.call_count, 3)

    def test_configuration_runs_preflight_once(self):
        with patch.object(
            desktop.mapping_checks, "check", wraps=desktop.mapping_checks.check
        ) as check:
            self.call("configure", config=self.config, rules_text=json.dumps(self.config["rules"]))
            self.assertEqual(check.call_count, 1)


if __name__ == "__main__":
    unittest.main()

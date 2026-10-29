"""Memory representation changes must preserve import and investigation semantics."""

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import desktop_worker
import engine
import record_search

BASE = Path(__file__).parent
spec = importlib.util.spec_from_file_location(
    "surge_before_memory", BASE / "tests/fixtures/memory-baseline-engine.py"
)
before = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = before
spec.loader.exec_module(before)


class MemoryRegressionTests(unittest.TestCase):
    def test_valid_adapters_match_previous_engine_exactly(self):
        cases = [
            (
                "data.json",
                json.dumps(
                    [
                        {
                            "reading": i,
                            "a": "same value " * 8,
                            "b": "same value " * 8,
                            "nested": {"text": "Straße 😀"},
                            "flag": True,
                            "null": None,
                        }
                        for i in range(300)
                    ],
                    ensure_ascii=False,
                ),
            ),
            ("data.json", '{"events":[{"x":"a","y":"a"},{"x":true,"y":1}]}'),
            ("data.json", '\ufeff{"records":[{"x":9007199254740993,"y":"9007199254740993"}]}'),
            ("data.jsonl", '\n{"reading":3,"text":"same"}\n{"reading":5,"text":"same"}\n'),
            ("data.csv", 'reading,text,other\n3,same,same\n5,"multi\nline","multi\nline"\n'),
        ]
        for name, text in cases:
            with self.subTest(name=name, text=text[:50]):
                old, new = [module.parse_bytes(text.encode(), name) for module in (before, engine)]
                self.assertEqual(old.manifest(), new.manifest())
                self.assertEqual(old.text, new.text)
                self.assertEqual(old.rows, new.rows)

    def test_import_error_locations_match_previous_engine(self):
        inputs = [
            '[{"x":1,"x":2},{"good":1}]',
            '[{"nested":{"x":1,"x":2}},{"a":[1]}]',
            '[{"x":1,"x":2,"later":{"a":1,"a":2}}]',
            '[{"earlier":{"a":1,"a":2},"x":1,"x":2}]',
            '[{"x":1,"x":2,"y":3,"x":4,"y":5}]',
            '[{"":1,"":2}]',
            '{"events":[],"events":[{"x":1}]}',
            '[{"nested":{"a":1},"nested.a":2}]',
            '[{"x":NaN},{"x":Infinity}]',
            "[" + ",".join('{"x":[1]}' for _ in range(25)) + "]",
            '[{"x":"ok"},broken]',
        ]
        for text in inputs:
            errors = []
            for module in (before, engine):
                with self.assertRaises(ValueError) as raised:
                    module.parse_bytes(text.encode(), "data.json")
                errors.append((type(raised.exception), str(raised.exception)))
            self.assertEqual(*errors)

    def test_shared_text_preserves_types_and_source_bytes(self):
        text = json.dumps(
            [
                dict(
                    a="repeated long text " * 40,
                    b="repeated long text " * 40,
                    truth=True,
                    one=1,
                    label="1",
                    empty="",
                    absent=None,
                )
            ]
            * 2
        )
        data = engine.parse_bytes(text.encode(), "data.json")
        self.assertIs(data.rows[0]["a"], data.rows[1]["b"])
        self.assertIs(type(data.rows[0]["truth"]), bool)
        self.assertIs(type(data.rows[0]["one"]), int)
        self.assertIs(type(data.rows[0]["label"]), str)
        self.assertEqual(data.text, text)
        # Replacing one cell in a standalone Dataset does not mutate another row.
        data.rows[0]["a"] = "changed"
        self.assertEqual(data.rows[1]["b"], "repeated long text " * 40)

    def test_pool_eviction_does_not_change_unique_values_or_analysis(self):
        rows = [
            dict(reading=i % 17, a=f"value-{i}", b=f"value-{i}", text=f"unique-{i}")
            for i in range(2000)
        ]
        raw = json.dumps(rows).encode()
        old, new = [m.parse_bytes(raw, "data.json") for m in (before, engine)]
        reference = engine.parse_bytes(
            b'[{"reading":1},{"reading":2},{"reading":3},{"reading":4},{"reading":5}]', "ref.json"
        )
        config = dict(desktop_worker.default_config(), features=["reading"])
        self.assertEqual(new.rows, old.rows)
        self.assertEqual(
            engine.analyze(new, reference, config), before.analyze(old, reference, config)
        )

    def test_compact_search_offsets_preserve_unicode_and_escapes(self):
        for text, query in [
            ("Straße 😀 Straße", "STRASSE"),
            ("😀😀😀", "😀"),
            ('"a\\na\\na"', "\\n"),
            ("ßsss", "s"),
            ("no matches", "zzz"),
        ]:
            offsets = desktop_worker.compact_spans(text, query)
            self.assertEqual(
                list(zip(offsets[::2], offsets[1::2])), record_search.match_spans(text, query)
            )

    def test_dense_cache_is_packed_and_copy_reaches_last_match(self):
        ws = desktop_worker.Workspace()
        ws.current = engine.parse_bytes(
            json.dumps([{f"field{i}": "a" * 4096 for i in range(64)}]).encode(), "dense.json"
        )
        view = ws.dispatch("inspect", dict(revision=0, row=1, query="a", match=262143))
        cache = ws.inspection_cache[1]
        stored = sum(len(f[part]) * f[part].itemsize for f in cache for part in ("names", "spans"))
        self.assertLessEqual(stored, 2 * 1024 * 1024)
        self.assertEqual(view["match_total"], 262144)
        self.assertEqual(view["matches"][-1]["index"], 262143)
        self.assertEqual(
            ws.dispatch("copy", dict(revision=0, row=1, query="a", match=262143, scope="match"))[
                "text"
            ],
            "a",
        )

    def test_verified_comparison_reuses_rows_without_changing_source_name_or_findings(self):
        folder = BASE / "verification/temporary-test-files"
        folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            current = engine.parse_bytes(b'[{"x":"read"},{"x":"write"}]', "incoming.json")
            config = dict(
                desktop_worker.default_config(),
                rules=[dict(name="Write", field="x", op="eq", value="write")],
            )
            previous_source = replace(current, name="renamed.json")
            previous_result = engine.analyze(previous_source, None, config)
            case = Path(temp) / "case.json"
            engine.save_case(case, previous_source, None, config, previous_result)
            ws = desktop_worker.Workspace()
            ws.current, ws.config = current, config
            ws.dispatch("analyze", {"revision": 0})
            original = json.dumps(ws.result, sort_keys=True)
            ws.dispatch("compare", dict(revision=0, path=str(case)))
            self.assertIs(ws.previous[0].rows, current.rows)
            self.assertEqual(ws.previous[0].name, "renamed.json")
            self.assertEqual(ws.previous[3], previous_result)
            self.assertEqual(json.dumps(ws.result, sort_keys=True), original)
            verified = ws.previous
            tampered = json.loads(case.read_text())
            tampered["payload"]["current"]["text"] = '[{"x":"tampered"}]'
            case.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError, "integrity"):
                ws.dispatch("compare", dict(revision=0, path=str(case)))
            self.assertIs(ws.previous, verified)

    def test_source_sharing_requires_exact_text_and_format(self):
        data = engine.parse_bytes(b'[{"x":1}]', "data.json")
        changed = engine.parse_bytes(b'[{"x":2}]', "data.json")
        self.assertIs(desktop_worker.share_verified_source(changed, (data,)), changed)
        format_changed = replace(data, format="jsonl")
        self.assertIs(desktop_worker.share_verified_source(format_changed, (data,)), format_changed)


if __name__ == "__main__":
    unittest.main()

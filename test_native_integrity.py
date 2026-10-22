import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import engine
import desktop_worker
import native_integrity as native
import importlib.util

spec = importlib.util.spec_from_file_location(
    "native_capture_cli", Path(__file__).parent / "scripts/native_capture.py"
)
native_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native_cli)


def capture():
    reference = "908bc1c3"
    row = dict(
        schema="native-code-range-v1",
        reference_hex=reference,
        reference_sha256=hashlib.sha256(bytes.fromhex(reference)).hexdigest(),
        range_size=4,
        range_rva=4096,
        module_sha256="a" * 64,
        memory_status="complete",
        observed_hex=reference,
        page_protection=32,
        session_id="1-start",
        captured_at="2026-10-21T12:00:00Z",
        pid=1,
        scenario="clean",
        build="v1",
    )
    return dict(
        schema="native-code-capture-v1",
        observations=[dict(row, phase=p) for p in ("initial", "sample", "restored")],
    )


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.capture = capture()
        self.empty = dict(schema=native.BASELINE_SCHEMA, entries=[])
        self.approved = native.approve(self.capture, self.empty, "Reviewed fixture v1")

    def result(self, capture=None, registry=None):
        rows = native.convert(capture or self.capture, registry or self.approved)
        data = engine.parse_bytes(json.dumps(rows).encode(), "native.json")
        return engine.analyze(data, None, native.default_policy(data))

    def test_clean_and_unapproved_update(self):
        self.assertEqual(self.result()["summary"]["No finding"], 3)
        update = copy.deepcopy(self.capture)
        for row in update["observations"]:
            row["module_sha256"] = "b" * 64
        self.assertEqual(self.result(update)["summary"]["Review"], 3)
        approved = native.approve(update, self.approved, "Reviewed update")
        self.assertEqual(self.result(update, approved)["summary"]["No finding"], 3)

    def test_memory_and_protection_changes_are_independent(self):
        changed = copy.deepcopy(self.capture)
        changed["observations"][1]["observed_hex"] = "918bc1c3"
        result = self.result(changed)
        self.assertEqual(result["summary"]["Review"], 1)
        self.assertEqual(
            result["records"][1]["evidence"][0]["name"], "Code differs from approved baseline"
        )
        changed = copy.deepcopy(self.capture)
        changed["observations"][1]["page_protection"] = 64
        self.assertEqual(self.result(changed)["summary"]["Review"], 1)

    def test_failed_or_unloaded_memory_is_unknown(self):
        for status in ("failed", "not_loaded"):
            changed = copy.deepcopy(self.capture)
            changed["observations"][1].update(memory_status=status, observed_hex=None)
            result = self.result(changed)
            self.assertEqual(result["summary"]["Unknown"], 1)
            self.assertEqual(result["summary"]["Review"], 0)

    def test_approval_refuses_changes_and_duplicate_identities(self):
        changed = copy.deepcopy(self.capture)
        changed["observations"][1]["observed_hex"] = "918bc1c3"
        with self.assertRaises(ValueError):
            native.approve(changed, self.empty, "Must fail")
        with self.assertRaises(ValueError):
            native.approve(self.capture, self.approved, "Duplicate")

    def test_oversized_or_inconsistent_evidence_rejected(self):
        for key, value in (
            ("reference_hex", "00" * 65),
            ("range_size", 999),
            ("observed_hex", "zz"),
        ):
            changed = copy.deepcopy(self.capture)
            changed["observations"][0][key] = value
            with self.assertRaises(ValueError):
                native.convert(changed, self.approved)

    def test_import_recognizes_native_and_rejects_forged_verdict(self):
        rows = native.convert(self.capture, self.approved)
        data = engine.parse_bytes(json.dumps(rows).encode(), "native.json")
        workspace = desktop_worker.Workspace()
        with patch.object(engine, "load_dataset", return_value=data):
            workspace.dispatch("import", {"role": "current", "path": "native.json"})
        self.assertEqual(workspace.config["time_format"], "iso8601")
        self.assertEqual(len(workspace.config["rules"]), 3)
        rows[1]["memory_matches"] = False
        malformed = engine.parse_bytes(json.dumps(rows).encode(), "bad.json")
        with (
            patch.object(engine, "load_dataset", return_value=malformed),
            self.assertRaises(ValueError),
        ):
            workspace.dispatch("import", {"role": "current", "path": "bad.json"})
        self.assertIs(workspace.current, data)
        ordinary = engine.parse_bytes(b'[{"reading":1}]', "ordinary.json")
        self.assertIsNone(native.default_policy(ordinary))

    def test_collector_failure_exports_unknown_without_approving(self):
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).parent / "verification/temporary-test-files"
        ) as folder:
            root = Path(folder)
            registry = root / "baseline.json"
            output = root / "failure.jsonl"
            argv = [
                "native_capture.py",
                "capture",
                "--baselines",
                str(registry),
                "--output",
                str(output),
            ]
            with (
                patch("sys.argv", argv),
                patch.object(native_cli, "collect", side_effect=OSError("Fixture missing")),
            ):
                native_cli.main()
            self.assertFalse(registry.exists())
            data = engine.load_dataset(output)
            result = engine.analyze(data, None, native.default_policy(data))
            self.assertEqual(result["records"][0]["status"], "Unknown")
            with (
                patch("sys.argv", argv),
                patch.object(native_cli, "collect", side_effect=OSError("Fixture missing")),
                self.assertRaises(FileExistsError),
            ):
                native_cli.main()
            argv = [
                "native_capture.py",
                "approve",
                "--baselines",
                str(registry),
                "--reason",
                "Must not approve",
            ]
            with (
                patch("sys.argv", argv),
                patch.object(native_cli, "collect", side_effect=OSError("Fixture missing")),
                self.assertRaises(ValueError),
            ):
                native_cli.main()
            self.assertFalse(registry.exists())


class MultiRangeTests(unittest.TestCase):
    def setUp(self):
        base = capture()["observations"][0]
        self.ranges = [
            dict(
                range_name=name,
                range_rva=rva,
                range_size=4,
                reference_hex=base["reference_hex"],
                reference_sha256=base["reference_sha256"],
            )
            for name, rva in (("LabCodeProbe", 4096), ("LabCodeSecondary", 8192))
        ]
        self.capture = dict(
            schema="native-code-capture-v2",
            ranges=self.ranges,
            observations=[
                dict(base, **spec, phase=phase) for phase in native.PHASES for spec in self.ranges
            ],
        )
        self.empty = dict(schema=native.BASELINE_SCHEMA, entries=[])
        self.approved = native.approve(self.capture, self.empty, "Reviewed both ranges")

    def test_approval_covers_both_ranges_and_is_order_independent(self):
        self.assertEqual(len(self.approved["entries"]), 2)
        changed = copy.deepcopy(self.capture)
        changed["observations"].reverse()
        self.assertEqual(len(native.approve(changed, self.empty, "Reviewed")["entries"]), 2)
        rows = native.convert(self.capture, self.approved)
        self.assertEqual(len({r["event_id"] for r in rows}), 6)
        self.assertTrue(all(r["coverage_compared_ranges"] == 2 for r in rows))

    def test_update_needs_new_approval_for_both_ranges(self):
        changed = copy.deepcopy(self.capture)
        for row in changed["observations"]:
            row["module_sha256"] = "b" * 64
        rows = native.convert(changed, self.approved)
        self.assertTrue(
            all(
                r["coverage_unapproved_ranges"] == 2 and r["coverage_compared_ranges"] == 0
                for r in rows
            )
        )
        approved = native.approve(changed, self.approved, "Reviewed update")
        self.assertTrue(all(r["memory_matches"] is True for r in native.convert(changed, approved)))

    def test_second_range_change_and_partial_collection(self):
        changed = copy.deepcopy(self.capture)
        changed["observations"][3]["observed_hex"] = "918bc1c3"
        rows = native.convert(changed, self.approved)
        self.assertFalse(rows[3]["memory_matches"])
        self.assertTrue(rows[2]["memory_matches"])
        self.assertEqual(rows[2]["coverage_changed_ranges"], 1)
        changed["observations"][2].update(memory_status="failed", observed_hex=None)
        rows = native.convert(changed, self.approved)
        self.assertEqual(rows[2]["coverage_read_ranges"], 1)
        self.assertEqual(rows[2]["coverage_unavailable_ranges"], 1)
        with self.assertRaises(ValueError):
            native.approve(changed, self.empty, "Must fail")

    def test_missing_duplicate_overlapping_or_mixed_ranges_rejected(self):
        bad = []
        c = copy.deepcopy(self.capture)
        c["observations"].pop()
        bad.append(c)
        c = copy.deepcopy(self.capture)
        c["observations"][1] = c["observations"][0]
        bad.append(c)
        c = copy.deepcopy(self.capture)
        c["ranges"][1]["range_rva"] = 4097
        bad.append(c)
        c = copy.deepcopy(self.capture)
        c["observations"][3]["session_id"] = "other"
        bad.append(c)
        c = copy.deepcopy(self.capture)
        c["ranges"][1]["range_name"] = "LabCodeProbe"
        bad.append(c)
        for c in bad:
            with self.subTest(c=c), self.assertRaises(ValueError):
                native.convert(c, self.approved)
            with self.subTest(approval=c), self.assertRaises(ValueError):
                native.approve(c, self.empty, "Must fail")

    def test_import_rejects_missing_ranges_and_forged_coverage(self):
        rows = native.convert(self.capture, self.approved)
        for mutation in ("missing", "total", "manifest", "phase", "bool"):
            changed = copy.deepcopy(rows)
            if mutation == "missing":
                changed.pop(3)
            if mutation == "phase":
                changed = changed[2:]
            if mutation == "total":
                changed[2]["coverage_read_ranges"] = 99
            if mutation == "bool":
                changed[2]["coverage_unavailable_ranges"] = False
            if mutation == "manifest":
                changed[2]["range_manifest_sha256"] = "0" * 64
            data = engine.parse_bytes(json.dumps(changed).encode(), "bad.json")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                native.default_policy(data)

    def test_legacy_approval_does_not_approve_new_manifest(self):
        registry = copy.deepcopy(self.approved)
        for entry in registry["entries"]:
            del entry["range_manifest_sha256"]
            del entry["range_name"]
        self.assertTrue(
            all(r["baseline_approved"] is False for r in native.convert(self.capture, registry))
        )


if __name__ == "__main__":
    unittest.main()

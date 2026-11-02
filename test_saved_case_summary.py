"""Saved native summaries use verified evidence, never retained live status."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import desktop_worker as desktop
import engine
import native_integrity as native
import native_stream
from test_native_integrity import capture


class SavedCaseSummaryTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).parent / "verification" / "temporary-test-files"
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="surge-saved-summary-", dir=folder)
        self.root = Path(self.temp.name)
        self.ws = desktop.Workspace()
        base = capture()["observations"][0]
        base["build"] = "v2"
        ranges = [
            dict(
                range_name=name,
                range_rva=rva,
                **{key: base[key] for key in ("range_size", "reference_hex", "reference_sha256")},
            )
            for name, rva in (("LabCodeProbe", 4096), ("LabCodeSecondary", 8192))
        ]
        self.capture = dict(
            schema="native-code-capture-v2",
            ranges=ranges,
            observations=[
                dict(base, **spec, phase=phase) for phase in native.PHASES for spec in ranges
            ],
        )
        self.empty = dict(schema=native.BASELINE_SCHEMA, entries=[])
        self.approved = native.approve(self.capture, self.empty, "Owned test fixture")
        self.counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def save(self, rows, config=None):
        self.counter += 1
        data = engine.parse_bytes(engine.canonical(rows).encode(), "observations.json")
        config = config or native.default_policy(data)
        result = engine.analyze(data, None, config)
        path = self.root / f"case-{self.counter}.json"
        engine.save_case(path, data, None, config, result)
        return path

    def open_rows(self, rows, config=None):
        return self.ws.dispatch("open", {"path": str(self.save(rows, config))})

    def test_approved_reopened_case_is_historical_even_with_a_live_collector(self):
        self.ws.capture = Mock()
        self.ws.capture.status.return_value = {"state": "running", "session_id": "new-live"}
        self.ws.inspected_capture = {"session_id": "old-live"}
        state = self.open_rows(native.convert(self.capture, self.approved))
        self.assertEqual(state["saved_result"], dict(expected=True, ranges=2, review=0, unknown=0))
        self.assertEqual(state["summary"]["No finding"], 6)
        self.assertIsNone(state["inspected_capture"])
        self.assertIsNone(state["demo_result"])
        self.assertEqual(state["capture"]["session_id"], "new-live")
        self.ws.capture.snapshot.assert_not_called()

    def test_unapproved_case_keeps_review_and_never_claims_expected(self):
        state = self.open_rows(native.convert(self.capture, self.empty))
        self.assertEqual(state["saved_result"], dict(expected=False, ranges=2, review=6, unknown=0))

    def test_changed_or_unreadable_evidence_prevents_expected_result(self):
        for fields, review, unknown in (
            ({"observed_hex": "918bc1c3"}, 1, 0),
            ({"page_protection": 64}, 1, 0),
            ({"memory_status": "failed", "observed_hex": None}, 0, 1),
        ):
            with self.subTest(fields=fields):
                capture_data = copy.deepcopy(self.capture)
                capture_data["observations"][0].update(fields)
                state = self.open_rows(native.convert(capture_data, self.approved))
                self.assertEqual(
                    state["saved_result"],
                    dict(expected=False, ranges=2, review=review, unknown=unknown),
                )

    def test_disabled_integrity_rules_do_not_turn_unapproved_evidence_into_success(self):
        rows = native.convert(self.capture, self.empty)
        data = engine.parse_bytes(engine.canonical(rows).encode(), "observations.json")
        config = native.default_policy(data)
        config["rules"] = [
            dict(name="Other rule", field="range_size", op="eq", value=0, priority="Warning")
        ]
        state = self.open_rows(rows, config)
        self.assertEqual(state["summary"]["No finding"], 6)
        self.assertFalse(state["saved_result"]["expected"])

    def test_collection_failure_is_unknown_and_cannot_claim_expected(self):
        rows = native_stream.snapshot_rows([], state="failed", error="Producer disconnected")
        state = self.open_rows(rows)
        self.assertEqual(state["saved_result"], dict(expected=False, ranges=0, review=0, unknown=1))

    def test_recomputed_case_with_inconsistent_native_verdict_is_rejected_atomically(self):
        self.open_rows(native.convert(self.capture, self.approved))
        before = copy.deepcopy(self.ws.snapshot())
        rows = native.convert(self.capture, self.approved)
        # A generic case can recompute its analysis after this source edit. The
        # native bytes/hash checks must still reject its invented match verdict.
        rows[0]["observed_hex"] = "918bc1c3"
        config = copy.deepcopy(self.ws.config)
        path = self.save(rows, config)
        engine.open_case(path)
        with self.assertRaisesRegex(ValueError, "derived verdict"):
            self.ws.dispatch("open", {"path": str(path)})
        self.assertEqual(self.ws.snapshot(), before)

    def test_generic_case_has_no_native_summary_even_with_similar_columns(self):
        rows = [
            dict(
                reading=1,
                baseline_approved=True,
                memory_matches=True,
                protection_matches=True,
                memory_status="complete",
            )
        ]
        config = desktop.default_config()
        config["rules"] = [
            dict(name="Limit", field="reading", op="gt", value=5, priority="Warning")
        ]
        state = self.open_rows(rows, config)
        self.assertIsNone(state["saved_result"])

    def test_edit_or_import_clears_historical_summary(self):
        rows = native.convert(self.capture, self.approved)
        self.open_rows(rows)
        config = copy.deepcopy(self.ws.config)
        self.ws.dispatch(
            "configure",
            dict(
                revision=self.ws.revision,
                config=config,
                rules_text=engine.canonical(config["rules"]),
            ),
        )
        self.assertIsNone(self.ws.snapshot()["saved_result"])
        self.open_rows(rows)
        source = self.root / "generic.json"
        source.write_text('[{"reading":1}]', encoding="utf-8")
        state = self.ws.dispatch("import", dict(role="current", path=str(source)))
        self.assertIsNone(state["saved_result"])

    def test_export_preserves_verified_summary_without_creating_live_association(self):
        opened = self.open_rows(native.convert(self.capture, self.approved))
        for method in ("save", "library_snapshot"):
            with self.subTest(method=method):
                target = self.root / f"{method}.json"
                self.ws.dispatch(method, dict(path=str(target), revision=self.ws.revision))
                state = self.ws.snapshot()
                self.assertEqual(state["saved_result"], opened["saved_result"])
                self.assertIsNone(state["inspected_capture"])
                self.assertIsNone(state["demo_result"])
                reopened = desktop.Workspace().dispatch("open", {"path": str(target)})
                self.assertEqual(reopened["saved_result"], state["saved_result"])


if __name__ == "__main__":
    unittest.main()

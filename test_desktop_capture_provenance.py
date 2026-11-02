"""Snapshot display metadata follows validated evidence, not a moving collector.

Synthetic owned rows only: no child process, image loading or external target.
"""

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import desktop_worker as desktop
import native_stream as stream
from test_native_replay_contract import sample
from test_native_window import many_ranges


class Capture:
    build = "v1"

    def __init__(self, rows):
        self.rows = rows
        self.state = "running"
        self.session_id = rows[0]["session_id"]
        self.sequence = 9  # Collection has advanced beyond the inspected rows.

    def snapshot(self):
        return copy.deepcopy(self.rows)

    def status(self):
        return dict(state=self.state, session_id=self.session_id, final_sequence=self.sequence)

    def stop(self):
        self.state = "stopped"


class CaptureProvenanceTests(unittest.TestCase):
    def setUp(self):
        decoder, observations = many_ranges(2)
        self.rows = stream.snapshot_rows(
            [
                decoder.accept(sample(observations, sequence=1)),
                decoder.accept(sample(observations, sequence=2, elapsed=500)),
            ]
        )
        self.ws = desktop.Workspace()
        self.ws.capture = Capture(self.rows)

    def inspect(self):
        return self.ws.dispatch("native_snapshot", {})

    def test_endpoint_comes_from_inspected_rows_and_stays_stable(self):
        state = self.inspect()
        metadata = copy.deepcopy(state["inspected_capture"])
        self.assertEqual(metadata["final_sequence"], 2)
        self.assertEqual(metadata["capture_state"], "stopped")
        self.assertEqual(state["capture"]["state"], "running")
        self.assertEqual(metadata["session_id"], self.rows[0]["session_id"])
        self.assertEqual(metadata["captured_at"], self.rows[-1]["captured_at"])
        self.assertTrue(metadata["inspected_at"].endswith("+00:00"))
        self.assertEqual((metadata["samples"], metadata["records"]), (2, 4))
        self.assertEqual(state["capture"]["final_sequence"], 9)
        self.ws.capture.sequence = 10
        self.ws.dispatch("native_status", {})
        self.assertEqual(self.ws.snapshot()["inspected_capture"], metadata)

    def test_restart_preserves_old_snapshot_with_different_session_identity(self):
        metadata = self.inspect()["inspected_capture"]
        self.ws.capture.stop()
        new_capture = Capture(self.rows)
        new_capture.session_id = "different-owned-session"
        with patch.object(stream, "NativeSession", return_value=new_capture):
            self.ws.dispatch("native_start", {"build": "v1"})
        state = self.ws.snapshot()
        self.assertEqual(state["inspected_capture"], metadata)
        self.assertNotEqual(state["capture"]["session_id"], metadata["session_id"])

    def test_failed_or_empty_inspect_keeps_previous_metadata_and_evidence(self):
        metadata = self.inspect()["inspected_capture"]
        current = self.ws.current
        self.ws.capture.rows = []
        with self.assertRaisesRegex(ValueError, "first collection sample"):
            self.inspect()
        self.assertEqual(self.ws.inspected_capture, metadata)
        self.assertIs(self.ws.current, current)
        self.ws.capture.rows = copy.deepcopy(self.rows)
        self.ws.capture.rows[-1]["stream_sequence"] = 999
        with self.assertRaises(ValueError):
            self.inspect()
        self.assertEqual(self.ws.inspected_capture, metadata)
        self.assertIs(self.ws.current, current)

    def test_stop_publishes_snapshot_and_empty_stop_does_not_replace_it(self):
        state = self.ws.dispatch("native_stop", {})
        self.assertEqual(state["inspected_capture"]["final_sequence"], 2)
        self.assertEqual(state["capture"]["state"], "stopped")
        self.assertEqual(state["inspected_capture"]["capture_state"], "stopped")
        metadata = state["inspected_capture"]
        self.ws.capture.rows = []
        self.assertEqual(self.ws.dispatch("native_stop", {})["inspected_capture"], metadata)

    def test_current_import_and_case_open_clear_live_association(self):
        folder = Path(__file__).parent / "verification" / "temporary-test-files"
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as temp:
            root = Path(temp)
            self.inspect()
            case = root / "snapshot.case.json"
            self.ws.dispatch("save", dict(revision=self.ws.revision, path=str(case)))
            path = root / "data.json"
            path.write_text(json.dumps([{"value": 1}]), encoding="utf-8")
            self.ws.dispatch("import", dict(role="reference", path=str(path)))
            self.assertIsNotNone(self.ws.inspected_capture)
            self.ws.dispatch("import", dict(role="current", path=str(path)))
            self.assertIsNone(self.ws.inspected_capture)
            self.inspect()
            self.ws.dispatch("open", dict(path=str(case)))
            self.assertIsNone(self.ws.inspected_capture)
            self.assertIsNotNone(self.ws.result)

    def test_running_snapshot_state_does_not_follow_stopped_collector_status(self):
        for row in self.ws.capture.rows:
            row["stream_capture_state"] = "running"
        self.ws.capture.stop()
        state = self.inspect()
        self.assertEqual(state["capture"]["state"], "stopped")
        self.assertEqual(state["inspected_capture"]["capture_state"], "running")

    def test_failed_import_or_open_preserves_snapshot_metadata(self):
        metadata = self.inspect()["inspected_capture"]
        for method, args in (
            ("import", dict(role="current", path="missing.json")),
            ("open", dict(path="missing.case.json")),
        ):
            with self.subTest(method=method):
                with self.assertRaises((ValueError, OSError)):
                    self.ws.dispatch(method, args)
                self.assertEqual(self.ws.inspected_capture, metadata)

    def test_health_only_snapshot_does_not_invent_endpoint(self):
        self.ws.capture.rows = stream.snapshot_rows([], error="Owned fixture unavailable.")
        metadata = self.inspect()["inspected_capture"]
        self.assertIsNone(metadata["session_id"])
        self.assertIsNone(metadata["final_sequence"])
        self.assertIsNone(metadata["captured_at"])
        self.assertIsNone(metadata["capture_state"])
        self.assertEqual((metadata["samples"], metadata["records"]), (0, 0))

    def test_native_status_uses_retained_not_decoded_sequence(self):
        decoder, _ = many_ranges(2)
        decoder.sequence = 10
        session = stream.NativeSession.__new__(stream.NativeSession)
        session.lock = threading.Lock()
        session.state, session.error, session.build = "stopped", None, "v1"
        session.decoder, session.window = decoder, stream.SampleWindow()
        session.retained_sequence, session.retained_dropped = 7, 0
        self.assertEqual(session.status()["final_sequence"], 7)


if __name__ == "__main__":
    unittest.main()

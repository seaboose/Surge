"""Owned-game recorder controls stay separate from gameplay and evidence."""
import json
from pathlib import Path
import tempfile
import time
import unittest

from survive_capture import CaptureManager
from survive_recorder_bridge import RecorderBridge
from test_survive_capture import SID, lines, row


class Trial:
    def __init__(self, root):
        self.root = root
        self.running = True

    def _trial_path(self, trial_id):
        return self.root / trial_id

    def status(self):
        return {"trial": {"trial_id": "d" * 32, "process_state": "running" if self.running else "exited"}}


class RecorderBridgeTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).parent / "verification/temporary-test-files"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="recorder-bridge-", dir=base)
        self.root = Path(self.temp.name)
        self.capture = CaptureManager(self.root / "sources", self.root / "captures", poll_seconds=.01)
        self.study = Trial(self.root / "trials")
        self.trial_id = "d" * 32
        self.folder = self.study._trial_path(self.trial_id)
        self.folder.mkdir(parents=True)
        self.source = self.capture.source_root / (SID + ".jsonl")
        self.raw = b"".join(lines(row(0, "run_start", detail="fixed_seed"), row(.03)))
        self.capture.start("next")
        self.source.write_bytes(self.raw)
        self.wait(lambda c: c["records"] == 2)
        self.recording_id = self.capture.active.recording_id
        (self.folder / "recording.json").write_text(json.dumps({"trial_id": self.trial_id, "recording_id": self.recording_id}))
        self.bridge = RecorderBridge(self.capture, self.study, self.trial_id, poll_seconds=.02)

    def tearDown(self):
        self.capture.close()
        self.bridge.close()
        self.temp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = self.capture.status()["capture"]
            if predicate(value):
                return value
            time.sleep(.01)
        self.fail("Expected bounded recorder transition did not happen")

    def request(self, **changes):
        value = {"schema": "survive-recorder-control-v1", "trial_id": self.trial_id,
                 "recording_id": self.recording_id, "command": "stop_recording"}
        value.update(changes)
        (self.folder / "recorder-stop.json").write_text(json.dumps(value))

    def test_game_request_stops_only_recorder_and_keeps_exact_partial_prefix(self):
        self.bridge.start()
        self.request()
        value = self.wait(lambda c: c["state"] == "stopped")
        self.assertTrue(self.study.running)
        self.assertEqual(value["stop_reason"], "game_operator_stop")
        self.assertEqual(value["analysis_state"], "unavailable")
        self.assertIsNone(value["completion"])
        saved = self.capture.recording_root / self.recording_id / "source.jsonl"
        self.assertEqual(saved.read_bytes(), self.raw)
        with self.source.open("ab") as stream:
            stream.write(b'{"later_game_bytes":"continue after recorder stops"}\n')
        self.bridge.tick()
        status = json.loads((self.folder / "recorder-status.json").read_text())
        self.assertEqual(status["state"], "stopped")
        self.assertTrue(status["stop_requested"])
        self.assertEqual(saved.read_bytes(), self.raw)
        self.assertNotIn(b"run_end", saved.read_bytes())

    def test_invalid_request_is_visible_and_cannot_control_the_recorder(self):
        for changes in ({"trial_id": "e" * 32}, {"recording_id": "f" * 32},
                        {"command": "stop_game"}, {"path": "../other"}):
            self.request(**changes)
            self.bridge.tick()
            status = json.loads((self.folder / "recorder-status.json").read_text())
            self.assertEqual(status["state"], "recording")
            self.assertIn("does not match", status["error"])
            self.assertFalse(status["stop_requested"])
        (self.folder / "recorder-stop.json").write_text("x" * 2049)
        self.bridge.tick()
        self.assertEqual(self.capture.active.state, "recording")
        self.assertIsNotNone(self.bridge.error)

    def test_old_bridge_request_cannot_stop_a_new_recording(self):
        old = self.capture.active
        self.capture.stop()
        self.capture.start("next")
        self.request()
        self.bridge.tick()
        self.assertIsNot(old, self.capture.active)
        self.assertEqual(self.capture.active.state, "waiting")
        self.assertFalse(self.capture.active.stop_event.is_set())

    def test_owned_process_exit_preserves_partial_unknown_after_drain(self):
        self.request(command="invalid_command_cannot_block_exit_finalization")
        self.study.running = False
        self.bridge.exited_at = time.monotonic() - 3
        self.bridge.tick()
        value = self.capture.status()["capture"]
        self.assertEqual(value["state"], "stopped")
        self.assertEqual(value["stop_reason"], "owned_game_exited")
        self.assertEqual(value["analysis_state"], "unavailable")
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertIn("does not match", self.bridge.error)

    def test_bridge_binding_and_status_path_are_bounded(self):
        (self.folder / "recording.json").write_text(json.dumps({"trial_id": self.trial_id, "recording_id": "f" * 32}))
        with self.assertRaisesRegex(ValueError, "saved trial binding"):
            RecorderBridge(self.capture, self.study, self.trial_id)
        target = self.folder / "recorder-status.json"
        target.mkdir()
        with self.assertRaisesRegex(ValueError, "regular local file"):
            self.bridge.tick()
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(self.capture.active.state, "recording")
        target.rmdir()


if __name__ == "__main__":
    unittest.main()

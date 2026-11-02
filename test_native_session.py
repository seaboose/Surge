"""Process ownership, bounded retention, and incomplete evidence regression checks."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import engine
import native_integrity as native
import native_stream

ROOT = Path(__file__).resolve().parent
EXECUTABLE = ROOT / "native/build/surge_owned_app.exe"


@unittest.skipUnless(
    os.name == "nt" and EXECUTABLE.is_file(), "Build the owned Windows app first"
)
class NativeSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Each run explicitly approves a fresh clean owned capture in memory.
        # The operator's baseline registry is never read or changed.
        with tempfile.TemporaryDirectory(prefix="surge-session-test-") as folder:
            run = subprocess.run(
                [
                    str(ROOT / "native/build/surge_fixture.exe"),
                    "--build",
                    "v1",
                    "--scenario",
                    "clean",
                ],
                cwd=folder,
                capture_output=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if run.returncode:
                raise AssertionError(run.stderr.decode(errors="replace"))
            capture = json.loads((Path(folder) / "exported_code_audit.json").read_text())
        cls.registry = native.approve(
            capture,
            dict(schema=native.BASELINE_SCHEMA, entries=[]),
            "Fresh clean owned build for session regression checks",
        )

    def start(self):
        session = native_stream.NativeSession("v1", self.registry)
        self.addCleanup(session.stop)
        return session

    def wait_for(self, session, predicate, timeout=6):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            status = session.status()
            if predicate(status):
                return status
            if status["state"] == "failed":
                self.fail(status["error"])
            time.sleep(0.02)
        self.fail(f"Collection did not reach expected state: {session.status()}")

    def analyze(self, rows):
        data = engine.parse_bytes(json.dumps(rows).encode(), "owned-stream.json")
        return engine.analyze(data, None, native.default_policy(data))

    def test_repeated_start_stop_owns_child_and_preserves_snapshots(self):
        identities = set()
        for _ in range(3):
            session = self.start()
            status = self.wait_for(session, lambda s: s["samples"] >= 2)
            identities.add(status["session_id"])
            snapshot = session.snapshot()
            frozen = copy.deepcopy(snapshot)
            self.assertTrue(all(row["memory_matches"] for row in snapshot))
            self.assertTrue(all(row["pid"] == session.process.pid for row in snapshot))
            stopped = session.stop()
            self.assertEqual(stopped["state"], "stopped")
            self.assertIsNone(stopped["error"])
            self.assertIsNotNone(session.process.poll())
            self.assertFalse(session.reader.is_alive())
            self.assertEqual(snapshot, frozen)
            self.assertEqual(session.stop()["state"], "stopped")
            self.assertEqual(self.analyze(session.snapshot())["summary"]["Review"], 0)
        self.assertEqual(len(identities), 3)

    def test_retained_window_is_bounded_and_omission_is_unknown(self):
        with patch.object(native_stream, "MAX_SAMPLES", 3):
            session = self.start()
            self.wait_for(session, lambda s: s["samples"] >= 6)
            stopped = session.stop()
            self.assertEqual(stopped["records"], 6)
            self.assertEqual(stopped["evicted_samples"], stopped["samples"] - 3)
            rows = session.snapshot()
            health = [row for row in rows if row.get("stream_health")]
            self.assertEqual(len(health), 1)
            self.assertEqual(len(rows), 7)
            self.assertIsNone(health[0]["memory_matches"])
            self.assertEqual(self.analyze(rows)["summary"]["Unknown"], 1)

    def test_abrupt_child_exit_retains_evidence_with_unknown_health(self):
        session = self.start()
        self.wait_for(session, lambda s: s["samples"] >= 2)
        session.process.kill()
        self.assertTrue(session.closed.wait(5))
        status = session.stop()
        self.assertEqual(status["state"], "failed")
        self.assertIn("disconnected", status["error"])
        self.assertFalse(session.reader.is_alive())
        rows = session.snapshot()
        self.assertGreaterEqual(len(rows), 5)
        self.assertEqual(self.analyze(rows)["summary"]["Unknown"], 1)

    def test_control_pipe_eof_finishes_without_orphan(self):
        session = self.start()
        self.wait_for(session, lambda s: s["samples"] >= 1)
        session.process.stdin.close()
        self.assertTrue(session.closed.wait(5))
        self.assertEqual(session.status()["state"], "stopped")
        self.assertTrue(session.decoder.ended)
        self.assertIsNotNone(session.process.poll())
        self.assertFalse(session.reader.is_alive())

    def test_stale_capture_snapshot_carries_unknown_health(self):
        session = self.start()
        self.wait_for(session, lambda s: s["samples"] >= 1)
        # Freeze only the receiver clock. The child remains an ordinary owned
        # process; this regression checks stale-status and exported-evidence agree.
        with patch.object(native_stream.time, "monotonic", return_value=time.monotonic() + 10):
            self.assertIsNotNone(session.status()["error"])
            rows = session.snapshot()
            self.assertEqual(self.analyze(rows)["summary"]["Unknown"], 1)
        session.stop()

    def test_scope_rejects_non_owned_build_before_start(self):
        with patch.object(native_stream.subprocess, "Popen") as launch:
            for build in ("v3", "../other.exe", "1234", None):
                with self.assertRaises(ValueError):
                    native_stream.NativeSession(build, self.registry)
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

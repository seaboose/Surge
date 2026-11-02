"""Safety and evidence contracts of the real-launcher smoke check."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import check_launcher as launcher


class LauncherRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="surge launcher contract ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.application = self.root / "owned application"
        self.application.mkdir()
        self.appdata = self.root / "application data"
        self.appdata.mkdir()

    def setup_files(self):
        for name in (
            "Start-Surge.cmd", "Start-Surge.ps1", "desktop/main.cjs",
            "desktop/dist/index.html", "desktop/node_modules/electron/dist/electron.exe",
            ".venv/Scripts/python.exe",
        ):
            path = self.application / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("owned placeholder", encoding="utf-8")
        (self.application / "desktop/package.json").write_text('{"name":"surge-desktop"}', encoding="utf-8")

    def test_existing_profile_refusal_preserves_contents_without_launch(self):
        profile = self.appdata / "surge-desktop"
        profile.mkdir()
        evidence = profile / "keep.txt"
        evidence.write_bytes(b"existing user evidence")
        with (
            patch.object(launcher, "ROOT", self.root),
            patch.object(launcher, "ordinary_appdata", return_value=self.appdata),
            patch.object(launcher.subprocess, "Popen") as start,
        ):
            self.assertEqual(launcher.main(["--application-root", str(self.application)]), 1)
        start.assert_not_called()
        self.assertEqual(evidence.read_bytes(), b"existing user evidence")
        results = list((self.root / "verification/qualification").glob("launcher-*/artifacts/results.json"))
        self.assertEqual(len(results), 1)
        report = json.loads(results[0].read_text(encoding="utf-8"))
        self.assertFalse(report["launch_attempted"])
        self.assertEqual(report["criteria"]["L1"], "failed")
        self.assertEqual(report["criteria"]["L2"], "not_run")
        self.assertEqual(report["human_acceptance"], "pending")
        self.assertEqual(report["native_dialogs"], "not_run")

    def test_preconditions_reject_missing_setup_and_unexpected_profile_name(self):
        with self.assertRaises(FileNotFoundError):
            launcher.preconditions(self.application, self.appdata)
        self.setup_files()
        profile = launcher.preconditions(self.application, self.appdata)
        self.assertEqual(profile, self.appdata / "surge-desktop")
        self.assertFalse(profile.exists())
        (self.application / "desktop/package.json").write_text('{"name":"different"}', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "profile isolation"):
            launcher.preconditions(self.application, self.appdata)

    def test_liveness_requires_owned_renderer_worker_and_window(self):
        electron = str(self.application / "desktop/node_modules/electron/dist/electron.exe")
        python = str(self.application / ".venv/Scripts/python.exe")
        main = dict(ProcessId=10, ParentProcessId=1, ExecutablePath=electron, CommandLine="electron owned application")
        worker = dict(ProcessId=11, ParentProcessId=10, ExecutablePath=python, CommandLine="python desktop_worker")
        renderer = dict(ProcessId=12, ParentProcessId=10, ExecutablePath=electron, CommandLine="electron --type=renderer")
        window = {"handle": 7, "pid": 10, "title": "Surge — Development"}
        with patch.object(launcher, "owned_window", return_value=[window]):
            self.assertIsNotNone(launcher.observe([main, worker, renderer], self.application))
            self.assertIsNone(launcher.observe([main, worker], self.application))
            self.assertIsNone(launcher.observe([main, renderer], self.application))
            self.assertIsNone(launcher.observe([main, worker, dict(renderer, ParentProcessId=99)], self.application))
        with patch.object(launcher, "owned_window", return_value=[]):
            self.assertIsNone(launcher.observe([main, worker, renderer], self.application))

    def test_window_enumeration_requires_the_visible_owned_development_title(self):
        # The hosted failure had the correct worker/renderer but this current
        # source-window title was discarded by the old product-title filter.
        windows = {
            7: (10, True, "Surge — Development"),
            8: (99, True, "Surge — Development"),
            9: (10, False, "Surge — Development"),
            10: (10, True, "Surge"),
            11: (10, True, "Surge — Test session"),
            12: (10, True, "Surge could not start"),
        }
        user = Mock()
        user.GetWindowThreadProcessId.side_effect = (
            lambda handle, pid: setattr(pid._obj, "value", windows[handle][0])
        )
        user.IsWindowVisible.side_effect = lambda handle: windows[handle][1]
        user.GetWindowTextW.side_effect = (
            lambda handle, title, size: setattr(title, "value", windows[handle][2])
        )
        user.EnumWindows.side_effect = lambda callback, parameter: all(
            callback(handle, parameter) for handle in windows
        )
        with (
            patch.object(launcher.ctypes, "WinDLL", return_value=user, create=True),
            patch.object(launcher.ctypes, "WINFUNCTYPE", return_value=lambda callback: callback, create=True),
        ):
            self.assertEqual(launcher.owned_window(10), [
                {"handle": 7, "pid": 10, "title": "Surge — Development"}
            ])
            del windows[7]
            self.assertEqual(launcher.owned_window(10), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

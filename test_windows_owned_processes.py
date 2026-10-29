"""Owned Windows process identity and fail-closed native inspection controls."""
import ctypes
from ctypes import wintypes
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

from scripts import windows_owned_processes as inspector


class FakeKernel:
    def __init__(self, entries=(), first_error=18, next_error=18):
        self.entries = list(entries)
        self.position = -1
        self.first_error, self.next_error = first_error, next_error
        self.closed, self.queried = [], []
        self.open_error = self.image_error = None
        self.exit_code = inspector.STILL_ACTIVE

    def CreateToolhelp32Snapshot(self, flags, pid):
        return 500

    def fill(self, pointer, failure):
        if self.position >= len(self.entries):
            ctypes.set_last_error(failure)
            return False
        pid, parent, name, _ = self.entries[self.position]
        entry = pointer._obj
        entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile = pid, parent, name
        return True

    def Process32FirstW(self, snapshot, pointer):
        self.position = 0
        return self.fill(pointer, self.first_error)

    def Process32NextW(self, snapshot, pointer):
        self.position += 1
        return self.fill(pointer, self.next_error)

    def OpenProcess(self, flags, inherit, pid):
        self.queried.append(pid)
        if self.open_error:
            ctypes.set_last_error(self.open_error)
            return None
        return pid

    def QueryFullProcessImageNameW(self, handle, flags, buffer, size):
        if self.image_error:
            ctypes.set_last_error(self.image_error)
            return False
        buffer.value = next(x[3] for x in self.entries if x[0] == handle)
        size._obj.value = len(buffer.value)
        return True

    def GetExitCodeProcess(self, handle, value):
        value._obj.value = self.exit_code
        return True

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return True


@unittest.skipUnless(os.name == "nt", "Windows process identity contract")
class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(r"C:\owned-package")

    def test_native_structure_layout_matches_windows_x64(self):
        self.assertEqual(ctypes.sizeof(wintypes.DWORD), 4)
        self.assertEqual(inspector.ProcessEntry.th32DefaultHeapID.offset, 16 if ctypes.sizeof(ctypes.c_void_p) == 8 else 12)
        self.assertEqual(ctypes.sizeof(inspector.ProcessEntry), 568 if ctypes.sizeof(ctypes.c_void_p) == 8 else 556)

    def test_exact_owned_boundary_and_parent_preserved(self):
        api = FakeKernel([(1, 50, "Surge.exe", r"C:\owned-package\Surge.exe"),
                          (2, 51, "python.exe", r"C:\owned-package-other\python.exe"),
                          (3, 52, "unrelated.exe", r"C:\other\unrelated.exe")])
        actual = inspector.processes_owned_by(self.root, api=api)
        self.assertEqual(actual, [{"ProcessId": 1, "ParentProcessId": 50, "ExecutablePath": r"C:\owned-package\Surge.exe"}])
        self.assertEqual(api.queried, [1, 2])
        self.assertEqual(api.closed, [1, 2, 500])

    def test_empty_snapshot_is_allowed_only_for_no_more_files(self):
        self.assertEqual(inspector.processes_owned_by(self.root, api=FakeKernel()), [])
        api = FakeKernel(first_error=5)
        with self.assertRaisesRegex(OSError, "enumeration was incomplete"):
            inspector.processes_owned_by(self.root, api=api)
        self.assertEqual(api.closed, [500])

    def test_standalone_game_is_owned_only_inside_the_extracted_package(self):
        api = FakeKernel([(10, 5, "SurgeMovementLab.exe", r"C:\owned-package\resources\app\survive-game\SurgeMovementLab.exe"),
                          (11, 6, "SurgeMovementLab.exe", r"C:\another-game\SurgeMovementLab.exe"),
                          (12, 6, "UnrealEditor.exe", r"C:\engine\UnrealEditor.exe")])
        actual = inspector.processes_owned_by(self.root, api=api)
        self.assertEqual([row["ProcessId"] for row in actual], [10])
        self.assertEqual(actual[0]["ParentProcessId"], 5)
        self.assertEqual(api.queried, [10, 11])

    def test_mid_enumeration_failure_does_not_return_partial_list(self):
        api = FakeKernel([(1, 50, "Surge.exe", r"C:\owned-package\Surge.exe")], next_error=5)
        with self.assertRaisesRegex(OSError, "enumeration was incomplete"):
            inspector.processes_owned_by(self.root, api=api)
        self.assertEqual(api.closed, [1, 500])

    def test_live_relevant_image_failure_is_not_hidden(self):
        api = FakeKernel([(1, 50, "Surge.exe", r"C:\owned-package\Surge.exe")])
        api.image_error = 5
        with self.assertRaisesRegex(OSError, "live relevant process"):
            inspector.processes_owned_by(self.root, api=api)
        self.assertEqual(api.closed, [1, 500])

    def test_unqueryable_relevant_process_fails_closed(self):
        api = FakeKernel([(1, 50, "Surge.exe", r"C:\owned-package\Surge.exe")])
        api.open_error = 5
        with self.assertRaisesRegex(OSError, "ownership is unverified"):
            inspector.processes_owned_by(self.root, api=api)
        self.assertEqual(api.closed, [500])

    def test_confirmed_process_exit_races_are_not_live_survivors(self):
        for error_at_open in (True, False):
            api = FakeKernel([(1, 50, "Surge.exe", r"C:\owned-package\Surge.exe")])
            if error_at_open:
                api.open_error = 87
            else:
                api.image_error, api.exit_code = 5, 0
            with self.subTest(error_at_open=error_at_open):
                self.assertEqual(inspector.processes_owned_by(self.root, api=api), [])
                self.assertIn(500, api.closed)

    def test_original_five_second_deadline_fails_and_closes_snapshot(self):
        api = FakeKernel([(1, 50, "Surge.exe", r"C:\owned-package\Surge.exe")])
        with self.assertRaisesRegex(TimeoutError, "5-second"):
            inspector.processes_owned_by(self.root, api=api, clock=iter([0, 5]).__next__)
        self.assertEqual(api.closed, [500])

    def test_real_child_identity_and_parent_without_shell_or_wmi(self):
        child = subprocess.Popen([sys.executable, "-I", "-B", "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            began = time.monotonic()
            values = inspector.processes_owned_by(Path(sys.executable).parent)
            own = next(x for x in values if x["ProcessId"] == child.pid)
            self.assertEqual(own["ParentProcessId"], os.getpid())
            self.assertEqual(Path(own["ExecutablePath"]).resolve(), Path(sys.executable).resolve())
            self.assertLess(time.monotonic() - began, 5)
        finally:
            child.stdin.close()
            child.wait(timeout=5)
        self.assertNotIn(child.pid, {x["ProcessId"] for x in inspector.processes_owned_by(Path(sys.executable).parent)})

    def test_cli_inspection_error_is_nonzero_and_diagnostic(self):
        output = io.StringIO()
        with mock.patch.object(inspector, "processes_owned_by", side_effect=OSError("owned incomplete snapshot")), mock.patch("sys.stderr", output):
            self.assertEqual(inspector.main(["--application", str(self.root)]), 1)
        self.assertIn('"status": "failed"', output.getvalue())


if __name__ == "__main__":
    unittest.main()

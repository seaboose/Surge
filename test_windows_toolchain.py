import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.windows_toolchain import discover_windows_toolchain


class WindowsToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def touch(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"owned fixture")

    def fixture(self, edition="2022/BuildTools"):
        install = "Microsoft Visual Studio/" + edition
        vc = install + "/VC/Tools/MSVC/14.44.35207"
        for name in ("include/vector", "lib/x64/libcmt.lib"):
            self.touch(vc + "/" + name)
        for name in ("Lib/10.0.26100.0/ucrt/x64/ucrt.lib", "Lib/10.0.26100.0/um/x64/kernel32.lib",
                     "Include/10.0.26100.0/ucrt/stdio.h", "Include/10.0.26100.0/shared/sdkddkver.h",
                     "Include/10.0.26100.0/um/Windows.h"):
            self.touch("Windows Kits/10/" + name)
        return self.root / install, self.root / vc

    def test_original_build_tools_without_locator(self):
        _, expected = self.fixture()
        vc, _, version = discover_windows_toolchain(self.root)
        self.assertEqual((vc, version), (expected, "10.0.26100.0"))

    def test_locator_supports_enterprise_outside_default_folder(self):
        install, expected = self.fixture("custom/Enterprise")
        self.touch("Microsoft Visual Studio/Installer/vswhere.exe")
        calls = []
        def run(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout=str(install) + "\n")
        vc, _, _ = discover_windows_toolchain(self.root, run)
        self.assertEqual(vc, expected)
        self.assertIn("Microsoft.VisualStudio.Component.VC.Tools.x86.x64", calls[0][0])
        self.assertEqual(calls[0][1]["timeout"], 10)

    def test_refuses_missing_sdk_libraries(self):
        self.fixture()
        (self.root / "Windows Kits/10/Lib/10.0.26100.0/um/x64/kernel32.lib").unlink()
        with self.assertRaisesRegex(RuntimeError, "complete x64 Windows SDK"):
            discover_windows_toolchain(self.root)

    def test_incomplete_higher_version_and_nonversion_ignored(self):
        _, expected = self.fixture()
        for name in ("99.0", "Auxiliary"):
            self.touch("Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/" + name + "/include/vector")
        self.assertEqual(discover_windows_toolchain(self.root)[0], expected)

    def test_locator_failure_is_not_silently_replaced(self):
        self.fixture()
        self.touch("Microsoft Visual Studio/Installer/vswhere.exe")
        def run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, args[0])
        with self.assertRaises(subprocess.CalledProcessError):
            discover_windows_toolchain(self.root, run)

    def test_locator_requires_one_absolute_installation(self):
        self.touch("Microsoft Visual Studio/Installer/vswhere.exe")
        for output in ("", "relative/path", "first\nsecond"):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                discover_windows_toolchain(self.root, lambda *a, **k: SimpleNamespace(stdout=output))


if __name__ == "__main__":
    unittest.main()

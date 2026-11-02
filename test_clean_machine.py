"""Clean qualification must not confuse a hosted launch with a fresh Windows VM."""
import copy
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from scripts.check_clean_machine import guest_preconditions, isolated_script_command


class IsolatedToolEntryPoints(unittest.TestCase):
    def test_isolated_imports_resolve_tool_siblings_not_working_directory(self):
        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            Path(temporary, 'check_windows_package.py').write_text("raise RuntimeError('untrusted cwd import')", encoding='utf-8')
            for script in ('check_survive_package.py', 'check_windows_package.py', 'verify_windows_consumer.py'):
                command = isolated_script_command(sys.executable, root / 'scripts' / script, '--help')
                result = subprocess.run(command, cwd=temporary, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            result = subprocess.run([sys.executable, '-I', '-B', str(root / 'scripts/check_clean_machine.py'), '--help'], cwd=temporary, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


class CleanGuestPreconditions(unittest.TestCase):
    def setUp(self):
        self.probe = {"machine": {"model": "Virtual Machine"}, "os": {"architecture": "64-bit"},
                      "path_commands": [], "installed_developer_products": [],
                      "known_engine_roots": [], "registered_engines": []}
        self.provenance = {"provisioning": "fresh-vm", "image": "Windows 11 x64 test image", "created_utc": "2026-10-28T00:00:00Z"}

    def test_clean_guest_with_explicit_provisioning_is_eligible(self):
        self.assertEqual(guest_preconditions(self.probe, self.provenance), [])

    def test_host_model_is_not_qualified_by_hypervisor_flag(self):
        self.probe["machine"].update(model="System Product Name", hypervisor_present=True)
        self.assertTrue(guest_preconditions(self.probe, self.provenance))

    def test_each_developer_dependency_source_blocks_clean_claim(self):
        for field, value in (("path_commands", [{"Name": "node.exe", "Source": "C:\\Tools\\node.exe"}]),
                             ("installed_developer_products", [{"DisplayName": "Python 3.13"}]),
                             ("installed_store_developer_products", [{"Name": "PythonSoftwareFoundation.Python.3.13"}]),
                             ("known_engine_roots", ["UE_5.8"]), ("registered_engines", ["owned-test-engine"])):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.probe)
                changed[field] = value
                self.assertTrue(guest_preconditions(changed, self.provenance))

    def test_windows_store_alias_is_recorded_but_not_an_installed_interpreter(self):
        self.probe["path_commands"] = [{"Name": "python.exe", "Source": "C:\\Fixtures\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe"}]
        self.assertEqual(guest_preconditions(self.probe, self.provenance), [])

    def test_missing_invalid_or_timezone_free_provenance_blocks(self):
        for provenance in (None, {}, {**self.provenance, "provisioning": "existing-host"},
                           {**self.provenance, "created_utc": "2026-10-28"},
                           {**self.provenance, "unexpected": True}):
            self.assertTrue(guest_preconditions(self.probe, provenance))

    def test_non_x64_is_not_eligible(self):
        self.probe["os"]["architecture"] = "32-bit"
        self.assertTrue(guest_preconditions(self.probe, self.provenance))


if __name__ == "__main__":
    unittest.main()

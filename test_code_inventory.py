"""A learning inventory must not turn private/generated trees into source scope."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import code_inventory


class CodeInventoryTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parent / "verification/temporary-test-files"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="code-inventory-", dir=base)
        self.root = Path(self.temp.name)
        self.write("scripts/build_windows_package.py",
                   "BACKEND = ('engine',)\nDESKTOP = ('main.cjs',)\nraise RuntimeError('must never execute builder')\n")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def test_inventory_separates_runtime_tests_and_tools_without_opening_private_trees(self):
        source = self.write("engine.py", "# first-party\n\nvalue = 1\n")
        self.write("desktop/main.cjs", "module.exports = {};\n")
        self.write("desktop/src/App.jsx", "export default function App() {}\n")
        self.write("test_engine.py", "# test\n")
        self.write("scripts/build.py", "# development only\n")
        self.write("docs/guide.md", "A guide\n")
        for prefix in ("node_modules", "verification", "_Recovery", "third_party", ".venv", "output",
                       "unreal/SurgeMovementLab/Saved", "unreal/SurgeMovementLab/telemetry/local",
                       "unreal/SurgeMovementLab/telemetry/tmpabcdefgh",
                       "unreal/SurgeMovementLab/profiles/evidence"):
            path = self.root / prefix / "private.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\xff")  # Invalid source encoding: traversing it would fail.
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        report = code_inventory.inventory(self.root)
        values = {f["path"]: f for f in report["files"]}
        self.assertEqual(values["engine.py"]["category"], "backend_runtime_source")
        self.assertEqual(values["engine.py"]["physical_lines"], 3)
        self.assertEqual(values["engine.py"]["sha256"], before)
        self.assertEqual(report["runtime_source_total"]["files"], 3)
        self.assertEqual(values["test_engine.py"]["category"], "tests")
        self.assertEqual(values["scripts/build.py"]["category"], "development_tools")
        self.assertFalse(any(f.endswith("private.py") for f in values))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.assertFalse(report["release_capabilities"]["reviewed_snapshot_matches"])
        self.assertIsNone(report["release_capabilities"]["full_survive_workflow"]["declared_payload"])
        json.dumps(report, allow_nan=False)

    def test_versioned_adapters_are_runtime_dependencies_not_obsolete_files(self):
        for name in code_inventory.ADAPTERS:
            self.write("unreal/SurgeMovementLab/telemetry/" + name, "# runtime adapter\n")
        self.write("unreal/SurgeMovementLab/telemetry/test_v3.py", "# regression\n")
        self.write("app.py", "# alternative interface\n")
        report = code_inventory.inventory(self.root)
        self.assertEqual(report["categories"]["survive_analysis_runtime_source"]["files"], 4)
        self.assertEqual(report["categories"]["tests"]["files"], 1)
        self.assertEqual(report["categories"]["alternate_interfaces"]["files"], 1)

    def test_inventory_refuses_dynamic_package_declarations_and_unbounded_source(self):
        path = self.root / "scripts/build_windows_package.py"
        path.write_text("BACKEND=tuple(['engine'])\nDESKTOP=('main.cjs',)\n", encoding="utf-8")
        with self.assertRaises((ValueError, TypeError)):
            code_inventory.inventory(self.root)
        path.write_text("BACKEND=('engine',)\nDESKTOP=('main.cjs',)\n", encoding="utf-8")
        self.write("engine.py", "x" * 256)
        with patch.object(code_inventory, "MAX_FILE_BYTES", 128), self.assertRaisesRegex(ValueError, "bound"):
            code_inventory.inventory(self.root)
        with patch.object(code_inventory, "MAX_FILES", 1), self.assertRaisesRegex(ValueError, "entry count"):
            code_inventory.inventory(self.root)


if __name__ == "__main__":
    unittest.main()

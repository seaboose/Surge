"""Downloaded evidence must fail closed without running its frozen sources."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.verify_model_evidence import verify, STREAM_SOURCES


class ModelEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="surge-model-evidence-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fingerprints = {}
        for name in STREAM_SOURCES:
            path = self.root / "source" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            # Invalid Python is deliberate: offline verification must only hash it.
            path.write_bytes(b"frozen non-executable test bytes\n")
            fingerprints[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.report = dict(schema="surge-stream-model-v1", status="failed",
                           original_campaign="incomplete", error="Deliberate preflight failure",
                           controls=[], runs=[], phases=[], source_sha256=fingerprints,
                           limits=dict(ordinary_input_bytes=262144, process_memory_bytes=1073741824,
                                       ordinary_seconds=5, boundary_seconds=15, total_seconds=5400,
                                       log_bytes=10485760, development_seconds=900,
                                       final_seconds=600, replay_seconds=900))
        self.write()

    def write(self):
        (self.root / "report.json").write_text(json.dumps(self.report), encoding="utf-8")
        manifest = [dict(path=p.relative_to(self.root).as_posix(), bytes=p.stat().st_size,
                         sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in sorted(self.root.rglob("*"))
                    if p.is_file() and p.name != "evidence-manifest.json"]
        (self.root / "evidence-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_failed_attempt_requires_explicit_inspection_and_stays_failed(self):
        with self.assertRaises(ValueError):
            verify(self.root)
        result = verify(self.root, allow_failed=True)
        self.assertEqual(result["status"], "failed_attempt_preserved")
        self.assertEqual(result["completed_cases"], 0)

    def test_changed_downloaded_bytes_are_rejected(self):
        (self.root / "source/engine.py").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            verify(self.root, allow_failed=True)

    def test_escaping_manifest_path_is_rejected_before_reading(self):
        path = self.root / "evidence-manifest.json"
        path.write_text(json.dumps([dict(path="../outside.txt", bytes=0, sha256="0"*64)]))
        with self.assertRaisesRegex(ValueError, "escaping"):
            verify(self.root, allow_failed=True)

    def test_missing_frozen_source_claim_is_rejected(self):
        self.report["source_sha256"].pop("engine.py")
        self.write()
        with self.assertRaises(ValueError):
            verify(self.root, allow_failed=True)

    def test_weaker_limits_are_rejected_even_when_manifest_is_consistent(self):
        self.report["limits"]["ordinary_seconds"] = 6
        self.write()
        with self.assertRaises(ValueError):
            verify(self.root, allow_failed=True)

    def test_partial_failure_cannot_be_relabeled_passed(self):
        self.report["status"] = "passed"
        self.write()
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_duplicate_scenario_inventory_is_rejected(self):
        row = dict(phase="development", id="positive-2-1", recipe=dict(kind="positive"), status="not_run")
        self.report["runs"] = [row, row]
        self.write()
        with self.assertRaisesRegex(ValueError, "Duplicate scenario"):
            verify(self.root, allow_failed=True)

    def test_cli_invalid_report_returns_nonzero_with_diagnostic(self):
        self.report["limits"]["ordinary_seconds"] = 6
        self.write()
        script = Path(__file__).resolve().parent / "scripts/verify_model_evidence.py"
        result = subprocess.run([sys.executable, "-B", str(script), str(self.root), "--allow-failed"],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Model limit differs: ordinary_seconds", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_import_preserves_path_and_root_test_module_resolution(self):
        root = Path(__file__).resolve().parent
        check = """import importlib.util, json, sys
from pathlib import Path
original_path = list(sys.path)
import scripts.verify_model_evidence
resolved = importlib.util.find_spec("test_native_stream").origin
print(json.dumps({"path_preserved": sys.path == original_path, "resolved": resolved}))
assert sys.path == original_path, "Verifier import changed the caller's module search path"
assert Path(resolved).resolve() == Path.cwd() / "test_native_stream.py", resolved
import test_native_stream
assert Path(test_native_stream.__file__).resolve() == Path.cwd() / "test_native_stream.py"
"""
        result = subprocess.run([sys.executable, "-B", "-c", check], cwd=root,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["path_preserved"])


if __name__ == "__main__":
    unittest.main()

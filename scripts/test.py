"""Run the portable Python suite, including evaluation-protocol regressions."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))
for folder in ("verification/temporary-test-files", "verification/electron"):
    (ROOT / folder).mkdir(parents=True, exist_ok=True)
loader = unittest.TestLoader()
suite = loader.discover(str(ROOT), pattern="test_*.py")
suite.addTests(
    loader.discover(
        str(ROOT / "benchmarks"),
        pattern="test_refinement4_protocol.py",
        top_level_dir=str(ROOT / "benchmarks"),
    )
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)

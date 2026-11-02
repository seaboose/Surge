"""Real case-reader and worker checks using bounded, retained owned fixtures."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import desktop_worker as desktop
import engine


class CaseRecoveryWorkerTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).parent / "verification" / "qualification" / "case-recovery-worker"
        parent.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="attempt-", dir=parent))
        self.rows = [{"reading": 7, "owned_padding": "x" * 1024} for _ in range(70)]
        self.data = engine.parse_bytes(engine.canonical(self.rows).encode(), "owned.json")
        self.config = desktop.default_config()
        self.config["rules"] = [
            dict(name="Owned threshold", field="reading", op="gt", value=5, priority="Warning")
        ]
        self.result = engine.analyze(self.data, None, self.config)
        self.original = self.root / "original.case.json"
        engine.save_case(self.original, self.data, None, self.config, self.result)
        self.raw = self.original.read_bytes()
        self.assertGreater(len(self.raw), 65536)
        self.assertLessEqual(len(self.raw), 256 * 1024)
        self.ws = desktop.Workspace()
        self.ws.dispatch("open", {"path": str(self.original)})
        self.before = copy.deepcopy(self.ws.snapshot())

    def tearDown(self):
        # Retain owned inputs even on assertion failure; no user files are touched.
        files = [
            dict(path=p.name, bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(self.root.iterdir()) if p.is_file()
        ]
        (self.root / "fixtures.json").write_text(
            json.dumps(dict(test=self.id(), files=files), indent=2), encoding="utf-8"
        )

    def test_truncated_case_is_refused_without_replacing_investigation(self):
        for length in (0, 1, 65535, 65536, len(self.raw) - 1):
            with self.subTest(length=length):
                partial = self.root / f"partial-{length}.case.json"
                partial.write_bytes(self.raw[:length])
                for method in ("library_verify", "open"):
                    with self.assertRaises(ValueError):
                        self.ws.dispatch(method, {"path": str(partial)})
                    self.assertEqual(self.ws.snapshot(), self.before)
        self.assertEqual(self.original.read_bytes(), self.raw)

    def test_modified_complete_case_is_refused_without_replacing_investigation(self):
        doc = json.loads(self.raw)
        doc["payload"]["current"]["text"] = doc["payload"]["current"]["text"].replace(
            '"reading":7', '"reading":8'
        )
        self.assertNotEqual(doc["payload"]["current"]["text"], self.data.text)
        changed = self.root / "changed.case.json"
        changed.write_text(json.dumps(doc), encoding="utf-8")
        for method in ("library_verify", "open"):
            with self.assertRaisesRegex(ValueError, "integrity"):
                self.ws.dispatch(method, {"path": str(changed)})
            self.assertEqual(self.ws.snapshot(), self.before)
        self.assertEqual(self.original.read_bytes(), self.raw)

    def test_snapshot_and_verified_reopen_preserve_actual_evidence(self):
        target = self.root / "snapshot.case.json"
        self.ws.dispatch(
            "library_snapshot", {"path": str(target), "revision": self.ws.revision}
        )
        self.assertEqual(self.ws.snapshot(), self.before)
        self.assertEqual(
            self.ws.dispatch("library_verify", {"path": str(target)}), {"verified": True}
        )
        self.assertEqual(self.ws.snapshot(), self.before)
        restored = desktop.Workspace()
        state = restored.dispatch("open", {"path": str(target)})
        self.assertEqual(restored.current.text, self.data.text)
        self.assertEqual(restored.result, self.result)
        self.assertEqual(state["summary"], self.before["summary"])
        self.assertIsNone(state["inspected_capture"])
        self.assertEqual(self.original.read_bytes(), self.raw)


if __name__ == "__main__":
    unittest.main()

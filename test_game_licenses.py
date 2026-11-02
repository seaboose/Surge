"""Keep attribution unless the exact reviewed payload and notice bytes match."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parent / "unreal/SurgeMovementLab/scripts/package-standalone.py"
SPEC = importlib.util.spec_from_file_location("game_packaging", SCRIPT)
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class GameNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.game = root / "game"
        self.notices = root / "notices"
        self.game.mkdir()
        self.notices.mkdir()
        (self.game / "Game.exe").write_bytes(b"Reviewed fixture runtime")
        (self.notices / "editor.license").write_bytes(b"Editor attribution")
        (self.notices / "runtime.license").write_bytes(b"Runtime attribution")
        runtime = [{"path": "Game.exe", "sha256": packaging.digest(self.game / "Game.exe")}]
        self.fingerprint = hashlib.sha256(json.dumps(runtime, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.omissions = {packaging.digest(self.notices / "editor.license")}

    def selected(self):
        return {path.name for path in packaging.engine_notice_files(self.notices, self.game)}

    def test_unreviewed_payload_keeps_all_notices(self):
        self.assertEqual(self.selected(), {"editor.license", "runtime.license"})

    def test_exact_review_omits_only_matching_notice(self):
        with patch.object(packaging, "REVIEWED_WINDOWS_RUNTIME_SHA256", self.fingerprint), patch.object(packaging, "UNUSED_NOTICE_SHA256", self.omissions):
            self.assertEqual(self.selected(), {"runtime.license"})

    def test_changed_runtime_or_extra_dependency_keeps_attribution(self):
        with patch.object(packaging, "REVIEWED_WINDOWS_RUNTIME_SHA256", self.fingerprint), patch.object(packaging, "UNUSED_NOTICE_SHA256", self.omissions):
            (self.game / "NewDependency.dll").write_bytes(b"New dependency")
            self.assertEqual(self.selected(), {"editor.license", "runtime.license"})

    def test_changed_notice_keeps_attribution(self):
        with patch.object(packaging, "REVIEWED_WINDOWS_RUNTIME_SHA256", self.fingerprint), patch.object(packaging, "UNUSED_NOTICE_SHA256", self.omissions):
            (self.notices / "editor.license").write_bytes(b"Changed attribution")
            self.assertEqual(self.selected(), {"editor.license", "runtime.license"})


if __name__ == "__main__":
    unittest.main()

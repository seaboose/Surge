"""Installed runtime identity, separate durable data, and no editor fallback."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from survive_runtime import RuntimeLayout, ADAPTERS, PROFILES
from survive_study import StudyManager


class FakeProcess:
    pid = 12345
    returncode = 0
    def poll(self): return self.returncode


class SurviveRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(__file__).resolve().parent / "verification/temporary-test-files"
        self.base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="packaged-survive-", dir=self.base)
        self.root = Path(self.temp.name)
        self.app = self.root / "release/resources/app"
        self.data = self.root / "profile/Survive"
        self.game = self.app / "survive-game"
        self.exe = "SurgeMovementLab/Binaries/Win64/SurgeMovementLab-Win64-Shipping.exe"
        for name, raw in ((self.exe, b"owned-game"), ("SurgeMovementLab/Content/Paks/game.pak", b"cooked-content")):
            path = self.game / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.manifest = {"schema": "survive-standalone-game-v1", "standalone": True,
                         "platform": "Win64", "configuration": "Shipping", "engine_version": "5.8.4",
                         "entry_executable": self.exe, "files": []}
        for path in sorted(self.game.rglob("*")):
            if path.is_file():
                self.manifest["files"].append({"path": path.relative_to(self.game).as_posix(),
                                                "bytes": path.stat().st_size,
                                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        self.descriptor = {"schema": "surge-survive-runtime-v1", "game_root": "survive-game",
                           "game_executable": self.exe, "game_manifest": "survive-game-manifest.json",
                           "game_manifest_sha256": ""}
        self.identity()
        lab = self.app / "unreal/SurgeMovementLab"
        for name in (*ADAPTERS, "survive-policy.json"):
            self.write(lab / "telemetry" / name, "{}")
        for name in PROFILES:
            self.write(lab / "profiles" / (name + ".json"), json.dumps({"id": name}))
        for name in ("engine.py", "survive_capture.py", "survive_study.py", "survive_runtime.py"):
            self.write(self.app / name, "# fixture runtime\n")
        self.layout = RuntimeLayout(self.app, self.data, packaged=True)
        self.launches = []
        def launch(args, **kwargs):
            self.launches.append((args, kwargs))
            return FakeProcess()
        self.study = StudyManager(runtime=self.layout, popen_factory=launch, monitor=False)

    def tearDown(self):
        self.assertTrue(self.root.resolve().is_relative_to(self.base.resolve()))
        self.temp.cleanup()

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def identity(self):
        path = self.app / "survive-game-manifest.json"
        self.write(path, json.dumps(self.manifest))
        self.descriptor["game_manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write(self.app / "survive-runtime.json", json.dumps(self.descriptor))

    def start(self):
        return self.study.start("scripted", 1337, PROFILES[0], "test", "practice")

    def test_packaged_launch_uses_only_owned_game_and_separate_data(self):
        before = {p.relative_to(self.app).as_posix(): p.read_bytes() for p in self.app.rglob("*") if p.is_file()}
        trial = self.start()["trial"]["trial_id"]
        args, kwargs = self.launches[0]
        self.assertEqual(args[0], str(self.game / self.exe))
        self.assertEqual(kwargs["cwd"], str((self.game / self.exe).parent))
        self.assertFalse(kwargs["shell"])
        self.assertIn("-SurviveSavedDir=" + str(self.data), args)
        self.assertIn("-UserDir=" + str(self.data / "Unreal"), args)
        self.assertNotIn("UnrealEditor", " ".join(args))
        self.assertEqual(self.study.directory, self.data / "StudyTrials")
        self.assertEqual(self.study.actions, self.data / "StudyActions")
        self.assertEqual(self.study._manifest(trial)["runtime_kind"], "standalone")
        self.assertEqual(before, {p.relative_to(self.app).as_posix(): p.read_bytes() for p in self.app.rglob("*") if p.is_file()})

    def test_missing_descriptor_game_or_analysis_asset_fails_without_editor_fallback(self):
        targets = [self.app / "survive-runtime.json", self.game / self.exe,
                   self.app / "unreal/SurgeMovementLab/telemetry/prepare_v3.py"]
        for path in targets:
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaises(ValueError):
                        self.start()
                    self.assertFalse(self.launches)
                finally:
                    path.write_bytes(raw)

    def test_corrupt_manifest_and_same_size_game_change_are_rejected(self):
        manifest = self.app / "survive-game-manifest.json"
        original = manifest.read_bytes()
        manifest.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.start()
        manifest.write_bytes(original)
        exe = self.game / self.exe
        exe.write_bytes(b"X" * exe.stat().st_size)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.start()
        self.assertFalse(self.launches)

    def test_descriptor_paths_cannot_escape_or_launch_another_executable(self):
        for name in ("../other.exe", "C:/other.exe", "Engine/CrashReportClient.exe", "//host/file.exe",
                     "SurgeMovementLab/Binaries/Win64/SurgeMovementLab.exe",
                     "SurgeMovementLab/Binaries/Win64/SurgeMovementLab-Win64-Development.exe",
                     "SurgeMovementLab/Binaries/Win64/../other.exe", "survive-game\\other.exe"):
            with self.subTest(name=name):
                self.descriptor["game_executable"] = name
                self.identity()
                with self.assertRaises(ValueError):
                    self.layout.verify_game()
        self.assertFalse(self.launches)

    def test_manifest_rejects_wrong_platform_nonstandalone_and_duplicate_paths(self):
        original = json.loads(json.dumps(self.manifest))
        cases = [{"platform": "Linux"}, {"standalone": False}, {"configuration": "Development"}, {"engine_version": "x" * 65},
                 {"files": [self.manifest["files"][0], self.manifest["files"][0]]}]
        for changes in cases:
            with self.subTest(changes=changes):
                self.manifest = dict(original, **changes)
                self.identity()
                with self.assertRaises(ValueError):
                    self.layout.verify_game()

    def test_packaged_data_root_is_explicit_local_and_disjoint(self):
        for data in (None, "relative", self.app / "Saved", self.root, "//server/share/Survive"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                RuntimeLayout(self.app, data, packaged=True)
        source = RuntimeLayout(self.app)
        self.assertEqual(source.saved, self.app / "unreal/SurgeMovementLab/Saved")
        self.assertFalse(source.packaged)

    def test_relocated_application_reuses_saved_trials_and_freeze_without_copying_private_data(self):
        trial = self.start()["trial"]["trial_id"]
        frozen = self.study.freeze()["freeze"]
        original = (self.data / "StudyTrials" / trial / "trial.json").read_bytes()
        relocated = self.root / "relocated release/resources/app"
        shutil.copytree(self.app, relocated)
        moved = StudyManager(runtime=RuntimeLayout(relocated, self.data, packaged=True),
                             popen_factory=lambda *a, **k: FakeProcess(), monitor=False)
        self.assertEqual(moved.trials()[0]["trial_id"], trial)
        self.assertEqual(moved.freeze()["freeze"], frozen)
        self.assertEqual((self.data / "StudyTrials" / trial / "trial.json").read_bytes(), original)
        self.assertFalse((relocated / "unreal/SurgeMovementLab/Saved").exists())

    def test_held_out_launch_verifies_once_per_trial_and_rejects_later_drift(self):
        self.study.freeze()
        with patch.object(self.layout, "verify_game", wraps=self.layout.verify_game) as verify:
            self.study.start("scripted", 9001, PROFILES[0], "test", "held-out")
            self.assertEqual(verify.call_count, 1)
            exe = self.game / self.exe
            exe.write_bytes(b"X" * exe.stat().st_size)
            with self.assertRaisesRegex(ValueError, "changed"):
                self.study.start("scripted", 9007, PROFILES[0], "test", "held-out")
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(len(self.launches), 1)

    def test_workspace_routes_all_services_to_the_trusted_data_root(self):
        from survive_workspace import SurviveWorkspace, validate
        with patch("survive_runtime.ROOT", self.app):
            service = SurviveWorkspace(survive_data_root=self.data, packaged=True)
            try:
                self.assertEqual(service.capture.source_root, self.data / "Telemetry")
                self.assertEqual(service.capture.recording_root, self.data / "SurgeRecordings")
                self.assertEqual(service.study.directory, self.data / "StudyTrials")
                self.assertEqual(service.investigations.root, self.data / "Investigations")
            finally:
                service.close()
        for field in ("packaged", "survive_data_root", "game_executable", "game_window"):
            with self.assertRaises(ValueError):
                validate("survive_sources", {field: "untrusted"})

    def test_worker_uses_constructor_configuration_and_legacy_operations_stay_lazy(self):
        from desktop_worker import Workspace
        for window in (None, {"x": -1044, "y": 48, "width": 1008, "height": 567}):
            with self.subTest(game_window=window):
                worker = Workspace(survive_data_root=str(self.data), packaged=True, game_window=window)
                self.assertIsNone(worker.survive)
                with patch("survive_workspace.SurviveWorkspace") as factory:
                    worker.dispatch("state", {})
                    factory.assert_not_called()
                    worker.dispatch("survive_sources", {})
                    factory.assert_called_once_with(survive_data_root=str(self.data), packaged=True, game_window=window)
                    factory.return_value.dispatch.assert_called_once_with("survive_sources", {})
                    worker.close()


if __name__ == "__main__":
    unittest.main()

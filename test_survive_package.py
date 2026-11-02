"""Small owned game artifacts verify runtime packaging without launching a game."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from scripts import survive_package as package
from scripts import check_windows_package as consumer


class SurvivePackageTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parent / "verification/qualification/survive-package-controls"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stage = self.root / "stage"
        self.game = self.stage / "game"
        self.game.mkdir(parents=True)
        self.executable = "SurgeMovementLab/Binaries/Win64/SurgeMovementLab-Win64-Shipping.exe"
        self.contents = {self.executable: b"owned nonexecutable fixture",
                         "SurgeMovementLab/Content/Paks/SurgeMovementLab.pak": b"owned cooked fixture",
                         "licenses/Unreal-notice.txt": b"owned notice fixture"}
        for name, value in self.contents.items():
            path = self.game / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        self.manifest = dict(schema="survive-standalone-game-v1", standalone=True,
                             configuration="Shipping", platform="Win64", engine_version="5.8.4",
                             entry_executable=self.executable, licenses=["licenses/Unreal-notice.txt"],
                             files=[dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                                    for name, raw in self.contents.items()])
        self.save()

    def save(self):
        (self.stage / "game-manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_copy_preserves_exact_game_identity_and_only_declared_analysis_assets(self):
        source = self.root / "source"
        for name in package.RUNTIME_ASSETS:
            target = source / "unreal/SurgeMovementLab" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("owned analysis fixture: " + name, encoding="utf-8")
        private = source / "unreal/SurgeMovementLab/Saved/player.jsonl"
        private.parent.mkdir()
        private.write_text("never ship", encoding="utf-8")
        app = self.root / "app"
        app.mkdir()
        result = package.copy_runtime(self.stage, app, source, time.monotonic() + 10)
        self.assertEqual(result["files"], len(self.contents))
        self.assertEqual({p.relative_to(app / "survive-game").as_posix(): p.read_bytes()
                          for p in (app / "survive-game").rglob("*") if p.is_file()}, self.contents)
        descriptor = json.loads((app / "survive-runtime.json").read_text())
        self.assertEqual(descriptor["game_executable"], self.executable)
        self.assertEqual(descriptor["game_manifest_sha256"], package.digest(app / descriptor["game_manifest"]))
        self.assertEqual(set(result["assets_sha256"]), set(package.RUNTIME_ASSETS))
        self.assertFalse((app / "unreal/SurgeMovementLab/Saved").exists())
        self.assertEqual((self.game / self.executable).read_bytes(), self.contents[self.executable])

    def test_changed_or_unlisted_game_files_fail_before_copy(self):
        binary = self.game / self.executable
        binary.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            package.validate_game(self.stage, time.monotonic() + 10)
        binary.write_bytes(self.contents[self.executable])
        (self.game / "extra.txt").write_text("not declared")
        with self.assertRaisesRegex(ValueError, "Undeclared"):
            package.validate_game(self.stage, time.monotonic() + 10)

    def test_development_or_wrong_platform_game_cannot_enter_product_package(self):
        for field, value in (("configuration", "Development"), ("configuration", "DebugGame"),
                             ("platform", "Linux"), ("platform", None), ("standalone", False)):
            with self.subTest(field=field, value=value):
                previous = self.manifest[field]
                self.manifest[field] = value
                self.save()
                with self.assertRaisesRegex(ValueError, "Unsupported standalone game manifest"):
                    package.validate_game(self.stage, time.monotonic() + 10)
                self.manifest[field] = previous
        self.save()

    def test_manifest_rejects_private_development_unsafe_and_duplicate_paths(self):
        original = json.loads(json.dumps(self.manifest))
        for name in ("../escape.exe", "C:/game.exe", "SurgeMovementLab/Source/Game.cpp",
                     "SurgeMovementLab/Saved/player.jsonl", "Engine/debug.pdb", self.executable.upper()):
            with self.subTest(name=name):
                self.manifest = json.loads(json.dumps(original))
                self.manifest["files"].append(dict(path=name, bytes=0, sha256=hashlib.sha256(b"").hexdigest()))
                self.save()
                with self.assertRaises(ValueError):
                    package.validate_game(self.stage, time.monotonic() + 10)
        self.assertFalse((self.root / "escape.exe").exists())

    def test_missing_licences_and_expansion_limits_fail_closed(self):
        self.manifest["licenses"] = []
        self.save()
        with self.assertRaisesRegex(ValueError, "licences"):
            package.validate_game(self.stage, time.monotonic() + 10)
        self.manifest["licenses"] = ["licenses/Unreal-notice.txt"]
        self.save()
        with patch.dict(package.GAME_LIMITS, expanded_bytes=1):
            with self.assertRaisesRegex(ValueError, "expanded-size"):
                package.validate_game(self.stage, time.monotonic() + 10)

    def test_combined_consumer_uses_fixed_limits_and_requires_game_components(self):
        contents = {name: b"owned" for name in (
            "Surge.exe", "resources/python/python.exe", "resources/app/desktop_worker.py",
            "resources/app/desktop/main.cjs", "resources/app/native/build/surge_owned_app.exe",
            "resources/app/native/baselines.json", "resources/app/package-identity.json",
            "resources/app/survive_runtime.py", "resources/app/survive-runtime.json",
            "resources/app/survive-game-manifest.json", "resources/app/survive-game/" + self.executable)}
        contents.update({"resources/app/unreal/SurgeMovementLab/" + name: b"owned" for name in package.RUNTIME_ASSETS})
        archive = self.root / "combined.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for name, raw in contents.items():
                output.writestr(name, raw)
        manifest = dict(schema="surge-windows-package-v1", package_kind="surge-survive",
                        survive=dict(game_executable="survive-game/" + self.executable),
                        archive=dict(bytes=archive.stat().st_size, sha256=package.digest(archive)),
                        files=[dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                               for name, raw in contents.items()])
        self.assertEqual(consumer.verify_package(archive, manifest)["package_kind"], "surge-survive")
        manifest["limits"] = {"expanded_bytes": 100 * 1024**3}
        manifest["files"][0]["bytes"] = package.COMBINED_LIMITS["expanded_bytes"] + 1
        with self.assertRaisesRegex(ValueError, "3072 MiB"):
            consumer.verify_package(archive, manifest)
        manifest["files"][0]["bytes"] = len(contents["Surge.exe"])
        manifest["survive"]["game_executable"] = "survive-game/not-present.exe"
        with self.assertRaisesRegex(ValueError, "Required bundled component"):
            consumer.verify_package(archive, manifest)

    def test_restricted_environment_recovers_missing_windows_variables(self):
        with patch.dict(consumer.os.environ, {}, clear=True):
            environment = consumer.restricted_environment(self.root)
        self.assertTrue(environment["SYSTEMROOT"])
        self.assertEqual(environment["SYSTEMROOT"], environment["WINDIR"])
        self.assertEqual(environment["PATH"], consumer.os.pathsep.join((
            str(Path(environment["SYSTEMROOT"]) / "System32"), environment["SYSTEMROOT"])))
        self.assertNotIn("NODE_OPTIONS", environment)
        if consumer.os.name == "nt":
            self.assertTrue(Path(environment["SYSTEMROOT"]).is_dir())


if __name__ == "__main__":
    unittest.main()

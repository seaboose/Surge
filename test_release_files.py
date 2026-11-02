"""Source packaging excludes both clone and worktree Git metadata."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.release_files import MANIFEST, source_files


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parent
        parent = self.repo / "verification/qualification/release-metadata-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=parent))

    def fixture(self, name, metadata):
        root = self.attempt / name
        (root / "scripts").mkdir(parents=True)
        (root / "desktop").mkdir()
        for script in ("release_files.py", "check_release.py", "package_source.py"):
            shutil.copyfile(self.repo / "scripts" / script, root / "scripts" / script)
        (root / "desktop/package.json").write_text(
            json.dumps(dict(dependencies={}, devDependencies={})), encoding="utf-8"
        )
        (root / "README.md").write_text("Owned publishable fixture café\n", encoding="utf-8")
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")
        (root / ".gitattributes").write_text("*.md text eol=lf\n", encoding="utf-8")
        if metadata == "directory":
            (root / ".git").mkdir()
            (root / ".git/config").write_text("Owned metadata; exclude this.\n", encoding="utf-8")
        else:
            (root / ".git").write_text("gitdir: ../owned-history/worktrees/release\n", encoding="utf-8")
        self.review(root, "README.md", ".gitignore", ".gitattributes", "desktop/package.json",
                    "scripts/release_files.py", "scripts/check_release.py", "scripts/package_source.py")
        return root

    def review(self, root, *names):
        manifest = root / MANIFEST
        existing = manifest.read_text(encoding="utf-8").splitlines() if manifest.exists() else []
        manifest.write_text("\n".join(sorted(set(existing) | set(names) | {MANIFEST})) + "\n",
                            encoding="utf-8")

    def expected_files(self, root):
        names = ["README.md", ".gitignore", ".gitattributes", "desktop/package.json",
                 "scripts/release_files.py", "scripts/check_release.py", "scripts/package_source.py", MANIFEST]
        return {name: (root / name).read_bytes() for name in names}

    def test_inventory_excludes_worktree_pointer_and_keeps_publishable_files(self):
        root = self.fixture("worktree", "file")
        files = {p.relative_to(root).as_posix(): p.read_bytes() for p in source_files(root)}
        self.assertNotIn(".git", files)
        self.assertEqual(files, self.expected_files(root))

    def test_equivalent_root_spelling_preserves_inventory_and_consumer_hashes(self):
        from scripts import check_first_use, check_launcher, check_release_compatibility

        root = self.fixture("equivalent-root", "directory")
        alias = root / "desktop" / ".."
        self.assertEqual(alias.resolve(), root.resolve())
        self.assertNotEqual(alias, root.resolve())
        actual = {p.relative_to(alias).as_posix(): p.read_bytes() for p in source_files(alias)}
        self.assertEqual(actual, self.expected_files(root))
        for consumer in (check_first_use.manifest_for, check_launcher.identity,
                         check_release_compatibility.source_manifest):
            with self.subTest(consumer=consumer.__module__):
                self.assertEqual(consumer(alias), consumer(root))

    def test_survive_sessions_trials_and_downloaded_media_are_private(self):
        root = self.fixture("survive-private", "directory")
        lab = root / "unreal/SurgeMovementLab"
        private = ["Saved/Telemetry/player.jsonl", "Saved/SurgeRecordings/session/raw.jsonl",
                   "Saved/Investigations/person/0001.json",
                   "Saved/StudyTrials/person/manifest.json", "Saved/StudyActions/trial.jsonl",
                   "telemetry/local/run/source.jsonl", "profiles/evidence/reference.mp4",
                   "Binaries/Win64/module.dll", "Intermediate/build.obj", "checkpoints/private.json"]
        for name in private:
            target = lab / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Private test evidence", encoding="utf-8")
        public = lab / "Source/Game.cpp"
        public.parent.mkdir(parents=True, exist_ok=True)
        public.write_text("// Original source", encoding="utf-8")
        self.review(root, public.relative_to(root).as_posix())
        names = {p.relative_to(root).as_posix() for p in source_files(root)}
        self.assertIn("unreal/SurgeMovementLab/Source/Game.cpp", names)
        self.assertTrue(all("unreal/SurgeMovementLab/" + name not in names for name in private))

    def test_developer_kit_excludes_recovery_and_local_verification(self):
        root = self.fixture("developer-kit", "directory")
        private = ["_Recovery/reconnection.json", "RECOVERY-STATUS.txt",
                   "LOCAL-NOTES.md", ".editor/settings.toml", ".workspace/settings.md", ".cloud/credentials",
                   "output/surge-logos/prompts.txt", "output/surge-logos/draft.png",
                   "verification/local_probe.py", "verification/user-profile/recording.jsonl",
                   "unreal/SurgeMovementLab/docs/calibration/inspect-ability-video.cjs"]
        public = ["test_survive_runtime.py", "scripts/check_survive_package.py",
                  "unreal/SurgeMovementLab/docs/calibration/movement-review.md"]
        for name in private + public:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Owned fixture", encoding="utf-8")
        self.review(root, *public)
        names = {p.relative_to(root).as_posix() for p in source_files(root)}
        self.assertTrue(set(public).issubset(names))
        self.assertTrue(set(private).isdisjoint(names))

    def test_hidden_tool_directories_are_private_and_root_ci_is_publishable(self):
        root = self.fixture("hidden-tool-settings", "directory")
        private = [".editor/settings.json", "desktop/.tool/session.json",
                   "desktop/.github/local.json"]
        public = root / ".github/workflows/ci.yml"
        public.parent.mkdir(parents=True)
        public.write_text("name: Source check\n", encoding="utf-8")
        self.review(root, public.relative_to(root).as_posix())
        for name in private:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Private configuration", encoding="utf-8")
        names = {p.relative_to(root).as_posix() for p in source_files(root)}
        self.assertIn(".github/workflows/ci.yml", names)
        self.assertTrue(set(private).isdisjoint(names))

    def test_real_package_preserves_public_bytes_for_clone_and_worktree(self):
        packages = []
        for name, metadata in (("clone", "directory"), ("worktree", "file")):
            with self.subTest(metadata=metadata):
                root = self.fixture(name, metadata)
                env = os.environ.copy()
                for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONOPTIMIZE"):
                    env.pop(key, None)
                env.update(PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
                env["PATH"] = ""  # An exported package must not require Git or other tools.
                result = subprocess.run(
                    [sys.executable, "-B", "scripts/package_source.py"], cwd=root,
                    env=env, capture_output=True, timeout=20,
                )
                (root / "package-stdout.log").write_bytes(result.stdout)
                (root / "package-stderr.log").write_bytes(result.stderr)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
                with zipfile.ZipFile(root / "dist/surge-source.zip") as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
                    self.assertFalse(any(name == "Surge/.git" or name.startswith("Surge/.git/") for name in archive.namelist()))
                    actual = {name.removeprefix("Surge/"): archive.read(name) for name in archive.namelist()}
                self.assertEqual(actual, self.expected_files(root))
                manifest = json.loads((root / "dist/source-manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(set(manifest), set(actual))
                packages.append(actual)
        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0], packages[1])

    def test_manifest_rejects_missing_duplicate_and_unsafe_entries(self):
        root = self.fixture("invalid-manifest", "directory")
        manifest = root / MANIFEST
        valid = manifest.read_text(encoding="utf-8")
        for entry in ("missing.py", "../outside.py", "/outside.py", "C:/outside.py",
                      "scripts/../README.md", "scripts//release_files.py", "scripts\\release_files.py",
                      "README.md", "readme.md"):
            with self.subTest(entry=entry):
                manifest.write_text(valid + entry + "\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    list(source_files(root))
        manifest.write_text("README.md\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "include itself"):
            list(source_files(root))
        manifest.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            list(source_files(root))

    def test_unlisted_source_stays_private_until_explicitly_reviewed(self):
        root = self.fixture("unreviewed-source", "directory")
        extra = root / "local_probe.py"
        extra.write_text("print('private')\n", encoding="utf-8")
        self.assertNotIn(extra, list(source_files(root)))
        self.review(root, "local_probe.py")
        self.assertIn(extra, list(source_files(root)))

    def test_reviewed_symlink_is_rejected_even_when_target_is_inside_root(self):
        root = self.fixture("linked-source", "directory")
        link = root / "linked.md"
        try:
            link.symlink_to(root / "README.md")
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        self.review(root, "linked.md")
        with self.assertRaisesRegex(ValueError, "links"):
            list(source_files(root))


if __name__ == "__main__":
    unittest.main()

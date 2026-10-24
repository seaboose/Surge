"""Small owned archive and backend-closure checks for Windows packaging."""
import ast
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time
import unittest
import uuid
import zipfile

from scripts.build_windows_package import BACKEND, ROOT, dependency, extract_checked, package_filename


@contextmanager
def owned_fixture(prefix):
    # Preserve small owned controls, including failed attempts, under the workspace.
    path = ROOT / "verification/qualification/windows-package-controls" / (prefix + uuid.uuid4().hex[:12])
    path.mkdir(parents=True, exist_ok=False)
    yield path


class WindowsPackageTests(unittest.TestCase):
    def test_copied_package_name_identifies_clean_or_development_source(self):
        commit = "ca6e3bb7290a50de737a07859aff0bc4ed32cbec"
        self.assertEqual(package_filename("0.4.0", commit, False), "Surge-0.4.0-ca6e3bb-windows-x64.zip")
        self.assertEqual(package_filename("0.4.0", commit, True), "Surge-0.4.0-ca6e3bb-dirty-windows-x64.zip")

    def test_real_extraction_preserves_bytes_and_rejects_unsafe_names(self):
        with owned_fixture("archive-") as temporary:
            root = Path(temporary)
            good = root / "valid.zip"
            expected = {"nested/owned.txt": b"exact owned bytes\x00\xff", "caf\u00e9.txt": "Tokyo \u6771\u4eac".encode()}
            with zipfile.ZipFile(good, "w") as archive:
                for name, raw in expected.items():
                    archive.writestr(name, raw)
            extract_checked(good, root / "valid", time.monotonic() + 5)
            self.assertEqual({p.relative_to(root / "valid").as_posix(): p.read_bytes()
                              for p in (root / "valid").rglob("*") if p.is_file()}, expected)
            for index, names in enumerate((["../outside.txt"], ["/absolute.txt"], ["drive:stream"], ["same.txt", "SAME.txt"])):
                with self.subTest(names=names):
                    bad = root / f"bad-{index}.zip"
                    with zipfile.ZipFile(bad, "w") as archive:
                        for name in names:
                            archive.writestr(name, b"owned")
                    with self.assertRaises(ValueError):
                        extract_checked(bad, root / f"bad-{index}", time.monotonic() + 5)
            self.assertFalse((root / "outside.txt").exists())

    def test_cached_dependency_is_verified_without_replacing_bad_bytes(self):
        with owned_fixture("cache-") as temporary:
            root = Path(temporary)
            target = root / "owned.zip"
            target.write_bytes(b"owned archive")
            lock = dict(filename=target.name, url="https://invalid.example/unused", sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            actual, result = dependency(lock, root, time.monotonic() + 5)
            self.assertEqual(actual, target)
            self.assertTrue(result["cache_used"])
            target.write_bytes(b"changed owned bytes")
            with self.assertRaisesRegex(ValueError, "runtime_cache_hash_mismatch"):
                dependency(lock, root, time.monotonic() + 5)
            self.assertEqual(target.read_bytes(), b"changed owned bytes")

    def test_backend_allowlist_contains_actual_import_closure(self):
        found, todo = set(), ["desktop_worker"]
        while todo:
            name = todo.pop()
            if name in found:
                continue
            found.add(name)
            tree = ast.parse((ROOT / (name + ".py")).read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                imported = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
                todo.extend(module.split(".")[0] for module in imported if (ROOT / (module.split(".")[0] + ".py")).is_file())
        self.assertEqual(found, set(BACKEND))


if __name__ == "__main__":
    unittest.main()

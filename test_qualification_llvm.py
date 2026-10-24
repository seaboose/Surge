"""Fail-closed contracts for the embedded portable LLVM bootstrap."""

import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock


def load_helper():
    script = Path(__file__).parent / "scripts/setup_qualification_llvm.ps1"
    source = script.read_text(encoding="utf-8").split("$helperSource = @'\n", 1)[1].split("\n'@", 1)[0]
    namespace = {"__name__": "bootstrap_contract_test"}
    exec(compile(source, str(script), "exec"), namespace)
    return namespace


class QualificationLLVMTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_helper()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def archive(self, members):
        path = self.root / "fixture.tar.xz"
        with tarfile.open(path, mode="w:xz") as archive:
            for name, content, link in members:
                member = tarfile.TarInfo(name)
                if link:
                    member.type = tarfile.SYMTYPE
                    member.linkname = link
                    archive.addfile(member)
                else:
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
        return path

    def test_source_or_existing_destination_refused_without_network(self):
        validate = self.helper["refuse_source_destination"]
        with self.assertRaisesRegex(RuntimeError, "outside"):
            validate(self.root / "tools", self.root)
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            validate(self.root, self.root / "source")

    def test_hash_mismatch_preserves_download(self):
        response = io.BytesIO(b"changed")
        response.headers = {"Content-Length": "7"}
        path = self.root / "download"
        with mock.patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                self.helper["download"]("https://example.invalid/fixture", path, 7, "0" * 64)
        self.assertEqual(path.read_bytes(), b"changed")

    def test_overlong_download_refused_even_without_length_header(self):
        response = io.BytesIO(b"overlong")
        response.headers = {}
        with mock.patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "byte bound"):
                self.helper["download"]("https://example.invalid/fixture", self.root / "download", 2, "0" * 64)

    def test_verified_download_returns_actual_identity(self):
        response = io.BytesIO(b"fixture")
        response.headers = {"Content-Length": "7"}
        digest = hashlib.sha256(b"fixture").hexdigest()
        with mock.patch("urllib.request.urlopen", return_value=response):
            result = self.helper["download"]("https://example.invalid/fixture", self.root / "download", 7, digest)
        self.assertEqual(result["sha256"], digest)
        self.assertEqual(result["bytes"], 7)

    def test_download_time_bound_preserves_failed_attempt(self):
        response = io.BytesIO(b"fixture")
        response.headers = {"Content-Length": "7"}
        path = self.root / "download"
        with mock.patch("urllib.request.urlopen", return_value=response):
            with mock.patch("time.monotonic", side_effect=[0, 301]):
                with self.assertRaisesRegex(RuntimeError, "300-second"):
                    self.helper["download"]("https://example.invalid/fixture", path, 7, "0" * 64)
        self.assertTrue(path.is_file())

    def test_extracts_only_requested_toolchain_files(self):
        package = self.helper["PACKAGE"]
        archive = self.archive([(package + "/bin/clang-cl.exe", b"tool", None),
                                (package + "/unneeded.txt", b"omit", None),
                                (package + "/lib/clang/23/include/stddef.h", b"header", None)])
        result = self.helper["extract_selected"](archive, self.root / "extracted")
        self.assertEqual(result["files"], 2)
        self.assertEqual(result["extracted_bytes"], 10)
        self.assertFalse((self.root / "extracted" / package / "unneeded.txt").exists())

    def test_traversal_refused(self):
        package = self.helper["PACKAGE"]
        archive = self.archive([(package + "/../escape", b"unsafe", None)])
        with self.assertRaisesRegex(RuntimeError, "unsafe path"):
            self.helper["extract_selected"](archive, self.root / "extracted")

    def test_selected_link_refused(self):
        package = self.helper["PACKAGE"]
        archive = self.archive([(package + "/bin/clang-cl.exe", b"", "../../escape")])
        with self.assertRaisesRegex(RuntimeError, "regular file"):
            self.helper["extract_selected"](archive, self.root / "extracted")

    def test_extraction_budget_enforced(self):
        package = self.helper["PACKAGE"]
        archive = self.archive([(package + "/bin/clang-cl.exe", b"12345", None)])
        self.helper["MAX_EXTRACTED_BYTES"] = 4
        with self.assertRaisesRegex(RuntimeError, "Extracted-byte"):
            self.helper["extract_selected"](archive, self.root / "extracted")

    def test_extraction_time_bound_refuses_before_writing(self):
        package = self.helper["PACKAGE"]
        archive = self.archive([(package + "/bin/clang-cl.exe", b"tool", None)])
        with mock.patch("time.monotonic", side_effect=[0, 241]):
            with self.assertRaisesRegex(RuntimeError, "240-second"):
                self.helper["extract_selected"](archive, self.root / "extracted")
        self.assertFalse((self.root / "extracted").exists())

    def test_tool_hash_mismatch_prevents_execution(self):
        tool = self.root / "bin/clang-cl.exe"
        tool.parent.mkdir()
        tool.write_bytes(b"different")
        with self.assertRaisesRegex(RuntimeError, "differs from prior"):
            self.helper["verify_tools"](self.root)


if __name__ == "__main__":
    unittest.main()

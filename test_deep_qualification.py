"""Portable deep evidence must fail closed on missing, altered or partial checks."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch

from scripts import check_deep_qualification as deep
from scripts import qualify


class DeepQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "artifacts"
        self.root.mkdir()

    def partial_bundle(self):
        raw = b"# A small source identity fixture.\n"
        digest = hashlib.sha256(raw).hexdigest()
        normalized = hashlib.sha256(json.dumps([("fixture.py", digest)], separators=(",", ":")).encode()).hexdigest()
        source = dict(files=[dict(path="fixture.py", sha256=digest, normalized_sha256=digest)],
                      normalized_tree_sha256=normalized)
        git = dict(head="a" * 40, clean=True)
        deep.write_json(self.root / "source-manifest.json", {"fixture.py": dict(bytes=len(raw), sha256=digest)})
        with zipfile.ZipFile(self.root / "source.zip", "w") as archive:
            archive.writestr("fixture.py", raw)
        checks = []
        folder = self.root / "qualification"
        folder.mkdir()
        for index, (name, timeout) in enumerate(deep.STEPS):
            row = dict(id=name, timeout_seconds=timeout, status="not_run", log=name + ".log")
            if index < 3:
                log = folder / row["log"]
                log.write_text("Owned fixture check\n", encoding="utf-8")
                row.update(status="passed" if index < 2 else "failed", exit_code=0 if index < 2 else 73,
                           cleanup="not_needed", log_bytes=log.stat().st_size, log_sha256=deep.sha(log))
            checks.append(row)
        qualification = dict(schema="surge-qualification-v1", qualification_status="failed", checks=checks,
                             asan_requested=True, properties_requested=True, libfuzzer_requested=True,
                             retention_requested=True, total_limit_seconds=1800,
                             fuzzing=dict(status="incomplete", executed=False,
                                          targets={k: "not_run" for k in ("T1", "T2", "T3")}),
                             source_before=source, source_after=copy.deepcopy(source), source_unchanged=True,
                             git_before=git, git_after=copy.deepcopy(git),
                             existing_artifacts_before={name: False for name in deep.FRESH_PATHS},
                             sanitizer=dict(status="incomplete"))
        report = dict(schema="surge-deep-qualification-v1", status="failed", human_acceptance="pending",
                      broader_fuzzing="incomplete_not_run", source_before=source, source_after=copy.deepcopy(source),
                      source_unchanged=True, git_before=git, git_after=copy.deepcopy(git), profile_exit_code=1,
                      existing_artifacts_before={name: False for name in deep.FRESH_PATHS})
        deep.write_json(folder / "report.json", qualification)
        deep.write_json(self.root / "report.json", report)
        deep.seal_bundle(self.root)
        return report, qualification

    def save(self, report=None, qualification=None):
        if report is not None:
            deep.write_json(self.root / "report.json", report)
        if qualification is not None:
            deep.write_json(self.root / "qualification/report.json", qualification)
        deep.seal_bundle(self.root)

    def test_plan_retains_all_original_checks_and_limits(self):
        actual = qualify.plan(True, True, True, "owned-toolchain", True)
        self.assertEqual([(r["id"], r["timeout_seconds"]) for r in actual], deep.STEPS)
        self.assertEqual(len(deep.STEPS), 21)
        self.assertEqual(qualify.TOTAL_SECONDS, 1800)

    def test_preserved_partial_failure_verifies_but_cannot_qualify(self):
        self.partial_bundle()
        result = deep.verify_bundle(self.root, allow_failed=True)
        self.assertEqual(result["status"], "verified_failed")
        self.assertEqual(list(result["checks"].values()), ["passed", "passed", "failed"] + ["not_run"] * 18)
        with self.assertRaisesRegex(ValueError, "qualification_not_passed"):
            deep.verify_bundle(self.root)

    def test_manifest_rejects_tamper_missing_and_extra_files(self):
        self.partial_bundle()
        path = self.root / "qualification/setup.log"
        raw = path.read_bytes()
        path.write_bytes(raw + b"tampered")
        with self.assertRaisesRegex(ValueError, "artifact_hash_or_length"):
            deep.verify_bundle(self.root, True)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "artifact_file_set"):
            deep.verify_bundle(self.root, True)
        path.write_bytes(raw)
        (self.root / "unexpected.txt").write_text("extra")
        with self.assertRaisesRegex(ValueError, "artifact_file_set"):
            deep.verify_bundle(self.root, True)

    def test_resealed_outer_manifest_does_not_hide_changed_check_log(self):
        self.partial_bundle()
        (self.root / "qualification/setup.log").write_text("different bytes")
        deep.seal_bundle(self.root)
        with self.assertRaisesRegex(ValueError, "check_log_hash_or_length"):
            deep.verify_bundle(self.root, True)

    def test_profile_flags_counts_and_budgets_are_required(self):
        _, original = self.partial_bundle()
        for kind in ("flag", "missing", "duplicate", "total", "timeout"):
            data = copy.deepcopy(original)
            if kind == "flag":
                data["libfuzzer_requested"] = False
            elif kind == "missing":
                data["checks"].pop()
            elif kind == "duplicate":
                data["checks"][-1] = data["checks"][-2]
            elif kind == "total":
                data["total_limit_seconds"] += 1
            else:
                data["checks"][0]["timeout_seconds"] += 1
            self.save(qualification=data)
            with self.assertRaises(ValueError, msg=kind):
                deep.verify_bundle(self.root, True)

    def test_partial_failure_cannot_be_relabelled_passed(self):
        report, qualification = self.partial_bundle()
        report.update(status="passed", profile_exit_code=0)
        qualification["qualification_status"] = "passed"
        self.save(report, qualification)
        with self.assertRaisesRegex(ValueError, "qualification_not_passed"):
            deep.verify_bundle(self.root, True)

    def test_claims_and_clean_source_are_mandatory(self):
        original, _ = self.partial_bundle()
        for kind in ("human", "fuzz", "dirty", "fresh", "source"):
            report = copy.deepcopy(original)
            if kind == "human":
                report["human_acceptance"] = "passed"
            elif kind == "fuzz":
                report["broader_fuzzing"] = "complete"
            elif kind == "dirty":
                report["git_after"]["clean"] = False
            elif kind == "fresh":
                report["existing_artifacts_before"][".venv"] = True
            else:
                report["source_after"]["normalized_tree_sha256"] = "b" * 64
            self.save(report)
            with self.assertRaises(ValueError, msg=kind):
                deep.verify_bundle(self.root, True)

    def test_source_archive_rejects_unexpected_entry_even_with_resealed_manifest(self):
        self.partial_bundle()
        with zipfile.ZipFile(self.root / "source.zip", "a") as archive:
            archive.writestr("untracked.py", b"unexpected")
        deep.seal_bundle(self.root)
        with self.assertRaisesRegex(ValueError, "source_archive_file_set"):
            deep.verify_bundle(self.root, True)

    def test_artifact_paths_cannot_escape_or_use_windows_drive(self):
        for name in ("../outside", "/absolute", "C:/outside", "nested\\outside", "nested/../outside", ""):
            with self.assertRaises(ValueError, msg=name):
                deep.relative_file(self.root, name)

    def test_missing_requested_toolchain_evidence_cannot_verify(self):
        report, _ = self.partial_bundle()
        report["toolchain_evidence_requested"] = True
        self.save(report)
        with self.assertRaisesRegex(ValueError, "missing_or_ambiguous_passed_toolchain"):
            deep.verify_bundle(self.root, True)

    def test_preflight_failure_preserves_cause_and_never_starts_profile(self):
        profile = Mock()
        checkout = Path(self.temporary.name) / "checkout"
        identity = dict(files=[], normalized_tree_sha256="a" * 64)
        with patch.object(deep, "ROOT", checkout), \
                patch.object(deep, "package_source", return_value={}), \
                patch.object(qualify, "git_identity", return_value=dict(head="a" * 40, clean=False)), \
                patch.object(qualify, "source_identity", return_value=identity):
            folder, report = deep.execute("owned-toolchain", profile_runner=profile)
        profile.assert_not_called()
        self.assertEqual(report["status"], "failed")
        self.assertIn("clean_committed_checkout_required", report["error"])
        self.assertIn("verification_error", report)
        self.assertTrue((folder / "artifacts/verification.json").is_file())

    def test_empty_or_skipped_python_suite_cannot_be_relabelled_passed(self):
        _, original = self.partial_bundle()
        for log in ("", "Ran 0 tests\nOK", "Ran 10 tests\nOK (skipped=1)\n"):
            data = copy.deepcopy(original)
            data["checks"][2].update(status="passed", exit_code=0)
            row = data["checks"][3]
            path = self.root / "qualification" / row["log"]
            path.write_text(log, encoding="utf-8")
            row.update(status="passed", exit_code=0, cleanup="not_needed",
                       log_sha256=deep.sha(path), log_bytes=path.stat().st_size)
            self.save(qualification=data)
            with self.assertRaisesRegex(ValueError, "qualification_log_revalidation:python_suite"):
                deep.verify_bundle(self.root, True)


if __name__ == "__main__":
    unittest.main()

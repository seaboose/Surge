"""Claims and fingerprint controls for the read-only package report generator."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import report_windows_package as report


class PackageReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="surge-report-owned-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "owned.zip"
        with zipfile.ZipFile(self.package, "w") as archive:
            archive.writestr("owned.txt", b"owned fixture")
        self.manifest = {
            "schema": "surge-windows-package-v1",
            "archive": report.fingerprint(self.package),
            "source": {"commit": "a" * 40, "dirty": False},
            "files": [{"path": "owned.txt", "bytes": 13,
                       "sha256": hashlib.sha256(b"owned fixture").hexdigest()}],
        }
        self.build = {"schema": "surge-windows-package-build-v1", "status": "passed",
                      "elapsed_seconds": 1, "log_bytes": 0,
                      "steps": [{"id": name, "status": "passed"} for name in report.BUILD_STEPS]}
        self.consumer = {
            "schema": "surge-windows-package-consumer-v1", "status": "passed",
            "archive": self.manifest["archive"], "source": self.manifest["source"],
            "criteria": {f"W{i}": "passed" for i in range(2, 7)},
            "environment": {"token_elevated": False},
            "steps": [{"name": "owned aggregation fixture", "status": "passed"}],
            "human_acceptance": "pending",
        }
        # These tests isolate report aggregation. The consumer verifier has its
        # own retained-evidence controls and is exercised against actual runs.
        patcher = mock.patch.object(report, "verify_consumer_evidence", return_value={"status": "passed"})
        self.verifier = patcher.start()
        self.addCleanup(patcher.stop)
        for mode in ("journey", "replacement", "mismatch"):
            (self.root / mode).mkdir()
            (self.root / mode / "actual-processes.json").write_text(
                json.dumps({"main": {"token_elevated": False}, "worker": {"token_elevated": False}}), encoding="utf-8")
        self.write()

    def write(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        self.build.update(archive=self.manifest["archive"], source=self.manifest["source"],
                          manifest_sha256=report.fingerprint(self.root / "manifest.json")["sha256"])
        (self.root / "build.json").write_text(json.dumps(self.build), encoding="utf-8")
        self.consumer["manifest_sha256"] = report.fingerprint(self.root / "manifest.json")["sha256"]
        (self.root / "consumer.json").write_text(json.dumps(self.consumer), encoding="utf-8")

    def generate(self, **kwargs):
        return report.generate(self.package, self.root / "manifest.json", self.root / "build.json",
                               self.root / "consumer.json", **kwargs)

    def test_automated_evidence_cannot_complete_human_or_missing_hosted_gate(self):
        value = self.generate(local=self.root / "consumer.json")
        self.assertEqual(value["status"], "partial")
        self.assertEqual(value["criteria"]["W7"], "pending_hosted_verification_or_failure_probe")
        self.assertEqual(value["human_acceptance"], "pending")
        self.assertEqual(value["original_campaign"], "unfinished")
        self.assertEqual(value["criteria"]["W2"], "passed")

    def test_missing_non_elevated_local_execution_stays_partial(self):
        value = self.generate()
        self.assertEqual(value["criteria"]["W2"], "partial_local_non_elevated_check_pending")

    def test_partial_report_is_preserved_but_command_does_not_pass(self):
        output = self.root / "partial-report"
        arguments = ["report", "--package", str(self.package), "--manifest", str(self.root / "manifest.json"),
                     "--build-report", str(self.root / "build.json"), "--consumer-report", str(self.root / "consumer.json"),
                     "--output", str(output)]
        with mock.patch("sys.argv", arguments):
            self.assertEqual(report.main(), 1)
        self.assertEqual(report.read(output / "report.json")["status"], "partial")
        self.assertTrue((output / "report.md").is_file())

    def test_non_elevated_supervisor_cannot_mask_elevated_application(self):
        for role in ("main", "worker"):
            with self.subTest(role=role):
                observed = {"main": {"token_elevated": False}, "worker": {"token_elevated": False}}
                observed[role]["token_elevated"] = True
                (self.root / "journey/actual-processes.json").write_text(json.dumps(observed), encoding="utf-8")
                value = self.generate(local=self.root / "consumer.json")
                self.assertEqual(value["criteria"]["W2"], "partial_local_non_elevated_check_pending")

    def test_incomplete_consumer_evidence_cannot_be_masked_by_summary(self):
        self.verifier.side_effect = ValueError("Consumer steps did not all pass")
        with self.assertRaisesRegex(ValueError, "steps did not all pass"):
            self.generate()

    def test_missing_build_step_cannot_pass(self):
        self.build["steps"].pop()
        self.write()
        with self.assertRaisesRegex(ValueError, "build steps"):
            self.generate()

    def test_failed_missing_or_mismatched_consumer_rejected(self):
        original = copy.deepcopy(self.consumer)
        for change in (lambda c: c.update(status="failed"),
                       lambda c: c["criteria"].pop("W6"),
                       lambda c: c.update(archive={"sha256": "0" * 64})):
            with self.subTest(change=change):
                self.consumer = copy.deepcopy(original)
                change(self.consumer)
                self.write()
                with self.assertRaises(ValueError):
                    self.generate()

    def test_dirty_final_source_rejected(self):
        self.manifest["source"]["dirty"] = True
        self.write()
        with self.assertRaisesRegex(ValueError, "dirty"):
            self.generate()

    def test_a_passing_build_from_another_package_is_rejected(self):
        for key, value in (("archive", {"sha256": "b" * 64}),
                           ("source", {"commit": "b" * 40, "dirty": False}),
                           ("manifest_sha256", "b" * 64)):
            with self.subTest(key=key):
                self.write()
                other = report.read(self.root / "build.json")
                other[key] = value
                (self.root / "build.json").write_text(json.dumps(other), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "different package evidence"):
                    self.generate()

    def test_zip_inventory_and_payload_hashes_are_verified(self):
        bad = copy.deepcopy(self.manifest)
        bad["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Payload fingerprint"):
            report.verify_package(self.package, bad)
        with zipfile.ZipFile(self.package, "a") as archive:
            archive.writestr("extra.txt", b"extra")
        self.manifest["archive"] = report.fingerprint(self.package)
        with self.assertRaisesRegex(ValueError, "inventory"):
            report.verify_package(self.package, self.manifest)

    def test_failed_or_skipped_required_job_cannot_pass_hosted_gate(self):
        run = {"id": 1, "head_sha": "a" * 40, "status": "completed", "conclusion": "success",
               "html_url": "https://example.invalid/owned-fixture"}
        jobs = [{"name": name, "conclusion": "success"} for name in report.JOBS]
        (self.root / "run.json").write_text(json.dumps(run), encoding="utf-8")
        (self.root / "artifacts.json").write_text("[]", encoding="utf-8")
        for outcome in ("failure", "skipped", "cancelled", None):
            with self.subTest(outcome=outcome):
                jobs[0]["conclusion"] = outcome
                (self.root / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "did not succeed"):
                    report.verify_hosted(self.root, "a" * 40)

    def test_green_same_commit_run_cannot_substitute_an_unhosted_report(self):
        run = {"id": 1, "head_sha": "a" * 40, "status": "completed", "conclusion": "success",
               "html_url": "https://example.invalid/owned-fixture"}
        jobs = [{"name": name, "conclusion": "success"} for name in report.JOBS]
        artifacts = []
        for number, prefix in enumerate(("windows-package-", "windows-package-acceptance-",
                                         "deeper-qualification-", "first-use-"), 1):
            target = self.root / f"artifact-{number}.zip"
            with zipfile.ZipFile(target, "w") as archive:
                archive.writestr("report.json", b"actual hosted report")
            identity = report.fingerprint(target)
            artifacts.append({"id": number, "name": prefix + "owned", "expired": False,
                              "size_in_bytes": identity["bytes"], "digest": "sha256:" + identity["sha256"]})
        for name, data in (("run", run), ("jobs", jobs), ("artifacts", artifacts)):
            (self.root / (name + ".json")).write_text(json.dumps(data), encoding="utf-8")
        binding = {"role": "build", "name": "report.json", "bytes": 20,
                   "sha256": hashlib.sha256(b"different local data").hexdigest()}
        with self.assertRaisesRegex(ValueError, "not a unique hosted artifact member"):
            report.verify_hosted(self.root, "a" * 40, {"windows-package-": [binding]})


if __name__ == "__main__":
    unittest.main()

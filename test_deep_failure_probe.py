"""Keep the owned deep failure probe narrow, honest, and nonzero on success."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import probe_deep_qualification_failure as probe


class DeepFailureProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.artifacts = self.folder / "artifacts"
        self.qualification = self.artifacts / "qualification"
        self.qualification.mkdir(parents=True)
        (self.artifacts / "report.json").write_text(json.dumps(dict(status="failed", profile_exit_code=1)),
                                                   encoding="utf-8")
        self.report = dict(
            schema="surge-qualification-v1", qualification_status="failed",
            source_unchanged=True, asan_requested=True, properties_requested=True,
            libfuzzer_requested=True, retention_requested=True,
            fuzzing=dict(status="incomplete", executed=False,
                         targets={key: "not_run" for key in ("T1", "T2", "T3")}),
            sanitizer=dict(status="incomplete"),
            checks=[dict(id=name, status="passed" if i < 2 else "failed" if i == 2 else "not_run",
                         command=[probe.MARKER] if i == 2 else [name])
                    for i, name in enumerate(probe.EXPECTED_CHECK_IDS)],
        )
        for i, check in enumerate(self.report["checks"][:3]):
            log = self.qualification / (check["id"] + ".log")
            log.write_text(probe.MARKER if i == 2 else "completed", encoding="utf-8")
            check.update(exit_code=73 if i == 2 else 0,
                         log_bytes=log.stat().st_size, log_sha256=probe.sha(log))
        # The normal wrapper owns archive, profile, source, and bundle checks. These
        # tests isolate the additional strict controlled-failure contract.
        self.bundle_patch = patch.object(probe.runner, "verify_bundle",
                                        return_value=dict(status="verified_failed", git=dict(head="a" * 40, clean=True)))
        self.bundle = self.bundle_patch.start()
        self.addCleanup(self.bundle_patch.stop)

    def save(self):
        (self.qualification / "report.json").write_text(json.dumps(self.report), encoding="utf-8")

    def verify(self):
        self.save()
        return probe.verify_artifacts(self.artifacts)

    def test_expected_failure_is_verified_read_only_after_normal_bundle_verification(self):
        self.save()
        before = {p.relative_to(self.artifacts): p.read_bytes() for p in self.artifacts.rglob("*") if p.is_file()}
        result = probe.verify_artifacts(self.artifacts)
        self.bundle.assert_called_once_with(self.artifacts, allow_failed=True)
        self.assertEqual(result["status"], "verified_expected_failure")
        self.assertEqual(result["human_acceptance"], "pending")
        self.assertEqual(len(result["skipped_checks"]), 18)
        self.assertEqual({p.relative_to(self.artifacts): p.read_bytes() for p in self.artifacts.rglob("*") if p.is_file()}, before)

    def test_bundle_failure_or_pass_cannot_be_recast_as_expected_failure(self):
        self.bundle.return_value = dict(status="verified_passed")
        with self.assertRaisesRegex(ValueError, "bundle_did_not_verify_as_failed"):
            self.verify()
        self.bundle.side_effect = ValueError("artifact_fingerprint_mismatch")
        with self.assertRaisesRegex(ValueError, "artifact_fingerprint_mismatch"):
            self.verify()

    def test_inflated_or_incomplete_claims_are_rejected(self):
        original = copy.deepcopy(self.report)
        for key, value in (("qualification_status", "passed"), ("error", "unrelated_failure"),
                           ("source_unchanged", False), ("asan_requested", False),
                           ("properties_requested", False), ("libfuzzer_requested", False),
                           ("retention_requested", False), ("fuzzing", {"status": "passed"}),
                           ("sanitizer", {"status": "passed"})):
            with self.subTest(key=key):
                self.report = copy.deepcopy(original)
                self.report[key] = value
                with self.assertRaises(ValueError):
                    self.verify()

    def test_unrelated_failures_and_wrong_plans_are_rejected(self):
        self.report["checks"][2]["exit_code"] = 1
        with self.assertRaisesRegex(ValueError, "unexpected_failure_exit_or_reason"):
            self.verify()
        self.report["checks"][2]["exit_code"] = 73
        self.report["checks"][2]["reason"] = "log_limit_exceeded"
        with self.assertRaisesRegex(ValueError, "unexpected_failure_exit_or_reason"):
            self.verify()
        self.report["checks"][2].pop("reason")
        self.report["checks"][3]["id"] = "unreviewed_step"
        with self.assertRaisesRegex(ValueError, "unexpected_qualification_plan"):
            self.verify()

    def test_marker_must_be_both_observed_and_recorded(self):
        self.report["checks"][2]["command"] = ["cmake"]
        with self.assertRaisesRegex(ValueError, "injected_command_not_recorded"):
            self.verify()
        self.report["checks"][2]["command"] = [probe.MARKER]
        (self.qualification / "native_build.log").write_text("unrelated failure")
        with self.assertRaisesRegex(ValueError, "missing_owned_failure_marker"):
            self.verify()

    def test_logs_and_later_execution_claims_cannot_be_altered(self):
        for check in self.report["checks"][:3]:
            with self.subTest(log=check["id"]):
                log = self.qualification / (check["id"] + ".log")
                content = log.read_bytes()
                log.write_bytes(content + b"!")
                with self.assertRaisesRegex(ValueError, "log_length_mismatch"):
                    self.verify()
                check["log_bytes"] += 1
                with self.assertRaisesRegex(ValueError, "log_fingerprint_mismatch"):
                    self.verify()
                log.write_bytes(content)
                check["log_bytes"] -= 1
        self.report["checks"][3]["exit_code"] = 0
        with self.assertRaisesRegex(ValueError, "unexpected_later_execution_claim"):
            self.verify()
        self.report["checks"][3].pop("exit_code")
        (self.qualification / "python_suite.log").write_text("unexpected execution")
        with self.assertRaisesRegex(ValueError, "unexpected_later_check_log"):
            self.verify()

    def test_failed_or_later_steps_cannot_be_claimed_passed(self):
        self.report["checks"][3]["status"] = "passed"
        with self.assertRaisesRegex(ValueError, "incorrect_partial_check_statuses"):
            self.verify()

    def test_injection_changes_only_one_command_and_restores_original_plan(self):
        original_plan = probe.runner.qualify.plan
        original = original_plan(True, True, True, "owned-llvm", True)
        def inspect(llvm_bin):
            self.assertEqual(llvm_bin, "owned-llvm")
            changed = probe.runner.qualify.plan(True, True, True, llvm_bin, True)
            self.assertEqual([s for i, s in enumerate(changed) if i != 2],
                             [s for i, s in enumerate(original) if i != 2])
            self.assertEqual({k: v for k, v in changed[2].items() if k != "argv"},
                             {k: v for k, v in original[2].items() if k != "argv"})
            self.assertIn(probe.MARKER, changed[2]["argv"][-1])
            return 1
        with patch.object(probe.runner, "run_profile", side_effect=inspect):
            self.assertEqual(probe.owned_failure_profile("owned-llvm"), 1)
        self.assertIs(probe.runner.qualify.plan, original_plan)

    def test_successful_probe_keeps_nonzero_process_status_and_failed_report(self):
        self.save()
        with patch.object(probe.runner, "execute", return_value=(self.folder, {"status": "failed"})) as execute, \
             patch.object(probe.runner, "seal_bundle") as seal:
            self.assertEqual(probe.main(["--llvm-bin", "owned-llvm", "--toolchain-evidence", "toolchain"]), 1)
        execute.assert_called_once_with("owned-llvm", profile_runner=probe.owned_failure_profile,
                                        toolchain_evidence=Path("toolchain"))
        seal.assert_called_once_with(self.artifacts)
        result = json.loads((self.artifacts / "failure-probe.json").read_text())
        self.assertEqual(result["status"], "verified_expected_failure")
        self.assertEqual(json.loads((self.qualification / "report.json").read_text()), self.report)

    def test_probe_verification_error_is_preserved_and_stays_failed(self):
        self.save()
        self.bundle.side_effect = ValueError("artifact_fingerprint_mismatch")
        with patch.object(probe.runner, "execute", return_value=(self.folder, {"status": "failed"})), \
             patch.object(probe.runner, "seal_bundle"):
            self.assertEqual(probe.main(["--llvm-bin", "owned-llvm"]), 2)
        result = json.loads((self.artifacts / "failure-probe.json").read_text())
        self.assertEqual(result["status"], "probe_verification_failed")
        self.assertEqual(result["error"], "artifact_fingerprint_mismatch")


if __name__ == "__main__":
    unittest.main()

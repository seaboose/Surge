"""Reject misleading partial-report evidence in the owned CI failure probe."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts import probe_first_use_failure as probe


class FirstUseFailureProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.artifacts = Path(self.temporary.name)
        manifest = {"fixture.py": hashlib.sha256(b"owned source").hexdigest()}
        (self.artifacts / "source-manifest.json").write_text(json.dumps(manifest))
        with zipfile.ZipFile(self.artifacts / "surge-source.zip", "w") as archive:
            archive.writestr("Surge/fixture.py", b"owned source")
        for name in ("package", "cache_path"):
            (self.artifacts / (name + ".log")).write_text("completed")
        (self.artifacts / "setup.log").write_text(probe.MARKER)
        (self.artifacts / "report.md").write_text("failed; human acceptance pending")
        self.report = dict(
            schema="surge-first-use-release-v1", status="failed", human_acceptance="pending",
            fuzzing="incomplete_not_run", source_unchanged=True, initial_caches_absent=True,
            initial_artifacts_absent={key: True for key in (".venv", "desktop/node_modules", "desktop/dist",
                                                          "native/build", "native/captures", "native/baselines.json")},
            archive_sha256=probe.runner.sha(self.artifacts / "surge-source.zip"),
            manifest_sha256=probe.runner.sha(self.artifacts / "source-manifest.json"),
            steps=[dict(id=name, status="passed" if i < 2 else "failed" if i == 2 else "not_run",
                        **({"exit_code": 0 if i < 2 else 73} if i < 3 else {}))
                   for i, name in enumerate(probe.EXPECTED_STEP_IDS)],
        )
        for step in self.report["steps"][:3]:
            log = self.artifacts / (step["id"] + ".log")
            step.update(log_sha256=probe.runner.sha(log), log_bytes=log.stat().st_size)

    def verify(self):
        (self.artifacts / "report.json").write_text(json.dumps(self.report))
        return probe.verify_artifacts(self.artifacts)

    def test_complete_expected_evidence_is_accepted_without_changing_files(self):
        self.verify()
        before = {p.name: p.read_bytes() for p in self.artifacts.iterdir()}
        result = probe.verify_artifacts(self.artifacts)
        self.assertEqual(result["status"], "verified_expected_failure")
        self.assertEqual(result["human_acceptance"], "pending")
        self.assertEqual({p.name: p.read_bytes() for p in self.artifacts.iterdir()}, before)

    def test_other_failures_or_inflated_claims_are_rejected(self):
        for key, value in (("status", "passed"), ("error", "source_manifest_mismatch"),
                           ("human_acceptance", "passed"), ("fuzzing", "passed"),
                           ("source_unchanged", False), ("initial_caches_absent", False)):
            with self.subTest(key=key):
                original = dict(self.report)
                self.report[key] = value
                with self.assertRaises(ValueError):
                    self.verify()
                self.report = original
        self.report["steps"][2]["exit_code"] = 2
        with self.assertRaisesRegex(ValueError, "unexpected_failure_exit"):
            self.verify()

    def test_partial_step_states_and_missing_failure_marker_are_rejected(self):
        self.report["steps"][3]["status"] = "passed"
        with self.assertRaisesRegex(ValueError, "incorrect_partial_step_statuses"):
            self.verify()
        self.report["steps"][3]["status"] = "not_run"
        (self.artifacts / "setup.log").write_text("unrelated failure")
        with self.assertRaisesRegex(ValueError, "missing_owned_failure_marker"):
            self.verify()

    def test_archive_corruption_is_rejected_even_if_outer_hash_is_updated(self):
        with zipfile.ZipFile(self.artifacts / "surge-source.zip", "w") as archive:
            archive.writestr("Surge/fixture.py", b"different content")
        with self.assertRaisesRegex(ValueError, "archive_fingerprint_mismatch"):
            self.verify()
        self.report["archive_sha256"] = probe.runner.sha(self.artifacts / "surge-source.zip")
        with self.assertRaisesRegex(ValueError, "archived_source_hash_mismatch"):
            self.verify()

    def test_missing_completed_log_and_unexpected_later_log_are_rejected(self):
        (self.artifacts / "package.log").unlink()
        with self.assertRaisesRegex(ValueError, "missing_completed_step_log"):
            self.verify()
        (self.artifacts / "package.log").write_text("completed")
        (self.artifacts / "replay.log").write_text("should not have run")
        with self.assertRaisesRegex(ValueError, "unexpected_later_step_log"):
            self.verify()

    def test_log_mutation_is_rejected_for_each_executed_step(self):
        for name in ("package", "cache_path", "setup"):
            with self.subTest(step=name):
                log = self.artifacts / (name + ".log")
                original = log.read_bytes()
                log.write_bytes(original + b" altered")
                with self.assertRaisesRegex(ValueError, "log_length_mismatch"):
                    self.verify()
                self.report["steps"][probe.EXPECTED_STEP_IDS.index(name)]["log_bytes"] = log.stat().st_size
                with self.assertRaisesRegex(ValueError, "log_fingerprint_mismatch"):
                    self.verify()
                log.write_bytes(original)
                self.report["steps"][probe.EXPECTED_STEP_IDS.index(name)]["log_bytes"] = len(original)

    def test_later_steps_cannot_claim_execution_while_not_run(self):
        for key, value in (("exit_code", 0), ("log_sha256", "a" * 64), ("log_bytes", 0)):
            with self.subTest(field=key):
                self.report["steps"][3][key] = value
                with self.assertRaisesRegex(ValueError, "unexpected_later_execution_claim"):
                    self.verify()
                self.report["steps"][3].pop(key)


if __name__ == "__main__":
    unittest.main()

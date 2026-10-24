"""Consumer controls use owned tiny archives; no downloaded executable is run."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import check_windows_package as consumer
from scripts import verify_windows_consumer as verifier


class ConsumerContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def package(self, extra=None):
        contents = {name: b"owned fixture\n" for name in (
            "Surge.exe", "resources/python/python.exe", "resources/app/desktop_worker.py",
            "resources/app/desktop/main.cjs", "resources/app/native/build/surge_owned_app.exe",
            "resources/app/native/baselines.json", "resources/app/package-identity.json")}
        contents.update(extra or {})
        archive = self.root / "owned.zip"
        with zipfile.ZipFile(archive, "w") as stream:
            for name, raw in contents.items():
                stream.writestr(name, raw)
        manifest = dict(schema="surge-windows-package-v1", source=dict(commit="owned", dirty=True),
                        archive=dict(name=archive.name, bytes=archive.stat().st_size, sha256=consumer.digest(archive)),
                        files=[dict(path=n, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) for n, raw in contents.items()])
        return archive, manifest

    def test_exact_owned_inventory_extracts_without_execution(self):
        archive, manifest = self.package()
        result = consumer.verify_package(archive, manifest)
        self.assertEqual(result["files"], 7)
        destination = self.root / "space é"
        consumer.extract_verified(archive, destination)
        self.assertTrue(consumer.verify_payload(destination, manifest)["unchanged"])

    def test_payload_edit_is_rejected_after_extraction(self):
        archive, manifest = self.package()
        destination = self.root / "payload"
        consumer.extract_verified(archive, destination)
        (destination / "Surge.exe").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "payload changed"):
            consumer.verify_payload(destination, manifest)

    def test_archive_identity_rejects_appended_bytes(self):
        archive, manifest = self.package()
        with archive.open("ab") as stream:
            stream.write(b"unexpected")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            consumer.verify_package(archive, manifest)

    def test_case_collision_and_traversal_rejected_before_extract(self):
        for name in ("surge.exe", "../outside", "C:/outside", "resources/CON.txt", "resources/trailing."):
            with self.subTest(name=name):
                archive, manifest = self.package({name: b"owned"})
                with self.assertRaises(ValueError):
                    consumer.verify_package(archive, manifest)
        self.assertFalse((self.root.parent / "outside").exists())

    def test_forged_file_hash_is_not_masked_by_valid_zip_hash(self):
        archive, manifest = self.package()
        manifest["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "member digest"):
            consumer.verify_package(archive, manifest)

    def test_declared_expansion_fails_closed(self):
        archive, manifest = self.package()
        manifest["files"][0]["bytes"] = consumer.LIMITS["expanded_bytes"] + 1
        with self.assertRaisesRegex(ValueError, "768 MiB"):
            consumer.verify_package(archive, manifest)

    def test_failure_retains_prior_checks_and_skips_dependents(self):
        actions = []
        def failed():
            raise TimeoutError("owned deadline")
        report = {"steps": [{"name": n, "status": "not_run"} for n in ("before", "failure", "later")]}
        snapshots = []
        result = consumer.execute_steps([
            ("before", lambda: actions.append("before")), ("failure", failed),
            ("later", lambda: actions.append("later"))], report,
            lambda: snapshots.append(json.loads(json.dumps(report))))
        self.assertFalse(result)
        self.assertEqual(actions, ["before"])
        self.assertEqual([x["status"] for x in report["steps"]], ["passed", "failed", "not_run"])
        self.assertIn("TimeoutError", snapshots[-1]["error"])

    def test_existing_ordinary_profile_is_refused_without_mutation(self):
        archive, manifest = self.package()
        manifest_path = self.root / "manifest.json"
        consumer.write_json(manifest_path, manifest)
        profile = self.root / "surge-desktop"
        profile.mkdir()
        evidence = profile / "existing.case.json"
        evidence.write_bytes(b"user evidence must survive")
        with mock.patch.object(consumer, "ordinary_appdata", return_value=self.root), mock.patch.object(consumer, "token_identity", return_value={"token_elevated": False}), mock.patch.object(consumer, "run_owned") as run:
            code = consumer.main(["--package", str(archive), "--manifest", str(manifest_path), "--ordinary-profile", "--node", str(archive), "--output-root", str(self.root / "results")])
        self.assertEqual(code, 1)
        run.assert_not_called()
        self.assertEqual(evidence.read_bytes(), b"user evidence must survive")
        report = json.loads(next((self.root / "results").glob("*/artifacts/report.json")).read_text())
        self.assertIn("Refusing an existing profile", report["error"])
        self.assertTrue(all(x["status"] == "not_run" for x in report["steps"]))

    def test_app_environment_excludes_developer_command_lookup(self):
        with mock.patch.dict(consumer.os.environ, {"PATH": "C:/developer", "NODE_OPTIONS": "--inspect", "PYTHONPATH": "C:/developer/python", "SURGE_PYTHON": "C:/developer/python.exe"}):
            actual = consumer.restricted_environment(self.root)
        self.assertNotIn("developer", actual["PATH"])
        self.assertNotIn("NODE_OPTIONS", actual)
        self.assertIn("invalid-override", actual["SURGE_PYTHON"])

    def test_zone_metadata_records_only_presence_and_zone(self):
        target = self.root / "owned-download.zip"
        target.write_bytes(b"owned")
        with open(str(target) + ":Zone.Identifier", "wb") as stream:
            stream.write(b"[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://owned.invalid/?secret=do-not-retain\r\nReferrerUrl=https://owned.invalid/ref\r\n")
        actual = consumer.zone_identifier(target)
        self.assertEqual(actual, dict(present=True, zone_id=3, inspection="read"))
        self.assertNotIn("secret", json.dumps(actual))

    def test_absent_zone_metadata_is_distinguished_from_an_internet_zone(self):
        target = self.root / "owned-local.zip"
        target.write_bytes(b"owned")
        self.assertEqual(consumer.zone_identifier(target), dict(present=False, zone_id=None, inspection="absent"))

    def failure_evidence(self):
        _, manifest = self.package()
        base = self.root / "probe"
        base.mkdir()
        consumer.write_json(base / "package-manifest.json", manifest)
        consumer.write_json(base / "failure-probe-receipt.json", dict(status="verified_expected_failure", marker="exit marker", exit_code=73, timeout_marker="timeout marker", timeout_seconds=1))
        consumer.write_json(base / "failure-probe/supervisor.json", dict(status="failed", exit_code=73, forced_cleanup=False))
        consumer.write_json(base / "timeout-probe/supervisor.json", dict(status="failed", exit_code=1, forced_cleanup=True, error="TimeoutError: owned deadline"))
        (base / "failure-probe/console.log").write_text("exit marker\n")
        (base / "timeout-probe/console.log").write_text("timeout marker\n")
        report = dict(schema="surge-windows-package-consumer-v1", limits=consumer.LIMITS,
                      status="failed", elapsed_seconds=1.2, archive=manifest["archive"], source=manifest["source"],
                      manifest_sha256=consumer.digest(base / "package-manifest.json"),
                      steps=[dict(name=name, status="passed" if i == 0 else "failed" if i == 1 else "not_run") for i, name in enumerate(consumer.STEPS)],
                      failure_probe="verified_expected_failure")
        report["harness_source"] = []
        for relative in consumer.HARNESS:
            target = base / "harness-source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"owned frozen verifier fixture")
            report["harness_source"].append(consumer.file_record(target, base))
        report["harness_source_unchanged"] = True
        self.seal_report(base, report)
        return base, report, manifest

    def seal_report(self, base, report):
        report["evidence_files"] = [consumer.file_record(p, base) for p in base.rglob("*") if p.is_file() and p.name != "report.json"]
        consumer.write_json(base / "report.json", report)

    def test_offline_expected_failure_requires_both_underlying_failures(self):
        base, report, manifest = self.failure_evidence()
        self.assertEqual(consumer.verify_evidence(base / "report.json", manifest, True)["status"], "verified_expected_failure")
        consumer.write_json(base / "timeout-probe/supervisor.json", dict(status="passed", exit_code=0, forced_cleanup=False, error=None))
        self.seal_report(base, report)
        with self.assertRaisesRegex(ValueError, "timeout/cleanup"):
            consumer.verify_evidence(base / "report.json", manifest, True)

    def test_offline_changed_log_cannot_hide_behind_passed_receipt(self):
        base, _, manifest = self.failure_evidence()
        (base / "failure-probe/console.log").write_text("changed log\n")
        with self.assertRaisesRegex(ValueError, "digest/length"):
            consumer.verify_evidence(base / "report.json", manifest, True)

    def test_offline_failure_cannot_mark_later_steps_passed(self):
        base, report, manifest = self.failure_evidence()
        report["steps"][-1]["status"] = "passed"
        self.seal_report(base, report)
        with self.assertRaisesRegex(ValueError, "dependent checks"):
            consumer.verify_evidence(base / "report.json", manifest, True)

    def test_verifier_invalid_input_emits_failure_and_nonzero(self):
        bad = self.root / "malformed.json"
        bad.write_text("{}")
        output = io.StringIO()
        with mock.patch("sys.stderr", output):
            self.assertEqual(verifier.main(["--report", str(bad), "--manifest", str(bad)]), 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "failed")


if __name__ == "__main__":
    unittest.main()

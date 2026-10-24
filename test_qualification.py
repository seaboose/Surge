"""Qualification must never turn missing/failed checks into a passing report."""

import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

from scripts import qualify
from scripts.check_libfuzzer import corpus_bytes
from scripts.parser_boundary_contract import COUNT_POSITIVE_CONTROLS, GUARDS, case_ids, parse_output
from scripts.release_files import source_files


class QualificationTests(unittest.TestCase):
    def test_live_corpus_monitor_handles_removed_entry_but_propagates_other_errors(self):
        folder, removed, present = Mock(), Mock(), Mock()
        folder.iterdir.return_value = [removed, present]
        removed.stat.side_effect = FileNotFoundError()
        present.stat.return_value.st_size = 42
        self.assertEqual(corpus_bytes(folder), 42)
        removed.stat.side_effect = PermissionError()
        with self.assertRaises(PermissionError):
            corpus_bytes(folder)

    def test_environment_cannot_disable_assertions_or_override_checkout_runtime(self):
        keys = (
            "PYTHONOPTIMIZE",
            "PYTHONHOME",
            "PYTHONPATH",
            "SURGE_PYTHON",
            "ELECTRON_RUN_AS_NODE",
        )
        with patch.dict(qualify.os.environ, {key: "1" for key in keys}):
            env = qualify.test_environment("test-temp")
        self.assertTrue(all(key not in env for key in keys))
        self.assertEqual(env["TEMP"], "test-temp")

    def report(self):
        return dict(
            qualification_status="incomplete",
            started_at_utc="test",
            checks=[
                dict(id="first", status="not_run", log="first.log"),
                dict(id="second", status="not_run", log="second.log"),
            ],
        )

    def test_failed_step_stops_and_preserves_unrun_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            report = self.report()
            called = []

            def fail(step, log, env, deadline):
                called.append(step["id"])
                return dict(status="failed", exit_code=7)

            self.assertFalse(
                qualify.execute_steps(
                    report["checks"], Path(temp), report, {}, time.monotonic() + 10, fail
                )
            )
            self.assertEqual(called, ["first"])
            saved = json.loads((Path(temp) / "report.json").read_text())
            self.assertEqual([s["status"] for s in saved["checks"]], ["failed", "not_run"])
            self.assertIn("Fuzzing campaign: **incomplete", (Path(temp) / "report.md").read_text())

    def test_empty_and_skipped_python_results_cannot_pass(self):
        for text in ("", "Ran 0 tests\nOK", "Ran 10 tests\nOK (skipped=1)"):
            result = dict(status="passed")
            qualify.verify_test_output("python_suite", result, text)
            self.assertEqual(result["status"], "failed")
        result = dict(status="passed")
        qualify.verify_test_output("python_suite", result, "Ran 10 tests\nOK")
        self.assertEqual(result, dict(status="passed", tests=10))

    def test_native_zero_tests_cannot_pass(self):
        result = dict(status="passed")
        qualify.verify_test_output("native_ctest", result, "No tests were found!!!")
        self.assertEqual(result["status"], "failed")

    def test_native_summary_accepts_both_success_formats(self):
        for text in (
            "100% tests passed, 0 tests failed out of 3",
            "100% tests passed out of 3",
        ):
            result = dict(status="passed")
            qualify.verify_test_output("native_ctest", result, text)
            self.assertEqual(result, dict(status="passed", tests=3))

    def test_asan_detection_requires_expected_exit_and_specific_diagnostic(self):
        diagnostic = "ERROR: AddressSanitizer: heap-buffer-overflow"
        for status, code, text in (
            ("passed", 0, diagnostic),
            ("failed", 1, diagnostic),
            ("failed", 86, "missing DLL"),
            ("timed_out", 86, diagnostic),
            ("failed", 86, diagnostic + " ASAN_PROBE_COMPLETED"),
        ):
            result = dict(status=status, exit_code=code)
            qualify.verify_test_output("asan_detection", result, text)
            self.assertEqual(result["status"], "failed")
        result = dict(status="failed", exit_code=86)
        qualify.verify_test_output("asan_detection", result, diagnostic)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["expected_failure"])

    def test_asan_control_and_suite_cannot_silently_pass(self):
        for step, text in (
            ("asan_control", ""),
            ("asan_ctest", "No tests were found"),
            ("asan_ctest", "100% tests passed out of 3\nERROR: AddressSanitizer: bad-free"),
        ):
            result = dict(status="passed", exit_code=0)
            qualify.verify_test_output(step, result, text)
            self.assertEqual(result["status"], "failed")

    def test_asan_environment_is_pinned(self):
        with patch.dict(
            qualify.os.environ,
            {
                "ASAN_OPTIONS": "halt_on_error=0",
                "CL": "/fsanitize=none",
                "ASAN_SAVE_DUMPS": "dump.dmp",
            },
        ):
            env = qualify.test_environment("test-temp")
        self.assertIn("halt_on_error=1", env["ASAN_OPTIONS"])
        self.assertNotIn("CL", env)
        self.assertNotIn("ASAN_SAVE_DUMPS", env)

    def property_summary(self):
        runs = [
            dict(property=name, seed=number, repeat=repeat, evaluations=64, input_sha256="a" * 64)
            for name in ("manifest_partition", "stream_ordering", "replay_consistency")
            for number in (20261023, 17)
            for repeat in (1, 2)
        ]
        return dict(
            schema="surge-properties-v1",
            status="passed",
            hypothesis_version="6.170.8",
            runs=runs,
            evaluations=768,
            repeatability="passed",
            seeds=[20261023, 17],
            examples_per_property=64,
            original_fuzzing_campaign="incomplete",
        )

    def test_property_evidence_records_completed_counts(self):
        result = dict(status="passed", exit_code=0)
        qualify.verify_test_output(
            "properties", result, "SURGE_PROPERTIES_JSON=" + json.dumps(self.property_summary())
        )
        self.assertEqual(result["property_evidence"]["evaluations"], 768)

    def test_property_evidence_rejects_short_missing_and_nonrepeatable_runs(self):
        for change in ("short", "missing", "fingerprint", "duplicate", "version", "total"):
            summary = self.property_summary()
            if change == "short":
                summary["runs"][0]["evaluations"] = 0
            elif change == "missing":
                summary["runs"].pop()
            elif change == "fingerprint":
                summary["runs"][0]["input_sha256"] = "b" * 64
            elif change == "duplicate":
                summary["runs"][0] = summary["runs"][2]
            elif change == "version":
                summary["hypothesis_version"] = "unknown"
            else:
                summary["evaluations"] = 1
            result = dict(status="passed", exit_code=0)
            qualify.verify_test_output(
                "properties", result, "SURGE_PROPERTIES_JSON=" + json.dumps(summary)
            )
            self.assertEqual(result["status"], "failed", change)
        for text in ("", "SURGE_PROPERTIES_JSON={}", "SURGE_PROPERTIES_JSON=broken"):
            result = dict(status="passed", exit_code=0)
            qualify.verify_test_output("properties", result, text)
            self.assertEqual(result["status"], "failed")

    def test_failed_property_process_cannot_be_rescued_by_summary(self):
        result = dict(status="failed", exit_code=1)
        qualify.verify_test_output(
            "properties", result, "SURGE_PROPERTIES_JSON=" + json.dumps(self.property_summary())
        )
        self.assertEqual(result["status"], "failed")

    def pilot_summary(self):
        ids = (
            "asan_safe",
            "asan_detection",
            "runtime_control",
            "code_pe_tests",
            "manifest_pe_tests",
            "baseline_coverage",
            "final_coverage",
            "corpus_repeat",
            "fuzz_17",
            "fuzz_20261023",
            "boundaries_replay",
            "boundaries_coverage",
            "boundaries_repeat",
        )
        return dict(
            schema="surge-libfuzzer-pilot-v1",
            status="passed",
            original_campaign="incomplete",
            instrumentation="passed",
            controls="passed",
            source_unchanged=True,
            checks=[dict(id=name, status="passed") for name in ids],
            corpus_replay=dict(status="passed", files=3),
            fuzz_runs=[dict(seed=n, executions=5000) for n in (17, 20261023)],
            baseline_coverage=dict(summary=dict(branches=dict(covered=10))),
            final_coverage=dict(summary=dict(branches=dict(covered=11))),
            boundary_tests=dict(
                status="passed", repeatability="passed", executions=2*len(case_ids()),
                relocation_reader_executed=True,
                cases=[dict(id=n,status="PASS",expected="ACCEPT",actual="ACCEPT") for n in sorted(case_ids())],
                inputs=[dict(id=n,bytes=5120,sha256="a"*64) for n in sorted(case_ids())],
                guards={n:[[1,1,1,2,1,1]] for n in GUARDS},
                coverage=dict(summary=dict(branches=dict(covered=20,count=30))),
            ),
        )

    def test_boundary_report_rejects_missing_cases_and_unverified_guards(self):
        for change in ("missing", "duplicate", "mismatch", "guard", "reader", "size", "repeat"):
            data = self.pilot_summary()
            boundary = data["boundary_tests"]
            if change == "missing": boundary["cases"].pop()
            elif change == "duplicate": boundary["cases"][-1] = boundary["cases"][0]
            elif change == "mismatch": boundary["cases"][0]["actual"] = "Unexpected refusal"
            elif change == "guard": boundary["guards"][GUARDS[0]][0][5] = 0
            elif change == "reader": boundary["relocation_reader_executed"] = False
            elif change == "size": boundary["inputs"][0]["bytes"] = 65537
            else: boundary["repeatability"] = "incomplete"
            result = dict(status="passed", exit_code=0)
            qualify.verify_test_output("libfuzzer", result, "SURGE_LIBFUZZER_JSON="+json.dumps(data))
            self.assertEqual(result["status"], "failed", change)

    def test_boundary_output_rejects_extra_output_and_wrong_totals(self):
        text = "\n".join(f"CASE\t{name}\tPASS\tACCEPT\tACCEPT" for name in sorted(case_ids()))
        good = text + f"\nTOTAL\t{len(case_ids())}\t0"
        self.assertEqual(len(parse_output(good)), len(case_ids()))
        for bad in (good+"\nERROR: AddressSanitizer: test", text+"\nTOTAL\t1\t0", good.replace("PASS", "FAIL", 1)):
            with self.assertRaises(ValueError): parse_output(bad)

    def test_count_boundary_evidence_cannot_omit_upper_controls_or_guards(self):
        upper_controls = (
            "export_functions_4096", "export_names_4096",
            "manifest_cardinality_16", "export_manifest_combined_max",
        )
        changes = [("missing", name) for name in upper_controls]
        changes += [("mismatch", name) for name in upper_controls]
        changes += [("relabel", name) for name in sorted(COUNT_POSITIVE_CONTROLS)]
        changes += [("guard_missing", name) for name in GUARDS[-4:]]
        changes += [("guard_outcome", name) for name in GUARDS[-4:]]
        for change, name in changes:
            with self.subTest(change=change, name=name):
                data = self.pilot_summary()
                boundary = data["boundary_tests"]
                if change == "missing":
                    # A self-consistent shorter report still cannot omit a
                    # required upper-limit positive control.
                    boundary["cases"] = [r for r in boundary["cases"] if r["id"] != name]
                    boundary["inputs"] = [r for r in boundary["inputs"] if r["id"] != name]
                    boundary["executions"] = 2 * len(boundary["cases"])
                elif change == "mismatch":
                    next(r for r in boundary["cases"] if r["id"] == name)["actual"] = "Unexpected refusal"
                elif change == "relabel":
                    row = next(r for r in boundary["cases"] if r["id"] == name)
                    row["actual"] = row["expected"] = "Unsupported export count"
                elif change == "guard_missing":
                    del boundary["guards"][name]
                else:
                    boundary["guards"][name][0][4] = 0
                result = dict(status="passed", exit_code=0)
                qualify.verify_test_output("libfuzzer", result, "SURGE_LIBFUZZER_JSON=" + json.dumps(data))
                self.assertEqual(result["status"], "failed")

    def test_libfuzzer_requires_instrumentation_progress_and_completed_checks(self):
        for change in ("instrumentation", "coverage", "short", "checks", "replay"):
            data = self.pilot_summary()
            if change == "instrumentation":
                data["instrumentation"] = "incomplete"
            elif change == "coverage":
                data["final_coverage"]["summary"]["branches"]["covered"] = 10
            elif change == "short":
                data["fuzz_runs"][0]["executions"] = 1
            elif change == "checks":
                data["checks"].pop()
            else:
                data["corpus_replay"]["status"] = "failed"
            result = dict(status="passed", exit_code=0)
            qualify.verify_test_output(
                "libfuzzer", result, "SURGE_LIBFUZZER_JSON=" + json.dumps(data)
            )
            self.assertEqual(result["status"], "failed", change)
        result = dict(status="passed", exit_code=0)
        qualify.verify_test_output(
            "libfuzzer", result, "SURGE_LIBFUZZER_JSON=" + json.dumps(self.pilot_summary())
        )
        self.assertEqual(result["libfuzzer_evidence"]["status"], "passed")

    def test_failed_libfuzzer_process_or_missing_summary_cannot_pass(self):
        result = dict(status="failed", exit_code=70)
        qualify.verify_test_output(
            "libfuzzer", result, "SURGE_LIBFUZZER_JSON=" + json.dumps(self.pilot_summary())
        )
        self.assertEqual(result["status"], "failed")
        for text in ("", "SURGE_LIBFUZZER_JSON={}", "SURGE_LIBFUZZER_JSON=invalid"):
            result = dict(status="passed", exit_code=0)
            qualify.verify_test_output("libfuzzer", result, text)
            self.assertEqual(result["status"], "failed")

    def test_launch_error_is_recorded(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(qualify.subprocess, "Popen", side_effect=FileNotFoundError),
        ):
            result = qualify.run_command(
                dict(argv=["missing"], cwd=".", timeout_seconds=1),
                Path(temp) / "log",
                {},
                time.monotonic() + 10,
            )
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["reason"], "FileNotFoundError")

    def test_timeout_and_cancellation_request_scoped_cleanup(self):
        for cancelled in (False, True):
            process = Mock(returncode=None)
            process.poll.return_value = None
            with (
                tempfile.TemporaryDirectory() as temp,
                patch.object(qualify.subprocess, "Popen", return_value=process),
                patch.object(qualify, "stop_tree", return_value="tree_terminated") as cleanup,
            ):
                with patch.object(
                    qualify.time, "sleep", side_effect=KeyboardInterrupt if cancelled else None
                ):
                    result = qualify.run_command(
                        dict(argv=["test"], cwd=".", timeout_seconds=5),
                        Path(temp) / "log",
                        {},
                        time.monotonic() + (10 if cancelled else -1),
                    )
                self.assertEqual(result["status"], "cancelled" if cancelled else "timed_out")
                cleanup.assert_called_once_with(process)

    def test_total_deadline_does_not_launch_a_check(self):
        with tempfile.TemporaryDirectory() as temp:
            runner = Mock()
            report = self.report()
            self.assertFalse(
                qualify.execute_steps(
                    report["checks"], Path(temp), report, {}, time.monotonic() - 1, runner
                )
            )
            runner.assert_not_called()
            self.assertTrue(all(s["status"] == "not_run" for s in report["checks"]))

    def test_cleanup_tool_failure_still_attempts_direct_child_cleanup(self):
        process = Mock()
        process.poll.return_value = None
        with (
            patch.object(qualify.os, "name", "nt"),
            patch.object(qualify.subprocess, "run", side_effect=OSError("unavailable")),
        ):
            self.assertEqual(qualify.stop_tree(process), "tree_cleanup_failed")
            process.kill.assert_called_once()
            process.wait.assert_called_once_with(timeout=10)

    def test_qualification_temporary_python_is_not_publishable_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            generated = root / "verification/qualification/run-test/temp/stub.py"
            generated.parent.mkdir(parents=True)
            generated.write_text("temporary")
            build = root / "native/build-asan/generated.py"
            build.parent.mkdir(parents=True)
            build.write_text("generated build file")
            (root / "kept.py").write_text("source")
            self.assertEqual([p.name for p in source_files(root)], ["kept.py"])


if __name__ == "__main__":
    unittest.main()

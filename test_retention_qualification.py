"""Retention qualification must fail closed on incomplete or inconsistent evidence."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import qualify
from scripts.check_retention import finalize_report
from scripts.retention_contract import CASE_IDS, LIMITS, validate_evidence


def fingerprint(metrics):
    raw = json.dumps(metrics, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def summary():
    runs = []
    for name in CASE_IDS:
        metrics = {}
        if name.startswith("count_"):
            _, ranges, samples = name.split("_")
            ranges, samples = int(ranges), int(samples)
            retained = min(samples, 500)
            metrics = dict(
                ranges=ranges, samples=samples, retained=retained,
                evicted=samples - retained, accounted_bytes=1000,
                json_bytes=900, jsonl_bytes=901,
                case_replay="passed", snapshot_stable="passed", replay="passed",
            )
        elif name.startswith("import_"):
            label = name.split("_")[-1]
            metrics = dict(
                bytes=16_777_216 + {"minus": -1, "exact": 0, "plus": 1}[label],
                outcome="rejected_at_byte_guard" if label == "plus" else "accepted",
            )
        else:
            samples, retained, evicted, accounted = {
                "single_minus": (2, 1, 1, 8_372_223),
                "single_exact": (2, 1, 1, 8_372_224),
                "single_plus": (1, 1, 0, 1024),
                "aggregate_minus": (2, 2, 0, 8_372_223),
                "aggregate_exact": (2, 2, 0, 8_372_224),
                "aggregate_plus": (2, 1, 1, 8_368_129),
                "multiple_evictions": (5, 3, 2, 8_372_224),
                "utf8": (3, 2, 1, 8_369_152),
                "empty": (1, 1, 0, 1024),
            }[name]
            metrics = dict(samples=samples, retained=retained, evicted=evicted,
                           accounted_bytes=accounted)
        for repeat in (1, 2):
            runs.append(dict(
                id=name, repeat=repeat, status="passed", input_sha256="a" * 64,
                result_sha256=fingerprint(metrics), metrics=copy.deepcopy(metrics),
            ))
    return dict(
        schema="surge-retention-v1", status="passed",
        original_fuzzing_campaign="incomplete", repeatability="passed",
        evaluations=48, limits=dict(LIMITS), runs=runs,
    )


class RetentionQualificationTests(unittest.TestCase):
    def verify(self, data, resign_metrics=False):
        if resign_metrics:
            for row in data["runs"]:
                row["result_sha256"] = fingerprint(row["metrics"])
        result = dict(status="passed", exit_code=0)
        qualify.verify_test_output("retention", result, "SURGE_RETENTION_JSON=" + json.dumps(data))
        return result

    def test_complete_summary_records_only_validated_evidence(self):
        data = summary()
        self.assertEqual(len(CASE_IDS), 24)
        self.assertEqual(len(set(CASE_IDS)), 24)
        self.assertIs(validate_evidence(data), data)
        result = self.verify(data)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["retention_evidence"], data)

    def test_finalization_marks_validated_evidence_passed(self):
        expected = summary()
        data = copy.deepcopy(expected)
        data.update(status="incomplete", repeatability="incomplete")
        finalize_report(data)
        self.assertEqual(data, expected)

    def test_failed_finalization_preserves_incomplete_flags_and_evaluations(self):
        data = summary()
        data.update(status="incomplete", repeatability="incomplete")
        data["runs"][0]["input_sha256"] = "c" * 64
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, "repeatability failed"):
            finalize_report(data)
        self.assertEqual(data, before)

    def test_missing_duplicate_and_unrecognized_cases_fail_closed(self):
        for change in ("missing", "duplicate", "unknown", "wrong_repeat", "boolean_repeat"):
            with self.subTest(change=change):
                data = summary()
                if change == "missing":
                    data["runs"].pop()
                    data["evaluations"] -= 1
                elif change == "duplicate":
                    data["runs"][-1] = copy.deepcopy(data["runs"][0])
                elif change == "unknown":
                    data["runs"][0]["id"] = "unrecognized_case"
                elif change == "wrong_repeat":
                    data["runs"][0]["repeat"] = 3
                else:
                    data["runs"][0]["repeat"] = True
                self.assertEqual(self.verify(data)["status"], "failed")

    def test_unpassed_summary_or_evaluation_cannot_qualify(self):
        for field, value in (
            ("schema", "surge-retention-other"), ("status", "incomplete"),
            ("original_fuzzing_campaign", "complete"), ("repeatability", "failed"),
            ("evaluations", 47), ("evaluations", 48.0),
        ):
            with self.subTest(field=field, value=value):
                data = summary()
                data[field] = value
                self.assertEqual(self.verify(data)["status"], "failed")
        for status in ("failed", "not_run", "running"):
            data = summary()
            data["runs"][0]["status"] = status
            self.assertEqual(self.verify(data)["status"], "failed")

    def test_limits_cannot_be_relaxed_or_silently_omitted(self):
        for key in LIMITS:
            for change in ("higher", "missing", "wrong_type"):
                with self.subTest(key=key, change=change):
                    data = summary()
                    if change == "missing":
                        del data["limits"][key]
                    elif change == "higher":
                        data["limits"][key] += 1
                    else:
                        data["limits"][key] = float(data["limits"][key])
                    self.assertEqual(self.verify(data)["status"], "failed")

    def test_input_and_result_fingerprints_require_shape_and_repeatability(self):
        for field in ("input_sha256", "result_sha256"):
            for value in ("c" * 64, "a" * 63, "z" * 64, "A" * 64, None):
                with self.subTest(field=field, value=value):
                    data = summary()
                    data["runs"][0][field] = value
                    self.assertEqual(self.verify(data)["status"], "failed")

    def test_count_case_measurements_enforce_conservation_and_limits(self):
        for field, value in (
            ("ranges", 3), ("samples", 500), ("retained", 498),
            ("retained", 500), ("evicted", 1), ("accounted_bytes", 0),
            ("accounted_bytes", LIMITS["accounting_budget"] + 1),
            ("json_bytes", LIMITS["window_bytes"] + 1),
            ("jsonl_bytes", LIMITS["window_bytes"] + 1), ("json_bytes", True),
        ):
            with self.subTest(field=field, value=value):
                data = summary()
                data["runs"][0]["metrics"][field] = value
                self.assertEqual(self.verify(data, resign_metrics=True)["status"], "failed")

    def test_two_range_positive_control_cannot_be_relabelled_with_extra_eviction(self):
        data = summary()
        for row in data["runs"]:
            if row["id"] == "count_2_501":
                row["metrics"].update(retained=499, evicted=2)
        self.assertEqual(self.verify(data, resign_metrics=True)["status"], "failed")

    def test_case_replay_export_replay_and_snapshot_must_each_complete(self):
        for field in ("case_replay", "replay", "snapshot_stable"):
            with self.subTest(field=field):
                data = summary()
                data["runs"][0]["metrics"][field] = "not_run"
                self.assertEqual(self.verify(data, resign_metrics=True)["status"], "failed")

    def test_accounting_boundaries_require_their_specific_outcomes(self):
        for name in CASE_IDS:
            if name.startswith(("count_", "import_")):
                continue
            for field in ("samples", "retained", "evicted", "accounted_bytes"):
                with self.subTest(case=name, field=field):
                    data = summary()
                    for row in data["runs"]:
                        if row["id"] == name:
                            row["metrics"][field] += 1
                    self.assertEqual(self.verify(data, resign_metrics=True)["status"], "failed")

    def test_import_boundaries_require_exact_size_and_guard_outcome(self):
        for name in CASE_IDS:
            if not name.startswith("import_"):
                continue
            for field, value in (("bytes", 16), ("outcome", "unclassified_rejection")):
                with self.subTest(case=name, field=field):
                    data = summary()
                    for row in data["runs"]:
                        if row["id"] == name:
                            row["metrics"][field] = value
                    self.assertEqual(self.verify(data, resign_metrics=True)["status"], "failed")

    def test_metrics_must_match_the_result_fingerprint(self):
        data = summary()
        for row in data["runs"]:
            row["metrics"]["unchecked_detail"] = "changed after fingerprinting"
        self.assertEqual(self.verify(data)["status"], "failed")

    def test_missing_or_invalid_structure_is_rejected(self):
        examples = [None, [], {}, summary(), summary(), summary(), summary()]
        examples[3]["runs"] = None
        examples[4]["runs"][0] = None
        examples[5]["runs"][0]["metrics"] = []
        del examples[6]["runs"][0]["metrics"]["case_replay"]
        for data in examples:
            with self.subTest(data_type=type(data).__name__):
                result = self.verify(data)
                self.assertEqual(result["status"], "failed")
                self.assertNotIn("retention_evidence", result)

    def test_missing_invalid_or_duplicate_summary_cannot_pass(self):
        valid = "SURGE_RETENTION_JSON=" + json.dumps(summary())
        for text in ("", "SURGE_RETENTION_JSON=invalid", valid + "\n" + valid):
            result = dict(status="passed", exit_code=0)
            qualify.verify_test_output("retention", result, text)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "invalid_retention_evidence")

    def test_failed_process_cannot_be_rescued_by_a_passing_summary(self):
        for status in ("failed", "timed_out", "unavailable", "cancelled"):
            result = dict(status=status, exit_code=1)
            qualify.verify_test_output(
                "retention", result, "SURGE_RETENTION_JSON=" + json.dumps(summary())
            )
            self.assertEqual(result["status"], status)
            self.assertNotIn("retention_evidence", result)

    def test_retention_plan_is_optional_bounded_and_composable(self):
        self.assertNotIn("retention", [step["id"] for step in qualify.plan()])
        steps = qualify.plan(True, True, True, "llvm-bin", True)
        self.assertEqual(len(steps), 21)
        retention = [step for step in steps if step["id"] == "retention"]
        self.assertEqual(len(retention), 1)
        self.assertEqual(retention[0]["timeout_seconds"], 300)
        self.assertEqual(retention[0]["argv"][1:], ["-B", "scripts/check_retention.py"])

    def test_generated_report_distinguishes_retention_from_unfinished_campaign(self):
        with tempfile.TemporaryDirectory() as folder:
            report = dict(
                qualification_status="passed", started_at_utc="test", retention_requested=True,
                checks=[dict(id="retention", status="passed", retention_evidence=summary())],
            )
            qualify.write_reports(Path(folder), report)
            text = (Path(folder) / "report.md").read_text(encoding="utf-8")
            self.assertIn("Retention profile requested: True", text)
            self.assertIn("24 fixed cases, 48 evaluations", text)
            self.assertIn("Fuzzing campaign: **incomplete", text)
            self.assertEqual(json.loads((Path(folder) / "report.json").read_text()), report)


if __name__ == "__main__":
    unittest.main()

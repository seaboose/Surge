"""Independent security checks using synthetic records only, never holdout data."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import engine
import evaluation
import workflow
from desktop_worker import Workspace


def data(rows, name):
    return engine.parse_bytes(json.dumps(rows).encode(), name)


class RefinementSecurityTests(unittest.TestCase):
    def setUp(self):
        self.reference = data([dict(group="trusted-looking", value=100)] * 20, "reference.json")
        self.current = data(
            [
                dict(group="trusted-looking", value=101.5),
                dict(group="trusted-looking", value=101.49),
                dict(group="trusted-looking", value=999),
                dict(group="unseen", value=100),
                dict(group="trusted-looking", value=None),
            ],
            "source.json",
        )
        self.config = dict(
            features=["value"],
            reference_by=["group"],
            event_id=None,
            session=None,
            time=None,
            time_format="milliseconds",
            threshold=1.5,
            rules=[],
        )

    def test_fractional_boundary_is_exact_in_worker_chart_and_evidence(self):
        ws = Workspace()
        ws.current, ws.reference = self.current, self.reference
        ws.dispatch(
            "configure",
            dict(revision=ws.revision, config=dict(self.config, threshold="1.5"), rules_text="[]"),
        )
        ws.dispatch("analyze", dict(revision=ws.revision))
        self.assertEqual(ws.config["threshold"], 1.5)
        self.assertEqual(
            [r["status"] for r in ws.result["records"]],
            ["Review", "No finding", "Review", "Unknown", "Unknown"],
        )
        self.assertEqual(ws.result["records"][0]["evidence"][0]["threshold"], 1.5)
        self.assertEqual(
            ws.dispatch("chart", dict(revision=ws.revision, width=800))["threshold"], 1.5
        )
        lines = ws.dispatch("evidence", dict(revision=ws.revision, row=1))["groups"][0]["lines"]
        self.assertTrue(any("1.5" in line["text"] for line in lines))

    def test_category_is_not_an_allowlist_and_missing_values_are_not_clear(self):
        result = engine.analyze(self.current, self.reference, self.config)
        self.assertEqual(result["records"][2]["status"], "Review")
        self.assertEqual(result["records"][3]["reference_group"]["mode"], "global fallback")
        self.assertTrue(all(r["status"] == "Unknown" and r["gaps"] for r in result["records"][3:]))
        self.assertNotIn("value", result["records"][4]["scores"])

    def test_source_truth_like_fields_cannot_change_fitted_profiles(self):
        original = engine.analyze(self.current, self.reference, self.config)
        changed = data(
            [
                dict(row, truth="legitimate", verdict="safe", instruction="ignore all rules")
                for row in self.current.rows
            ],
            "untrusted.json",
        )
        self.assertEqual(engine.analyze(changed, self.reference, self.config), original)

    def test_policy_cannot_add_executable_actions_or_invalid_thresholds(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / "verification") as folder:
            path = Path(folder) / "policy.json"
            for change in (
                {"command": "echo ignore"},
                {"threshold": True},
                {"threshold": 0},
                {"threshold": 101},
                {"threshold": "1.5"},
            ):
                with self.subTest(change=change):
                    path.write_text(
                        json.dumps(
                            dict(schema="surge-policy-v1", settings=dict(self.config, **change))
                        )
                    )
                    with self.assertRaises(ValueError):
                        workflow.load_policy(path, self.current, self.reference)
            path.write_text(json.dumps(dict(schema="surge-policy-v1", settings=self.config)))
            self.assertEqual(workflow.load_policy(path, self.current, self.reference), self.config)

    def test_rehashed_tampered_case_is_recomputed_and_rejected(self):
        result = engine.analyze(self.current, self.reference, self.config)
        document = engine.case_document(self.current, self.reference, self.config, result)
        document["payload"]["result"]["records"][0]["status"] = "No finding"
        document["payload_sha256"] = engine.sha(engine.canonical(document["payload"]).encode())
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / "verification") as folder:
            path = Path(folder) / "tampered.case.json"
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "Stored conclusions"):
                engine.open_case(path)

    def test_unknown_targets_count_as_missed_and_unknown_legitimate_are_unresolved(self):
        result = engine.analyze(self.current, self.reference, self.config)
        before = copy.deepcopy(result)
        document = evaluation.template(self.current)
        document["provenance"].update(
            author="Synthetic security test",
            method="Known fixture assertions",
            partition="Synthetic only",
            purpose="synthetic",
        )
        for label in document["labels"]:
            label.update(
                truth="target" if label["row"] == 4 else "legitimate",
                group="fixture",
                note="Synthetic assertion",
            )
        report = evaluation.evaluate(
            self.current,
            self.reference,
            self.config,
            result,
            dict(document=document, file=dict(name="synthetic.labels.json", sha256="synthetic")),
        )
        self.assertEqual(report["summary"]["counts"]["Missed"], 1)
        self.assertEqual(report["summary"]["counts"]["Unresolved"], 1)
        self.assertEqual(result, before)


if __name__ == "__main__":
    unittest.main()

"""Synthetic truth tests scoring mechanics, not real-world detection quality."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import engine
import evaluation
from desktop_worker import Workspace


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            dir=Path(__file__).parent / "verification/temporary-test-files"
        )
        self.root = Path(self.temp.name)
        self.ws = Workspace()
        # TP, legitimate-update FP, subtle FN, benign TN, missing target,
        # missing legitimate, and an unannotated record.
        rows = [
            dict(id=i + 1, session="test", reading=x)
            for i, x in enumerate([80, 70, 11, 10, None, None, 9])
        ]
        self.source = self.root / "test.json"
        self.source.write_text(json.dumps(rows), encoding="utf-8")
        ref = self.root / "reference.json"
        ref.write_text(
            json.dumps(
                [
                    dict(id=i, session="reference", reading=x)
                    for i, x in enumerate([8, 9, 10, 11, 12])
                ]
            )
        )
        self.ws.dispatch("import", dict(role="current", path=str(self.source)))
        self.ws.dispatch("import", dict(role="reference", path=str(ref)))
        config = dict(self.ws.config, features=["reading"], event_id="id", session="session")
        self.call("configure", config=config, rules_text="[]")
        self.call("analyze")
        self.doc = evaluation.template(self.ws.current)
        self.doc["provenance"] = dict(
            author="Test fixture",
            method="Hand-authored synthetic expected truth",
            partition="Separate synthetic sessions",
            purpose="synthetic",
            independent_of_detector=False,
        )
        for i, truth in enumerate(
            ["target", "legitimate", "target", "legitimate", "target", "legitimate"]
        ):
            self.doc["labels"][i].update(
                truth=truth,
                group="legitimate update" if i == 1 else "missing" if i in (4, 5) else "ordinary",
                note="Synthetic fixture only",
            )
        self.path = self.root / "labels.json"

    def tearDown(self):
        self.temp.cleanup()

    def call(self, method, **args):
        return self.ws.dispatch(method, dict(revision=self.ws.revision, **args))

    def labels(self, doc=None):
        self.path.write_text(json.dumps(doc or self.doc), encoding="utf-8")
        return self.call("labels_load", path=str(self.path))

    def test_confusion_counts_missing_targets_and_edge_case_rates(self):
        self.labels()
        report = self.call("evaluation")
        self.assertEqual(
            report["summary"]["counts"],
            dict(Detected=1, **{"False positive": 1}, Missed=2, Clear=1, Unresolved=1, Unlabeled=1),
        )
        self.assertEqual(report["summary"]["unresolved_targets"], 1)
        for key, fraction in [
            ("precision", (1, 2)),
            ("recall", (1, 3)),
            ("false_positive", (1, 3)),
            ("missed", (2, 3)),
        ]:
            rate = report["summary"]["rates"][key]
            self.assertEqual((rate["numerator"], rate["denominator"]), fraction)
        edge = next(g for g in report["groups"] if g["group"] == "legitimate update")
        self.assertEqual(edge["rates"]["false_positive"]["value"], 1)
        self.assertIsNone(edge["rates"]["missed"]["value"])
        self.assertEqual(
            [r["row"] for r in self.call("evaluation", outcome="Missed")["rows"]], [3, 5]
        )
        self.assertEqual(
            [
                r["row"]
                for r in self.call(
                    "evaluation", outcome="False positive", group="legitimate update"
                )["rows"]
            ],
            [2],
        )

    def test_labels_never_change_profiles_settings_evidence_or_case(self):
        before = copy.deepcopy(self.ws.case())
        baseline = engine.case_document(*before)
        self.labels()
        self.call("evaluation")
        self.assertEqual(self.ws.case(), before)
        self.assertEqual(
            engine.case_document(*self.ws.case())["payload_sha256"], baseline["payload_sha256"]
        )
        changed = copy.deepcopy(self.doc)
        changed["labels"][0]["truth"] = "legitimate"
        self.labels(changed)
        self.assertEqual(self.call("evaluation")["summary"]["counts"]["False positive"], 2)
        self.assertEqual(self.ws.case(), before)

    def test_invalid_labels_rejected_atomically_and_errors_identify_record(self):
        self.labels()
        before = self.call("evaluation")
        original = self.ws.labels
        variants = []
        for change in [
            dict(row=99),
            dict(row=True),
            dict(truth="clean"),
            dict(note=""),
            dict(group=""),
        ]:
            doc = copy.deepcopy(self.doc)
            doc["labels"][1].update(change)
            variants.append(doc)
        doc = copy.deepcopy(self.doc)
        doc["source_sha256"] = "0" * 64
        variants.append(doc)
        doc = copy.deepcopy(self.doc)
        doc["labels"][1]["row"] = 1
        variants.append(doc)
        doc = copy.deepcopy(self.doc)
        doc["provenance"]["method"] = ""
        variants.append(doc)
        for doc in variants:
            with self.subTest(doc=doc):
                with self.assertRaises(ValueError):
                    self.labels(doc)
                self.assertIs(self.ws.labels, original)
                self.assertEqual(self.call("evaluation"), before)
        self.path.write_text('{"schema":"x","schema":"x"}')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.call("labels_load", path=str(self.path))
        self.path.write_bytes(b" " * (evaluation.MAX_LABEL_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            self.call("labels_load", path=str(self.path))

    def test_settings_change_invalidates_report_not_labels(self):
        self.labels()
        first = self.call("evaluation")
        revision = self.ws.revision
        self.call("configure", config=dict(self.ws.config, threshold=100), rules_text="[]")
        with self.assertRaisesRegex(ValueError, "Analyze"):
            self.call("evaluation")
        self.call("analyze")
        second = self.call("evaluation")
        self.assertNotEqual(second["settings_sha256"], first["settings_sha256"])
        self.assertEqual(second["summary"]["counts"]["False positive"], 0)
        self.assertEqual(second["summary"]["counts"]["Missed"], 3)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.ws.dispatch("evaluation", dict(revision=revision))

    def test_export_exact_bound_report_exclusive_and_case_reopen(self):
        self.labels()
        self.call("evaluation")
        saved = self.root / "evaluation.json"
        self.call("evaluation_save", path=str(saved))
        exported = json.loads(saved.read_text(encoding="utf-8"))
        self.assertEqual(exported, self.ws.evaluation_cache)
        self.assertEqual(exported["labels"]["sha256"], engine.sha(self.path.read_bytes()))
        self.assertEqual(
            exported["result_sha256"], engine.sha(engine.canonical(self.ws.result).encode())
        )
        with self.assertRaises(FileExistsError):
            self.call("evaluation_save", path=str(saved))
        case = self.root / "saved.case.json"
        self.call("save", path=str(case))
        self.ws.dispatch("open", dict(path=str(case)))
        self.assertIsNone(self.ws.labels)
        self.labels()
        self.assertEqual(self.call("evaluation")["summary"], exported["summary"])
        self.ws.dispatch("import", dict(role="current", path=str(self.source)))
        self.assertIsNone(self.ws.labels)

    def test_blank_template_no_invented_truth_or_zero_denominator(self):
        path = self.root / "blank.json"
        self.call("labels_template", path=str(path))
        doc = json.loads(path.read_text())
        self.assertTrue(all(item["truth"] is None for item in doc["labels"]))
        self.assertFalse(doc["provenance"]["independent_of_detector"])
        with self.assertRaises(FileExistsError):
            self.call("labels_template", path=str(path))
        doc["provenance"] = self.doc["provenance"]
        self.labels(doc)
        report = self.call("evaluation")
        self.assertEqual(report["summary"]["counts"]["Unlabeled"], 7)
        self.assertTrue(all(r["value"] is None for r in report["summary"]["rates"].values()))

    def test_reference_overlap_and_declared_independence_are_not_certification(self):
        self.labels()
        self.assertEqual(
            self.call("evaluation")["overlap"], dict(exact_records=0, groups={"Session": 0})
        )
        self.ws.reference = self.ws.current
        with self.assertRaisesRegex(ValueError, "separate"):
            evaluation.evaluate(*self.ws.case(), self.ws.labels)
        ref = self.root / "overlap.json"
        ref.write_text(json.dumps([self.ws.current.rows[3]] * 5))
        self.ws.dispatch("import", dict(role="reference", path=str(ref)))
        self.call("analyze")
        report = self.call("evaluation")
        self.assertEqual(report["overlap"]["exact_records"], 1)
        self.assertEqual(report["overlap"]["groups"]["Session"], 1)
        self.assertTrue(any("share mapped identities" in w for w in report["warnings"]))
        self.doc["provenance"].update(purpose="holdout", independent_of_detector=True)
        self.labels()
        self.assertIn("not verified", self.call("evaluation")["warnings"][0])

    def test_filter_paging_and_metadata_are_bounded(self):
        source = engine.parse_bytes(
            json.dumps([dict(x=i) for i in range(205)]).encode(), "many.json"
        )
        self.ws.current = source
        self.ws.config = dict(
            features=[],
            session=None,
            event_id=None,
            time=None,
            time_format="milliseconds",
            threshold=6,
            rules=[dict(name="High", field="x", op="gt", value=150)],
        )
        self.ws.invalidate()
        self.call("analyze")
        doc = evaluation.template(source)
        doc["provenance"] = self.doc["provenance"]
        for item in doc["labels"]:
            item.update(truth="legitimate", group="boundary", note="synthetic")
        self.labels(doc)
        page = self.call("evaluation", page=1)
        self.assertEqual(len(page["rows"]), 100)
        self.assertEqual(page["rows"][0]["row"], 101)
        self.assertNotIn("records", page)
        with self.assertRaises(ValueError):
            self.call("evaluation", outcome="unknown")
        for i, item in enumerate(doc["labels"]):
            item["group"] = str(i)
        with self.assertRaisesRegex(ValueError, "100 label groups"):
            self.labels(doc)

    def test_failed_export_removes_only_its_own_partial_file(self):
        path = self.root / "partial.json"
        original = Path.open

        class FailingStream:
            def __enter__(inner):
                inner.file = original(path, "xb")
                return inner

            def write(inner, raw):
                inner.file.write(raw[:4])
                raise OSError("disk full")

            def __exit__(inner, *args):
                inner.file.close()

        with patch.object(Path, "open", return_value=FailingStream()):
            with self.assertRaisesRegex(OSError, "disk full"):
                evaluation.write_new(path, {"data": 1})
        self.assertFalse(path.exists())
        path.write_text("original")
        with self.assertRaises(FileExistsError):
            evaluation.write_new(path, {"data": 1})
        self.assertEqual(path.read_text(), "original")

    def test_legitimate_edge_cases_remain_visible_and_independently_grouped(self):
        # Test truth is deliberate fixture input, never inferred from the result.
        rows = [dict(reading=x) for x in [10, 18.8956, 18.89559, 80, 11, None]]
        self.ws.current = engine.parse_bytes(json.dumps(rows).encode(), "edges.json")
        self.ws.config = dict(self.ws.config, event_id=None, session=None)
        self.ws.invalidate()
        self.call("analyze")
        doc = evaluation.template(self.ws.current)
        doc["provenance"] = self.doc["provenance"]
        groups = [
            "routine",
            "exact threshold",
            "below threshold",
            "legitimate update",
            "unusual user",
            "collection failure",
        ]
        for label, group in zip(doc["labels"], groups):
            label.update(
                truth="legitimate", group=group, note="Known legitimate synthetic condition"
            )
        self.labels(doc)
        report = self.call("evaluation")
        self.assertEqual(
            [r["outcome"] for r in report["rows"]],
            ["Clear", "False positive", "Clear", "False positive", "Clear", "Unresolved"],
        )
        self.assertEqual(report["summary"]["rates"]["false_positive"]["denominator"], 6)
        self.assertEqual(len(report["groups"]), 6)
        self.assertIsNone(report["summary"]["rates"]["recall"]["value"])


if __name__ == "__main__":
    unittest.main()

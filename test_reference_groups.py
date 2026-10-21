import copy
import json
from pathlib import Path
import tempfile
import unittest

import engine
import comparison
import mapping_checks
import workflow
from desktop_worker import Workspace


def dataset(rows, name="source.json"):
    return engine.parse_bytes(json.dumps(rows).encode(), name)


class ReferenceGroupTests(unittest.TestCase):
    def setUp(self):
        self.ref = dataset(
            [dict(kind="a", value=10 + i % 2) for i in range(80)]
            + [dict(kind="b", value=100 + i % 5) for i in range(20)],
            "reference.json",
        )
        self.source = dataset(
            [
                dict(kind="b", value=102),
                dict(kind="b", value=1000),
                dict(kind="new", value=10),
                dict(value=10),
            ]
        )
        self.base = dict(
            features=["value"],
            event_id=None,
            session=None,
            time=None,
            time_format="milliseconds",
            threshold=6,
            rules=[],
        )
        self.config = dict(self.base, reference_by=["kind"])

    def test_group_reduces_legitimate_deviation_and_retains_unexpected_change(self):
        old = engine.analyze(self.source, self.ref, self.base)
        new = engine.analyze(self.source, self.ref, self.config)
        self.assertEqual(old["records"][0]["status"], "Review")
        self.assertEqual(
            [r["status"] for r in new["records"]], ["No finding", "Review", "Unknown", "Unknown"]
        )
        self.assertEqual(new["records"][0]["reference_group"]["reference_rows"], 20)
        self.assertEqual(engine.profile_for_record(new, new["records"][0], "value")["center"], 102)
        self.assertTrue(all(new["records"][i]["gaps"] for i in (2, 3)))

    def test_profiles_do_not_depend_on_current_values_or_labels(self):
        first = engine.analyze(self.source, self.ref, self.config)
        changed = dataset([dict(kind="b", value=-999999, truth="legitimate")])
        second = engine.analyze(changed, self.ref, self.config)
        self.assertEqual(first["profiles"], second["profiles"])
        self.assertEqual(first["group_profiles"], second["group_profiles"])
        self.assertEqual(second["records"][0]["status"], "Review")

    def test_missing_and_undersized_groups_link_to_preflight_and_cannot_be_clear(self):
        ref = dataset(
            [dict(kind="a", value=10)] * 20 + [dict(kind="b", value=10)] * 19, "reference.json"
        )
        source = dataset(
            [dict(kind="a", value=10), dict(kind="b", value=10), dict(kind=None, value=10)]
        )
        result = engine.analyze(source, ref, self.config)
        self.assertEqual(
            [r["status"] for r in result["records"]], ["No finding", "Unknown", "Unknown"]
        )
        notes = mapping_checks.check(source, ref, self.config).groups["reference_by"]
        self.assertEqual(notes[0].rows, (2, 3))
        self.assertEqual(notes[0].fields, ("kind",))
        ref = dataset(
            [dict(kind="a", value=None)] * 3 + [dict(kind="a", value=10)] * 19, "reference.json"
        )
        result = engine.analyze(source, ref, self.config)
        self.assertEqual(result["records"][0]["reference_group"]["mode"], "global fallback")

    def test_invalid_mappings_and_cardinality_are_bounded(self):
        for by in (
            None,
            "kind",
            ["kind", "kind"],
            ["kind", "missing"],
            ["value"],
            ["kind"] * 3,
            [{}],
        ):
            with self.subTest(by=by), self.assertRaises(ValueError):
                engine.analyze(self.source, self.ref, dict(self.base, reference_by=by))
        ref = dataset([dict(kind=str(i), value=10) for i in range(129)], "many.json")
        with self.assertRaisesRegex(ValueError, "128"):
            engine.analyze(self.source, ref, self.config)
        self.assertTrue(mapping_checks.check(self.source, ref, self.config).blocked)

    def test_group_keys_preserve_types_and_two_field_combinations(self):
        self.assertNotEqual(
            engine.reference_key({"a": 1}, ["a"]), engine.reference_key({"a": "1"}, ["a"])
        )
        ref = dataset(
            [dict(kind="a", proto="tcp", value=10)] * 20
            + [dict(kind="a", proto="udp", value=100)] * 20,
            "ref.json",
        )
        source = dataset([dict(kind="a", proto="udp", value=100)])
        result = engine.analyze(source, ref, dict(self.base, reference_by=["kind", "proto"]))
        self.assertEqual(result["records"][0]["scores"]["value"], 0)
        self.assertEqual(result["records"][0]["reference_group"]["values"], ["a", "udp"])

    def test_default_results_and_old_saved_cases_are_unchanged(self):
        self.assertEqual(
            engine.analyze(self.source, self.ref, self.base),
            engine.analyze(self.source, self.ref, dict(self.base, reference_by=[])),
        )
        case = engine.open_case(Path(__file__).parent / "tests/fixtures/legacy.case.json")
        self.assertNotIn("group_profiles", case[3])

    def test_policy_case_roundtrip_and_inspector_comparison_use_selected_profile(self):
        ws = Workspace()
        ws.current = self.source
        ws.reference = self.ref
        ws.config = self.config
        ws.invalidate()
        ws.dispatch("analyze", dict(revision=ws.revision))
        evidence = ws.dispatch("evidence", dict(revision=ws.revision, row=1))
        self.assertEqual(evidence["reference_group"]["mode"], "matched")
        self.assertIn("102", evidence["groups"][0]["lines"][0]["text"])
        old = (self.source, self.ref, self.base, engine.analyze(self.source, self.ref, self.base))
        rows = {r.label: r for r in comparison.record_rows(ws.case(), old, 1)}
        self.assertEqual(rows["value · median"].current, "102")
        self.assertIn("matched", rows["Reference group"].current)
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).parent / "verification/temporary-test-files"
        ) as folder:
            path = Path(folder) / "case.json"
            engine.save_case(path, *ws.case())
            self.assertEqual(engine.open_case(path), ws.case())
            policy = Path(folder) / "policy.json"
            workflow.save_policy(policy, self.source, self.ref, self.config)
            self.assertEqual(workflow.load_policy(policy, self.source, self.ref), self.config)

    def test_worker_rejects_malformed_groups_and_keeps_rules_with_grouping(self):
        ws = Workspace()
        ws.current = self.source
        ws.reference = self.ref
        config = dict(self.config, rules=[dict(name="Huge", field="value", op="gt", value=500)])
        ws.dispatch(
            "configure", dict(revision=0, config=config, rules_text=json.dumps(config["rules"]))
        )
        before = copy.deepcopy(ws.config)
        with self.assertRaises(ValueError):
            ws.dispatch(
                "configure",
                dict(revision=ws.revision, config=dict(config, reference_by={}), rules_text="[]"),
            )
        self.assertEqual(before, ws.config)
        result = ws.dispatch("analyze", dict(revision=ws.revision))
        self.assertEqual(result["summary"]["Review"], 1)


if __name__ == "__main__":
    unittest.main()

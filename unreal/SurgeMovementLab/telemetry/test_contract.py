"""Synthetic contract tests. These are not Unreal capture/playtest evidence."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import derive


def capture(points, times=None, mode="walking"):
    times = times if times is not None else [i * .1 for i in range(len(points))]
    return ("\n".join(json.dumps(dict(schema="surge-movement-v1", session_id="a" * 32,
        seq=i, elapsed_s=t, x_cm=x, y_cm=0, z_cm=100, movement_mode=mode))
        for i, (x, t) in enumerate(zip(points, times))) + "\n").encode()


class ContractTests(unittest.TestCase):
    def test_walk_stop_redirect_and_acceleration_are_benign(self):
        self.assertTrue(all(r["excess_cm"] <= 0 for r in derive(capture([0, 20, 60, 120, 120, 60]))))

    def test_controlled_speed_change_creates_evidence(self):
        self.assertGreater(derive(capture([0, 120]))[0]["excess_cm"], 0)

    def test_hitch_and_unsupported_mode_are_unknown(self):
        self.assertIsNone(derive(capture([0, 600], [0, 1]))[0]["excess_cm"])
        self.assertIsNone(derive(capture([0, 120], mode="other"))[0]["excess_cm"])

    def test_labels_nonfinite_duplicate_time_and_gaps_are_rejected(self):
        raw = capture([0, 60])
        for bad in (raw.replace(b'"seq": 1', b'"seq": 2'),
                    capture([0, 60], [0, 0]), capture([0, float("nan")]),
                    raw.replace(b'"schema":', b'"label": true, "schema":'),
                    raw.replace(b'"seq": 0', b'"seq": 0, "seq": 0')):
            with self.assertRaises(ValueError):
                derive(bad)

    def test_existing_surge_engine_interprets_evidence_and_gaps(self):
        # Read-only compatibility check against the actual current engine.
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        import engine
        policy = json.loads(Path(__file__).with_name("surge-policy.json").read_text())
        rows = derive(capture([0, 60, 180, 780], [0, .1, .2, 1.2]))
        data = engine.parse_bytes(("\n".join(json.dumps(r) for r in rows)).encode(), "lab.jsonl")
        result = engine.analyze(data, None, policy)
        self.assertEqual([r["status"] for r in result["records"]], ["No finding", "Review", "Unknown"])


if __name__ == "__main__":
    unittest.main()

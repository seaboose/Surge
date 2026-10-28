"""Independent freeze checks with temporary synthetic files; no holdout reads."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / "benchmarks"))
import evaluate_refinement4 as protocol
from prepare_rt_iot2022 import sha


class ReviewBindingSecurityTests(unittest.TestCase):
    def test_changed_reviewed_source_blocks_freeze_before_snapshot(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / "verification") as folder:
            app = Path(folder)
            out = app / "out"
            out.mkdir()
            (app / "verification").mkdir()
            policy = dict(schema="surge-policy-v1", settings={"threshold": 2})
            policy_path = out / "candidate.policy.json"
            policy_path.write_text(json.dumps(policy))
            digest = sha(policy_path.read_bytes())
            (app / "reviewed.py").write_text("changed after review")
            (out / "development-selection.json").write_text(
                json.dumps(
                    dict(
                        policy_sha256=digest,
                        selected=policy["settings"],
                        reservation_sha256=protocol.PLAN_SHA,
                        addendum_sha256=protocol.ADDENDUM_SHA,
                        gates={name: True for name in protocol.DEVELOPMENT_GATES},
                        hashes={},
                    )
                )
            )
            (app / "verification/refinement4-security-review.json").write_text(
                json.dumps(
                    dict(
                        blocking_findings=[],
                        reviewed_sha256={
                            "benchmarks/rt-iot2022/refinement-4/candidate.policy.json": digest,
                            "reviewed.py": sha(b"reviewed original"),
                        },
                    )
                )
            )
            # Keep the standard policy key in the synthetic review without
            # creating or reading the real benchmark artifact.
            fake_policy = app / "benchmarks/rt-iot2022/refinement-4/candidate.policy.json"
            fake_policy.parent.mkdir(parents=True)
            fake_policy.write_bytes(policy_path.read_bytes())
            with (
                patch.object(protocol, "APP", app),
                patch.object(protocol, "OUT", out),
                patch.object(protocol, "verify_plan", return_value={}),
            ):
                with self.assertRaisesRegex(
                    ValueError, "Security-reviewed dependency changed: reviewed.py"
                ):
                    protocol.freeze()
            self.assertFalse((out / "candidate-source").exists())
            self.assertFalse((out / "freeze.json").exists())

    def test_blocking_review_cannot_be_bypassed_by_matching_policy(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / "verification") as folder:
            app = Path(folder)
            out = app / "out"
            out.mkdir()
            (app / "verification").mkdir()
            policy = dict(schema="surge-policy-v1", settings={"threshold": 2})
            (out / "candidate.policy.json").write_text(json.dumps(policy))
            digest = sha((out / "candidate.policy.json").read_bytes())
            (out / "development-selection.json").write_text(
                json.dumps(
                    dict(
                        policy_sha256=digest,
                        selected=policy["settings"],
                        reservation_sha256=protocol.PLAN_SHA,
                        addendum_sha256=protocol.ADDENDUM_SHA,
                        gates={name: True for name in protocol.DEVELOPMENT_GATES},
                        hashes={},
                    )
                )
            )
            (app / "verification/refinement4-security-review.json").write_text(
                json.dumps(
                    dict(
                        blocking_findings=["Synthetic unresolved issue"],
                        reviewed_sha256={
                            "benchmarks/rt-iot2022/refinement-4/candidate.policy.json": digest
                        },
                    )
                )
            )
            with (
                patch.object(protocol, "APP", app),
                patch.object(protocol, "OUT", out),
                patch.object(protocol, "verify_plan", return_value={}),
            ):
                with self.assertRaisesRegex(ValueError, "matching unblocked security review"):
                    protocol.freeze()
            self.assertFalse((out / "candidate-source").exists())


if __name__ == "__main__":
    unittest.main()

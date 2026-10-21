"""Reproduce the development-only selection; never read holdout inputs or labels.

The original selection was frozen before holdout opening. This script verifies
that decision from the recorded development search space, without changing it.
"""

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine, evaluation

ROOT = Path(__file__).resolve().parent / "rt-iot2022"
OUT = ROOT / "refinement-1"


def main():
    source = engine.load_dataset(OUT / "development.json")
    reference = engine.load_dataset(ROOT / "reference.json")
    baseline = json.loads((ROOT / "policy.json").read_text())["settings"]
    truth = [
        r["truth"] == "target"
        for r in evaluation.load(OUT / "development.labels.json", source)["document"]["labels"]
    ]
    original = engine.analyze(source, reference, baseline)
    original_flags = [r["status"] == "Review" for r in original["records"]]
    original_fp = sum(f and not t for f, t in zip(original_flags, truth))
    candidates = []
    for by in [["proto"], ["service"], ["proto", "service"]]:
        result = engine.analyze(source, reference, dict(baseline, reference_by=by))
        for count in range(1, 7):
            for fields in itertools.combinations(baseline["features"], count):
                scores = [max(r["scores"][f] for f in fields) for r in result["records"]]
                for threshold in [1, 2, 3, 4, 6, 8, 12]:
                    flags = [v >= threshold for v in scores]
                    fp = sum(f and not t for f, t in zip(flags, truth))
                    fn = sum(not f and t for f, t in zip(flags, truth))
                    lost = sum(
                        old and not f and t for old, f, t in zip(original_flags, flags, truth)
                    )
                    if fp < original_fp and lost == 0:
                        candidates.append(
                            dict(
                                reference_by=by,
                                features=list(fields),
                                threshold=threshold,
                                fp=fp,
                                fn=fn,
                                new_misses=lost,
                            )
                        )
    selected = min(
        candidates, key=lambda c: (c["fn"], c["fp"], len(c["features"]), len(c["reference_by"]))
    )
    frozen = json.loads((OUT / "candidate.policy.json").read_text())["settings"]
    assert all(selected[k] == frozen[k] for k in ("reference_by", "features", "threshold"))
    assert (selected["fp"], selected["fn"], selected["new_misses"]) == (222, 0, 0)
    audit = dict(
        search="3 grouping choices × 63 nonempty signal subsets × 7 thresholds; development only",
        selected=selected,
        acceptable_candidates=len(candidates),
        frozen_policy_verified=True,
    )
    (OUT / "development-selection-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()

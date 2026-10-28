"""One frozen-candidate holdout comparison; no optimization in this script."""

import json
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine, evaluation

ROOT = Path(__file__).resolve().parent / "rt-iot2022"
OUT = ROOT / "refinement-1"


def main():
    freeze = json.loads((OUT / "selection.json").read_text())
    assert engine.sha((OUT / "candidate.policy.json").read_bytes()) == freeze["candidate_sha256"]
    split = json.loads((OUT / "split.json").read_text())
    assert engine.sha((OUT / "holdout.json").read_bytes()) == split["holdout_sha256"]
    assert engine.sha((ROOT / "reference.json").read_bytes()) == split["reference_sha256"]
    with (OUT / "holdout-opened.json").open("x") as f:
        json.dump(
            dict(
                candidate_sha256=freeze["candidate_sha256"], holdout_sha256=split["holdout_sha256"]
            ),
            f,
        )
    source = engine.load_dataset(OUT / "holdout.json")
    ref = engine.load_dataset(ROOT / "reference.json")
    labels = evaluation.load(OUT / "holdout.labels.json", source)
    outcomes = {}
    for name, path in [
        ("baseline", ROOT / "policy.json"),
        ("candidate", OUT / "candidate.policy.json"),
    ]:
        config = json.loads(path.read_text())["settings"]
        result = engine.analyze(source, ref, config)
        report = evaluation.evaluate(source, ref, config, result, labels)
        evaluation.write_new(OUT / (name + ".evaluation.json"), report)
        engine.save_case(OUT / (name + ".case.json"), source, ref, config, result)
        outcomes[name] = report
    old, new = outcomes["baseline"], outcomes["candidate"]
    regressions = []
    recovered = []
    resolved = []
    introduced = []
    for before, after in zip(old["records"], new["records"]):
        if before["outcome"] == "Detected" and after["outcome"] == "Missed":
            regressions.append(after["row"])
        if before["outcome"] == "Missed" and after["outcome"] == "Detected":
            recovered.append(after["row"])
        if before["outcome"] == "False positive" and after["outcome"] != "False positive":
            resolved.append(after["row"])
        if (
            before["truth"] == "legitimate"
            and before["outcome"] != "False positive"
            and after["outcome"] == "False positive"
        ):
            introduced.append(after["row"])
    b, c = old["summary"]["counts"], new["summary"]["counts"]
    gate = c["False positive"] < b["False positive"] and c["Missed"] <= b["Missed"]
    summary = dict(
        accepted=gate,
        baseline=old["summary"],
        candidate=new["summary"],
        new_misses=regressions,
        recovered_targets=recovered,
        resolved_false_positives=resolved,
        new_false_positives=introduced,
        groups=dict(baseline=old["groups"], candidate=new["groups"]),
        limits="Fresh row/vector holdout from same public testbed; not session-independent, anti-cheat, or AI-attack validation. No guarantee of unchanged miss rates on future traffic.",
    )
    evaluation.write_new(OUT / "holdout-comparison.json", summary)
    print(
        json.dumps(
            dict(
                accepted=gate,
                baseline=old["summary"],
                candidate=new["summary"],
                new_misses=len(regressions),
                recovered=len(recovered),
                resolved_false_positives=len(resolved),
                new_false_positives=len(introduced),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

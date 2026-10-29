"""Select/freeze a development-only calibration; no holdout input is opened.

Run after the evaluator commits a fresh holdout reservation. Retained prototype
searches are development evidence only and do not change engine semantics.
"""

import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine, evaluation

APP = Path(__file__).resolve().parents[1]
ROOT = APP / "benchmarks/rt-iot2022"
OUT = ROOT / "refinement-3"
DEV = ROOT / "refinement-3-development"


def main():
    if not (OUT / "plan.json").is_file():
        raise ValueError("Evaluator must commit a fresh holdout reservation first.")
    if (OUT / "candidate.policy.json").exists() or (OUT / "development-selection.json").exists():
        raise ValueError("Candidate already frozen; never overwrite or retune it.")
    search = json.loads((DEV / "threshold-probe.json").read_text())
    candidates = [r for r in search["candidates"] if r["mode"] == "common"]
    # Prioritize the requested legitimate subgroup, then total noise, and retain
    # an already-supported shared threshold rather than expanding the engine.
    best = min(
        candidates,
        key=lambda r: (
            r["groups"]["Thing_Speak"],
            r["fp"],
            len(r["features"]),
            len(r["reference_by"]),
            r["threshold"],
        ),
    )
    source = engine.load_dataset(ROOT / "refinement-1/development.json")
    reference = engine.load_dataset(ROOT / "reference.json")
    labels = evaluation.load(ROOT / "refinement-1/development.labels.json", source)
    document = labels["document"]
    policy = json.loads((APP / "policies/rt-iot2022-reviewed.policy.json").read_text())
    old_config = dict(policy["settings"])
    policy["settings"].update(
        features=best["features"], reference_by=best["reference_by"], threshold=best["threshold"]
    )
    new_config = policy["settings"]
    old = engine.analyze(source, reference, old_config)
    new = engine.analyze(source, reference, new_config)
    old_report = evaluation.evaluate(source, reference, old_config, old, labels)
    new_report = evaluation.evaluate(source, reference, new_config, new, labels)
    changes = {k: [] for k in ["new_misses", "resolved_false_positives", "new_false_positives"]}
    for a, b in zip(old_report["records"], new_report["records"], strict=True):
        if a["outcome"] == "Detected" and b["outcome"] == "Missed":
            changes["new_misses"].append(b["row"])
        if a["outcome"] == "False positive" and b["outcome"] == "Clear":
            changes["resolved_false_positives"].append(b["row"])
        if (
            a["truth"] == "legitimate"
            and a["outcome"] != "False positive"
            and b["outcome"] == "False positive"
        ):
            changes["new_false_positives"].append(b["row"])
    b, c = old_report["summary"]["counts"], new_report["summary"]["counts"]
    before = {g["group"]: g for g in old_report["groups"]}
    after = {g["group"]: g for g in new_report["groups"]}
    legit = [g for g in before if before[g]["legitimate"]]
    gates = dict(
        total_false_positives_lower=c["False positive"] < b["False positive"],
        targeted_subgroup_false_positives_lower=after["Thing_Speak"]["counts"]["False positive"]
        < before["Thing_Speak"]["counts"]["False positive"],
        misses_not_higher=c["Missed"] <= b["Missed"],
        no_targets_lost=not changes["new_misses"],
        legitimate_unknown_not_higher=c["Unresolved"] <= b["Unresolved"],
        no_legitimate_subgroup_regression=all(
            after[g]["counts"]["False positive"] <= before[g]["counts"]["False positive"]
            and after[g]["counts"]["Unresolved"] <= before[g]["counts"]["Unresolved"]
            for g in legit
        ),
    )
    if not all(gates.values()):
        raise ValueError("Production development gate failed; do not freeze.")
    paths = [
        APP / "engine.py",
        APP / "evaluation.py",
        APP / "policies/rt-iot2022-reviewed.policy.json",
        ROOT / "reference.json",
        ROOT / "refinement-1/development.json",
        ROOT / "refinement-1/development.labels.json",
        DEV / "threshold-probe.json",
        Path(__file__),
        Path(__file__).with_name("probe_refinement3_development.py"),
    ]
    report = dict(
        schema="surge-development-selection-v1",
        data_access="Only original reference and refinement-1 development inputs/labels; no holdout data, labels, cases or outcomes opened.",
        search="3 group choices × 63 feature subsets × 20 shared thresholds; plus development-only prototype per-signal grids on 2/3 signals. Existing common-threshold candidates selected.",
        thresholds=[
            1,
            1.1,
            1.2,
            1.3,
            1.4,
            1.5,
            1.6,
            1.7,
            1.8,
            1.9,
            2,
            2.5,
            3,
            4,
            6,
            8,
            12,
            20,
            40,
            100,
        ],
        selection="Among existing shared-threshold candidates satisfying zero development misses, lower total FP, lower Thing_Speak FP and no legitimate subgroup FP rise: minimize Thing_Speak FP, total FP, feature count, group count, then threshold.",
        rationale="A modest shared threshold increase removes marginal deviations in legitimate Thing_Speak records while preserving every development target. No publisher labels, class exceptions or dataset-specific logic enter detection.",
        prototype_tradeoff="A new per-signal prototype produced171totalFP but111Thing_SpeakFP; existing shared threshold gives175totalFP and104Thing_SpeakFP without new engine complexity. Prototype not integrated.",
        baseline=old_report["summary"],
        candidate=new_report["summary"],
        groups=dict(baseline=old_report["groups"], candidate=new_report["groups"]),
        transitions={k: len(v) for k, v in changes.items()},
        transition_rows=changes,
        gates=gates,
        selected=new_config,
        minimum_development_target_score=min(
            r["max_deviation"]
            for r, l in zip(new["records"], document["labels"])
            if l["truth"] == "target"
        ),
        limitations=[
            "Repeated tuning reuses development data and can overfit; only one fresh frozen holdout may assess this candidate.",
            "Raising a threshold can lose previously detected targets on unseen data; reject if any are lost on holdout.",
            "Publisher IoT labels do not establish game anti-cheat or AI-attack effectiveness.",
            "Same numeric signals and rule support as previous policy; sensitivity is reduced from1.5to1.8, not universal improvement.",
        ],
        hashes={p.relative_to(APP).as_posix(): engine.sha(p.read_bytes()) for p in paths},
        reservation_sha256=engine.sha((OUT / "plan.json").read_bytes()),
    )
    with (OUT / "candidate.policy.json").open("x", encoding="utf-8") as f:
        json.dump(policy, f, indent=2)
        f.write("\n")
    report["policy_sha256"] = engine.sha((OUT / "candidate.policy.json").read_bytes())
    with (OUT / "development-selection.json").open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(
        json.dumps(
            dict(
                baseline=b,
                candidate=c,
                gates=gates,
                transitions=report["transitions"],
                policy_sha256=report["policy_sha256"],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

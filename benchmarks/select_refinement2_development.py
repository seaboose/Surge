"""Select/freeze a policy using development data only; never open holdout data.

The first refinement's approved grouped policy is the paired baseline. Alternative
profile probes are retained as research evidence, not integrated into detection.
"""

import json, runpy, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine, evaluation

ROOT = Path(__file__).resolve().parent / "rt-iot2022"
OUT = ROOT / "refinement-2"
DEV = ROOT / "refinement-2-development"


def counts(result, labels):
    flags = [r["status"] == "Review" for r in result["records"]]
    truth = [r["truth"] == "target" for r in labels]
    return dict(
        fp=sum(f and not t for f, t in zip(flags, truth)),
        fn=sum(not f and t for f, t in zip(flags, truth)),
        legitimate=sum(not t for t in truth),
        targets=sum(truth),
        legitimate_unknown=sum(
            r["status"] == "Unknown" and not t for r, t in zip(result["records"], truth)
        ),
    )


def main():
    runpy.run_path(str(Path(__file__).with_name("probe_profiles_development.py")))
    candidates = json.loads((DEV / "profile-probe.json").read_text())
    best = min(candidates, key=lambda c: (c["fp"], len(c["features"]), c["method"] != "raw"))
    if best["method"] != "raw":
        raise ValueError(
            "An unsupported experimental method won; do not export it as an existing-engine policy."
        )
    source = engine.load_dataset(ROOT / "refinement-1/development.json")
    reference = engine.load_dataset(ROOT / "reference.json")
    label_document = evaluation.load(ROOT / "refinement-1/development.labels.json", source)[
        "document"
    ]
    labels = label_document["labels"]
    policy = json.loads((ROOT / "refinement-1/candidate.policy.json").read_text())
    baseline = engine.analyze(source, reference, policy["settings"])
    policy["settings"].update(features=best["features"], threshold=best["threshold"])
    candidate = engine.analyze(source, reference, policy["settings"])
    before, after = counts(baseline, labels), counts(candidate, labels)
    transitions = dict(new_misses=0, new_false_positives=0, resolved_false_positives=0)
    for old, new, label in zip(baseline["records"], candidate["records"], labels):
        was, now = old["status"] == "Review", new["status"] == "Review"
        if label["truth"] == "target":
            transitions["new_misses"] += was and not now
        else:
            transitions["new_false_positives"] += not was and now
            transitions["resolved_false_positives"] += was and not now
    assert (
        after["fp"] < before["fp"]
        and after["fn"] <= before["fn"]
        and transitions["new_misses"] == 0
    )
    assert after["legitimate_unknown"] <= before["legitimate_unknown"]
    groups = {}
    for group in sorted({r["group"] for r in labels}):
        indices = [i for i, l in enumerate(labels) if l["group"] == group]
        groups[group] = {
            name: counts(
                dict(records=[r["records"][i] for i in indices]), [labels[i] for i in indices]
            )
            for name, r in [("baseline", baseline), ("candidate", candidate)]
        }
    paths = [
        ROOT / "refinement-1/development.json",
        ROOT / "refinement-1/development.labels.json",
        ROOT / "reference.json",
        ROOT / "refinement-1/candidate.policy.json",
        Path(engine.__file__),
        Path(__file__),
        Path(__file__).with_name("probe_profiles_development.py"),
        Path(__file__).with_name("probe_refinement2_development.py"),
        DEV / "profile-probe.json",
        DEV / "threshold-probe.json",
    ]
    report = dict(
        schema="surge-development-selection-v1",
        data_access="Development inputs and labels plus original reference only; no holdout inputs or labels opened.",
        selection="Minimize development false positives subject to zero missed targets; prefer fewer signals and existing raw method on ties.",
        search="First: 11 thresholds (2 to 100) independently across baseline three signals. Then: six profile methods × 63 nonempty subsets of six existing numeric signals × six global thresholds (1, 1.5, 2, 3, 4, 6).",
        rationale="Removing the noisy packet-rate signal reduces legitimate alerts. A lower common threshold preserves development target sensitivity in the two remaining signals. Existing engine and evidence semantics are unchanged.",
        baseline=before,
        candidate=after,
        transitions=transitions,
        groups=groups,
        selected=policy["settings"],
        limitations=[
            "Development selection is optimistic and must pass a fresh frozen holdout.",
            "Labels are publisher IoT categories; no anti-cheat effectiveness claim.",
            "Alternative profile methods were exploratory development-only prototypes, not production changes.",
        ],
        hashes={
            (
                str(p.relative_to(ROOT.parent.parent))
                if p.is_relative_to(ROOT.parent.parent)
                else str(p)
            ): engine.sha(p.read_bytes())
            for p in paths
        },
    )
    OUT.mkdir(exist_ok=True)
    # Exclusive creation prevents accidental post-evaluation overwrite of a candidate.
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
                baseline=before,
                candidate=after,
                transitions=transitions,
                policy_sha256=report["policy_sha256"],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

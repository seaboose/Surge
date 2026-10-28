"""Record development-only rejection; never create a failing candidate or open a holdout."""

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
import evaluation

APP = Path(__file__).resolve().parents[1]
ROOT = APP / "benchmarks/rt-iot2022"
OUT = ROOT / "refinement-4"
DEV = ROOT / "refinement-4-development"
FEATURES = [
    "flow_duration",
    "fwd_pkts_tot",
    "bwd_pkts_tot",
    "flow_pkts_per_sec",
    "fwd_pkts_payload.avg",
    "bwd_pkts_payload.avg",
]
GROUPINGS = [
    [],
    ["proto"],
    ["service"],
    ["proto", "service"],
    ["id.resp_p"],
    ["proto", "id.resp_p"],
    ["service", "id.resp_p"],
]


def main():
    if (OUT / "development-outcome.json").exists():
        raise ValueError("Development outcome already recorded; do not overwrite.")
    if (OUT / "candidate.policy.json").exists() or (OUT / "holdout-opened.json").exists():
        raise ValueError("This rejection path requires no frozen candidate or opened holdout.")
    common = json.loads((DEV / "threshold-probe.json").read_text())
    hybrid = json.loads((DEV / "hybrid-probe.json").read_text())
    interval = json.loads((DEV / "interval-probe.json").read_text())
    if common["candidates"] or hybrid or interval["accepted"]:
        raise ValueError(
            "A prototype needs separate production validation; cannot claim no candidate."
        )
    source = engine.load_dataset(ROOT / "refinement-1/development.json")
    reference = engine.load_dataset(ROOT / "reference.json")
    labels = evaluation.load(ROOT / "refinement-1/development.labels.json", source)
    truth = labels["document"]["labels"]
    config = json.loads((APP / "policies/rt-iot2022-refinement-3.policy.json").read_text())[
        "settings"
    ]
    result = engine.analyze(source, reference, config)
    report = evaluation.evaluate(source, reference, config, result, labels)
    targets = [i for i, row in enumerate(truth) if row["truth"] == "target"]
    group_rows = {
        group: [i for i, row in enumerate(truth) if row["group"] == group]
        for group in ("Wipro_bulb", "Thing_Speak", "MQTT_Publish")
    }
    limits = {
        g["group"]: g["counts"]["False positive"] for g in report["groups"] if g["legitimate"]
    }
    exact = []
    for grouping in GROUPINGS:
        numeric = engine.analyze(
            source, reference, dict(config, features=FEATURES, reference_by=grouping)
        )
        for count in range(1, 7):
            for features in itertools.combinations(FEATURES, count):
                scores = [
                    max(row["scores"][field] for field in features) for row in numeric["records"]
                ]
                threshold = min(100, min(scores[i] for i in targets))
                if threshold < 1:
                    continue
                groups = {
                    g: sum(scores[i] >= threshold for i in rows) for g, rows in group_rows.items()
                }
                if all(groups[g] <= limits[g] for g in groups):
                    exact.append(
                        dict(
                            features=features,
                            reference_by=grouping,
                            threshold=threshold,
                            groups=groups,
                        )
                    )
    exact.sort(key=lambda row: (row["groups"]["Wipro_bulb"], sum(row["groups"].values())))
    if any(row["groups"]["Wipro_bulb"] < limits["Wipro_bulb"] for row in exact):
        raise ValueError("Exact threshold candidate needs validation instead of rejection.")
    directional = []
    for directions in [("both", "upper"), ("both", "lower"), ("lower", "both"), ("upper", "both")]:
        groups = dict.fromkeys(group_rows, 0)
        unknown = dict.fromkeys(group_rows, 0)
        missed = []
        for i, (row, label, record) in enumerate(
            zip(source.rows, truth, result["records"], strict=True)
        ):
            flagged = False
            for field, direction in zip(config["features"], directions, strict=True):
                profile = engine.profile_for_record(result, record, field)
                score = (float(row[field]) - profile["center"]) / profile["scale"]
                directional_score = (
                    abs(score) if direction == "both" else score if direction == "upper" else -score
                )
                flagged |= directional_score >= config["threshold"]
            if label["truth"] == "target" and not flagged:
                missed.append(i + 1)
            elif label["truth"] == "legitimate":
                groups[label["group"]] += int(flagged)
                unknown[label["group"]] += int(not flagged and bool(record["gaps"]))
        directional.append(
            dict(
                directions=dict(zip(config["features"], directions)),
                groups=groups,
                missed=len(missed),
                missed_rows=missed,
                legitimate_unknown=unknown,
            )
        )
    wipro = []
    for row, label, record in zip(source.rows, truth, result["records"], strict=True):
        if label["group"] == "Wipro_bulb":
            wipro.append(
                dict(
                    row=record["row"],
                    source_record=row["source_record"],
                    source_values=row,
                    status=record["status"],
                    scores=record["scores"],
                    triggers=record["evidence"],
                    gaps=record["gaps"],
                    reference_group=record["reference_group"],
                )
            )
    long_rows = [
        record
        for row, label, record in zip(source.rows, truth, result["records"], strict=True)
        if label["truth"] == "legitimate" and float(row["flow_duration"]) > 62.049075
    ]
    paths = [
        APP / "engine.py",
        APP / "evaluation.py",
        APP / "policies/rt-iot2022-refinement-3.policy.json",
        ROOT / "reference.json",
        ROOT / "refinement-1/development.json",
        ROOT / "refinement-1/development.labels.json",
        OUT / "plan.json",
        OUT / "protocol-addendum.json",
        Path(__file__),
        *sorted(DEV.glob("*.json")),
        *sorted((APP / "benchmarks").glob("probe_refinement4*.py")),
    ]
    outcome = dict(
        schema="surge-development-outcome-v1",
        accepted=False,
        candidate_created=False,
        decision="Retain the round3 policy. No tested candidate met the development acceptance constraints.",
        data_access="Only original reference and refinement1 development inputs/labels plus reservation metadata. No holdout rows, labels, cases, results or raw archive opened.",
        baseline=report["summary"],
        baseline_groups=report["groups"],
        selected=config,
        baseline_long_duration=dict(
            records=len(long_rows),
            false_positives=sum(x["status"] == "Review" for x in long_rows),
            unresolved=sum(x["status"] == "Unknown" for x in long_rows),
            cutoff=62.049075,
        ),
        wipro=wipro,
        diagnosis=[
            "Five IRC Wipro development rows use a global fallback because their reference group has only seven rows, below the generic minimum20.",
            "Four DNS Wipro rows have payload31 against reference median36 and zero MAD; the existing explicit relative tolerance is narrow.",
            "Five SSL Wipro rows differ from their grouped duration/payload profiles; one additional TCP/no-service row has an undersupported reference group.",
            "Clearing a fallback finding can create Unknown, which is unresolved evidence and must not be counted as a false-positive improvement.",
        ],
        searches=dict(
            shared_and_per_signal="Seven group choices,63feature subsets and20 shared thresholds; plus20-threshold per-signal grids for2–3signals. No score-mask-feasible candidate; prototype does not replace production validation.",
            exact_shared=dict(
                method="For each of seven groupings and63feature subsets, choose min(100, minimum target maximum score): highest shared threshold that preserves all development targets; then check subgroup FP. This bounds common-threshold feasibility for these inputs.",
                best=exact[:3],
            ),
            hybrid="Four groupings,1–3signals,16shared thresholds, up to3 greedily selected scalar <=/>= rules across six numeric fields. Rule candidates respect each subgroup FP budget alone; unions additionally checked. Non-exhaustive greedy search, no passing candidate.",
            interval=dict(
                method=interval["description"],
                accepted=0,
                nearest_rejected=interval["nearest_rejected"][:3],
            ),
            directional=dict(
                method="Same two grouped signals and threshold1.8; replace one two-sided deviation with upper/lower signed tail, retaining gaps.",
                results=directional,
            ),
        ),
        runtime_changed=False,
        holdout_used=False,
        limitations=[
            "Bounded searches do not prove that no effective detector is possible.",
            "Fifteen Wipro development rows provide weak coverage; repeatedly reused development data can overfit.",
            "Port grouping was explored as untrusted reference context only; no identity/class allowlist or label-based runtime branch exists.",
            "Prototype metrics do not establish production feature support or independent-capture/game/AI effectiveness.",
        ],
        next_step="Gather independently labeled representative reference and development data, with enough supported legitimate modes, before changing detector semantics or spending the reserved holdout.",
        hashes={path.relative_to(APP).as_posix(): engine.sha(path.read_bytes()) for path in paths},
    )
    with (OUT / "development-outcome.json").open("x", encoding="utf-8") as handle:
        json.dump(outcome, handle, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            dict(
                accepted=False,
                baseline=report["summary"]["counts"],
                wipro_rows=len(wipro),
                best_exact=exact[:1],
                nearest_interval=interval["nearest_rejected"][:1],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

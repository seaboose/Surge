"""Development-only bounded policy search; never open benchmark holdouts."""

import itertools, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine

ROOT = Path(__file__).resolve().parent / "rt-iot2022"
OUT = ROOT / "refinement-4-development"
OUT.mkdir(exist_ok=True)
source = engine.load_dataset(ROOT / "refinement-1/development.json")
reference = engine.load_dataset(ROOT / "reference.json")
labels = json.loads((ROOT / "refinement-1/development.labels.json").read_text())["labels"]
base = json.loads(
    (ROOT.parent.parent / "policies/rt-iot2022-refinement-3.policy.json").read_text()
)["settings"]
features = [
    "flow_duration",
    "fwd_pkts_tot",
    "bwd_pkts_tot",
    "flow_pkts_per_sec",
    "fwd_pkts_payload.avg",
    "bwd_pkts_payload.avg",
]
truth = sum(1 << i for i, l in enumerate(labels) if l["truth"] == "target")
groups = {
    g: sum(1 << i for i, l in enumerate(labels) if l["group"] == g)
    for g in sorted({l["group"] for l in labels if l["truth"] == "legitimate"})
}
legit = sum(groups.values())
original = engine.analyze(source, reference, base)
original_mask = sum(1 << i for i, r in enumerate(original["records"]) if r["status"] == "Review")
limits = {g: (m & original_mask).bit_count() for g, m in groups.items()}
thresholds = [1, 1.25, 1.5, 1.75, 1.8, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 40, 60, 100]
results = []
for by in [
    [],
    ["proto"],
    ["service"],
    ["proto", "service"],
    ["id.resp_p"],
    ["proto", "id.resp_p"],
    ["service", "id.resp_p"],
]:
    result = engine.analyze(source, reference, dict(base, features=features, reference_by=by))
    scores = {f: [r["scores"].get(f) for r in result["records"]] for f in features}
    masks = {
        (f, t): sum(1 << i for i, s in enumerate(scores[f]) if s is not None and s >= t)
        for f in features
        for t in thresholds
    }
    # First existing common threshold and all feature subsets.
    for count in range(1, 7):
        for fields in itertools.combinations(features, count):
            for t in thresholds:
                mask = 0
                for f in fields:
                    mask |= masks[f, t]
                if truth & ~mask:
                    continue
                fp = (mask & legit).bit_count()
                gfp = {g: (mask & m).bit_count() for g, m in groups.items()}
                if (
                    fp < 175
                    and gfp["Wipro_bulb"] < limits["Wipro_bulb"]
                    and all(gfp[g] <= limits[g] for g in groups)
                ):
                    results.append(
                        dict(
                            mode="common",
                            reference_by=by,
                            features=fields,
                            threshold=t,
                            fp=fp,
                            groups=gfp,
                        )
                    )
    # Prototype per-signal thresholds over two/three feature subsets.
    for count in (2, 3):
        for fields in itertools.combinations(features, count):
            for ts in itertools.product(thresholds, repeat=count):
                mask = 0
                for f, t in zip(fields, ts):
                    mask |= masks[f, t]
                if truth & ~mask:
                    continue
                fp = (mask & legit).bit_count()
                gfp = {g: (mask & m).bit_count() for g, m in groups.items()}
                if (
                    fp < 175
                    and gfp["Wipro_bulb"] < limits["Wipro_bulb"]
                    and all(gfp[g] <= limits[g] for g in groups)
                ):
                    results.append(
                        dict(
                            mode="per_signal",
                            reference_by=by,
                            features=fields,
                            thresholds=ts,
                            fp=fp,
                            groups=gfp,
                        )
                    )
results.sort(
    key=lambda r: (r["groups"]["Wipro_bulb"], r["fp"], len(r["features"]), r["mode"] != "common")
)
(OUT / "threshold-probe.json").write_text(
    json.dumps(dict(baseline_groups=limits, candidates=results), indent=2) + "\n"
)
print(json.dumps(dict(baseline_groups=limits, top=results[:10], candidates=len(results)), indent=2))

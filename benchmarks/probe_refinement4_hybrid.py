import sys, json, itertools
from pathlib import Path

sys.path.insert(0, ".")
import engine

r = Path("benchmarks/rt-iot2022")
s = engine.load_dataset(r / "refinement-1/development.json")
ref = engine.load_dataset(r / "reference.json")
ls = json.loads((r / "refinement-1/development.labels.json").read_text())["labels"]
c = json.loads(Path("policies/rt-iot2022-refinement-3.policy.json").read_text())["settings"]
fs = [
    "flow_duration",
    "fwd_pkts_tot",
    "bwd_pkts_tot",
    "flow_pkts_per_sec",
    "fwd_pkts_payload.avg",
    "bwd_pkts_payload.avg",
]
masks = {
    g: sum(1 << i for i, l in enumerate(ls) if l["group"] == g)
    for g in ["Wipro_bulb", "Thing_Speak", "MQTT_Publish"]
}
masks["long"] = sum(
    1 << i
    for i, l in enumerate(ls)
    if l["truth"] == "legitimate" and float(s.rows[i]["flow_duration"]) > 62.049075
)
target = sum(1 << i for i, l in enumerate(ls) if l["truth"] == "target")
legit = masks["Wipro_bulb"] | masks["Thing_Speak"] | masks["MQTT_Publish"]
orig = engine.analyze(s, ref, c)
old = sum(1 << i for i, x in enumerate(orig["records"]) if x["status"] == "Review")
limits = {g: (old & m).bit_count() for g, m in masks.items()}
limits["Wipro_bulb"] -= 1
raw = []
for f in fs:
    vals = sorted((float(x[f]), i) for i, x in enumerate(s.rows))
    for op, vs in [("le", vals), ("ge", list(reversed(vals)))]:
        mask = 0
        for v, part in itertools.groupby(vs, key=lambda x: x[0]):
            for _, i in part:
                mask |= 1 << i
            if any((mask & m).bit_count() > limits[g] for g, m in masks.items()):
                break
            raw.append((f, op, v, mask))
results = []
for by in [[], ["proto"], ["service"], ["proto", "service"]]:
    a = engine.analyze(s, ref, dict(c, features=fs, reference_by=by))
    scores = [x["scores"] for x in a["records"]]
    for n in [1, 2, 3]:
        for features in itertools.combinations(fs, n):
            mx = [max(x[f] for f in features) for x in scores]
            for threshold in [1.8, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 40, 60, 100]:
                mask = sum(1 << i for i, v in enumerate(mx) if v >= threshold)
                if any((mask & m).bit_count() > limits[g] for g, m in masks.items()):
                    continue
                used = []
                for _ in range(3):
                    missing = target & ~mask
                    if not missing:
                        break
                    candidates = []
                    for f, op, v, rm in raw:
                        gain = (missing & rm).bit_count()
                        if not gain:
                            continue
                        joined = mask | rm
                        if (
                            any((joined & m).bit_count() > limits[g] for g, m in masks.items())
                            or (joined & legit).bit_count() >= 175
                        ):
                            continue
                        added = joined & ~mask
                        candidates.append(
                            (
                                (added & masks["Wipro_bulb"]).bit_count() * 10
                                + (added & legit).bit_count(),
                                -gain,
                                f,
                                op,
                                v,
                                rm,
                            )
                        )
                    if not candidates:
                        break
                    _, _, f, op, v, rm = min(candidates)
                    mask |= rm
                    used.append(dict(name=f"{f} {op} {v}", field=f, op=op, value=v))
                if not (target & ~mask):
                    results.append(
                        dict(
                            features=features,
                            reference_by=by,
                            threshold=threshold,
                            rules=used,
                            groups={g: (mask & m).bit_count() for g, m in masks.items()},
                            fp=(mask & legit).bit_count(),
                        )
                    )
results.sort(
    key=lambda x: (x["groups"]["Wipro_bulb"], x["fp"], len(x["rules"]), len(x["features"]))
)
print(
    json.dumps(
        {"limits": limits, "raw_candidates": len(raw), "count": len(results), "top": results[:5]},
        indent=2,
    )
)
Path("benchmarks/rt-iot2022/refinement-4-development/hybrid-probe.json").write_text(
    json.dumps(results, indent=2)
)

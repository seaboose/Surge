"""Development-only reference-interval feasibility prototype; never runtime code."""

import sys, json, itertools, statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine

ROOT = Path(__file__).resolve().parent / "rt-iot2022"
OUT = ROOT / "refinement-4-development"
s = engine.load_dataset(ROOT / "refinement-1/development.json")
ref = engine.load_dataset(ROOT / "reference.json")
ls = json.loads((ROOT / "refinement-1/development.labels.json").read_text())["labels"]
c = json.loads((ROOT.parent.parent / "policies/rt-iot2022-refinement-3.policy.json").read_text())[
    "settings"
]
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
thresholds = [1, 1.25, 1.5, 1.8, 2, 3, 4, 6, 10, 20, 40, 100]
tails = [0, 0.01, 0.05, 0.1, 0.25, 0.5]
accepted = []
near = []


def quantile(vals, q):
    pos = (len(vals) - 1) * q
    i = int(pos)
    return vals[i] if i == len(vals) - 1 else vals[i] + (vals[i + 1] - vals[i]) * (pos - i)


for by in [[], ["proto"], ["service"], ["proto", "service"]]:
    a = engine.analyze(s, ref, dict(c, features=fs, reference_by=by))
    gap = sum(1 << i for i, x in enumerate(a["records"]) if x["gaps"])
    groups = {None: ref.rows}
    for row in ref.rows:
        if by:
            groups.setdefault(engine.reference_key(row, by), []).append(row)
    values = {k: {f: sorted(float(x[f]) for x in rows) for f in fs} for k, rows in groups.items()}
    for q in tails:
        scores = {f: [] for f in fs}
        for row, rec in zip(s.rows, a["records"]):
            k = (
                rec.get("reference_group", {}).get("key")
                if rec.get("reference_group", {}).get("mode") == "matched"
                else None
            )
            for f in fs:
                p = engine.profile_for_record(a, rec, f)
                lo = quantile(values[k][f], q)
                hi = quantile(values[k][f], 1 - q)
                v = float(row[f])
                scores[f].append(max(lo - v, v - hi, 0) / p["scale"])
        mm = {
            (f, t): sum(1 << i for i, v in enumerate(vs) if v >= t)
            for f, vs in scores.items()
            for t in thresholds
        }
        for n in range(1, 7):
            for ff in itertools.combinations(fs, n):
                for t in thresholds:
                    mask = 0
                    for f in ff:
                        mask |= mm[f, t]
                    gp = {g: (mask & m).bit_count() for g, m in masks.items()}
                    miss = (target & ~mask).bit_count()
                    unknown = (legit & gap & ~mask).bit_count()
                    fp = (mask & legit).bit_count()
                    candidate = dict(
                        features=ff,
                        reference_by=by,
                        threshold=t,
                        tail_quantile=q,
                        groups=gp,
                        fp=fp,
                        missed=miss,
                        legitimate_unknown=unknown,
                    )
                    if fp < 175 and all(gp[g] <= limits[g] for g in masks):
                        near.append(candidate)
                        if miss == 0 and unknown == 0:
                            accepted.append(candidate)
accepted.sort(key=lambda x: (x["groups"]["Wipro_bulb"], x["fp"], len(x["features"])))
near.sort(key=lambda x: (x["missed"] + x["legitimate_unknown"], x["groups"]["Wipro_bulb"], x["fp"]))
result = dict(
    prototype_only=True,
    description="Reference-only central interval; outside distance divided by existing reference MAD/tolerance scale. Linear sample quantiles, tails0,.01,.05,.1,.25,.5; four group choices;63feature subsets;12shared thresholds. Existing group minimum20and fallback gaps retained.",
    accepted=accepted,
    nearest_rejected=near[:10],
)
(OUT / "interval-probe.json").write_text(json.dumps(result, indent=2))
print(
    json.dumps(dict(accepted=len(accepted), top=accepted[:3], nearest_rejected=near[:3]), indent=2)
)

"""Bounded alternative profile search on development data only."""

import itertools, json, statistics, sys, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine

ROOT = Path(__file__).resolve().parent / "rt-iot2022"
OUT = ROOT / "refinement-2-development"
source = engine.load_dataset(ROOT / "refinement-1/development.json")
reference = engine.load_dataset(ROOT / "reference.json")
config = json.loads((ROOT / "refinement-1/candidate.policy.json").read_text())["settings"]
features = json.loads((ROOT / "policy.json").read_text())["settings"]["features"]
labels = json.loads((ROOT / "refinement-1/development.labels.json").read_text())["labels"]
truth = sum(1 << i for i, r in enumerate(labels) if r["truth"] == "target")
legit = ((1 << len(labels)) - 1) ^ truth
groups = {}
for row in reference.rows:
    groups.setdefault(engine.reference_key(row, config["reference_by"]), []).append(row)


def quantile(v, q):
    x = (len(v) - 1) * q
    i = int(x)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (x - i)


results = []
for method in ["raw", "log", "asymmetric", "iqr", "interval10", "interval25"]:
    transform = (
        (lambda x: math.copysign(math.log1p(abs(x)), x)) if method == "log" else (lambda x: x)
    )

    def fit(rows):
        ans = {}
        for f in features:
            v = sorted(transform(n) for r in rows if (n := engine.number(r.get(f))) is not None)
            if len(v) < 20:
                return None
            m = statistics.median(v)
            s = statistics.median(abs(x - m) for x in v) * 1.4826 or max(abs(m) * 0.01, 1e-9)
            lo = hi = m
            ls = hs = s
            if method == "asymmetric":
                ls = max(s, (m - quantile(v, 0.1)) / 1.28155)
                hs = max(s, (quantile(v, 0.9) - m) / 1.28155)
            if method == "iqr":
                ls = hs = max(s, (quantile(v, 0.75) - quantile(v, 0.25)) / 1.349)
            if method.startswith("interval"):
                q = 0.1 if method == "interval10" else 0.25
                lo = quantile(v, q)
                hi = quantile(v, 1 - q)
            ans[f] = (lo, hi, ls, hs)
        return ans

    globalp = fit(reference.rows)
    profiles = {k: fit(r) for k, r in groups.items()}
    scores = {f: [] for f in features}
    for row in source.rows:
        p = profiles.get(engine.reference_key(row, config["reference_by"])) or globalp
        for f in features:
            v = transform(engine.number(row[f]))
            lo, hi, ls, hs = p[f]
            scores[f].append(max((lo - v) / ls, (v - hi) / hs, 0))
    for threshold in [1, 1.5, 2, 3, 4, 6]:
        masks = {
            f: sum(1 << i for i, s in enumerate(scores[f]) if s >= threshold) for f in features
        }
        for count in range(1, len(features) + 1):
            for fs in itertools.combinations(features, count):
                flags = 0
                for f in fs:
                    flags |= masks[f]
                fp = (flags & legit).bit_count()
                fn = (truth & ~flags).bit_count()
                if fn == 0:
                    results.append(
                        dict(method=method, threshold=threshold, features=fs, fp=fp, fn=fn)
                    )
results.sort(key=lambda r: (r["fp"], len(r["features"])))
(OUT / "profile-probe.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results[:15], indent=2))

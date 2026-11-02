"""Development-only probe. This script never opens test/holdout sources."""

import itertools, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine

ROOT = Path(__file__).resolve().parent / "rt-iot2022"
OUT = ROOT / "refinement-2-development"
OUT.mkdir(exist_ok=True)
source = engine.load_dataset(ROOT / "refinement-1/development.json")
reference = engine.load_dataset(ROOT / "reference.json")
config = json.loads((ROOT / "refinement-1/candidate.policy.json").read_text())["settings"]
labels = json.loads((ROOT / "refinement-1/development.labels.json").read_text())["labels"]
result = engine.analyze(source, reference, config)
truth = sum(1 << i for i, r in enumerate(labels) if r["truth"] == "target")
legit = ((1 << len(labels)) - 1) ^ truth
thresholds = [2, 3, 4, 6, 8, 12, 16, 24, 32, 64, 100]
masks = {
    f: {
        t: sum(1 << i for i, r in enumerate(result["records"]) if r["scores"].get(f, 0) >= t)
        for t in thresholds
    }
    for f in config["features"]
}
candidates = []
for ts in itertools.product(thresholds, repeat=3):
    flags = 0
    for f, t in zip(config["features"], ts):
        flags |= masks[f][t]
    fp = (flags & legit).bit_count()
    fn = (truth & ~flags).bit_count()
    if fn == 0:
        candidates.append(dict(thresholds=dict(zip(config["features"], ts)), fp=fp, fn=fn))
candidates.sort(key=lambda r: (r["fp"], sum(r["thresholds"].values())))
(OUT / "threshold-probe.json").write_text(json.dumps(candidates, indent=2) + "\n")
print(json.dumps(candidates[:12], indent=2))

"""Recompute the nine retained Survive development captures without altering them."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "unreal/SurgeMovementLab"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(LAB / "telemetry"))
import engine
from prepare_v3 import derive


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New result file; never overwrites evidence")
    args = parser.parse_args()
    reference = LAB / "telemetry/local/opportunity-v2-reanalysis-20261026T115100Z-b6a76d5c/report.json"
    if not reference.is_file():
        raise SystemExit("Retained local pilot is unavailable; no historical parity claim can be made.")
    original = json.loads(reference.read_text())
    trials = []
    for trial in original["trials"]:
        bundle = Path(trial["original_bundle"]).resolve()
        if not bundle.is_relative_to(LAB / "telemetry/local"):
            raise ValueError("Pilot reference points outside owned local evidence")
        raw = (bundle / "source.jsonl").read_bytes()
        previous = (bundle / "surge.jsonl").read_bytes()
        manifest = json.loads((bundle / "manifest.json").read_text())
        before = {name: digest((bundle / name).read_bytes()) for name in manifest["bundle_sha256"]}
        if before != manifest["bundle_sha256"] or digest(raw) != trial["raw_sha256"]:
            raise ValueError("Original pilot evidence fingerprint mismatch")
        current = ("\n".join(json.dumps(r, allow_nan=False, separators=(",", ":")) for r in derive(raw)) + "\n").encode()
        if current != previous:
            raise ValueError("Derived movement evidence changed for " + bundle.name)
        case_path = bundle.parent / (bundle.name + ".surge.case.json")
        case_hash = digest(case_path.read_bytes())
        data, reference_data, policy, reopened = engine.open_case(case_path)
        result = engine.analyze(engine.parse_bytes(current, data.name), reference_data, policy)
        if result != reopened:
            raise ValueError("Full Surge conclusions changed for " + bundle.name)
        counts = {name: sum(row["status"] == name for row in result["records"])
                  for name in ("Review", "Unknown", "No finding")}
        if counts != trial["verdict_counts"]:
            raise ValueError("Verdict counts changed")
        after = {name: digest((bundle / name).read_bytes()) for name in before}
        if before != after or digest(case_path.read_bytes()) != case_hash:
            raise ValueError("Original evidence changed during read-only regression")
        trials.append({"bundle": bundle.name, "source_sha256": digest(raw),
                       "derived_sha256": digest(current), "case_sha256": case_hash,
                       "derived_bytes_identical": True, "full_results_identical": True,
                       "original_files_unchanged": True, "counts": counts})
    output = {"schema": "survive-historical-regression-v1", "status": "passed",
              "created_utc": datetime.now(timezone.utc).isoformat(), "trials": trials,
              "limits": "Saved automated development captures only; no new human or detection-accuracy evidence."}
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(output, target, indent=2)
        target.write("\n")
    print(json.dumps({"status": "passed", "trials": len(trials), "output": str(args.output)}))


if __name__ == "__main__":
    main()

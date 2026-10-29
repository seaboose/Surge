"""Reproduce the saved, already-scored benchmark without tuning or opening a new holdout."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
import evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Extracted evaluation evidence directory")
    folder = parser.parse_args().folder.resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        if Path(name).name != name or (folder / name).stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Invalid evidence manifest entry")
        actual = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Evidence fingerprint differs: {name}")
    for name in ("baseline", "candidate"):
        source, reference, config, result = engine.open_case(folder / f"{name}.case.json")
        labels = evaluation.load(folder / "holdout.labels.json", source)
        actual = evaluation.evaluate(source, reference, config, result, labels)
        expected = json.loads((folder / f"{name}.evaluation.json").read_text(encoding="utf-8"))
        actual.pop("created_utc")
        expected.pop("created_utc")
        if actual != expected:
            raise ValueError(f"Saved evaluation differs: {name}")
        counts = actual["summary"]["counts"]
        print(
            f"{name}: {counts['False positive']} false positives; {counts['Missed']} missed targets"
        )
    print("Both cases and complete evaluation reports reproduce. No policy was changed.")


if __name__ == "__main__":
    main()

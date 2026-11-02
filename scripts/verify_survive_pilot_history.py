"""Verify the nine original pilot streams against an existing private report.

Run explicitly with --report REPORT.json --streams ORIGINAL_STREAMS_DIRECTORY.
This read-only history check is separate from portable unit tests: absent private
evidence is a failure, never a skip or a claimed historical pass. Public synthetic
fixtures do not replace these checks against the original bytes and conclusions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

import survive_capture as capture


def verify(report_path, streams_root):
    report = json.loads(Path(report_path).read_text(encoding="utf-8-sig"))
    trials = [trial for trial in report["trials"] if trial.get("raw_sha256") is not None]
    if len(trials) != 9:
        raise ValueError("Historical verification requires exactly nine recorded source hashes")
    candidates = tuple(Path(streams_root).rglob("source.jsonl"))
    profile, _, policy = capture._profile("survive-lucian-practice-v1")
    checked = 0
    for trial in trials:
        # Identity comes from the retained hash, not a guessed scenario label.
        source = next((path for path in candidates
                       if hashlib.sha256(path.read_bytes()).hexdigest() == trial["raw_sha256"]), None)
        if source is None:
            raise ValueError("Original pilot source is missing or its bytes changed")
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != trial["raw_sha256"]:
            raise ValueError("Original pilot source changed while being read")
        analysis, derived = capture._analysis(raw, profile, policy)
        if derived != source.with_name("surge.jsonl").read_bytes():
            raise ValueError("Historical derived bytes differ")
        if hashlib.sha256(derived).hexdigest() != trial["current_derived_sha256"]:
            raise ValueError("Historical derived hash differs")
        if analysis["counts"] != trial["verdict_counts"]:
            raise ValueError("Historical verdict counts differ")
        if not analysis["constraints"]:
            raise ValueError("Historical analysis has no constraints")
        checked += 1
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--streams", type=Path, required=True)
    args = parser.parse_args()
    checked = verify(args.report, args.streams)
    print(json.dumps({"status": "passed", "original_streams_verified": checked}))


if __name__ == "__main__":
    main()

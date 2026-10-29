"""Bound the owned-data approval pack and verify its retained local evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_approval_contract import SCENARIOS, SOURCES, MAX_INPUT, MAX_CASE, digest

SECONDS = 300
LOG_BYTES = 10 * 1024 * 1024


def verify(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "evidence-manifest.json").read_text(encoding="utf-8"))
    expected = {p.relative_to(folder).as_posix() for p in folder.rglob("*")
                if p.is_file() and p.name != "evidence-manifest.json"}
    seen = set()
    for item in manifest:
        relative = item["path"]
        path = (folder / relative).resolve()
        if relative in seen or not path.is_relative_to(folder):
            raise ValueError("Duplicate or escaping evidence path")
        seen.add(relative)
        raw = path.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("Evidence bytes do not match manifest: " + relative)
    if seen != expected:
        raise ValueError("Evidence manifest does not enumerate all retained files")
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    if (report["schema"] != "surge-approval-contract-v1" or report["status"] != "passed"
            or report["repeatability"] != "passed"
            or report["original_fuzzing_campaign"] != "incomplete"
            or report["held_back_phase"] is not False):
        raise ValueError("Approval contract report is incomplete")
    if set(report["source_sha256"]) != set(SOURCES):
        raise ValueError("Missing or unknown frozen source")
    if not 0 <= report["seconds"] <= SECONDS:
        raise ValueError("Approval pack exceeded the recorded time budget")
    identities = {(f"{c}-{s}-{state}", r) for c, s, state in SCENARIOS for r in (1, 2)}
    if type(report["evaluations"]) is not int or report["evaluations"] != len(identities):
        raise ValueError("Incomplete evaluation count")
    if report["limits"] != dict(max_input_bytes=MAX_INPUT, max_case_bytes=MAX_CASE,
                                outer_seconds=SECONDS, output_bytes=LOG_BYTES):
        raise ValueError("Different approval-pack limits")
    indexed = {}
    for row in report["runs"]:
        key = row["id"], row["repeat"]
        if key not in identities or key in indexed or row["status"] != "passed":
            raise ValueError("Missing, failed, duplicate, or unknown scenario")
        indexed[key] = row
        metrics = row["metrics"]
        count, size, state = row["id"].split("-", 2)
        if (metrics["ranges"], metrics["range_bytes"], metrics["state"], metrics["rows"]) != (
                int(count), int(size), state, 3 * int(count)):
            raise ValueError("Scenario dimensions differ")
        if digest(metrics) != row["result_sha256"]:
            raise ValueError("Semantic measurements differ from their fingerprint")
        if any(not 0 < n <= MAX_INPUT for n in metrics["input_sizes"].values()):
            raise ValueError("Encoded input exceeded budget")
        if not 0 < metrics["case_bytes"] <= MAX_CASE:
            raise ValueError("Saved case exceeded budget")
        if any(metrics[k] != "passed" for k in ("case_replay", "representation_changes")):
            raise ValueError("Replay or representation check incomplete")
    if set(indexed) != identities:
        raise ValueError("Missing scenarios")
    for name, repeat in identities:
        first, second = indexed[name, 1], indexed[name, 2]
        if any(first[k] != second[k] for k in ("input_sha256", "result_sha256")):
            raise ValueError("Repeated scenario fingerprints differ")
    for name, fingerprint in report["source_sha256"].items():
        if hashlib.sha256((folder / "source" / name).read_bytes()).hexdigest() != fingerprint:
            raise ValueError("Frozen source fingerprint differs")
    return dict(status="passed", evidence_files=len(manifest),
                evaluations=report["evaluations"], original_fuzzing_campaign="incomplete")


def run():
    folder = ROOT / "verification/qualification" / ("approval-supervisor-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    log = folder / "command.log"
    started = time.monotonic()
    breach = None
    with log.open("wb") as out:
        child = subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts/check_approval_contract.py")],
                                 cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        while child.poll() is None:
            if time.monotonic() - started > SECONDS or log.stat().st_size > LOG_BYTES:
                breach = "time" if time.monotonic() - started > SECONDS else "log"
                child.kill()
                break
            time.sleep(0.05)
        code = child.wait()
    result = dict(status="failed", exit_code=code, breach=breach,
                  seconds=round(time.monotonic() - started, 6),
                  log_bytes=log.stat().st_size,
                  log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    try:
        if code or breach or log.stat().st_size > LOG_BYTES:
            raise ValueError("Approval pack failed or exceeded its bound")
        lines = log.read_text(encoding="utf-8").splitlines()
        paths = [line.removeprefix("Approval contract evidence: ") for line in lines
                 if line.startswith("Approval contract evidence: ")]
        if len(paths) != 1:
            raise ValueError("Missing or duplicate child evidence location")
        child_folder = Path(paths[0]).resolve()
        if (child_folder.parent != folder.parent.resolve()
                or not child_folder.name.startswith("approval-contract-")):
            raise ValueError("Unexpected child evidence location")
        result["verification"] = verify(child_folder)
        result["evidence"] = child_folder.relative_to(ROOT).as_posix()
        result["status"] = "passed"
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(str(folder))
        print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify), sort_keys=True))
    else:
        raise SystemExit(run())

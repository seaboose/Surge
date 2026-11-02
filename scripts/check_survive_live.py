"""Bounded owned-engine integration checks; never represents human play.

Runs fixed practice controls, preserves every recording and trial, and verifies
the actual recorder, saved review, raw selection and external study association.
Requires the compiled local Unreal project. No dependency installation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from survive_capture import CaptureManager
from survive_study import StudyManager
from survive_workspace import SurviveWorkspace


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "verification" / ("survive-engine-study-" + stamp + "-" + uuid.uuid4().hex[:8])
    output.mkdir(exist_ok=False)
    capture = CaptureManager(max_seconds=150)
    study = StudyManager(headless=True, max_duration=120)
    service = SurviveWorkspace(capture, study)
    results = []
    cases = [("scripted", "survive-lucian-practice-v1"),
             ("mixed", "survive-lucian-practice-v1"),
             ("speed_probe", "survive-lucian-practice-v1"),
             ("scripted", "survive-lucian-reference-v1")]
    print("Owned Unreal integration evidence: " + str(output), flush=True)
    try:
        for index, (mode, profile) in enumerate(cases):
            print("Starting practice verification: " + mode + " / " + profile, flush=True)
            start = service.dispatch("survive_trial_start", {
                "mode": mode, "seed": 1337, "profile_id": profile,
                "participant": "verification", "phase": "practice",
            })
            trial_id = start["trial"]["trial_id"]
            recording_id = start["capture"]["recording_id"]
            save(output / (str(index) + "-started.json"), {"trial_id": trial_id, "recording_id": recording_id})
            deadline = time.monotonic() + 140
            growing = 0
            previous = 0
            while time.monotonic() < deadline:
                current = service.dispatch("survive_status", {})
                size = current["capture"]["records"]
                growing += size > previous
                previous = size
                state = current["capture"]["state"]
                if state in {"complete", "failed", "stopped"}:
                    break
                time.sleep(.5)
            else:
                raise AssertionError("Recorder exceeded bounded verification duration")
            while study._process.poll() is None and time.monotonic() < deadline:
                time.sleep(.2)
            if study._process.poll() is None:
                raise AssertionError("Owned game failed to exit after its round")
            saved = service.dispatch("survive_open", {"recording_id": recording_id})
            meta = saved["capture"]
            counts = (saved["view"]["analysis"] or {}).get("counts")
            check = {"mode": mode, "profile_id": profile, "trial_id": trial_id,
                     "recording_id": recording_id, "capture": meta, "counts": counts,
                     "live_growth_observations": growing, "engine_exit_code": study._process.returncode,
                     "source_kind": "headless-practice-verification; mixed manual windows idle"}
            save(output / (str(index) + "-capture.json"), check)
            assert meta["state"] == "complete" and meta["completion"] == "completed", meta
            assert study._process.returncode == 0, check
            assert growing >= 5, "The live recorder did not show incremental collection"
            assert counts["Review"] > 0 if mode == "speed_probe" else counts["Review"] == 0, counts
            raw = capture.source_root / (meta["session_id"] + ".jsonl")
            spool = capture.recording_root / recording_id / "source.jsonl"
            assert raw.read_bytes() == spool.read_bytes(), "Observer bytes differ from game source"
            assert hashlib.sha256(spool.read_bytes()).hexdigest() == meta["source_sha256"]
            selected = service.dispatch("survive_record", {"recording_id": recording_id, "seq": 300})
            assert selected["record"] == json.loads(raw.read_bytes().splitlines()[300])
            assert len(selected["record"]) == 31
            report = service.dispatch("survive_report", {})
            trial = next(row for row in report["trials"] if row["trial_id"] == trial_id)
            assert trial["complete"] and trial["source_association"]["state"] == "matched", trial
            assert not trial["included_in_confusion"], "Practice must not enter evaluation rates"
            check["source_association"] = trial["source_association"]
            check["passed"] = True
            results.append(check)
            save(output / (str(index) + "-passed.json"), check)
            print("Passed " + mode + ": " + json.dumps(counts), flush=True)
        save(output / "report.json", {"passed": True, "trials": results,
             "scope": "Four real-engine practice trials; no physical human-input or rendered-game validation."})
    except BaseException as exc:
        save(output / "failure.json", {"error": str(exc), "completed_trials": results})
        raise
    finally:
        service.close()
    print("All four owned-engine study checks passed: " + str(output / "report.json"), flush=True)


if __name__ == "__main__":
    main()

"""Validate server samples and derive bounded Surge input. No labels accepted.

This adapter is local to the game lab; it does not change Surge's engine.
"""
import argparse
import json
import math
from pathlib import Path

FIELDS = {"schema", "session_id", "seq", "elapsed_s", "x_cm", "y_cm", "z_cm", "movement_mode"}
MAX_BYTES = 4 * 1024 * 1024
MAX_ROWS = 6001
POLICY_SPEED_CM_S = 600.0
POSITION_SLACK_CM = 10.0


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def derive(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("Capture exceeds 4 MiB")
    lines = raw.decode("utf-8").splitlines()
    if not 2 <= len(lines) <= MAX_ROWS:
        raise ValueError("Expected 2–6001 complete samples")
    samples = []
    for index, line in enumerate(lines):
        if len(line) > 2048:
            raise ValueError("Oversized sample")
        row = json.loads(line, object_pairs_hook=unique_object)
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("Unexpected fields; labels and controller actions are forbidden")
        if row["schema"] != "surge-movement-v1":
            raise ValueError("Unsupported schema")
        session = row["session_id"]
        if not isinstance(session, str) or len(session) != 32 or any(c not in "0123456789abcdefABCDEF" for c in session):
            raise ValueError("Expected opaque GUID session")
        if type(row["seq"]) is not int or row["seq"] != index:
            raise ValueError("Missing, duplicate, or reordered sample; do not bridge gaps")
        for field in ("elapsed_s", "x_cm", "y_cm", "z_cm"):
            v = row[field]
            if type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e7:
                raise ValueError("Nonfinite or out-of-bounds numeric field")
        if not 0 <= row["elapsed_s"] <= 600.001:
            raise ValueError("Elapsed time outside capture budget")
        if row["movement_mode"] not in ("walking", "other"):
            raise ValueError("Unsupported movement mode")
        if samples and (session != samples[0]["session_id"] or row["elapsed_s"] <= samples[-1]["elapsed_s"]):
            raise ValueError("Mixed session or nonincreasing server time")
        samples.append(row)
    result = []
    for previous, current in zip(samples, samples[1:]):
        dt = current["elapsed_s"] - previous["elapsed_s"]
        distance = math.hypot(current["x_cm"] - previous["x_cm"], current["y_cm"] - previous["y_cm"])
        # Wall-clock/network arrival time is deliberately absent. Long hitches and
        # unsupported modes are Unknown, not clean movement and not speed findings.
        eligible = .05 <= dt <= .5 and previous["movement_mode"] == current["movement_mode"] == "walking"
        result.append({
            "session_id": current["session_id"], "event_id": str(current["seq"]),
            "elapsed_s": current["elapsed_s"], "dt_s": dt, "distance_cm": distance,
            "policy_speed_cm_s": POLICY_SPEED_CM_S, "position_slack_cm": POSITION_SLACK_CM,
            "excess_cm": distance - POLICY_SPEED_CM_S * dt - POSITION_SLACK_CM if eligible else None,
            "coverage": "eligible" if eligible else "unsupported interval or movement mode",
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.capture.open("rb") as stream:
        rows = derive(stream.read(MAX_BYTES + 1))
    # Exclusive creation protects earlier evidence and refuses input overwrite.
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

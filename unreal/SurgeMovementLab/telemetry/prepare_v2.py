"""Derive inspectable movement constraints from bounded Survive server evidence.

Ground truth and experiment actions are not inputs. v1 remains a separate legacy
walking-only format; a v2 capture must never be passed through its adapter.
"""
import argparse
import json
import math
from pathlib import Path

from prepare import unique_object

MAX_BYTES = 4 * 1024 * 1024
MAX_ROWS = 10000
FIELDS = {"schema", "session_id", "seq", "elapsed_s", "event", "x_cm", "y_cm", "z_cm",
          "movement_mode", "related_id", "detail", "a", "b", "c", "d",
          "source_x_cm", "source_y_cm", "velocity_x_cm_s", "velocity_y_cm_s"}
NUMERIC = {"elapsed_s", "x_cm", "y_cm", "z_cm", "a", "b", "c", "d",
           "source_x_cm", "source_y_cm", "velocity_x_cm_s", "velocity_y_cm_s"}
EVENTS = {"run_start", "run_end", "sample", "ability_request", "ability_grant",
          "ability_denied", "ability_start", "ability_end", "command_request",
          "command_grant", "command_denied", "command_stop", "threat_warning",
          "threat_fire", "threat_hit", "threat_expired", "threat_blocked"}
# Reviewed design constants; payload fields a/b/c/d cannot redefine this policy.
WALK_SPEED = 600.0
POSITION_SLACK = 10.0
ABILITY = {"dash": {"range_cm": 350.0, "cooldown_s": 4.0},
           "blink": {"range_cm": 450.0, "cooldown_s": 12.0}}


def load_rows(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("Capture exceeds 4 MiB")
    lines = raw.decode("utf-8").splitlines()
    if not 3 <= len(lines) <= MAX_ROWS:
        raise ValueError("Expected 3–10000 complete records")
    rows = []
    for index, line in enumerate(lines):
        if len(line) > 2048:
            raise ValueError("Oversized event")
        row = json.loads(line, object_pairs_hook=unique_object)
        if not isinstance(row, dict) or set(row) != FIELDS or row["schema"] != "survive-v2":
            raise ValueError("Unsupported fields/schema; experiment labels are forbidden")
        if type(row["seq"]) is not int or row["seq"] != index:
            raise ValueError("Missing, duplicate or reordered sequence")
        sid = row["session_id"]
        if not isinstance(sid, str) or len(sid) != 32 or any(c not in "0123456789abcdefABCDEF" for c in sid):
            raise ValueError("Expected opaque GUID session")
        if (not isinstance(row["event"], str) or not isinstance(row["movement_mode"], str)
                or row["event"] not in EVENTS or row["movement_mode"] not in {"walking", "dash", "blink", "other", "ended"}):
            raise ValueError("Unsupported event or mode")
        for field in ("detail", "related_id"):
            if not isinstance(row[field], str) or len(row[field]) > 80 or not row[field].isascii():
                raise ValueError("Oversized or invalid event context")
        for field in NUMERIC:
            value = row[field]
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e10:
                raise ValueError("Invalid numeric field")
        if not 0 <= row["elapsed_s"] <= 60.1:
            raise ValueError("Outside 60-second run (100 ms terminal-tick tolerance)")
        if rows and (sid != rows[0]["session_id"] or row["elapsed_s"] < rows[-1]["elapsed_s"]):
            raise ValueError("Mixed session or decreasing event time")
        rows.append(row)
    if rows[0]["event"] != "run_start" or rows[-1]["event"] != "run_end":
        raise ValueError("Incomplete capture: start/end records required")
    if sum(r["event"] == "run_start" for r in rows) != 1 or sum(r["event"] == "run_end" for r in rows) != 1:
        raise ValueError("Ambiguous run lifecycle")
    if rows[-1]["detail"] not in {"completed", "disconnect", "capture_limit", "write_failure"}:
        raise ValueError("Unrecognized completion state")
    if rows[-1]["detail"] == "completed" and rows[-1]["elapsed_s"] < 59.9:
        raise ValueError("Completed run ended before its declared 60-second duration")
    return rows


def derive(raw):
    rows = load_rows(raw)
    return derive_rows(rows)


def derive_rows(rows, *, walk_speed=WALK_SPEED, ability_policy=None, position_slack=POSITION_SLACK):
    """Shared measured constraints; callers supply reviewed policy, never row limits.

    Public v2 derive() retains its historical fixed defaults. New schemas may call
    this only after their own validation and explicit local profile selection.
    """
    ability_policy = ABILITY if ability_policy is None else ability_policy
    result = []
    previous_sample = None
    mobility_since_sample = False
    starts = {}
    last_start = {}
    used_activations = set()

    def observation(row, constraint, observed, allowed, unit, start_seq, eligible=True, inverse=False):
        ratio = allowed / max(observed + .001, .001) if inverse else observed / allowed
        result.append({"session_id": row["session_id"], "event_id": f"{row['seq']}:{constraint}",
                       "elapsed_s": row["elapsed_s"], "constraint": constraint,
                       "observed": observed, "allowed": allowed, "unit": unit,
                       "constraint_ratio": ratio if eligible else None,
                       "coverage": "eligible" if eligible else "unsupported interval or mobility transition",
                       "run_completion": rows[-1]["detail"],
                       "start_seq": start_seq, "end_seq": row["seq"]})

    for row in rows:
        event, t = row["event"], row["elapsed_s"]
        if event in {"ability_start", "ability_end"}:
            mobility_since_sample = True
            key = row["related_id"]
            ability = row["detail"]
            if not key or ability not in ability_policy:
                raise ValueError("Ability lifecycle requires an ID and known ability")
            if event == "ability_start":
                if key in used_activations or starts:
                    raise ValueError("Duplicate or overlapping mobility activation")
                used_activations.add(key)
                starts[key] = row
                if ability in last_start:
                    elapsed = t - last_start[ability]["elapsed_s"]
                    # Inverse ratio: >1 means a shorter-than-permitted interval.
                    observation(row, ability + "_cooldown", elapsed, ability_policy[ability]["cooldown_s"],
                                "seconds", last_start[ability]["seq"], inverse=True)
                last_start[ability] = row
            else:
                start = starts.pop(key, None)
                if start is None or start["detail"] != ability:
                    raise ValueError("Unmatched ability end")
                distance = math.hypot(row["x_cm"] - start["x_cm"], row["y_cm"] - start["y_cm"])
                observation(row, ability + "_range", distance,
                            ability_policy[ability]["range_cm"] + position_slack, "cm", start["seq"])
        if event == "sample":
            if previous_sample is None and t - rows[0]["elapsed_s"] > .15:
                observation(row, "capture_start_gap", t - rows[0]["elapsed_s"], .15,
                            "seconds", rows[0]["seq"], eligible=False)
                result[-1]["coverage"] = "unobserved trajectory before first sample"
            if previous_sample:
                dt = t - previous_sample["elapsed_s"]
                if dt <= 0:
                    raise ValueError("Nonincreasing trajectory sample time")
                distance = math.hypot(row["x_cm"] - previous_sample["x_cm"], row["y_cm"] - previous_sample["y_cm"])
                eligible = (.015 <= dt <= .15 and not mobility_since_sample and not starts
                            and previous_sample["movement_mode"] == row["movement_mode"] == "walking")
                observation(row, "walking_displacement", distance, walk_speed * dt + position_slack,
                            "cm", previous_sample["seq"], eligible)
            previous_sample = row
            mobility_since_sample = False
    if starts and rows[-1]["detail"] == "completed":
        raise ValueError("Completed run has unfinished mobility")
    if previous_sample is None or rows[-1]["elapsed_s"] - previous_sample["elapsed_s"] > .15:
        start = previous_sample or rows[0]
        observation(rows[-1], "capture_end_gap", rows[-1]["elapsed_s"] - start["elapsed_s"],
                    .15, "seconds", start["seq"], eligible=False)
        result[-1]["coverage"] = ("unobserved trajectory after last sample" if previous_sample
                                 else "no trajectory samples retained")
    if rows[-1]["detail"] != "completed":
        observation(rows[-1], "run_completion", 0, 1, "completion", rows[0]["seq"], eligible=False)
        result[-1]["coverage"] = "partial capture: " + rows[-1]["detail"]
    if not result:
        raise ValueError("No comparable intervals or completed abilities")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.capture.open("rb") as source:
        result = derive(source.read(MAX_BYTES + 1))
    with args.output.open("x", encoding="utf-8", newline="\n") as target:
        for row in result:
            target.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

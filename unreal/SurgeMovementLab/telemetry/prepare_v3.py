"""Bounded Survive v3 validation and profile-based movement evidence.

The expected profile is selected locally by the operator, never by incoming data.
Old adapters and their fixed limits remain available for historical captures.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import prepare_v2 as legacy
from prepare import unique_object

PROFILE_ROOT = Path(__file__).resolve().parents[1] / "profiles"
PROFILE_IDS = {"survive-lucian-practice-v1", "survive-lucian-reference-v1"}
EXTRA = {"server_tick", "delta_s", "monotonic_s", "profile_id", "path_radius_cm",
         "hit_radius_cm", "visual_radius_cm", "threat_x_cm", "threat_y_cm",
         "nearest_clearance_cm", "clearance_valid", "baseline_threat"}
FIELDS = legacy.FIELDS | EXTRA
EVENTS = legacy.EVENTS | {"threat_cancelled"}
EXTRA_NUMERIC = EXTRA - {"profile_id", "clearance_valid", "baseline_threat", "server_tick"}


def load_profile(profile_id="survive-lucian-practice-v1"):
    if profile_id not in PROFILE_IDS:
        raise ValueError("Choose a reviewed local profile explicitly")
    path = PROFILE_ROOT / (profile_id + ".json")
    raw = path.read_bytes()
    if len(raw) > 128 * 1024:
        raise ValueError("Profile is oversized")
    profile = json.loads(raw, object_pairs_hook=unique_object)
    if profile.get("id") != profile_id or profile.get("schema") != "survive-reference-profile-v1":
        raise ValueError("Unsupported local profile")
    profile["file_sha256"] = hashlib.sha256(raw).hexdigest()
    for group, fields in {"movement": ("walk_speed_cm_s", "path_radius_cm", "hit_radius_cm", "visual_radius_cm"),
                          "dash": ("max_range_cm", "speed_cm_s", "cooldown_s"),
                          "blink": ("max_range_cm", "cooldown_s"),
                          "projectile": ("speed_cm_s", "radius_cm", "cast_delay_s", "range_cm"),
                          "circle": ("radius_cm", "delay_s")}.items():
        for field in fields:
            value = profile.get(group, {}).get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1e6:
                raise ValueError("Invalid reviewed profile numeric field: " + group + "." + field)
    return profile


def load_rows(raw, profile):
    if len(raw) > legacy.MAX_BYTES:
        raise ValueError("Capture exceeds 4 MiB")
    lines = raw.decode("utf-8").splitlines()
    if not 3 <= len(lines) <= legacy.MAX_ROWS:
        raise ValueError("Expected 3–10000 complete records")
    rows = []
    for index, line in enumerate(lines):
        if len(line) > 3072:
            raise ValueError("Oversized v3 event")
        row = json.loads(line, object_pairs_hook=unique_object)
        if not isinstance(row, dict) or set(row) != FIELDS or row.get("schema") != "survive-v3":
            raise ValueError("Unsupported v3 fields/schema; no labels or unknown fields accepted")
        if row["profile_id"] != profile["id"]:
            raise ValueError("Capture profile differs from explicitly selected policy profile")
        if type(row["server_tick"]) is not int or not 0 <= row["server_tick"] <= 1e9:
            raise ValueError("Invalid server tick")
        if type(row["clearance_valid"]) is not bool or row["baseline_threat"] not in ("yes", "no", "unknown"):
            raise ValueError("Invalid threat metric availability")
        for field in EXTRA_NUMERIC:
            value = row[field]
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e10:
                raise ValueError("Invalid v3 numeric field: " + field)
        if not 0 <= row["delta_s"] <= 60 or not 0 <= row["monotonic_s"] <= 86400:
            raise ValueError("Invalid timing interval")
        for field in ("path_radius_cm", "hit_radius_cm", "visual_radius_cm"):
            if abs(row[field] - profile["movement"][field]) > .01:
                raise ValueError("Capture geometry differs from reviewed profile: " + field)
        if not isinstance(row["event"], str) or row["event"] not in EVENTS:
            raise ValueError("Unsupported v3 event")
        if rows and (row["server_tick"] < rows[-1]["server_tick"] or row["monotonic_s"] < rows[-1]["monotonic_s"]):
            raise ValueError("Decreasing tick or monotonic clock")
        rows.append(row)
    sample_ticks = [r["server_tick"] for r in rows if r["event"] == "sample"]
    if any(b <= a for a, b in zip(sample_ticks, sample_ticks[1:])):
        raise ValueError("Trajectory samples must use distinct increasing server ticks")
    # Reuse v2's scalar/session/sequence/lifecycle validation, without permitting
    # incoming fields to select a different policy. Cancelled threats are metadata
    # for constraint derivation, bridged to an existing terminal event only here.
    bridge = [dict({k: r[k] for k in legacy.FIELDS}, schema="survive-v2",
                   event="threat_expired" if r["event"] == "threat_cancelled" else r["event"],
                   detail="disconnect" if r["event"] == "run_end" and r["detail"] == "restart" else r["detail"])
              for r in rows]
    legacy.load_rows("\n".join(json.dumps(r, allow_nan=False) for r in bridge).encode())
    return rows


def derive_rows(rows, profile):
    policy = {kind: {"range_cm": profile[kind]["max_range_cm"], "cooldown_s": profile[kind]["cooldown_s"]}
              for kind in ("dash", "blink")}
    result = legacy.derive_rows(rows, walk_speed=profile["movement"]["walk_speed_cm_s"],
                                ability_policy=policy, position_slack=5.0)
    result.extend(_dash_timing_rows(rows, profile))
    # A partial-run marker remains last even when a censored activation adds an
    # observation at the same terminal sequence. Stable ordering preserves the
    # historical constraints' ordering within each source record.
    result.sort(key=lambda record: (record["end_seq"], record["constraint"] == "run_completion"))
    for record in result:
        record["profile_id"] = profile["id"]
        record["policy_sha256"] = profile["file_sha256"]
    return result


def _dash_timing_rows(rows, profile):
    """Conservative maxima, not proof of exact dash speed or full-path coverage.

    Only successive samples wholly within one activation support displacement.
    Start/end edges remain with the legacy transition exclusions. Duration uses
    matched events plus contiguous in-dash samples and a bounded terminal tick;
    a wall stop may shorten either distance or duration without a violation.
    """
    result = []
    active = None
    previous_sample = None
    previous_point = None
    duration_supported = False
    sample_count = 0
    speed = profile["dash"]["speed_cm_s"]
    maximum_duration = profile["dash"]["max_range_cm"] / speed

    def observation(row, constraint, observed, allowed, unit, start_seq, reason=None):
        result.append({"session_id": row["session_id"], "event_id": f"{row['seq']}:{constraint}",
                       "elapsed_s": row["elapsed_s"], "constraint": constraint,
                       "observed": observed, "allowed": allowed, "unit": unit,
                       "constraint_ratio": observed / allowed if reason is None else None,
                       "coverage": reason or "eligible", "run_completion": rows[-1]["detail"],
                       "start_seq": start_seq, "end_seq": row["seq"]})

    def supported_tick(row):
        return 0 < row["delta_s"] <= .15

    for row in rows:
        event = row["event"]
        if event == "ability_start" and row["detail"] == "dash":
            active = row
            previous_sample = None
            previous_point = row
            sample_count = 0
            # An ability can begin between character ticks; its start delta is
            # not the elapsed time until the first movement update.
            duration_supported = row["movement_mode"] == "dash"
        elif active is not None and event == "sample":
            gap = row["elapsed_s"] - previous_point["elapsed_s"]
            duration_supported &= (0 <= gap <= .15 and row["movement_mode"] == "dash"
                                   and supported_tick(row))
            previous_point = row
            sample_count += 1
            if previous_sample is not None:
                dt = row["elapsed_s"] - previous_sample["elapsed_s"]
                distance = math.hypot(row["x_cm"] - previous_sample["x_cm"],
                                      row["y_cm"] - previous_sample["y_cm"])
                supported = (.015 <= dt <= .15 and supported_tick(row) and supported_tick(previous_sample)
                             and previous_sample["movement_mode"] == row["movement_mode"] == "dash")
                observation(row, "dash_displacement", distance, speed * dt + 5., "cm", previous_sample["seq"],
                            None if supported else "unsupported in-dash interval or movement-state mismatch")
            previous_sample = row
        elif active is not None and event == "ability_end" and row["related_id"] == active["related_id"]:
            dt = row["elapsed_s"] - active["elapsed_s"]
            tail_gap = row["elapsed_s"] - previous_point["elapsed_s"]
            supported = (duration_supported and sample_count > 0 and 0 <= tail_gap <= .15
                         and supported_tick(row) and row["detail"] == "dash"
                         and row["movement_mode"] == "walking")
            # FinishRound() ends an active dash before run_end. That endpoint
            # cannot establish the activation's natural duration.
            terminal_boundary = abs(row["elapsed_s"] - rows[-1]["elapsed_s"]) <= .001
            reason = ("activation censored at run boundary" if terminal_boundary else
                      None if supported else "unsupported dash duration: sample gap, state or terminal tick")
            # At normal completion, EndDash runs on the first update at/after
            # maximum distance. One observed end-tick interval plus1ms is a
            # conservative quantization allowance, never an incoming speed limit.
            tick_allowance = row["delta_s"] if supported_tick(row) else 0.
            observation(row, "dash_duration", dt, maximum_duration + tick_allowance + .001,
                        "seconds", active["seq"], reason)
            active = None
            previous_sample = previous_point = None
    if active is not None:
        observation(rows[-1], "dash_duration", rows[-1]["elapsed_s"] - active["elapsed_s"],
                    maximum_duration + .001, "seconds", active["seq"], "unfinished activation in partial capture")
    return result


def derive(raw, profile_id="survive-lucian-practice-v1"):
    profile = load_profile(profile_id)
    return derive_rows(load_rows(raw, profile), profile)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", choices=sorted(PROFILE_IDS), default="survive-lucian-practice-v1")
    args = parser.parse_args()
    with args.capture.open("rb") as source:
        records = derive(source.read(legacy.MAX_BYTES + 1), args.profile)
    with args.output.open("x", encoding="utf-8", newline="\n") as target:
        for record in records:
            target.write(json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

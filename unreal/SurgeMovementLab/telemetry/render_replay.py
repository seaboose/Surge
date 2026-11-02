"""Export validated Survive v3 evidence to a standalone, offline replay.

The selected local profile is explicit. Source kind is an operator assertion,
not evidence authenticity. Player samples are replayed, never resimulated.
"""
import argparse
import base64
from bisect import bisect_right
import hashlib
import json
import math
from pathlib import Path
import re

from audit_v3 import summarize
from prepare_v2 import MAX_BYTES
from prepare_v3 import PROFILE_IDS, PROFILE_ROOT, derive_rows, load_profile, load_rows

SOURCE_KINDS = {"unspecified", "owned-unreal-capture", "synthetic-fixture"}
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
TEMPLATE = Path(__file__).with_name("replay-template.html")
POINT_EVENTS = {"run_start", "sample", "ability_start", "ability_end", "run_end"}
TERMINALS = {"threat_hit", "threat_expired", "threat_blocked", "threat_cancelled"}


def script_json(value):
    """JSON data inside a script element cannot terminate its HTML container."""
    result = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    for character, replacement in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                                   ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        result = result.replace(character, replacement)
    return result


def build_points(rows):
    points = [{"t": row["elapsed_s"], "seq": row["seq"], "x": row["x_cm"],
               "y": row["y_cm"], "mode": row["movement_mode"], "event": row["event"],
               "detail": row["detail"], "next_eligible": False, "next_coverage": "capture tail"}
              for row in rows if row["event"] in POINT_EVENTS]
    for left, right in zip(points, points[1:]):
        dt = right["t"] - left["t"]
        blink = (left["mode"] == "blink" or right["mode"] == "blink"
                 or left["detail"] == "blink" or right["detail"] == "blink")
        supported = left["mode"] in {"walking", "dash"} and right["mode"] in {"walking", "dash"}
        if dt <= 0:
            reason = "same-time recorded boundary"
        elif dt > .15:
            reason = "unobserved gap over 150 ms"
        elif blink:
            reason = "blink boundary; no interpolation"
        elif not supported:
            reason = "unsupported movement transition"
        else:
            reason = "sampled linear interpolation"
            left["next_eligible"] = True
        left["next_coverage"] = reason
    return points


def player_at(points, elapsed):
    """Reference replay semantics, also implemented by the static viewer."""
    if not points:
        return None
    index = bisect_right([p["t"] for p in points], elapsed) - 1
    if index < 0:
        return dict(x=points[0]["x"], y=points[0]["y"], coverage="before first position", seq=points[0]["seq"])
    left = points[index]
    if abs(elapsed - left["t"]) <= 1e-9:
        return dict(x=left["x"], y=left["y"], coverage="recorded position", seq=left["seq"])
    if index + 1 < len(points) and left["next_eligible"]:
        right = points[index + 1]
        alpha = (elapsed - left["t"]) / (right["t"] - left["t"])
        return dict(x=left["x"] + alpha * (right["x"] - left["x"]),
                    y=left["y"] + alpha * (right["y"] - left["y"]),
                    coverage=left["next_coverage"], seq=left["seq"])
    return dict(x=left["x"], y=left["y"], coverage="holding recorded position: " + left["next_coverage"], seq=left["seq"])


def build_threats(rows, profile):
    groups = {}
    for row in rows:
        if not row["event"].startswith("threat_"):
            continue
        group = groups.setdefault(row["related_id"], {})
        key = "warning" if row["event"] == "threat_warning" else "fire" if row["event"] == "threat_fire" else "terminal"
        group[key] = row
    result = []
    for related_id, group in groups.items():
        warning, fire, terminal = group["warning"], group.get("fire"), group.get("terminal")
        circle = warning["detail"].startswith("circle")
        speed = math.hypot(warning["velocity_x_cm_s"], warning["velocity_y_cm_s"])
        max_distance = profile["projectile"]["range_cm"]
        # Older captures may record terrain-blocked projectiles. Do not extend
        # their reconstructed position through the recorded collision endpoint.
        if not circle and terminal and terminal["event"] == "threat_blocked" and speed:
            projected = ((terminal["threat_x_cm"] - warning["source_x_cm"]) * warning["velocity_x_cm_s"]
                         + (terminal["threat_y_cm"] - warning["source_y_cm"]) * warning["velocity_y_cm_s"]) / speed
            max_distance = min(max_distance, max(0., projected))
        result.append({"id": related_id, "pattern": warning["detail"],
                       "warning_s": warning["elapsed_s"], "fire_s": fire["elapsed_s"] if fire else None,
                       "terminal_s": terminal["elapsed_s"] if terminal else None,
                       "warning_seq": warning["seq"], "fire_seq": fire["seq"] if fire else None,
                       "terminal_seq": terminal["seq"] if terminal else None,
                       "terminal_event": terminal["event"] if terminal else None,
                       "source": [warning["source_x_cm"], warning["source_y_cm"]],
                       "target": [warning["a"], warning["b"]],
                       "velocity": [warning["velocity_x_cm_s"], warning["velocity_y_cm_s"]],
                       "speed": speed, "radius": warning["c"], "max_distance": max_distance,
                       "terminal_position": [terminal["threat_x_cm"], terminal["threat_y_cm"]] if terminal else None})
    return result


def projectile_at(threat, elapsed):
    if threat["fire_s"] is None or elapsed < threat["fire_s"] or threat["speed"] <= 0:
        return None
    traveled = min(threat["max_distance"], max(0., elapsed - threat["fire_s"]) * threat["speed"])
    return [threat["source"][i] + threat["velocity"][i] / threat["speed"] * traveled for i in (0, 1)]


def build_model(raw, *, profile_id, source_kind="unspecified"):
    if source_kind not in SOURCE_KINDS:
        raise ValueError("Unsupported operator-asserted source kind")
    profile = load_profile(profile_id)
    profile_raw = (PROFILE_ROOT / (profile_id + ".json")).read_bytes()
    if hashlib.sha256(profile_raw).hexdigest() != profile["file_sha256"]:
        raise ValueError("Profile changed while preparing replay; retry after it is frozen")
    rows = load_rows(raw, profile)
    # Validate ability lifecycle as well as the scalar and threat contracts.
    derive_rows(rows, profile)
    summary = summarize(rows, profile)
    return {"schema": "survive-offline-replay-v1", "source_sha256": hashlib.sha256(raw).hexdigest(),
            "profile_sha256": profile["file_sha256"], "source_kind_operator_asserted": source_kind,
            "authenticity": "not_attested", "profile": profile, "session_id": rows[0]["session_id"],
            "duration_s": rows[-1]["elapsed_s"], "completion": rows[-1]["detail"],
            "rows": rows, "points": build_points(rows), "threats": build_threats(rows, profile),
            "summary": summary,
            "arena_illustration": {"half_extent": 1300, "fingerprint_available": False,
                                   "obstacles": [[-520, -430, -280, -70], [300, 240, 580, 480]]}}


def render_model(model):
    template = TEMPLATE.read_text(encoding="utf-8")
    script = re.search(r'<script id="replay-code">([\s\S]*?)</script>', template)
    style = re.search(r'<style id="replay-style">([\s\S]*?)</style>', template)
    if not script or not style or template.count("__SURVIVE_PAYLOAD_JSON__") != 1:
        raise ValueError("Invalid local replay template")
    def csp_hash(text):
        return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode("ascii")
    # Resolve trusted template placeholders before embedding data. Otherwise an
    # incoming detail containing a placeholder could be silently rewritten.
    output = (template.replace("__SURVIVE_SCRIPT_SHA256__", csp_hash(script.group(1)))
              .replace("__SURVIVE_STYLE_SHA256__", csp_hash(style.group(1)))
              .replace("__SURVIVE_PAYLOAD_JSON__", script_json(model)))
    if len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("Replay export exceeds 16 MiB")
    return output


def export_replay(raw, output, *, profile_id, source_kind="unspecified"):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Replay output already exists")
    model = build_model(raw, profile_id=profile_id, source_kind=source_kind)
    html = render_model(model)
    # Exclusive creation also protects against another process creating the path
    # after validation. No existing evidence or source capture is overwritten.
    with output.open("x", encoding="utf-8", newline="\n") as target:
        target.write(html)
    return {"source_sha256": model["source_sha256"], "profile_sha256": model["profile_sha256"],
            "profile_id": profile_id, "source_records": len(model["rows"]),
            "trajectory_points": len(model["points"]), "completion": model["completion"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path, help="New local HTML file; parent directory must exist")
    parser.add_argument("--profile", required=True, choices=sorted(PROFILE_IDS))
    parser.add_argument("--source-kind", choices=sorted(SOURCE_KINDS), default="unspecified",
                        help="Operator assertion only; does not establish authenticity")
    args = parser.parse_args()
    try:
        with args.capture.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        result = export_replay(raw, args.output, profile_id=args.profile, source_kind=args.source_kind)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

"""Create paired, explicitly synthetic mobility/replay showcases locally.

Fixed coordinate fixtures exercise evidence tools; no game or input device runs.
Synthetic labels and the intentional-change description remain outside raw rows.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import uuid

from analyze_v3 import build_bundle
from prepare_v3 import load_profile

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "telemetry" / "local"
PROFILE = "survive-lucian-practice-v1"
DASH_TICK_DURATION = 19 / 60


def _position(t, excess):
    """This single authored trajectory is a fixture, not collision simulation."""
    if t < 1: return -700., -800.
    if t < 3: return -700 + 335 * (t - 1), -800.
    if t < 3 + DASH_TICK_DURATION: return -30 + min(425., 1350 * (t - 3)), -800.
    if t < 4 + DASH_TICK_DURATION: return 395 + 335 * (t - 3 - DASH_TICK_DURATION), -800.
    if t < 7: return 730., -800.
    if t < 8: return 730., -400.
    if t < 10: return 730., -400 + 335 * (t - 8)
    if t < 10 + (8 / 60 if excess else DASH_TICK_DURATION):
        return 730., 270 + min(425., (425 / .12 if excess else 1350) * (t - 10))
    if t < 14: return 730., 695.
    if t < 16: return 730 - 335 * (t - 14), 695.
    if t < 16 + DASH_TICK_DURATION: return 60 - min(425., 1350 * (t - 16)), 695.
    if t < 20: return -365., 695.
    if t < 22: return -765., 695 - 335 * (t - 20)
    if t < 22 + DASH_TICK_DURATION: return -765., 25 - min(425., 1350 * (t - 22))
    if t < 24: return -765., -400.
    if t < 26: return -765., -400 - 335 * (t - 24)
    if t < 28: return -765., -1070.
    if t < 30: return -765 + 335 * (t - 28), -1070.
    if t < 30 + DASH_TICK_DURATION: return -95 + min(425., 1350 * (t - 30)), -1070.
    if t < 40: return 330., -1070.
    if t < 42: return 330 - 335 * (t - 40), -670.
    return -340., -670.


def create_capture(*, excess=False):
    """Return strict v3 bytes; scenario identity never enters the event schema."""
    profile = load_profile(PROFILE)
    dash_spans = [(3., 3 + DASH_TICK_DURATION),
                  (10., 10 + (8 / 60 if excess else DASH_TICK_DURATION)),
                  (16., 16 + DASH_TICK_DURATION), (22., 22 + DASH_TICK_DURATION),
                  (30., 30 + DASH_TICK_DURATION)]
    events = []
    sid = ("2" if excess else "1") * 32

    def add(t, event="sample", *, priority=5, position=None, mode=None, **fields):
        x, y = _position(t, excess) if position is None else position
        if mode is None:
            mode = "dash" if any(start <= t < end for start, end in dash_spans) else "walking"
        row = dict(schema="survive-v3", session_id=sid, seq=0, elapsed_s=t,
                   event=event, x_cm=x, y_cm=y, z_cm=90, movement_mode=mode,
                   related_id="", detail="", a=0, b=0, c=0, d=0,
                   source_x_cm=0, source_y_cm=0, velocity_x_cm_s=0, velocity_y_cm_s=0,
                   server_tick=round(t * 60), delta_s=1 / 60, monotonic_s=t,
                   profile_id=PROFILE, path_radius_cm=41, hit_radius_cm=65, visual_radius_cm=50,
                   threat_x_cm=0, threat_y_cm=0, nearest_clearance_cm=0,
                   clearance_valid=False, baseline_threat="unknown")
        row.update(fields)
        events.append((t, priority, len(events), row))

    add(0, "run_start", priority=0, detail="practice", a=1337, b=.5, c=60, d=3)
    for index in range(1801):
        add(index / 30)
    for index, (start, end) in enumerate(dash_spans, 1):
        context = dict(detail="dash", related_id=f"ability-{index}", a=425,
                       b=profile["dash"]["max_duration_s"], c=4)
        for event, priority in (("ability_request", 1), ("ability_grant", 2), ("ability_start", 3)):
            add(start, event, priority=priority, mode="dash" if event == "ability_start" else "walking", **context)
        add(end, "ability_end", priority=4, mode="walking", **context)
    blinks = [(7., (730., -800.), (730., -400.)),
              (20., (-365., 695.), (-765., 695.)),
              (40., (330., -1070.), (330., -670.))]
    for index, (t, before, after) in enumerate(blinks, 6):
        context = dict(detail="blink", related_id=f"ability-{index}", a=400, b=0, c=12)
        for event, priority in (("ability_request", 1), ("ability_grant", 2), ("ability_start", 3)):
            add(t, event, priority=priority, position=before,
                mode="blink" if event == "ability_start" else "walking", **context)
        add(t, "ability_end", priority=4, position=after, mode="blink", **context)
    commands = [(1., (0., -800.)), (3 + DASH_TICK_DURATION, (730., -800.)),
                (8., (730., 270.)), (14., (60., 695.)), (20., (-765., 25.)),
                (24., (-765., -1070.)), (28., (-95., -1070.)), (40., (-340., -670.))]
    for index, (t, destination) in enumerate(commands, 1):
        # A command sharing a blink timestamp follows that blink's recorded
        # landing; its position must not appear to teleport before ability_start.
        for event, priority in (("command_request", 6), ("command_grant", 7)):
            add(t, event, priority=priority, detail="move", related_id=f"command-{index}",
                a=destination[0], b=destination[1])
    for t in (4 + DASH_TICK_DURATION, 26., 42.):
        add(t, "command_stop", detail="stop")

    def projectile(key, warning, source, target, outcome, terminal, initial):
        dx, dy = target[0] - source[0], target[1] - source[1]
        length = math.hypot(dx, dy)
        vx, vy = 1200 * dx / length, 1200 * dy / length
        common = dict(detail="projectile_" + ("aimed" if initial else "random"), related_id=key,
                      a=target[0], b=target[1], c=70, d=1200,
                      source_x_cm=source[0], source_y_cm=source[1], velocity_x_cm_s=vx,
                      velocity_y_cm_s=vy, baseline_threat="yes" if initial else "no")
        fire = warning + .25
        add(warning, "threat_warning", threat_x_cm=source[0], threat_y_cm=source[1], **common)
        add(fire, "threat_fire", threat_x_cm=source[0], threat_y_cm=source[1], **common)
        add(terminal, "threat_" + outcome, threat_x_cm=source[0] + vx * (terminal - fire),
            threat_y_cm=source[1] + vy * (terminal - fire), **common)

    def circle(key, warning, target, aimed, outcome):
        px, py = _position(warning, excess)
        initial = math.hypot(px - target[0], py - target[1]) <= 315
        common = dict(detail="circle_" + ("aimed" if aimed else "random"), related_id=key,
                      a=target[0], b=target[1], c=250, d=.75,
                      source_x_cm=target[0], source_y_cm=target[1],
                      threat_x_cm=target[0], threat_y_cm=target[1], baseline_threat="yes" if initial else "no")
        add(warning, "threat_warning", **common)
        add(warning + .75, "threat_fire", **common)
        add(warning + .75, "threat_" + outcome, **common)

    projectile("1", .5, (-700., -1250.), (-700., -800.), "hit", 61 / 60, True)
    projectile("2", 5., (-800., 800.), (500., 800.), "expired", 5.25 + 1300 / 1200, False)
    circle("3", 8., (730., -400.), True, "hit")
    circle("4", 9.5, (730., 102.5), True, "expired")
    circle("5", 13., (-500., -800.), False, "expired")
    circle("6", 19.5, (-365., 695.), True, "expired")
    add(60., "run_end", priority=10, mode="ended", detail="completed")
    ordered = sorted(events, key=lambda item: item[:3])
    return ("\n".join(json.dumps(dict(item[3], seq=index), allow_nan=False, separators=(",", ":"))
                      for index, item in enumerate(ordered)) + "\n").encode()


def create_showcase(output):
    """Write a new local directory, two replay bundles and reopened Surge cases."""
    output = Path(output).resolve()
    if not output.is_relative_to(LOCAL.resolve()) or output == LOCAL.resolve():
        raise ValueError("Showcase output must be a new directory within telemetry/local")
    LOCAL.mkdir(exist_ok=True)
    output.mkdir(exist_ok=False)
    sys.path.insert(0, str(ROOT.parents[1]))
    import engine
    records = []
    for name, excess in (("legal-mobility", False), ("dash-speed-change", True)):
        raw = create_capture(excess=excess)
        directory = output / name
        summary = build_bundle(raw, directory, profile_id=PROFILE, source_kind="synthetic-fixture",
                               phase="development", include_replay=True)
        config = json.loads((directory / "policy.json").read_text())
        current = engine.parse_bytes((directory / "surge.jsonl").read_bytes(), "SYNTHETIC-" + name + ".jsonl")
        result = engine.analyze(current, None, config)
        case = output / (name + ".surge.case.json")
        receipt = engine.save_case(case, current, None, config, result)
        reopened = engine.open_case(case)
        if reopened[3] != result:
            raise ValueError("Synthetic showcase case did not reopen identically")
        records.append({"scenario": name, "source_sha256": hashlib.sha256(raw).hexdigest(),
                        "counts": dict(Counter(record["status"] for record in result["records"])),
                        "audit_issues": summary["audit_issues"], "case": case.name,
                        "case_sha256": receipt["sha256"], "reopen_matches": True})
    receipt = {"schema": "survive-synthetic-showcase-v1", "source_kind": "synthetic-fixture",
               "not_unreal_evidence": True, "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "profile_id": PROFILE, "cases": records,
               "external_actions": [{"scenario": "dash-speed-change", "activation_start_s": 10.,
                                     "actual_distance_cm": 425, "actual_travel_duration_s": .12,
                                     "nominal_speed_cm_s": 1350, "changed_speed_cm_s": 425 / .12}],
               "limits": ["Authored coordinate fixtures, not engine simulation or human input.",
                          "Paired examples are correlated and are not an accuracy evaluation.",
                          "Six scripted attacks illustrate patterns, not the native random scheduler.",
                          "Server clearance is explicitly unavailable; replay uses sampled geometry.",
                          "Transition Unknowns are retained; No finding does not prove exact movement equivalence."]}
    with (output / "showcase.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New directory inside telemetry/local")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or LOCAL / ("synthetic-mobility-showcase-" + stamp + "-" + uuid.uuid4().hex[:8])
    receipt = create_showcase(output)
    print(json.dumps({"output": str(output.resolve()), "cases": receipt["cases"]}, allow_nan=False))


if __name__ == "__main__":
    main()

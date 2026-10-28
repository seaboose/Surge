"""Replay geometry audit and descriptive metrics, separate from detector decisions.

Recorded player positions and ability discontinuities drive replay; this is not a
new bot simulation. Sampled interpolation has explicit timing/coverage limits.
"""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import math

TERMINALS = {"threat_hit", "threat_expired", "threat_blocked", "threat_cancelled"}
DETAILS = {"projectile_aimed", "projectile_random", "circle_aimed", "circle_random"}


def segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    dd = dx * dx + dy * dy
    alpha = max(0., min(1., ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / dd)) if dd else 0.
    return math.hypot(point[0] - start[0] - alpha * dx, point[1] - start[1] - alpha * dy)


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lower = int(index)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (index - lower)


def _finite_ratio(numerator, denominator):
    ratio = numerator / denominator if denominator > 0 else None
    return ratio if ratio is not None and math.isfinite(ratio) else None


def _run_quality(rows, samples, profile):
    """Describe observed coverage; never infer unrecorded frames or authenticity."""
    duration = rows[-1]["elapsed_s"] - rows[0]["elapsed_s"]
    monotonic_duration = rows[-1]["monotonic_s"] - rows[0]["monotonic_s"]
    intervals = [b["elapsed_s"] - a["elapsed_s"] for a, b in zip(samples, samples[1:])]
    monotonic_intervals = [b["monotonic_s"] - a["monotonic_s"] for a, b in zip(samples, samples[1:])]
    span = samples[-1]["elapsed_s"] - samples[0]["elapsed_s"] if samples else 0.
    supported = sum(dt for dt in intervals if 0 < dt <= .15)
    return {"scope": "Recorded sample intervals only; short intervals do not prove collision or input coverage.",
            "complete_round": rows[-1]["detail"] == "completed",
            "observed_simulation_s": duration,
            "target_sample_hz": profile["capture"]["sample_hz_target"],
            "observed_sample_hz_over_span": _finite_ratio(len(samples) - 1, span),
            "sample_span_s": span,
            "supported_sample_interval_s": supported,
            "supported_sample_interval_fraction": min(1., supported / duration) if duration > 0 else None,
            "gap_over_150ms_s": sum(dt for dt in intervals if dt > .15),
            "leading_unsampled_s": samples[0]["elapsed_s"] - rows[0]["elapsed_s"] if samples else None,
            "trailing_unsampled_s": rows[-1]["elapsed_s"] - samples[-1]["elapsed_s"] if samples else None,
            "simulation_per_monotonic_second": _finite_ratio(duration, monotonic_duration),
            "sample_monotonic_interval_s": {"p50": percentile(monotonic_intervals, .5),
                                             "p95": percentile(monotonic_intervals, .95),
                                             "max": max(monotonic_intervals, default=None)}}


def _prewarning_motion(rows, warning_index, samples, sample_times):
    """Use a preceding sample and the actual warning position, with no gap/ability interpolation."""
    warning = rows[warning_index]
    unavailable = {"status": "unavailable", "interval_s": None, "displacement_cm": None}
    prior_index = bisect_left(sample_times, warning["elapsed_s"]) - 1
    if prior_index < 0 or warning["movement_mode"] != "walking":
        return unavailable
    row_index, previous = samples[prior_index]
    dt = warning["elapsed_s"] - previous["elapsed_s"]
    if not 0 < dt <= .15 or previous["movement_mode"] != "walking":
        return unavailable
    if any(r["event"] in {"ability_start", "ability_end"} or r["movement_mode"] in {"blink", "dash"}
           for r in rows[row_index + 1:warning_index]):
        return unavailable
    displacement = math.hypot(warning["x_cm"] - previous["x_cm"], warning["y_cm"] - previous["y_cm"])
    return {"status": "observed_displacement" if displacement > .01 else "no_observed_displacement",
            "interval_s": dt, "displacement_cm": displacement}


def _accepted_context(group, rows, commands, command_indices, samples, sample_times, *, action_scope=False):
    warning = group["warning"]
    warning_index = group["warning_index"]
    terminal_index = group.get("terminal_index", len(rows) - 1)
    next_command = bisect_right(command_indices, warning_index)
    accepted = commands[next_command] if next_command < len(commands) else None
    if accepted and accepted[0] >= terminal_index:
        accepted = None
    seq_key = "action_seq" if action_scope else "command_seq"
    scope = ("Server warning to first later accepted move/stop/dash/blink event; descriptive, no execution or causal guarantee."
             if action_scope else "Server warning to first later accepted move command; descriptive, no causal attribution.")
    result = {"scope": scope,
              "status": "observed" if accepted else "none_before_threat_terminal" if "terminal" in group else "none_before_capture_end",
              "latency_simulation_s": None, "latency_monotonic_s": None,
              seq_key: None, "other_active_threats_at_warning": group["other_active_at_warning"],
              "other_active_threats_at_command": None,
              "prewarning_motion": _prewarning_motion(rows, warning_index, samples, sample_times)}
    if accepted:
        _, command, active_count = accepted
        result.update(latency_simulation_s=command["elapsed_s"] - warning["elapsed_s"],
                      latency_monotonic_s=command["monotonic_s"] - warning["monotonic_s"],
                      other_active_threats_at_command=max(0, active_count - 1))
        result[seq_key] = command["seq"]
    if action_scope:
        result["action_kind"] = ("move" if command["event"] == "command_grant" else
                                 "stop" if command["event"] == "command_stop" else command["detail"]) if accepted else None
        result["action_event"] = command["event"] if accepted else None
        # A grant is receipt/authorization context, not proof the movement ran.
        result["other_active_threats_at_action"] = result.pop("other_active_threats_at_command")
    return result


def _projectile_clearance(group, points, times, profile):
    fire = group.get("fire")
    terminal = group.get("terminal")
    if fire is None or terminal is None or terminal["event"] == "threat_cancelled":
        return None, 0., "censored or not fired", 0.
    begin, end = fire["elapsed_s"], terminal["elapsed_s"]
    if terminal["event"] == "threat_blocked":
        vx, vy = fire["velocity_x_cm_s"], fire["velocity_y_cm_s"]
        speed_squared = vx * vx + vy * vy
        if speed_squared:
            # The terminal timestamp is a frame boundary, while the recorded
            # collision endpoint can lie partway through that frame. Never extend
            # the reconstructed missile through terrain until the frame ends.
            contact_age = ((terminal["threat_x_cm"] - fire["source_x_cm"]) * vx
                           + (terminal["threat_y_cm"] - fire["source_y_cm"]) * vy) / speed_squared
            end = min(end, max(begin, begin + contact_age))
    if end <= begin:
        return None, 0., "no flight interval", 0.
    first = max(0, bisect_right(times, begin) - 1)
    last = min(len(points) - 1, bisect_left(times, end))
    minimum = None
    covered = 0.
    supported_max_interval = 0.
    combined = profile["movement"]["hit_radius_cm"] + profile["projectile"]["radius_cm"]
    for index in range(first, last):
        left, right = points[index], points[index + 1]
        dt = right["elapsed_s"] - left["elapsed_s"]
        lo, hi = max(begin, left["elapsed_s"]), min(end, right["elapsed_s"])
        if hi <= lo or not 0 < dt <= .15:
            continue
        # Blink start/end at one timestamp is a discontinuity, never a vulnerable
        # interpolated trajectory. Conservative exclusion also covers cast edges.
        if left["movement_mode"] == "blink" or right["movement_mode"] == "blink":
            continue
        relative = []
        for t in (lo, hi):
            alpha = (t - left["elapsed_s"]) / dt
            px = left["x_cm"] + alpha * (right["x_cm"] - left["x_cm"])
            py = left["y_cm"] + alpha * (right["y_cm"] - left["y_cm"])
            qx = fire["source_x_cm"] + fire["velocity_x_cm_s"] * (t - begin)
            qy = fire["source_y_cm"] + fire["velocity_y_cm_s"] * (t - begin)
            relative.append((qx - px, qy - py))
        clearance = segment_distance((0, 0), relative[0], relative[1]) - combined
        minimum = clearance if minimum is None else min(minimum, clearance)
        covered += hi - lo
        supported_max_interval = max(supported_max_interval, dt)
    fraction = min(1., covered / (end - begin))
    return minimum, fraction, ("sampled interpolation" if fraction >= .99 else "partial sampled interpolation"), supported_max_interval


def summarize(rows, profile):
    groups = {}
    points = [r for r in rows if r["event"] == "sample" or r["event"] in {"ability_start", "ability_end"}]
    times = [r["elapsed_s"] for r in points]
    samples = [r for r in rows if r["event"] == "sample"]
    indexed_samples = [(i, r) for i, r in enumerate(rows) if r["event"] == "sample"]
    sample_times = [r["elapsed_s"] for r in samples]
    intervals = [b["elapsed_s"] - a["elapsed_s"] for a, b in zip(samples, samples[1:])]
    strata = defaultdict(Counter)
    audit_issues = []
    threat_records = []
    active = set()
    peak_active = 0
    accepted_commands = []
    accepted_actions = []
    for row_index, row in enumerate(rows):
        if row["event"] == "command_grant" and row["detail"] == "move":
            accepted_commands.append((row_index, row, len(active)))
            accepted_actions.append((row_index, row, len(active)))
        elif ((row["event"] == "command_stop" and row["detail"] == "stop") or
              (row["event"] == "ability_grant" and row["detail"] in {"dash", "blink"})):
            accepted_actions.append((row_index, row, len(active)))
        if not row["event"].startswith("threat_"):
            continue
        key = row["related_id"]
        if not key or row["detail"] not in DETAILS:
            raise ValueError("Threat records require a known pattern and ID")
        group = groups.setdefault(key, {"detail": row["detail"]})
        if group["detail"] != row["detail"]:
            raise ValueError("Threat changed pattern/targeting identity")
        kind = "warning" if row["event"] == "threat_warning" else "fire" if row["event"] == "threat_fire" else "terminal"
        if kind == "terminal" and row["event"] not in TERMINALS:
            raise ValueError("Unsupported threat event")
        if kind in group:
            raise ValueError("Duplicate threat lifecycle stage")
        if kind != "warning" and "warning" not in group:
            raise ValueError("Threat event precedes warning")
        if kind == "terminal" and row["event"] != "threat_cancelled" and "fire" not in group:
            raise ValueError("Resolved threat did not fire")
        if "terminal" in group:
            raise ValueError("Threat event after terminal outcome")
        if kind == "warning":
            circle = row["detail"].startswith("circle")
            radius = profile["circle" if circle else "projectile"]["radius_cm"]
            payload = profile["circle"]["delay_s"] if circle else profile["projectile"]["speed_cm_s"]
            speed = math.hypot(row["velocity_x_cm_s"], row["velocity_y_cm_s"])
            expected_speed = 0 if circle else profile["projectile"]["speed_cm_s"]
            if abs(row["c"] - radius) > .01 or abs(row["d"] - payload) > .01 or abs(speed - expected_speed) > .01:
                raise ValueError("Threat descriptor differs from selected profile; geometry audit unavailable")
        if "warning" in group:
            fixed = ("a", "b", "c", "d", "source_x_cm", "source_y_cm", "velocity_x_cm_s", "velocity_y_cm_s")
            if any(abs(row[field] - group["warning"][field]) > .001 for field in fixed):
                raise ValueError("Threat changed committed target or flight parameters")
        group[kind] = row
        if kind == "warning":
            group["warning_index"] = row_index
            group["other_active_at_warning"] = len(active)
            active.add(key)
            peak_active = max(peak_active, len(active))
        elif kind == "terminal":
            group["terminal_index"] = row_index
            active.discard(key)
    command_indices = [command[0] for command in accepted_commands]
    action_indices = [action[0] for action in accepted_actions]
    for key, group in groups.items():
        warning, fire, terminal = group["warning"], group.get("fire"), group.get("terminal")
        pattern = group["detail"]
        counts = strata[pattern]
        counts["warned"] += 1
        counts["fired"] += fire is not None
        outcome = terminal["event"].removeprefix("threat_") if terminal else "censored"
        if outcome == "blocked" and not profile["projectile"].get("blocked_by_terrain", False):
            audit_issues.append("Threat " + key + ": blocked outcome contradicts selected pass-through-terrain profile")
        counts[outcome] += 1
        counts["reported_initial_threat_" + warning["baseline_threat"]] += 1
        nominal_delay = profile["circle"]["delay_s"] if pattern.startswith("circle") else profile["projectile"]["cast_delay_s"]
        observed_delay = fire["elapsed_s"] - warning["elapsed_s"] if fire else None
        if fire:
            if observed_delay + .001 < nominal_delay:
                audit_issues.append("Threat " + key + ": fired before selected warning delay")
        combined = profile["movement"]["hit_radius_cm"] + profile["circle" if pattern.startswith("circle") else "projectile"]["radius_cm"]
        best_heading_degrees = nominal_circle_budget = None
        unavailable_reason = None
        if pattern.startswith("circle"):
            initial_distance = math.hypot(warning["x_cm"] - warning["a"], warning["y_cm"] - warning["b"])
            initial = initial_distance <= combined
            minimum_escape = max(0., combined - initial_distance)
            ideal_walk_possible = None
            ideal_window = None
            if initial:
                nominal_circle_budget = nominal_delay - minimum_escape / profile["movement"]["walk_speed_cm_s"]
                ideal_walk_possible = nominal_circle_budget > 0
            else:
                unavailable_reason = "not initially exposed; no escape is required"
            clearance = (math.hypot(fire["x_cm"] - fire["a"], fire["y_cm"] - fire["b"]) - combined) if fire else None
            fraction, method = (1., "circle fire position") if fire else (0., "not fired")
            supported_max_interval = 0.
        else:
            speed = math.hypot(warning["velocity_x_cm_s"], warning["velocity_y_cm_s"])
            if speed <= 0:
                raise ValueError("Projectile has zero committed speed")
            endpoint = (warning["source_x_cm"] + warning["velocity_x_cm_s"] / speed * profile["projectile"]["range_cm"],
                        warning["source_y_cm"] + warning["velocity_y_cm_s"] / speed * profile["projectile"]["range_cm"])
            initial = segment_distance((warning["x_cm"], warning["y_cm"]),
                                       (warning["source_x_cm"], warning["source_y_cm"]), endpoint) <= combined
            minimum_escape, ideal_walk_possible, ideal_window = None, None, None
            dx, dy = warning["x_cm"] - warning["source_x_cm"], warning["y_cm"] - warning["source_y_cm"]
            ux, uy = warning["velocity_x_cm_s"] / speed, warning["velocity_y_cm_s"] / speed
            along, lateral = dx * ux + dy * uy, abs(dx * uy - dy * ux)
            walk_speed = profile["movement"]["walk_speed_cm_s"]
            if pattern != "projectile_aimed":
                unavailable_reason = "model requires a centered aimed projectile"
            elif not initial:
                unavailable_reason = "not initially exposed; no escape is required"
            elif lateral > .001:
                unavailable_reason = "warning position is not centered on the committed trajectory"
            elif not 0 <= along <= profile["projectile"]["range_cm"]:
                unavailable_reason = "closest-point model lies outside the projectile center range"
            elif not 0 < walk_speed < speed:
                unavailable_reason = "model requires projectile speed above walking speed"
            else:
                # For the best straight heading, cos(theta)=walk_speed/speed.
                # This is not a perpendicular-only sidestep. Tangency is a hit,
                # so the reported budget is a supremum: start strictly earlier.
                ideal_window = nominal_delay + along / speed - combined / walk_speed
                best_heading_degrees = math.degrees(math.acos(walk_speed / speed))
                ideal_walk_possible = ideal_window > 0
            clearance, fraction, method, supported_max_interval = _projectile_clearance(group, points, times, profile)
        counts["geometric_initial_threat"] += initial
        counts["no_ideal_walking_escape"] += ideal_walk_possible is False
        # This geometric counterfactual deliberately excludes terrain. Record the
        # server's terrain-aware estimate separately; do not overwrite either.
        if initial and fire and outcome not in {"censored", "cancelled"}:
            counts["geometric_exposed_resolved"] += 1
            counts["geometric_exposed_hits"] += outcome == "hit"
        consistency = "unavailable"
        if terminal and terminal["clearance_valid"] and clearance is not None:
            allowance = (profile["projectile"]["speed_cm_s"] + profile["dash"]["speed_cm_s"]) * supported_max_interval + 5.
            if pattern.startswith("circle"):
                allowance = 5.
            consistency = ("partial_sampling_unavailable" if fraction < .99 else
                           "within_sampling_allowance" if abs(clearance - terminal["nearest_clearance_cm"]) <= allowance
                           else "review_geometry_or_sampling")
            if consistency.startswith("review"):
                audit_issues.append("Threat " + key + ": clearance differs beyond sampled timing allowance")
        threat_records.append({"threat_id": key, "pattern": pattern, "outcome": outcome,
                               "warning_s": warning["elapsed_s"], "fire_s": fire["elapsed_s"] if fire else None,
                               "terminal_s": terminal["elapsed_s"] if terminal else None,
                               "server_initial_threat": warning["baseline_threat"],
                               "geometric_initial_threat_without_terrain": initial,
                               "nominal_walking_escape_possible_without_terrain": ideal_walk_possible,
                               "nominal_centered_best_heading_budget_s": ideal_window,
                               "nominal_best_heading_degrees_from_projectile_forward": best_heading_degrees,
                               "nominal_circle_walk_delay_budget_s": nominal_circle_budget,
                               "nominal_warning_delay_s": nominal_delay, "observed_warning_to_fire_s": observed_delay,
                               "nominal_model_unavailable_reason": unavailable_reason,
                               "ideal_walking_escape_possible_without_terrain": ideal_walk_possible,
                               "minimum_circle_escape_cm": minimum_escape,
                               "ideal_centered_perpendicular_window_s": ideal_window,
                               "sampled_nearest_clearance_cm": clearance, "sampled_flight_coverage": fraction,
                               "method": method, "clearance_consistency": consistency,
                               "command_after_warning": _accepted_context(group, rows, accepted_commands, command_indices,
                                                                          indexed_samples, sample_times),
                               "action_after_warning": _accepted_context(group, rows, accepted_actions, action_indices,
                                                                          indexed_samples, sample_times, action_scope=True),
                               "server_nearest_clearance_cm": terminal["nearest_clearance_cm"] if terminal and terminal["clearance_valid"] else None})
    end = rows[-1]
    return {"schema": "survive-run-summary-v2", "opportunity_model_version": "nominal-walk-v2",
            "legacy_opportunity_field_aliases": {
                "ideal_walking_escape_possible_without_terrain": "nominal_walking_escape_possible_without_terrain",
                "ideal_centered_perpendicular_window_s": "nominal_centered_best_heading_budget_s"},
            "profile_id": profile["id"],
            "policy_sha256": profile["file_sha256"], "session_id": rows[0]["session_id"],
            "completion": end["detail"], "records": len(rows), "trajectory_samples": len(samples),
            "simulation_duration_s": end["elapsed_s"], "server_monotonic_duration_s": end["monotonic_s"],
            "run_quality": _run_quality(rows, samples, profile),
            "sample_interval_s": {"p50": percentile(intervals, .5), "p95": percentile(intervals, .95),
                                  "max": max(intervals, default=None), "over_150ms": sum(dt > .15 for dt in intervals)},
            "commands": dict(Counter(r["event"] for r in rows if r["event"].startswith("command_"))),
            "peak_active_warned_attacks": peak_active,
            "abilities": dict(Counter(r["detail"] + ":" + r["event"] for r in rows if r["event"].startswith("ability_"))),
            "attack_strata": {key: dict(value) for key, value in sorted(strata.items())},
            "threats": threat_records, "audit_issues": audit_issues,
            "limits": ["Local unsigned evidence; no authenticity guarantee.",
                       "Sampled interpolation cannot prove all between-sample movement or collision behavior.",
                       "Geometric initial exposure excludes terrain; server estimate is recorded separately.",
                       "Nominal walking budgets assume immediate full speed, no obstacles or competing threats; they do not measure human reaction.",
                       "Centered projectile budget uses the best angled straight heading, with an in-range closest point; the legacy perpendicular field name is deprecated.",
                       "Budgets use the selected nominal delay; observed warning-to-fire delay is reported separately. Tangency counts as a hit, so start strictly earlier than the budget.",
                       "Counts describe one run; adjacent observations are correlated.",
                       "Warning-to-command latency includes held steering and existing movement; it is not human reaction time.",
                       "Accepted action timing also includes stops and mobility grants; a grant does not prove execution or a dodge.",
                       "Overlapping threats may share the same command; no command is causally assigned to a threat.",
                       "No pure human reaction time or automated-cheating verdict is computed."]}

"""Small calibration helper adapted from dcass5212/lol-dodge-calc, MIT.

Source: index.html evaluate(), commit af8c5d40ff8eda343cc0e80af27f4304cf9343d5.
Copyright (c) 2026 dcass5212. Full notice: ../third_party/lol-dodge-calc-LICENSE.
Changes: Python, explicit centimeter/second units, validated inputs, no item or
League movement-speed formulas. This idealized calculation is NOT hit detection,
a reaction-time measurement, or a model of dash/blink/obstacle movement.
"""
import math


def dodge_window_seconds(*, cast_delay_s, distance_cm, projectile_speed_cm_s,
                         player_radius_cm, projectile_radius_cm, walk_speed_cm_s):
    """Legacy centered-line budget, using the best straight angled heading.

    Assumes constant speed, straight nonhoming projectile, instantaneous walk
    acceleration, and no other threats/obstacles. Negative means no walking
    escape under these assumptions when projectile speed exceeds walking speed.
    Tangency is a hit, so movement must start strictly before this budget. This
    legacy helper has no range/centering checks; v3 summary adds those checks.
    All input distances share the same scale. Historical numeric output is kept.
    """
    values = (cast_delay_s, distance_cm, projectile_speed_cm_s, player_radius_cm,
              projectile_radius_cm, walk_speed_cm_s)
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Calibration requires finite nonnegative numbers")
    if projectile_speed_cm_s <= 0 or walk_speed_cm_s <= 0:
        raise ValueError("Speeds must be positive")
    combined_radius = player_radius_cm + projectile_radius_cm
    arrival_s = cast_delay_s + distance_cm / projectile_speed_cm_s
    return arrival_s - combined_radius / walk_speed_cm_s

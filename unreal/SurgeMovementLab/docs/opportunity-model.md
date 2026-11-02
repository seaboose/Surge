# Descriptive walking opportunity model

Summary v2 uses `nominal-walk-v2`. These budgets describe simplified geometry;
they do not change detector limits or measure human reaction time.

For a centered aimed projectile, let cast delay be C, initial forward distance D,
projectile speed u, walking speed v, and combined hit radius R. For u > v, the
best straight heading has `cos(theta) = v/u` relative to projectile forward.
The latest start budget is `C + D/u - R/v`. Start strictly earlier: tangency is a
hit. When closest approach lies within active flight, a perpendicular sidestep
instead has budget
`C + D/u - R * sqrt(1/v² + 1/u²)`.

At D=900, C=.25, u=1200, v=335 and R=135, the best heading is about73.79 degrees
and its budget is .597015 seconds. Perpendicular movement gives .581606 seconds.
The model requires initial exposure, centering within .001 units, an aimed shot,
and D within the projectile center's range. Other cases return null with a
reason; an exposed range endcap does not make the formula applicable.

For a circle, minimum escape distance is the combined radius minus the initial
distance to its center, clamped to zero. The budget is nominal delay minus
escape distance divided by walking speed. A centered315 combined radius at335
speed and .75 delay has a negative budget of about−.190299 seconds. An initially
unexposed circle returns null, rather than counting a random miss as an escape.

Both models assume immediate full walking speed, free terrain, no competing
threats and no latency. `nominal_warning_delay_s` and actual
`observed_warning_to_fire_s` are separate; a late fire does not enlarge the
nominal budget. Negative budgets describe this model, not a failed player.

Canonical fields are `nominal_centered_best_heading_budget_s`,
`nominal_circle_walk_delay_budget_s`, and
`nominal_walking_escape_possible_without_terrain`. The old
`ideal_centered_perpendicular_window_s` name was incorrect. It and
`ideal_walking_escape_possible_without_terrain` remain explicit deprecated
aliases, identified in `legacy_opportunity_field_aliases`. Historical bundles
stay intact; the pilot retains its original analysis in `frozen-inputs.zip`.

# Descriptive data quality

The v3 summary adds `run_quality` without changing detector input or decisions.
It reports sample rate over the recorded sample span, leading/trailing unsampled
time, and the portion of the observed run covered by adjacent sample intervals
of at most150ms. Longer intervals remain gaps; no samples are invented. This is
sampling coverage, not proof of collision/input coverage. Partial runs retain
their actual completion status and use their observed duration. No-sample runs
have zero supported coverage and unavailable sample-span measurements.

Monotonic sample cadence and simulation-seconds per monotonic second are separate
from simulation cadence. They describe timing differences without identifying a
cause or estimating unrecorded frame rates.

Each threat adds `command_after_warning`: time from the server warning record to
the first later `command_grant:move`, bounded by that threat's terminal record or
capture end. Record order resolves simultaneous timestamps. Denials, stops and
commands after resolution do not count. Absence is censored, not assigned a large
latency. Both simulation and monotonic durations are retained.

`action_after_warning` separately includes the first accepted move, S stop, dash
grant or blink grant under the same timing/censoring rules. It records the event,
kind and sequence; denied abilities do not count. This avoids losing mobility/stop
context when no new walking destination is needed. A grant is authorization, not
proof that the action executed or avoided a hit. The move-only metric is retained.

This is **not human reaction time**. Held steering can produce grants, movement
can already be underway, server warning time need not equal visible cue onset,
and overlapping threats can share one command. Counts of other active threats
at warning/command make overlap visible; no command is causally attributed to a
threat. Prewarning displacement uses a preceding sample within150ms and the
actual warning position, only in walking mode with no intervening ability edge.
It reports observed displacement, not continuous velocity or player intention.

Existing exposure/outcome strata remain separate, so random misses are not
converted into successful reactive dodges. These additions make sparse/partial
evidence easier to assess; they provide no automated-cheating verdict.

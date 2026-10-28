# V3 dash timing evidence

`dash_displacement` compares successive samples wholly inside one dash against
the reviewed profile's1350 units/second plus5 units of positional allowance.
`dash_duration` compares a matched activation against425/1350 seconds, allowing
one recorded terminal tick plus1ms for frame quantization. Input payload numbers
cannot redefine these limits. The profile bytes and historical v1/v2 rules remain
unchanged.

Both checks use the existing `constraint_ratio`: above1 produces Review; missing
support produces Unknown. A sample gap over150ms, a movement-state mismatch or an
unsupported tick cannot establish compliance. Duration additionally requires
in-dash samples, matching start/end events and an end away from the run boundary.
Incomplete activations remain Unknown. A dash stopped by a wall may have a shorter
distance/duration; the requested200-unit minimum is not a minimum actual travel
distance and is not enforced as one.

These are maximum-envelope checks. They do not prove exact speed, catch motion
that starts and finishes between samples, evaluate start/end transition speed,
detect a slower dash as a violation, or establish evidence authenticity. The
allowances are conservative and fixed for the current provisional Survive profile.
Nine synthetic regression scenarios cover legal timing, excess in-dash speed with
legal total range, overlong duration with legal speed, wall stops, gaps, state/tick
changes, terminal censoring, partial capture and current Surge compatibility.

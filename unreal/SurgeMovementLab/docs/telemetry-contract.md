# Historical walking-only telemetry v1

Survive now writes `survive-v2`; use `prepare_v2.py` and
[the v2 contract](survive-design.md). This document and the original adapter are
retained for earlier walking-only evidence. The formats are not interchangeable.

UTF-8 JSON Lines, one flat object per server sample. No account, machine, user,
process path or network-address identifiers. `session_id` is a fresh opaque GUID
per spawned unit/capture. It is not persistent player identity. Source is local,
unsigned and editable; a GUID and file hash do not establish authenticity.

| Field | Meaning |
|---|---|
| schema | Constant `surge-movement-v1` |
| session_id | 32 hexadecimal GUID characters |
| seq | Zero-based contiguous integer |
| elapsed_s | Server world elapsed simulation seconds from capture start |
| x_cm, y_cm, z_cm | Server actor world position in centimeters |
| movement_mode | `walking` or `other`, from CharacterMovement |

Capture is authority-only, at most once every 0.1 simulation seconds, with no
catch-up samples. Limits per spawned unit: 600 simulation seconds, 6001 rows,
4 MiB UTF-8 bytes. GameMode admits up to four simultaneous units. Capture stops
at a limit or write failure; there is no silent ring-buffer eviction or reuse of
the session filename. Disconnect destroys the character. Files are not deleted
automatically. New sessions can create more files; the operator must bound disk
retention between runs. File I/O is synchronous in this small skeleton; measure
tick impact before considering an asynchronous bounded writer.

The adapter reads at most 4 MiB + 1 byte, limits line length to 2048 characters,
requires 2–6001 rows, exact fields, finite bounded numbers, contiguous sequence,
one session and strictly increasing elapsed time. Missing/reordered samples,
duplicate keys, labels, mixed sessions and malformed input reject the whole
conversion. A complete prefix of a truncated capture can still parse: inspect
server logs and reconcile planned duration/row count before claiming coverage.
EndPlay logs row/byte counts and failure state; it is not a signed completion
manifest. No interval after the last retained sample is covered.

For adjacent valid samples:

`distance_cm = hypot(dx, dy)`

`excess_cm = distance_cm - 600 * dt_s - 10`

The fixed 600 cm/s policy comes from reviewed game design, not a mutable speed
field in evidence. Ten cm is an initial positional tolerance, to freeze before
held-out collection and validate empirically. Review when `excess_cm > 0`.
Intervals are eligible only when both endpoints are walking and 0.05 ≤ dt ≤ 0.5
seconds. Otherwise `excess_cm` is null, making Surge's rule input unavailable
and producing Unknown. Metadata includes interval, distance, fixed limit,
tolerance and coverage explanation; labels and action logs remain external.

This measures a lower bound on horizontal travel (straight-line displacement).
Corners can hide excess path speed. No conclusion covers between-sample loops,
unsupported modes, missing tail records, tampered server evidence or modified
policy. Endpoint modes cannot prove an interval contained no intermediate mode
change. The first sample supplies position only; no verdict precedes it.
Legitimate slopes, knockback, dashes and teleports need explicit model revisions
before inclusion. Network arrival timing is never used as movement time.

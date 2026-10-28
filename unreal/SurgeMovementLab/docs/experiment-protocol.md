# Survive collection protocol

Development collection has executed: nine real automated 60-second rounds across
seeds 1337, 2027 and 4242, with frozen inputs, bound replay bundles and reopened
Surge cases. Human studies and held-out collection have not run.
[Completed pilot](../telemetry/local/development-pilot-review-20261026T112755Z-88b998ed/report.md),
[collection plan](collection-plan.json).

## Completed development gates

Unreal C++/UHT builds and both native checks pass. Rendered CUA operation checked
left/middle rejection, RMB movement, S/Q/E and restart. The first S click followed
arrival; a later engine-injected probe separately demonstrated S stopping motion,
fresh-press resumption and Q clearing held steering. The final application-focus
probe clears the held latch on deactivation and retains it through reactivation
for a complete observation. Physical sustained RMB holding remains unproved.

Practice uses Q 4s / E 12s. The separate reference capture accepts two dashes and
one blink, and records five cooldown denials consistent with Q 16s / E 300s. It
does not test the exact readiness thresholds or a 300-second blink regrant.

## Executed pilot matrix

Each seed used a fresh process for each condition, with the practice profile and
fixed compiled build. Condition/phase/action labels stay outside detector input.

| Condition | Actual action | Review / Unknown per run |
| --- | --- | --- |
| Nominal baseline | Walk 335, legal Q/E, stops and obstacles | 0 / 45 |
| Controlled speed change | Authority walk 1200 at actual logged times near 20-35s | 94 / 43 |
| Restoration baseline | New Smoke process initializes walk 335 | 0 / 45 |

All nine captures contain 1800 trajectory samples, with no geometry-audit issues
or unambiguous probe finding outside the logged change window. Six-decimal action
timestamps require rounding bounds. The control windows include substantial idle
time, path endings and mobility exclusions: they are not independently labeled
positive intervals. Counts describe correlated records, not detection accuracy.
Fresh restoration processes do not test carryover or persisted restoration.
Same-seed observable choices match; aimed coordinates/times need not be identical.

The non-Shipping smoke driver calls real game handlers and exits after its bounded
round. It is automated input, not human dodging or physical mouse validation.
Rendered CUA actions, engine-injected held keys and NullRHI handlers have separate
provenance. Retain the earlier failed/partial attempts alongside successful runs.

## Future player and held-out collection

Give physical participants two unscored practice rounds, still captured and labeled
externally. Before a held-out study, freeze source/build, profile, policy, adapter
version, arena, camera/viewport, frame limit and action schedule. Seeds 9001, 9007
and 9011 remain reserved; do not tune on them. Rotate condition order across later
repetitions and preserve all failures. Report independent runs as well as intervals.

Define opportunity and independent action/state labels before inspecting findings.
Only then report appropriate confusion counts, coverage exclusions and timing.
Accepted commands may precede movement; held steering and overlapping threats make
warning-to-command time descriptive rather than a causal human reaction measure.
The initial milestone is local single-player authority; networking is later work.

## Evidence and reporting

Retain raw JSONL, exact profile, derived constraints, versioned summary, replay,
engine logs, runtime/build records and hashes. Keep source kind, phase, actions,
conditions and labels external. Smoke context binds the selected practice/reference
profile and invocation flag; rendered/input checks use their own sidecars. Missing
camera/map/FPS/input measurements remain unmeasured.

Bundles create new directories and write manifests last. Missing run_end rejects
conversion; partial completion, sample gaps and unsupported mobility intervals stay
Unknown. Import `surge.jsonl` with `survive-policy.json` in existing Surge.

Report all/exposed attacks by aimed/random, line/circle and movement mode, with
resolved/cancelled/censored outcomes, clearance and overlap. Retain No finding,
Review, Unknown and rejected counts, sample/monotonic cadence and uncertain labels.
Use versioned descriptive summaries; do not compare changed denominators as if
they were the same metric. Local unsigned evidence is not authenticity proof.

This supports controlled movement-policy demonstrations, not real-cheat accuracy,
input authenticity, Vanguard behavior or exact League parity. Synthetic fixtures
remain integration evidence. [Historical v2 protocol](experiment-protocol-v2-history.md)
retains the placeholder-era discussion; current limits come from reviewed profiles.

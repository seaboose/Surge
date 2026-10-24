# Bounded approval and verdict contract acceptance

Defined before execution. This fixed defensive pack uses owned synthetic data only.
It supplements the original T2 oracle requirement; it does not complete T1, T2,
T3, or the earlier development/freeze/held-back campaign.

1. Exercise 78 named scenarios: 2, 3, and 16 ranges; 1- and 64-byte references;
   and 13 states. The states are approved/unapproved clean, changed, unavailable,
   and unexpected protection; changed module identity; changed coverage
   declaration; legacy approval against versioned capture; versioned approval
   against legacy capture; and a mixed per-range state. Use a fixed fixture clock.
2. Declare expected per-row approval, comparison availability, byte equality,
   protection equality, verdict, and gaps from a small explicit truth table.
   Compare conversion and actual JSON/JSONL import/default analysis against those
   expectations. Never derive expectations from production conversion results.
   A rejected-everything implementation must fail the positive cases.
3. A module change or semantics-preserving split of an excluded interval must
   require new approval. Legacy and versioned approvals must not cross. Approval
   itself must accept only complete, unchanged, execute-read observations and
   reject changed, unreadable, or unexpected-protection captures. Input objects
   and the supplied approval registry must remain unchanged.
4. Reverse JSON object-key order and add legal JSON whitespace; require equal
   imported records, summaries, and source row values. Poison a derived byte
   comparison value in each scenario; both JSON and JSONL must reject it. This
   is consistency checking, not source authentication.
5. Save and reopen the JSONL investigation for every scenario, requiring exact
   source manifest, configuration, and recomputed result equality. Retain hashes
   and byte sizes; remove only the successful temporary case created by this
   check. Preserve any failed case and every failed attempt.
6. Execute all 78 scenarios twice (156 evaluations) with equal input and semantic
   result fingerprints. Keep each encoded input at most 1 MiB and each saved case
   at most 8 MiB. Stop on the first unexpected failure. Use a 300-second outer
   process deadline and a 10 MiB output limit. Report per-case duration and total
   time; no OS memory ceiling or per-case isolation is claimed. Do not change
   limits after a failed attempt.
7. Preserve acceptance/source snapshots, complete/pending scenario inventory,
   stdout/stderr, first failure, and SHA-256 manifests under a unique ignored
   qualification directory. No production changes, native code loading,
   collection subprocess, external target, protected holdout, or native fuzz
   campaign is part of this pack.

Remaining original requirements include a coordinated held-back final phase,
native generated-layout resolution oracles, every declared mutation category,
instrumented deep-branch reachability for that phase, isolated per-case time and
private-memory limits, stream framing/state-transition combinations, and the
original aggregate gates. Earlier parser, Hypothesis, and retention evidence
keeps its own source identity and limits.

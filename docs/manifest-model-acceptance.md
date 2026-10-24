# Isolated manifest, approval and verdict acceptance extension

Defined before execution. This component uses synthetic owned capture objects,
JSON/JSONL evidence, and local approval objects only. Native binaries, live
process collection, external targets and protected evaluation data are excluded.

1. A byte-occupancy model must independently verify exact disjoint checked and
   excluded coverage of executable spans. Generated layouts vary 2/3/16 ranges,
   code lengths through 1 and 64 bytes, names, RVA placement, and explicit span
   partitions. Positive declarations must validate unchanged; single-reason
   invalid dimensions, types, keys, hashes, names, counts, holes, overlaps,
   outside coverage and totals must be refused.
2. Freeze an explicit approval/verdict truth table before testing: approved clean
   is No finding; approved changed/protection mismatch is Review; approved
   unreadable is Unknown; unapproved observations are Review with comparison
   gaps. Verify byte/protection comparisons are absent when unavailable, and
   approval is unavailable across changed module/declaration or legacy/versioned
   identity. Reject nonclean new approval and duplicate approval identities.
3. Exercise the production encoded-evidence entry point in both JSON and JSONL,
   including embedded manifest strings. Missing/mixed metadata, poisoned derived
   fields and duplicate JSON object keys must be rejected, including duplicates
   inside embedded range/integrity manifests. Identical duplicate values remain
   ambiguous representation and must not be silently normalized. This explicit
   duplicate-key rule is frozen before executing its regressions.
4. Legal whitespace/object-key reorder must preserve meaning and canonical
   digest. Manifest array reorder and splitting an excluded interval may preserve
   coverage but change declaration identity and require new approval. Changed
   module identity similarly requires new approval even when checked bytes are
   unchanged. Save/reopen a fixed subset and compare actual source/config/result.
5. Keep every ordinary encoded input at most 256 KiB. Every recipe runs in an
   owned isolated Python worker under the verified Windows 1 GiB process
   private-memory limit and five-second deadline. Record timings/peak private
   bytes, strict positive/negative outcomes and rejection distributions.
6. Run fixed development recipes using seed 17, then freeze sources, generator,
   oracle, limits, categories and the final recipe. Generate concrete final
   combinations only afterward using seed 2026102302 and different layout/name/
   length/approval combinations; run once and replay the exact final recipes
   twice. Final input and semantic result fingerprints must match. Stop at first
   unexpected failure and preserve completed/unrun cases, source and logs.
7. Keep development within 20,000 cases/10 minutes, final within 10,000/5 minutes,
   replay/reporting within 15 minutes, component execution within 90 minutes,
   logs within 10 MiB and retained ordinary corpus within 32 MiB. A production fix
   invalidates the prior final source identity; at most one replacement final
   attempt is allowed within remaining original limits. Do not silently reset
   failed-attempt budgets.

Python's existing declared-name representation permits 64 ASCII identifier
characters; the native descriptor permits at most 63 visible characters plus
NUL. Positive Python 64-character representation is not a claim that the native
producer emits that descriptor. Native ambiguity and loader behavior remain T1
responsibilities. This component adds T2 evidence; the combined original T1/T2/T3
campaign still requires its coordinated cross-target gates and source identity.

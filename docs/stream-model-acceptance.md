# Isolated stream-model acceptance extension

Defined before execution. Owned synthetic records and a fake in-memory pipe
exercise the production decoder, reader, retention window, importer and case
replay. Child processes run this Python test worker only; no native collector,
generated executable, external target, or protected holdout is used.

1. Independently generate delivered/lost slots, expected per-range verdicts,
   immutable snapshots and retained sequence identities. Valid JSON and JSONL
   must agree with the model and saved investigations must reopen identically.
   Exercise fixed session/process/build identity, nondecreasing time, accounted
   loss, and all four approved observation modes. Do not infer expectations from
   the decoder's own acceptance or counter formulas.
2. A fixed negative matrix must cover ready/sample/end ordering, duplicate and
   missing ranges, sequence/drop rollback, clock/type boundaries, every live
   identity component, missing/mismatched health, malformed framing and UTF-8,
   and 32 KiB minus/at/plus one byte lines. A valid prefix must survive a later
   reader error with Unknown health; no new recovery-after-malformed-input
   behavior is required. Positive boundaries must execute too.
3. Every case runs in an owned isolated Python child assigned to a Windows job
   with a 1 GiB process private-memory limit before its input is released.
   Enforce five seconds per ordinary case and fifteen seconds for the existing
   deterministic retention boundaries. Record actual duration and job peak
   private-memory accounting. Verify the job configuration and an allocation
   refusal control, plus a deliberately timed-out test worker, before campaign
   execution. Stop on unexpected failure or a resource breach.
4. Ordinary encoded inputs remain at most 256 KiB and ordinary histories at
   most 64 samples. Re-run the existing 24 deterministic production-limit
   scenarios under isolated fifteen-second/1 GiB controls. Large fixtures are
   regenerated, hashed and removed after success; preserve failing fixtures.
   Preserve at most 200 findings and 32 MiB of ordinary corpus, with 10 MiB logs.
5. Development uses seed 17. After development passes, freeze exact source,
   generator, expected outcomes, limits, categories, and final recipe. Only then
   generate final concrete variants using seed 2026102303, shifted layout RVAs,
   distinct names, process identity, range lengths/counts, and different loss,
   elapsed-time and observation-mode combinations. Final cases run once and
   their exact recipes replay twice. Compare input and semantic result hashes;
   timings and measured memory are reported separately. No replacement final
   attempt is automatic after a failure.
6. Record target-file executed lines/arcs and function reachability without
   claiming exhaustive branch coverage. Keep development within the original
   T3 limit of 10,000 histories/15 minutes, final within 5,000/10 minutes, and
   deterministic replay/reporting within 15 minutes; all component execution
   must remain within 90 minutes. Preserve failed attempts and unrun inventory.

This component can add original T3 model, framing, bounded-isolation, and
held-back evidence. It cannot by itself complete the original combined T1/T2/T3
campaign, native generated-layout oracle, broader T2 malformed-schema matrix,
or cross-target development/freeze/final acceptance. Earlier milestones retain
their own recorded source identities and scopes.

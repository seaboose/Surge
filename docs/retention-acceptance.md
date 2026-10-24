# Bounded retention acceptance criteria

Defined before running the new checks. Scope: synthetic, owned in-memory data,
the existing decoder, retention window, importer, and saved-case replay. No
external process targets, image loading, protected evaluation inputs, or new
fuzz campaign. Production limits must remain unchanged.

## Required checks

1. Decode 2, 3, and 16 ranges through histories of 499, 500, and 501 samples.
   At every append, compare retained groups with an independent longest-suffix
   model constrained by both 500 samples and the actual accounting budget.
   Verify whole groups, sequence order, exact eviction/conservation counters,
   and exact tracked byte totals. Two-range controls must retain 499/500/500
   samples respectively; other counts may hit the byte budget sooner.
2. Exercise accounting budget B−1, B, and B+1, where B = 8,388,608 − 16,384
   = 8,372,224 bytes. Test both a single incoming group and the total of old and
   incoming groups. Check multiple-group eviction and UTF-8 multibyte sizing.
   Empty and oversized groups must leave all previous state unchanged. These
   direct internal padding fixtures test accounting; they are not valid native
   stream observations or a claim that such a group can pass the decoder.
3. For every decoder-valid history, serialize the final snapshot as JSON and
   JSONL. Each actual UTF-8 export must be at most 8 MiB and under the 16 MiB
   import limit, parse successfully, and reproduce equal record conclusions
   and summary counts. Retained clean observations must be No finding; eviction
   must add exactly one Unknown health record and no Review records. Save and
   reopen one case per history and require exact recomputed result equality.
   A snapshot taken at sample 498 must remain unchanged after later appends
   and evictions. Use a fixed synthetic fixture clock for health, approval and case
   generation; do not discard timestamps or baseline fingerprints when comparing.
4. Independently test actual import bytes at 16 MiB−1, 16 MiB, and 16 MiB+1
   for JSON and JSONL using valid whitespace-padded synthetic records. The
   first two must import and the last must fail specifically at the byte guard.
5. Run all 24 named scenarios twice (48 evaluations). Retain per-scenario
   input/result fingerprints and require identical results on repeat. The
   runner must preserve completed and unrun cases on failure, fail closed on
   missing/duplicate/failed evidence, and remain bounded to 300 seconds by
   qualification. No individual generated import exceeds 16 MiB+1; no
   incoming accounting group exceeds B+1; no history exceeds 501 samples or
   16 ranges. Keep generated files in the ignored verification directory.
6. Pass the complete qualification with the retention profile from a new
   isolated clean checkout, preserving logs, source identity, all failed
   attempts, and clean before/after status. A failed attempt remains failed.

## Claims excluded

These fixed cases do not complete the original T1/T2/T3 campaign, establish
arbitrary-history coverage, or prove a memory/RSS ceiling. They do not add
long-duration capture, concurrency/race testing, every supported import format,
10,000-row/64-field boundaries, the 64 MiB case limit, trusted attestation, or
resistance to an equally privileged local actor. Existing short desktop/native,
ASan, property, and parser checks retain their separate scope and provenance.

## Fixture correction after the first attempt

The initial specification fixed only health timestamps. Attempt
`retention-f0511442985d` completed all 48 individual checks but failed repeat
comparison because synthetic approval time also changes the baseline digest.
The fixture now fixes approval time before generating that approval. All
timestamps and baseline digests remain compared; no production limit or
boundary expectation changed. The initial criteria and failed harness/report
remain preserved with that attempt.
Read-only review also identified variable case creation timestamp width as a
potential byte-count difference; the final fixture fixes that clock before
writing as well. No such case-size failure was observed.

# Bounded relocation and parser-boundary acceptance criteria

Defined before implementation/execution, 23 October 2026.

Scope: deterministic, synthetic, owned byte buffers passed only to `LabImage`; no loading generated images, collector/process access, external targets, or protected holdout use. This extends qualification evidence, not the original T1/T2/T3 campaign.

1. At most 100 named cases, each input at most 64 KiB. Run the complete fixed case list twice, in separate processes, each with a 15-second outer limit; keep the existing pilot's 900-second overall and 10 MiB per-command log limits. No random mutations are added to this boundary pack. The existing two-seed libFuzzer pilot remains separately counted.
2. Relocation cases cover absent/empty directories, ABSOLUTE padding, disjoint DIR64 entries, exact adjacency and overlap at both declared ranges, multiple blocks, truncated headers/tails, block-size below/exactly/above bounds and odd payloads, unsupported types, target at/beyond the image end and 32-bit-address addition, unmapped directory spans, and the encoded 1 MiB directory-size threshold. The large directory itself is not allocated: exact 1 MiB tests mapping refusal and 1 MiB + 1 tests the cap, not a successful maximum-size traversal.
3. Parser cases cover truncated structural inputs; section counts 0/96/97; executable-section counts 0/32/33 with positive exact-limit layouts; image-size encoded bounds; probe lengths 0/1/63/64/65; declaration count below/above its accepted interval; and file-backed mapping start/end/one-past/oversized-length queries. Accepted fixtures must resolve exact range names, RVAs, lengths and expected bytes; refusals must have the specified diagnostic. Positive controls prevent an implementation that rejects everything from passing.
4. Expected relocation overlap is determined by a small independent half-open byte-interval oracle over the known declared ranges. Include non-overlapping neighbors as well as overlapping cases. Fixed malformed cases have explicit expectations. Production parser changes, if any are needed, require a preserved failing regression first.
5. Compile with ASan and source coverage; retain the existing safe/fault ASan controls. Verify relocation-block reader entry and both outcomes of every branch record on the relocation validation guards (directory cap/presence, truncated header, block sizing, ABSOLUTE/type discrimination, target bound, overlap). Report target-header coverage separately for the deterministic pack and the fuzz corpus; do not substitute one for the other or claim complete parser coverage.
6. Preserve input hashes, per-case actual/expected outcomes, repeat output hashes, source/tool/binary/log hashes, raw source coverage and all failed attempts. A mismatch, sanitizer finding, unexpected exception, timeout, missing case, duplicate case, or missing required coverage fails qualification.
7. Integrate the bounded pack into the optional libFuzzer qualification profile and verify the combined checks from a clean checkout. Preserve earlier UI/toolchain failures. Report exact executed counts and remaining limitations; original campaign gates stay incomplete.

Not covered: arbitrary PE compatibility, executing relocated code, loader behavior, exhaustive relocation layouts, real 1 MiB traversal, maximum export/manifest-cardinality packs, cross-machine reproducibility, comprehensive semantic oracle, retention-limit tests or held-back final variants. Finite ASan/coverage evidence is not a memory-safety proof.

## Subsequent count/cardinality extension

The [export-count and manifest-cardinality criteria](export-cardinality.md) add 23 fixed cases to the original 65, still within the 100-case and 64 KiB/input bounds. Historical results retain their original scope.

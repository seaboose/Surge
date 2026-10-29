# Bounded approval and verdict contract results

24 October 2026 UTC. **The fixed approval/verdict pack passed all 156 evaluations
(78 scenarios, each repeated twice).** This adds an independent expected-outcome
table for an identified gap in the original T2 specification. T1, T2, and T3
remain incomplete under their original aggregate acceptance criteria.

## Verified results

The final supervised run took 24.484 seconds, including 23.781 seconds inside
the pack. It exercised 3,276 observation rows across 2, 3, and 16 configured
ranges, using 1- and 64-byte reference lengths. The slowest scenario took 0.360
seconds. Maximum encoded input was 622,885 bytes (1 MiB limit); maximum saved
case was 734,879 bytes (8 MiB limit). Output was 6,367 bytes (10 MiB limit), and
no timeout or size limit was reached.

- All approved/unapproved clean, changed, unreadable, and unexpected-protection
  rows matched the explicit approval, comparison, verdict, and gap truth table.
  Mixed per-range states also matched their individual expectations.
- Changing module identity, splitting an excluded interval while preserving
  its byte coverage, or crossing legacy/versioned approval boundaries required
  fresh approval. New clean approvals worked; changed, unreadable, and
  unexpected-protection captures were refused.
- JSON and JSONL both imported and produced equal records and summary counts.
  Legal whitespace and reversed object-key order preserved meaning. Both
  encodings refused an inconsistent derived byte-comparison value in every
  scenario: 312 expected refusals, separate from the 156 scenario count.
- All 156 saved JSONL investigations reopened with equal source manifests,
  source text, configuration, and recomputed results. Successful temporary case
  files were removed only after verification; their size and hash remain in
  the result. No failed application case required retention.
- All 78 input/result fingerprint pairs matched on repeat. Eight deliberate
  evidence-corruption controls were refused: changed bytes, a missing file,
  duplicate manifest entry, missing scenario, mismatched repeat, changed limits,
  incorrectly marking original fuzzing complete, and a missing frozen source.
  The unchanged positive artifact passed verification.

No production defect was found and no production code was changed by this pack.
These results implement the [predeclared criteria](approval-contract-acceptance.md),
with source fingerprints and attempt identities in the
[validation record](../evidence/approval-contract-validation.json).

## Preserved attempts

1. `approval-contract-9b9bf60fc725` failed on the first scenario before any
   evaluation completed. The fixture's mock clock also mocked timestamp parsing,
   producing a `MagicMock` comparison error. This was a harness error. The failed
   report, pending inventory, source snapshot, and console log are preserved.
2. After limiting the fixture clock override to retain real parsing,
   `approval-contract-3de7997ebc9a` passed 156 evaluations in 23.688 seconds
   (24.328 seconds supervised).
3. After adding the reusable bounded entry point and offline evidence verifier,
   `approval-contract-49047c267f36` passed 156 evaluations in 23.781 seconds
   (24.484 seconds supervised). This final attempt froze both runner files.

That is 312 completed evaluations across the two successful attempts. The first
failed attempt remains failed. Neither successful attempt is a held-back final
phase; no development/final separation is claimed. Limits and expected outcomes
were not relaxed after failure.

## Reproduction and remaining work

From the repository root, run `python -B scripts/run_approval_contract.py`.
The wrapper enforces the 300-second process deadline and 10 MiB output budget,
then verifies the result inventory and retained file hashes. It creates unique
`verification/qualification/approval-supervisor-*` and `approval-contract-*`
directories. Verify an existing result with
`python -B scripts/run_approval_contract.py --verify <approval-contract-directory>`.
The worker script alone is a lower-level entry point without the outer guard.

This is a deterministic contract pack, not coverage-guided fuzzing, a statistical
accuracy estimate, attestation, or proof of freedom from defects. It does not
enforce an OS private-memory ceiling or isolated per-case timeout. Its 1 MiB
encoded-input cap differs from the original campaign's 256 KiB ordinary-input
cap; its larger one-shot 16-range captures therefore cannot silently count
toward that original campaign.

Original T1 remains incomplete: prior verified ASan/libFuzzer and boundary packs
do not supply the coordinated generated-layout resolution oracle, all required
mutation categories, or held-back final-phase coverage. Original T2 now has
this additional truth-table evidence, but still lacks the complete malformed
schema/embedded-JSON matrix, all specified metamorphic cases, and original
development/freeze/final sequence and resource enforcement. Original T3 retains
its separate Hypothesis and production-limit retention evidence, but lacks the
full framing/state-transition combinations and held-back histories under the
original process/time/memory controls. The original 90-minute campaign was not
started or consumed by this separately scoped fixed pack.

These measurements are local, from the recorded source files; hosted execution
and the broader release qualification require separate evidence. Unfamiliar-user
acceptance remains pending. Prior parser and retention results keep their
original scope and source identities.

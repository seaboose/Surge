# Bounded case-library interruption and recovery

Criteria recorded before execution on 23 October 2026. Scope is Surge's local
case library and portable export, using only newly created owned fixtures.
This is a fixed recovery campaign, not the broader fuzzing campaign.

## Required outcomes

1. **Save and import publication:** a failure or abrupt owned-child termination
   before publication must not expose a valid-looking partial library entry.
   After publication, the entry must be complete and reopen with matching
   evidence. Original imported evidence and unrelated cases remain byte-identical.
2. **Rename:** interrupted or failed metadata replacement leaves the old or new
   complete name, with unchanged case bytes. Reopening, another rename, and
   deletion of that owned case remain usable after restart. Unrelated or
   unexpected files must not be silently deleted.
3. **Export:** an existing destination is never overwritten, including when it
   appears immediately before publication. Failed or interrupted copy/validation
   must not leave partial bytes at the requested final destination. An export
   published before interruption must be complete and independently verifiable.
   Owned temporary residue may remain after abrupt termination, but must not be
   mistaken for a published case or cause loss of existing evidence.
4. **Restart and damaged entries:** a fresh library instance/process can list and
   reopen surviving cases. Structurally unreadable entries are reported as
   unavailable; a structurally present but invalid case is refused on verified
   open and must not replace the current investigation. Valid cases remain usable.
   This does not require expensive full validation of every case on every list.
5. **Failure accuracy:** injected write, permission, short/zero-write, validation
   and publication failures must produce failure rather than success or a hang.
   Completed publication followed by cleanup failure must be reported accurately.
   No automatic retry may hide a failed campaign attempt.
6. **Independent checks and preservation:** use explicit expected outcomes and
   byte hashes of original evidence, existing destinations and unrelated cases.
   Run every fixed scenario twice in fresh directories and compare semantic
   outcomes, ignoring generated IDs/timestamps. Keep per-case outcomes, failure
   details, raw logs, tested source hashes and interrupted directory state.
7. **Integration:** existing case-library, desktop boundary/runtime, worker case,
   and relevant UI journeys must still pass after any narrow fix. Add the bounded
   recovery regression to the existing desktop test path, with nonzero exit on
   failure and fixed budgets. Do not claim hosted CI qualification of new changes
   unless a new hosted run actually occurs.

## Bounds and method

- At most 48 named fixed scenarios, each run twice; at most 96 scenario executions.
- Each generated case/input at most 256 KiB. All fixtures and retained state stay
  under the dedicated ignored qualification attempt directory; no user library
  or external application's data is touched.
- At most one owned scenario child at a time. Each child has a 5-second deadline;
  the entire recovery campaign has a 300-second deadline and 10 MiB log ceiling.
  The complete attempt directory is bounded to 64 MiB, excluding the recorded
  source snapshot. Repeated runs retain separate attempt directories.
- Inject filesystem failures only inside the owned test child. Simulate ENOSPC
  and permission errors; do not fill a real disk or change host permissions.
- For abrupt interruption, stop only the child launched by the harness after an
  acknowledged persistence boundary. Restart inspection occurs in a fresh
  process. A terminated test child is an expected control, not an application pass.
- Include successful controls, failures before publication, interruption around
  publication, invalid input, and an existing-destination race. Verification of
  real portable cases uses Surge's actual case reader in a separate integration
  check; the fast filesystem harness may use an explicit owned-fixture verifier.

## Limits and reporting

Preserve initial failing regressions before changing application code. Separate
application defects, test-harness/environment failures, and intentional controls.
Report exact scenario counts and unexecuted checks; missing evidence fails the
campaign. Ordinary process termination is not a power-loss or filesystem
durability test. No claims about filesystem corruption, hostile concurrent
writers, physical storage failure, network shares, multiple Surge writers,
native-dialog acceptance, or broad operating-system compatibility follow.

Unfamiliar-tester acceptance remains pending. The original broader T1/T2/T3
campaign remains incomplete. The previous hosted result belongs to commit
064c6a1; it cannot qualify this milestone's later source changes.

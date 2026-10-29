# Validation and limitations

The public release is an unsigned Windows review candidate. Clean-machine and
unfamiliar-user acceptance remain pending. A developer-host test, prepared VM,
or hosted run does not establish either result. Release checksums identify the
exact tested package; source changes require a new validation receipt.

## What the project demonstrates

- Owned-game recording, replay, movement constraints and evidence-linked reports.
- Native range measurement, explicit baseline approval and bounded transport.
- Input validation, saved-case recomputation and missing-evidence handling.

Survive's scripted legal commands can satisfy every movement rule. No finding
does not prove human input. Controlled violations and synthetic fixtures do not
establish real-cheat accuracy. Human comparison data, held-out evaluation and
synchronized input/display timing require separate collection and validation.
See the [study design](survive-study.md) and [game protocol](../unreal/SurgeMovementLab/docs/experiment-protocol.md).

The native demo checks two ranges totaling 15 bytes at a 500 ms target interval.
Changes outside coverage or between samples can be missed. Local unsigned
observations and approvals are not attestation. See [SECURITY](../SECURITY.md).

## Reproduce checks

After [source setup](../README.md#build-from-source):

```powershell
.\.venv\Scripts\python.exe -B scripts/test.py
.\.venv\Scripts\python.exe -B scripts/verify_native_demo.py
pnpm --dir desktop test
.\.venv\Scripts\python.exe -B scripts/check_release.py
```

GUI/native integration checks have additional prerequisites. The
[qualification guide](qualification.md), [native guide](../native/README.md),
and [package checks](windows-package-check.md) describe them. The separate
[clean-machine procedure](clean-machine-qualification.md) must retain failed
attempts and report incomplete work honestly.

## Historical evidence

Reports in `docs/` and `evidence/` identify their original source snapshots and
scope. They are retained for review; a past pass does not qualify current source.
Useful entry points include:

- [Adversarial correctness](adversarial-correctness-results.md).
- [ASan controls](qualification-asan-results.md) and [bounded parser fuzzing](libfuzzer-pilot-results.md).
- [Independent manifest model](manifest-model-results.md) and [stream model](stream-model-results.md).
- [Performance and reliability](performance-reliability-results.md).
- [Separate IoT evaluation](evaluation.md), whose false-positive rate is unsuitable for deployment.

The original combined T1/T2/T3 fuzzing campaign remains incomplete. One-host
performance measurements do not establish endurance or other hardware behavior.
Historical first-use JSON reports replace local interpreter locations with
`<python-runtime>/python.exe`; command outcomes and recorded hashes are preserved.
The replacement is a publication redaction, not a newly executed command.
The adversarial report also omits tool-provider access and coordination details;
its recorded checks and incomplete campaign status remain unchanged.

# Native compatibility checks

Surge checks code ranges declared by its own DLL. A versioned manifest binds the module fingerprint, x64 layout, checked ranges and executable exclusions. Approval is explicit for that complete manifest. Loader fixups that touch a checked range are unsupported; the collector refuses the comparison rather than masking bytes.

Run the compatibility matrix on Windows with the [native build prerequisites](../native/README.md#build-once):

```powershell
.\.venv\Scripts\python.exe -B scripts/test_native_compatibility.py
```

The runner creates fresh disposable builds for Release, Debug and MinSizeRel. MinSizeRel adds a third declared routine to check that coverage follows the manifest. Each configuration runs native parser checks and both owned DLL versions, including:

- Explicit approval and a legitimate update before and after approval.
- Forced loading away from the preferred image address.
- Persistent changes at the first and final byte of the primary range, and in the secondary range.
- An unreadable range, module unload and reload.
- Import through Surge's workspace and saved-case replay.
- Rejection of the rebase control outside explicit test mode.

Expected outcomes come from the external control actions. They are not detector fields. Reports record compiler versions and flags, implementation fingerprints, coverage and per-action outcomes. The default report is `verification/native-compatibility.json`; local approvals, published demos and the normal native build are unchanged.

Use `--config Release --config Debug` for development. Run `--config MinSizeRel` after freezing the implementation for an additional compatibility check. This is a fresh build configuration, not an independent detection dataset or proof of resistance to an adversary.

The [published run](../evidence/native-compatibility-validation.json) passed all three configurations: 116 clean range observations, 18 detected persistent in-range changes, 20 unavailable observations reported as Unknown, and seven unapproved observations requiring review. All 161 records replayed through Surge's workspace and saved-case format. The final MinSizeRel variant passed on its first run after the implementation freeze; its third range raised declared coverage from 15 to 24 bytes. These small controlled counts are correctness checks, not accuracy estimates.

The report preserves exact evaluated source fingerprints and adds verified LF-normalized fingerprints for Git's line-ending conversion; no source content was changed for that translation.

The checked routines remain small assembly fixtures. Compiler settings vary the collector and DLL support code; they do not establish correct boundaries for arbitrary optimized C++ functions. The owned fixtures require non-incremental linking: Debug's incremental export thunks caused the first development run to refuse a range, and the build now explicitly avoids that layout. The parser does not follow arbitrary jump thunks.

Unchecked executable bytes, changes between samples, fabricated local evidence and compromised collectors remain outside these checks. The GUI's **Our app → Start → Inspect** workflow is unchanged.

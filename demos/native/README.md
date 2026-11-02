# Native evidence demo

These five cases replay controlled observations from Surge's own Windows app. No compiler, running collector, network access or local approval file is needed to replay them. From the repository root, run:

```powershell
python -B scripts/verify_native_demo.py
```

Python 3.11 or newer is sufficient. After desktop setup, choose **Case library**, then **Open case file** and select a file here. This inspects the external case without adding it to the library; choose **Import case** instead to keep a library copy. Each case contains two samples of two ranges, so four records. If **Findings only** is checked, uncheck it to see clean observations. Select record 3 to inspect the controlled observation and its coverage.

- **approved-update.case.json:** four No finding records. The reviewed v2 build matches its explicit approval.
- **unapproved-update.case.json:** four Review records. The same legitimate v2 build has no approval in this case; review is not a claim of malicious behavior.
- **changed-code.case.json:** one Review and three No finding records. The second sample's first range differs from its approved bytes.
- **unreadable.case.json:** one Unknown and three No finding records. The second sample reads one of two ranges; unreadable memory is not clean evidence.
- **outside-coverage.case.json:** four No finding records despite an externally controlled change outside the two ranges. This demonstrates a known blind spot, not a detection success.

`expected.json` supplies separately declared per-record outcomes, coverage and file fingerprints. The verifier checks those against recomputed cases and validates native evidence. Expected outcomes and controller actions are never fields used by the detector. The scenarios are correctness demonstrations, not an independent population or real-cheat accuracy benchmark.

## Publication changes

The cases derive from real captures. Paths become fixed DLL filenames; PID, process creation identity, load address, session names, dates, sample positions and timing are normalized. The two selected samples become a self-contained four-record window. Collection timing is zeroed and cannot be used for performance claims. Code bytes, module fingerprints, permissions and approval comparisons are preserved. Case and source fingerprints are recomputed after normalization. Local baselines are neither included nor modified. Each manifest entry retains a fingerprint of its original selected capture for provenance; a fingerprint is not authentication.

## Regenerate from the owned app

On Windows, [build the native targets](../../native/README.md#build-once), then run:

```powershell
python -B scripts/build_native_demo.py
python -B scripts/verify_native_demo.py
```

Regeneration replaces these five demo cases and their expected-outcome manifest only. It uses an isolated in-memory approval registry. Compiler output can change DLL fingerprints, so regenerated files need not be byte-identical; the declared outcomes must still pass. The generator uses gated test controls to change only our own DLL and never executes altered probe bytes.

For live collection, build the native targets and [review and approve the exact v2 sample](../../native/README.md#approve-and-collect), then choose **Try Demo → Start collection → Inspect snapshot**. **Stop collection** opens the final snapshot without another inspection step. Replay and live collection use the same Python decision logic, but opening a case does not start a collector or require a local approval. Coverage remains two ranges totaling 15 bytes; changes wholly between samples can also be missed.

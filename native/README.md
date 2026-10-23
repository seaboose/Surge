# Native evidence

Surge recognizes `surge-native-integrity-v1` JSONL automatically. Use **Import data**, select a capture, then **Analyze**. No additional screen, plugin, or mapping is required. Select a finding to see its observed and expected code hashes. **Details** shows the range and baseline fingerprint; **Source values** retains the complete observation.

The reusable `surge_collector` C++ library measures memory. The separate `fixture_runner.cpp` executable loads our owned DLL and creates test scenarios. The collector has no mutation or scenario API. `collector_smoke` verifies collection without linking the scenario runner. This is separation of responsibilities within an owned process, not a new security boundary. It loads only the two fixed fixture DLLs beside itself, reads its own process, and accepts no arbitrary PID, address, or DLL path. It does not attach to games or Vanguard. The controlled memory-change scenario changes one byte in the fixture's code range, never executes that altered code, and restores it before exit.

## Build once

Install Visual Studio Build Tools with Desktop development with C++ and the Windows SDK, plus CMake 3.25 or newer. From the Surge folder:

```powershell
cmake -S native -B native/build -A x64
cmake --build native/build --config Release
ctest --test-dir native/build -C Release --output-on-failure
```

## Approve and collect

Approval is an explicit decision after reviewing your own fixture build. Collection never creates or updates a baseline.

For continuous collection after building, choose **Our app** in Surge, select v1 or v2, and **Start**. **Inspect** opens an analyzed snapshot without stopping collection or moving the records you are reading. **Stop** ends collection and opens its final retained snapshot. **Export** saves the current window as JSONL; use **Save case** for the inspected investigation. Starting another session replaces the capture window, so export evidence you want to retain first. Existing imported evidence stays in place until Inspect or Stop supplies a new snapshot.

The app samples every 500 ms, holds up to 500 full samples, and stops after ten minutes. An 8 MiB encoded-byte budget, including space reserved for snapshot metadata, keeps larger manifests within Surge's import limit. This is a bounded recent window, not an archive of the entire session. Removed older samples and transport drops produce an Unknown collection-health record. Failed or stale collection remains visible; readable ranges retain their own measured verdicts. No baseline file means the build requires review. Approval still uses the explicit command below.

```powershell
.\.venv\Scripts\python.exe scripts/native_capture.py approve --build v1 --reason "Reviewed fixture build v1"
.\.venv\Scripts\python.exe scripts/native_capture.py capture --build v1 --scenario clean --output native/captures/clean.jsonl
.\.venv\Scripts\python.exe scripts/native_capture.py capture --build v1 --scenario memory-change --output native/captures/changed.jsonl
```

Open either JSONL in Surge. Each capture has two range observations at each of the initial, sample, and restored snapshots (six records), with UTC timestamps and a session combining PID and process creation time. Outputs never overwrite an existing capture.

To test an update, collect `--build v2` before approval: it requires review. Then approve v2 with a reason and collect again into a new file: an unchanged approved v2 should have no finding. Earlier approvals remain available for v1. A rebuilt DLL has a different file fingerprint and needs a new approval.

`--scenario secondary-change` changes only the second range. `--scenario unreadable` makes the first range unavailable while the second remains readable; `--scenario unloaded` makes both unavailable. These test collection gaps. Those observations are **Unknown**, not clean. Startup or collection failure produces an explicit failed observation; failed approval leaves the registry unchanged. Malformed baseline registries stop collection instead of silently resetting approvals.

## What is checked

Windows CNG computes SHA-256 of the DLL and the bounded code range. The approved identity includes the DLL hash, range name, relative virtual address, range size, expected bytes, and fingerprint of the complete range manifest. Both configured ranges must be readable and unchanged before the command approves them together. Old single-range approvals remain readable but do not automatically approve a new manifest. A strict x64 PE parser rejects invalid layouts, forwarded exports, overlapping or missing file-backed ranges, writable code, and ranges touched by import or relocation fixups. The fixture's two small assembly routines deliberately have no relocation-dependent operands, so changing the module load address does not require changing its expected bytes.

The DLL exports a read-only, pointer-free `LabIntegrityManifest` declaration. Version 1 names 2–16 bounded export pairs; the collector resolves them from the owned file, not a user-supplied address. Its `surge-integrity-manifest-v1` evidence binds the architecture, module fingerprint and size, image size, ranges, executable file-backed spans and exclusions. Checked and excluded spans must partition those executable bytes exactly. Excluded bytes have no measured verdict; the denominator includes executable file padding and is not the whole process.

Approval now also binds this complete versioned manifest. Legacy cases and approvals remain readable, but legacy approvals cannot approve versioned observations. Review and explicitly approve the newly built fixture; collection never migrates approval automatically. A changed coverage declaration requires a separate approval even when its selected bytes are unchanged.

Unsupported versions, malformed declarations, overlapping sections, writable executable sections and fixups touching checked ranges are refused. Owned fixture DLLs disable incremental linking: export jump stubs are not treated as original routine boundaries. The collector does not discover arbitrary optimized C++ functions. See the [compatibility matrix](../docs/native-compatibility.md) for what was tested.

An in-memory mismatch and an unexpected page protection are separate review reasons. A missing approval is a review lead, not evidence that an update is malicious. Failure to read memory leaves comparison values unavailable. The inspector preserves raw bytes, hashes, permissions, Win32 errors, source identity, and approval provenance.

## Reproduce checks

```powershell
.\.venv\Scripts\python.exe -m unittest test_native_integrity -v
.\.venv\Scripts\python.exe scripts/test_native_live.py
.\.venv\Scripts\python.exe scripts/test_native_stream.py
.\.venv\Scripts\python.exe -m unittest test_native_session -v
cd desktop
node native.test.cjs
pnpm run test:stream
```

Coverage in the existing inspector reports ranges read, compared with approval, unavailable, unapproved, and changed. Versioned observations also show executable bytes in scope; Details explains exclusions and includes both manifest fingerprints. Declared scope is separate from successfully read bytes. The default manifest covers two routines totaling 15 bytes. A clean sibling range can have No finding while the snapshot has incomplete coverage; the unavailable range remains Unknown.

Imports verify coverage against every exported range and reject missing, duplicate, inconsistent, or overlapping declarations. Failed preparation of an unsupported image produces a failed capture rather than skipping a range. The manifest and records are unsigned; consistent fabrication is still outside this trust boundary.

The live runner uses its own isolated approval registry and exports cases into `native/captures`. It covers both DLL builds, unapproved and approved updates, changed memory, unreadable pages, unload/reload, and repeated process starts. These are controlled software checks, not measurements of real-cheat detection accuracy. Existing network evaluation evidence and protected holdouts are untouched.

Each test run gets a new folder; `native/captures/latest.json` identifies the newest one. `baseline_sha256` is the SHA-256 of the registry's canonical JSON content, so whitespace changes alone do not change its identity.

## Trust boundary

The registry and JSONL are local, unsigned evidence. Their fingerprints identify content; they do not authenticate the collector or prevent an attacker with equivalent privileges from fabricating an entire capture or editing approvals. Import validation rejects inconsistent derived verdicts, not an internally consistent forgery. Approval records are exported by fingerprint and reason; retain `baselines.json` alongside captures for review. Only one operator should modify a registry at a time. No automated enforcement, kernel driver, third-party attachment, or general-purpose memory scanner is included.

## Continuous collection contract

`surge_owned_app.exe` links the same collector library as the fixture runner. It loads only its own fixed DLL and emits a ready frame, complete sample frames, and an ending frame as UTF-8 JSON lines over an inherited pipe. Each frame declares `surge-native-stream-v1`. The ready frame fixes the build, manifest, interval and duration. Samples have increasing sequence numbers, monotonic elapsed time, UTC observation timestamps, and a cumulative transport-drop count. Process creation identity distinguishes PID reuse. The ending accounts for samples dropped after the last delivered frame.

The writer has a 32-frame queue. A full queue drops a new sample and increments its counter; the next delivered sequence exposes the gap. A blocked final write is canceled after a two-second drain period. Normal stdin accepts only `stop`; EOF also stops. Collection and DLL lifecycle operations share one thread, avoiding reads of an image during unload. Wall-clock adjustment cannot reverse monotonic elapsed time. Slow collection can delay the next sample without incrementing the transport-drop count; elapsed spacing exposes that delay.

The Python reader validates frame size, manifest, process identity, ordering and coverage before retaining a sample. It freezes the baseline registry for that session. Investigation uses a copied window, keeping background collection separate from mapping, selection and case state. Snapshots retain their sequence bounds and collection state, so missing beginning, internal or final samples cannot silently pass structural validation.

The independent validation runner starts the owned app with `--test-controls`, schedules changes through a separate control pipe and records acknowledgments outside the detector inputs. It tests approved updates, unapproved builds, changes in either configured range, unreadability, unload/reload, restarts, interrupted consumers and replay. It also verifies two explicit limits: a change outside the configured ranges and a change restored between samples may go undetected. These checks establish fixture correctness, not effectiveness against real cheats. Use `--soak-seconds 90` for the longer local performance run; default CI checks are shorter.

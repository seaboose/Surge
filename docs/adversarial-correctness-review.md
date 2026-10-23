# Adversarial correctness review and bounded fuzzing specification

Review date: 23 October 2026. Reviewed HEAD: `2b9e3c8bbfc22c7a82827f39e404fa87e7eb8fb5`, with the existing uncommitted performance/reliability milestone present. This is a review and proposed acceptance contract, not a completed fuzzing result. No production implementation, approval registry, native binary, published evidence, or protected network holdout was changed for this review.

## Outcome

The owned-app measurement design has a useful, deliberately small integrity contract. Its explicit byte ranges, complete coverage partition, approval-manifest binding, fail-closed collection errors, and bounded complete-sample retention support that contract. The review found two reproducible inconsistencies in **imported live evidence validation** that should be addressed before declaring the next correctness milestone complete:

1. A reversed sample sequence combined with a decreasing cumulative loss counter can pass replay validation and omit the required loss-health observation.
2. Imported live observations do not enforce the process-creation and build identity checks applied to the live stream; even an invalid PID can pass.

Both findings concern internally inconsistent evidence. Neither establishes a bypass of a trusted collector, arbitrary process access, a memory-safety exploit, or client authentication. Local evidence and approvals are already explicitly unsigned.

A third finding is a documentation/precedence discrepancy: an unreadable observation from an unapproved build is classified **Review with gaps**, not Unknown. Recovered staleness also has a narrower guarantee than the phrase “remains visible” suggests: current staleness produces health evidence, but a recovered stall need not leave a health record in the final export. These need precise contracts, not a larger product.

## Review method and evidence boundaries

The parent project's `AGENTS.md` and complete `Coordination/Surge-Handoff-Part-2.md` were read first. The initial repository status contained only the previously described performance work: modifications to README.md, SECURITY.md, desktop/README.md and docs/release-checks.md; new reliability runner, specification, results and sanitized evidence files. Those changes were preserved.

The review read the PE and descriptor parser, collector, owned producer, manifest and approval validation, stream decoder, retention/export validation, default policy, relevant engine/case paths and existing focused tests. Selected Python counterexamples were executed in memory using existing synthetic fixture builders, through `engine.parse_bytes` → `native_integrity.default_policy` → `engine.analyze`. No mutated executable was loaded or run. No random campaign, native sanitizer campaign, full suite rerun, or fresh performance run was performed.

Local reproduction source and results are in the parent project's `work/adversarial-review/reproduce.py` and `reproduction-results.json`. They are review scratch material, not a new published validation dataset. Repository-relative file/line references below refer to the reviewed tree before any fixes. “Reproduced” means executed here; “source inspection” identifies reasoning from code rather than a demonstrated runtime failure.

## The contract that exists today

### Supported layout and measurement

- **Fixed owned binaries only.** `OwnedCollector` accepts v1/v2 and constructs the DLL path beside its executable. It reads at most 64 MiB and keeps a read-only-sharing file handle open (`native/code_range_collector.cpp:82`, `:93`, `:98`). The app loads that fixed path (`native/owned_app.cpp:113`). This is neither arbitrary PID scanning nor a safe loader for hostile DLLs. An owned DLL is executable code, so mutations in the proposed parser harness must never reach `LoadLibraryExW`.
- **Bounded x64 PE subset.** The parser requires AMD64/DLL, exact PE32+ optional-header size, 16 directories, 1–96 sections, image size at most 512 MiB, bounded and nonoverlapping raw/virtual sections, and unique file-backed mapping for accessed bytes (`native/code_range_pe.hpp:26`, `:47`, `:156`). The collector's 64 MiB file limit is outside `LabImage`; a standalone harness must supply its own input limit.
- **Executable scope is file-backed scope.** It includes `SizeOfRawData` from executable, nonwritable sections, at most 32 such spans (`native/code_range_pe.hpp:75`). It does not claim every executable virtual byte, zero-fill tail, allocated page, or whole process. Checked and excluded intervals partition these file-backed spans exactly. The C++ collector constructs exclusions (`native/code_range_collector.cpp:116`); Python independently checks interval continuity and totals (`integrity_manifest.py:83`). Python is validating the declaration, not rereading the DLL to authenticate it.
- **Pointer-free declaration.** The v1 descriptor is exactly 2,064 bytes and contains 2–16 begin/end export pairs (`native/lab_manifest.hpp:5`, `:17`). It must reside wholly in one file-backed nonwritable, nonexecutable section. Names have canonical zero padding; the native limit is 63 visible ASCII identifier characters plus NUL. Begin/end identifiers must all be unique. Checked ranges are nonempty, at most 64 bytes, nonoverlapping, and wholly within one executable nonwritable file-backed section (`native/code_range_pe.hpp:91`, `:144`, `:223`). Default fixtures cover two ranges/15 bytes; the compatibility third-range fixture covers 24 bytes.
- **Specific fixup checks.** Checked ranges may not overlap the declared IAT span. The base-relocation directory is limited to 1 MiB; its blocks must be well formed, non-ABSOLUTE entries must be DIR64, their targets must fit the image, and no 8-byte target may overlap a checked range (`native/code_range_pe.hpp:241`). This does not implement the full Windows loader. Ordinary Release/Debug/MinSizeRel owned builds and forced rebasing were previously tested; arbitrary optimized routine boundaries, incremental thunks, unusual loader metadata and arbitrary third-party DLLs are not established support. Non-incremental fixture linking is explicit (`native/CMakeLists.txt:14`).
- **A sample is not an atomic process snapshot.** For each range, the collector checks module path, resolved begin-export address, committed MEM_IMAGE allocation ownership, containment in one queried region, and a complete self-memory read (`native/code_range_collector.cpp:198`). Protection comes from the preceding `VirtualQuery`; ranges are read in sequence. This supports bounded observations, not a simultaneous view or a proof that protection and bytes never changed between the two calls.

The header parser checks a useful structural subset; it is not a complete PE-format validator. For example, its optional-header checks do not enforce section/file alignment or a lower bound for `SizeOfHeaders` covering all headers (`native/code_range_pe.hpp:40`). Existing synthetic parser fixtures leave alignment fields zero (`native/manifest_pe_tests.cpp:29`). Acceptance by `LabImage` alone must not be reported as Windows loadability. There is no demonstrated native memory-safety defect in this review.

### Trust and approval

Approval is an explicit operator decision about the whole versioned manifest and configured reference ranges. The CLI requests a new clean capture and atomically replaces the registry only after successful validation (`scripts/native_capture.py:64`, `:103`). `approve` requires all configured phase/range observations to be readable, unchanged, and exactly PAGE_EXECUTE_READ (32); collection does not approve automatically (`native_integrity.py:310`). The live decoder takes a copy of the registry at session creation (`native_stream.py:106`).

Versioned matching binds module hash, range RVA/size, range name, range-manifest digest and integrity-manifest digest. Legacy and versioned approvals do not cross (`native_integrity.py:380`). Imported evidence recomputes observed hashes and derived match flags, but does not obtain and authenticate the original registry from its fingerprint (`native_integrity.py:445`). Expected hashes and approval assertions in consistently forged local evidence remain forgeable; this is explicitly outside the trust boundary, not a newly discovered weakness.

Trust assumptions are that the owned binaries, OS facilities, collector, local approval decision and analysis code behave as reviewed, and that the supplied evidence provenance is appropriate to the investigation. An equally privileged attacker controlling those components is outside the guarantee. SHA-256 fingerprints bind content; they do not attest who produced it. Changes outside declared coverage, restored before a read, or introduced between samples may be missed.

### What the verdicts establish

These meanings assume the native default policy. Saved investigations preserve their chosen configuration, and cases recompute under that configuration (`engine.py:783`, `:826`); a case fingerprint is not an assertion that the native default policy was used.

- **No finding:** for that range observation, the default rules have no finding or missing input: approval is asserted, observed bytes match the approved expected hash, and the reported page protection is exactly 32. It does not mean the entire DLL/session is verified, that every sibling range was readable, or that the evidence is authentic.
- **Review:** at least one default rule matched: unapproved build, approved-byte mismatch, or unexpected readable-page protection (`native_integrity.py:492`). A measured approved-byte mismatch is the in-scope integrity finding. An unapproved update is a review request, not evidence of malicious modification. Review can coexist with unavailable inputs.
- **Unknown:** there is a missing rule input or another analysis gap and no higher-priority finding. An approved unreadable range or a collection-health record is Unknown. Review takes precedence over gaps (`engine.py:743`), so the blanket statement “all unavailable observations are Unknown” is not currently true.
- **Health evidence:** transport drops, retention eviction, collection errors, and currently observed staleness do not convert readable sibling ranges into findings. They add Unknown health observations. A retained window is not a session archive.

The normal target is 500 ms for at most ten minutes, with a 32-frame native writer queue, 32 KiB line limit, and at most 500 complete samples within an 8 MiB encoded budget including reserves (`native/owned_app.cpp:16`, `:74`, `:226`; `native_stream.py:23`, `:338`). Sequence loss and retention omissions are distinct. An elapsed-time gap without a generated sample does not increment the producer's transport-drop count; the producer deliberately avoids catch-up bursts (`native/owned_app.cpp:354`).

## Confirmed findings

### C1 — Replay accepts sequence and loss-counter rollback

**Priority: fix before correctness acceptance. Reproduced.**

The live decoder rejects decreasing cumulative drops and nonincreasing sequence numbers (`native_stream.py:137`, `:142`). Export validation instead compares only the difference between consecutive counters (`native_stream.py:252`). It does not separately require increasing sequence or nondecreasing drops. The final health requirement uses the final drop count (`native_stream.py:287`).

Concrete reproducer, using two approved, versioned ranges and otherwise unchanged valid rows:

1. First group: `stream_sequence=3`, `stream_dropped_samples=2`, `stream_elapsed_ms=0`, event IDs `3:<range>`.
2. Second group: `stream_sequence=2`, `stream_dropped_samples=0`, `stream_elapsed_ms=500`, event IDs `2:<range>`.
3. Both groups: stopped snapshot, zero evictions, final sequence 2, final drops 0; no health row.

The first-group equation passes (`3 - 1 = 0 + 2`). The second passes because both differences are −2. The final equation passes, and the final zero-drop count avoids the health requirement. Full import/default analysis returned **4 No finding, 0 Review, 0 Unknown, 0 rows with gaps**. The unmutated control returned 2 No finding.

This is an impossible producer history accepted as a coherent export, with an explicitly declared earlier loss disappearing from health. It does not demonstrate that the genuine producer emits it. The bounded fix should enforce explicit sequence/drop monotonicity before the difference equation, with deterministic rejection tests at the replay boundary as well as the live boundary.

### C2 — Replay omits live process/build identity checks

**Priority: fix before correctness acceptance. Reproduced.**

`convert_frame` validates positive 32-bit PID and decimal process-creation identity, then compares session/PID/module hash/process creation/build across sibling observations (`native_stream.py:76`). `StreamDecoder.accept` also binds that identity across samples and to the ready build (`:153`). `validate_export` compares a different identity tuple omitting `process_started` and `build`; it does not validate PID's type/range (`:216`). `check_observation` does not supply those omitted checks (`native_integrity.py:31`).

Starting with one valid two-range approved versioned snapshot, each of these independent mutations passed full import/default analysis as **2 No finding, 0 Unknown**:

- Change only one sibling's `process_started` from `"1"` to `"999"`.
- Change only one sibling's `build` from `"v1"` to `"v2"`.
- Set both PIDs to −1.

Thus a replay can contradict its own process/build metadata while retaining measured-range verdicts. This matters because process creation is the documented discriminator for PID reuse (`native/README.md:75`). It is a provenance-consistency bug, not proof that a v2 module was actually measured or that a forged local source has been authenticated.

The bounded fix should define one live-export identity contract and apply it to all sibling rows and samples. Versioned live rows should retain valid positive PID, process-creation representation, supported build and their session consistency. Preserve deliberate legacy compatibility with explicit tests; do not silently require fields that historical schemas never promised. Decide explicitly whether a session string must encode PID/creation or is an opaque identifier; the present live checker does not enforce the encoding either.

### C3 — Unavailable plus unapproved is Review, contrary to blanket Unknown language

**Priority: clarify the contract and add one regression. Reproduced; not a clean-result bug.**

An empty registry and a versioned six-row capture with one `memory_status="failed"`, `observed_hex=null` observation produced **6 Review, 0 Unknown**. All rows have gaps because an unapproved observation lacks an approved expected-byte comparison; the unreadable row also lacks protection input. Its unapproved-build finding still takes precedence (`native_integrity.py:415`, `:492`; `engine.py:743`).

`README.md:15`, `native/README.md:35` and `:61` describe missing/unavailable observations as Unknown without this qualification. Recommended narrow resolution: preserve the engine's general finding-over-gaps precedence and document that unreadable approved observations are Unknown, whereas unreadable unapproved observations retain Review plus explicit collection gaps. Do not suppress the unreadable condition in details or assert a successful byte comparison. If the product instead requires Unknown to dominate, that is a deliberate verdict change needing an explicit decision before tests are frozen.

### Reproduce C1/C2 without the review scratch directory

From the repository root, run the following with the repository Python environment. It uses the existing `test_native_window.many_ranges` synthetic fixture, opens no child process, and writes no files. The `analyze` helper deliberately includes the encoded import and native default-policy boundaries. On the reviewed tree the control and each C2 mutation return two No finding records; C1 returns four. A corrected tree should reject the malformed cases.

```python
import copy
import engine
import native_integrity as native
import native_stream as stream
from test_native_window import many_ranges

def analyze(rows):
    data = engine.parse_bytes(engine.canonical(rows).encode(), "review.json")
    return engine.analyze(data, None, native.default_policy(data))["summary"]

decoder, observations = many_ranges(2)
group = decoder.accept(dict(
    schema=stream.STREAM_SCHEMA, type="sample", sequence=1,
    elapsed_ms=0, dropped_samples=0, observations=observations,
))
control = stream.snapshot_rows([group])
print("control", analyze(control))
first, second = copy.deepcopy(group), copy.deepcopy(group)
for rows, sequence, dropped, elapsed in ((first, 3, 2, 0), (second, 2, 0, 500)):
    for row in rows:
        row.update(stream_sequence=sequence, stream_dropped_samples=dropped,
                   stream_elapsed_ms=elapsed,
                   event_id=f"{sequence}:{row['range_name']}")
print("C1", analyze(stream.snapshot_rows(
    [first, second], dropped=0, final_sequence=2,
)))
for field, value in (("process_started", "999"), ("build", "v2"), ("pid", -1)):
    rows = copy.deepcopy(control)
    for row in (rows if field == "pid" else rows[1:]):
        row[field] = value
    print("C2", field, analyze(rows))
```

## Assurance gaps and hypotheses, not confirmed exploits

### A1 — Recovered staleness is not durable history

`_health_error` checks monotonic time elapsed since the last received frame; a new frame resets that timestamp (`native_stream.py:431`, `:496`). The decoder/export checker requires elapsed time to be nondecreasing but does not reject or label large gaps (`:146`, `:254`). Two valid approved sample groups at elapsed 0 and 6,500 ms replayed as **4 No finding, 0 Unknown** with no health row.

This proves replay accepts the long gap. Source inspection explains why health observed during a stall may disappear after recovery; this review did not suspend a real producer again. The prior performance milestone demonstrated current staleness and recovery, not durable retention of every stall. `native/README.md:77` already explicitly says that slow collection can delay samples without increasing transport drops and that elapsed spacing exposes the delay. This is a historical-health assurance choice, not a contradiction of that sampling contract or a confirmed detection bug. Between-sample integrity is explicitly excluded.

For this small milestone, state the existing limit precisely: “staleness is current collection health; recovered pauses remain visible in elapsed timing if retained, and are not guaranteed a final Unknown record.” Historical gap logging is a separate feature, not required to repair C1/C2. Tests must not call every long gap transport loss or demand whole-session continuity.

### A2 — Native parser acceptance is not a full loader-layout guarantee

Source inspection found useful fuzz targets, but no reproduced native crash or mismeasurement:

- Export lookup returns the first matching name without checking duplicate names or sorted name-table order (`native/code_range_pe.hpp:202`). The collector subsequently compares the runtime begin export address, which can refuse disagreement (`native/code_range_collector.cpp:221`). Test duplicate/ambiguous exports as parser contract cases; do not infer a false clean result without an owned, loadable reproduction.
- The import-fixup check uses the declared IAT directory. It does not traverse every import/delay-import structure or other loader metadata (`native/code_range_pe.hpp:241`). Unsupported loader arrangements need a precise reject-or-out-of-scope classification; the absence of a directory traversal alone is not proof that the current owned fixtures are mismeasured.
- Native descriptor names permit at most 63 visible characters, whereas the Python identifier regex permits 64 (`native/code_range_pe.hpp:109`; `native_integrity.py:77`, `:278`). This is a static cross-layer envelope discrepancy. The fuzz plan should test the boundary and record whether Python deliberately accepts a broader historical representation or is meant to mirror descriptor v1 exactly.
- `integrity_manifest.validate` accepts an exclusion reason `loader_fixup`, while the current producer emits only `not_declared` and rejects fixups intersecting checked ranges (`integrity_manifest.py:41`; `native/code_range_collector.cpp:193`). That does not mask checked bytes. Treat it as a broader representable declaration, already exercised by approval-binding tests, unless the schema contract is deliberately tightened.

### A3 — Resource and runtime limits remain scoped

Native work is bounded but nested: up to 16 ranges, repeated export-name resolution and relocation walks. Random small inputs can overwhelmingly reject at the DOS header and tell little about those deeper loops. Parser memory safety, worst supported traversal cost, loader behavior, concurrent mutation, and ten-minute GUI resource behavior are different questions. The bounded milestone below tests the first two selectively and preserves the existing compatibility/performance evidence for the others.

## Proposed small fuzzing milestone — frozen acceptance specification v1

This section defines future work. No fuzz campaign is authorized or reported as completed by this document. Its objective is to find and regress violations of the existing narrow integrity/evidence contract, including C1/C2, without adding scanners, new target classes, automatic enforcement, attestation, a general PE loader, or a new UI.

### Preflight and freeze

1. Record a clean source fingerprint or explicit patch fingerprint, OS, Python, compiler/SDK, harness version, sanitizer configuration and deterministic generator version. Preserve unrelated uncommitted work. Use disposable scratch builds and private temporary registries; never use `native/baselines.json` as a campaign output.
2. Verify an available Windows x64 native toolchain. CMake availability does not establish LLVM/libFuzzer/ASan availability. Prefer a coverage-guided, AddressSanitizer-enabled native harness if supported; confirm instrumentation by its diagnostic/self-check in an isolated test binary. Otherwise use an MSVC AddressSanitizer deterministic mutation driver and report “bounded mutation testing; no coverage-guided native claim.” If memory instrumentation is unavailable, do not mark native memory-safety acceptance passed; report that portion incomplete. Do not silently install a toolchain or broaden the milestone.
3. Commit to C3's documented precedence and A1's current-health interpretation before writing expected outcomes. Freeze the handling of 64-character names and ambiguous PE exports before using those cases as acceptance oracles. A rejected unsupported layout is acceptable; silently redefining it as supported after a failed final run is not.
4. Keep the existing controlled native positive/negative tests as development seeds. C1/C2 reproductions are mandatory development regressions, not held-back discoveries. No protected network holdout, game sample, private third-party binary or external process is needed.

### Three harness boundaries

**T1 — Native disk-image parser.** Feed bounded bytes to `LabImage`, then call `executable_ranges()` and `declared_ranges()`, and serialize the successfully resolved normalized ranges/spans for oracle comparison. Keep the input vector alive throughout. Catch only the parser's expected refusal exception; access violations, sanitizer reports, hangs and unexpected failures are findings. No `LoadLibrary`, `GetProcAddress` against fuzzed modules, collector construction, or executable code invocation. Exercise `probe` directly only in a separate legacy seed mode; full descriptor mode is the main target. Do not mistake successful construction alone for full validation.

Seeds: existing synthetic parser fixture; real owned v1/v2 bytes from the reviewed builds; a generated three-range layout; a minimal 2-range layout; one max-dimension synthetic layout. Store file hashes and normalize away local paths in reports. Mutations: truncate at every structure boundary; mutate header/count/size/RVA values around 0, 1, maximum and maximum+1; raw/virtual overlap and adjacency; section flags; export ordinal/count/name/forwarder cases; descriptor magic/version/count, canonical padding and unused entries; empty, 1-, 64- and 65-byte ranges; relocation block length/type/target boundaries; IAT and DIR64 overlap one byte before/at/after each checked edge. Include structure-preserving mutations that relocate tables while updating their pointers, so accepted deep paths are exercised.

**T2 — Python manifest, approval and verdict pipeline.** Use generated objects and their encoded JSON/JSONL forms through the production entry boundary, then `integrity_manifest.validate`, `validate_baselines`, `approve`/`convert`, and native default analysis as applicable. Direct validator tests supplement, rather than replace, actual encoded import. Include legacy/versioned approval separation and imported encoded manifest strings. Avoid native subprocess collection; approval fixtures are in-memory synthetic owned captures.

Seeds: 2/3/16 ranges; minimum/maximum code lengths; adjacent/gapped executable spans with correct exclusions; empty and fully approved registries; clean, changed, unreadable and unapproved combinations. Mutations: booleans versus integers, floats, negatives, huge numbers, missing/extra keys, duplicate JSON keys, invalid hex/hash/name lengths, partition holes/overlaps/outside spans, totals, metadata/digest mismatch, range reorder, schema downgrade/mixing, duplicate approvals, and poisoned derived match flags. Test embedded manifest JSON parsing separately: do not assume its duplicate-key policy is identical to the outer `engine.decode` path.

**T3 — Stream, complete-sample retention and replay.** Feed finite frame sequences to `StreamDecoder`; test framing with a bounded in-memory/fake-pipe reader using the production line rules; pass accepted groups through `SampleWindow`, `snapshot_rows`, encoded import and native default analysis. Use temporary case round-trips for a fixed subset of accepted examples. No real child processes, six-second sleeps, ten-minute sessions or renderer fuzzing. Existing runtime journeys remain smoke integration checks.

Seeds/mutations: ready/sample/end state transitions; missing/duplicate/reordered frames and ranges; independently changed and jointly rolled-back sequence/drop counters; changes to every identity component; PID/creation/build type and value boundaries; equal/negative/backward/nonfinite elapsed time; end before sample; duplicate end; frame after end; truncated/missing newline and UTF-8 boundaries; 32 KiB−1/at/+1 line sizes; health omission/wrong-session/mismatched counters; count and byte eviction; immutable snapshot checks; and malformed input after previously accepted samples. Both C1 and C2 must be exercised with versioned approved fixtures so “accepted but Review because unapproved” cannot conceal a consistency failure.

### Independent oracles and metamorphic properties

Do not use “the implementation accepted it” as the expected result. Do not copy the production validator into the oracle. Record generator intent before constructing input bytes.

1. **Coverage oracle:** for small generated layouts (image at most 64 KiB), independently enumerate executable byte sets and disjoint checked/excluded sets. Expected acceptance requires an exact disjoint union, correct totals, and each checked range within one declared file-backed executable span. This differs from the production interval walk. For large boundary layouts use a separately implemented event sweep, never allocate a 512 MiB bitmap.
2. **Native resolution oracle:** a model builder chooses section/file offsets, export identities, checked bytes and relocation spans first, then encodes them. Successful parse must reproduce those exact intended values. Single-reason invalid mutations have predeclared refusal expectations. Structure-preserving relocation of metadata must preserve resolved range content and scope. Differential comparisons with Python cover normalized manifests only; agreement between two implementations is corroboration, not proof of PE validity.
3. **Approval/verdict oracle:** use a small truth table independent of conversion code. Approved+complete+equal+protection32 gives no finding; approved+complete+different gives Review; complete unexpected protection gives Review; approved unreadable gives Unknown; unapproved gives Review with comparison gaps, including when unreadable; health gives Unknown. Any explicit byte-comparison claim requires readable bytes and approval. A manifest or module identity change must require new approval; stale/legacy approval must not silently authorize it. SHA recomputation alone is not the entire oracle.
4. **Stream oracle:** maintain a reference state machine with strictly increasing generated sequence, nondecreasing cumulative drops, fixed session/build/process identity, and nondecreasing elapsed time. Track delivered, lost and evicted sample numbers as sets or explicit short lists. Derive conservation from those lists, not the production subtraction formulas. Valid snapshots must agree with that model; impossible histories must reject on live input and replay.
5. **Retention oracle:** independently retain the latest whole groups under count and the specified encoded-byte accounting. Actual exported UTF-8 bytes must be at most 8 MiB and importable within 16 MiB/10,000-row/64-field limits. Excluded samples must be whole, eviction counts exact, and health present when required. Oversized incoming samples must not destroy prior retained evidence. Capture an existing snapshot, append/evict later groups, and verify the earlier snapshot's serialized value is unchanged.
6. **Round-trip properties:** accepted conversion → JSONL → import/default analysis must preserve original measured values, identities, coverage, default verdicts and gaps. A case made from that validated dataset must reopen with the same source/configuration/result. Do not use case recomputation to infer authenticity or force every arbitrary custom-policy case through the native default policy.
7. **Safe representation changes:** JSON object key order and legal whitespace must not change meaning or canonical digest. Array order is not assumed hash-neutral: manifest digests bind the actual arrays. Split a valid excluded interval into adjacent same-reason intervals and update totals; coverage semantics remain equivalent, but changed declaration fingerprints require new approval. Flip an excluded on-disk byte: checked byte expectations remain unchanged, while whole-module identity changes. An in-memory outside-range change need not be detected. These are distinct properties.

### Fixed budgets and separation of development/final variants

Use one worker at a time on one host. The campaign is at most **90 minutes wall time** after harness/toolchain preflight: at most 45 minutes development, 30 minutes final, and 15 minutes deterministic replay/reporting. Harness construction and human triage are separate work, not hidden campaign time. Stop at the time or attempt cap, whichever occurs first; a cap reached before required coverage is incomplete, not a pass.

- T1 development: at most 100,000 inputs or 20 minutes; final: at most 50,000 or 15 minutes.
- T2 development: at most 20,000 cases or 10 minutes; final: at most 10,000 or 5 minutes.
- T3 development: at most 10,000 histories or 15 minutes; final: at most 5,000 or 10 minutes.

Ordinary native input limit: 1 MiB. Add a fixed deterministic boundary pack with at most 2 MiB file size to hold 1 MiB/1 MiB+1 relocation directories plus headers and other required sections. The collector's 64 MiB/64 MiB+1 file envelope is source-inspected only and excluded from this milestone's runtime coverage: T1 does not construct the collector, load mutated DLLs, or claim that a copied size check tests the production constructor. Do not represent the smaller parser domain as exhaustive 64 MiB testing. Ordinary Python encoded input limit: 256 KiB; ordinary histories: 0–64 samples. A separate deterministic pack must cover 499/500/501 samples, 2/3/16 ranges, and encoded retention/import limits. This keeps most work small while explicitly identifying the untested outer file-size boundary.

Set an isolated-worker 5-second per-case timeout and 1 GiB private-memory cap; large deterministic boundary cases have 15 seconds under the same memory cap. A timed-out or resource-exceeding supported case is a finding requiring triage, not automatically a vulnerability or silently an unsupported seed. Record actual timings/peaks and the cost of max-dimension seeds. Budget breaches stop the campaign for review; they do not trigger unlimited minimization or more runs. Keep at most 200 minimized failures and 32 MiB of minimized corpus, plus a bounded log (10 MiB); larger required deterministic fixtures may be regenerated from source rather than duplicated.

Development uses fixed seeds and known cases. Before the final phase, freeze source, generator, oracles, thresholds, required branch categories, final seed recipe and expected outcomes. Final variants must combine different generated section positions, descriptor/export names, range lengths/counts, relocation placement, span partitioning and stream transition combinations, with separate fixed RNG seeds. Random seed changes alone are not independent coverage. Generate/inspect final concrete cases only after the freeze and preserve their hashes. This is a held-back synthetic check, not an independent adversarial dataset or statistical accuracy estimate.

If a final case fails, preserve the original result, minimize it and move it into development regression. Any fix changes the source fingerprint and invalidates that final acceptance attempt. Allow at most one replacement frozen final attempt, and only within the unused original 90-minute total, phase-time caps and target attempt caps. All reruns, minimization executions and retries consume those same caps; no budget resets. If there is insufficient remaining budget, or the replacement fails, report an incomplete milestone and remaining issues. Do not relabel the first failed final run as a rehearsal.

### Acceptance gates

All of the following are required; no aggregate “tests passed” count replaces a gate. T1 passes only with native instrumentation, native semantic oracles and required deep-path coverage satisfied; T2 passes only with the manifest/approval/verdict oracles and compatibility regressions satisfied; T3 passes only with the stream/retention/replay model, C1/C2 regressions and production-limit pack satisfied. An unexecuted or unavailable target is incomplete, not a pass.

1. **C1/C2 closed:** deterministic regressions reject counter rollback, sibling/cross-sample process/build conflicts, invalid PID/creation identity and the corresponding malformed exported forms. The tests exercise the versioned approved path and verify valid old formats remain intentionally compatible. C3 and A1 are documented with their chosen exact semantics.
2. **Native safety:** no unexplained sanitizer report, crash, unexpected exception, hang or memory-budget breach in T1. Missing instrumentation is reported as incomplete native safety validation. An intentional parser refusal is not a crash. Unsupported seeds must have a documented reason; they may not be removed merely to improve the pass count.
3. **Semantic correctness:** zero unresolved oracle violations, silent coverage changes, malformed histories accepted as coherent, invented approval, changed bytes labeled matching, or unavailable bytes labeled successfully compared. C1/C2 must fail before their fixes and pass after them. Valid positive seeds must still resolve and replay; an implementation rejecting everything fails.
4. **Reachability:** each required category above has at least one executed positive/deep-path case where applicable and one boundary/negative case. Record rejection reason distribution and accepted counts. In instrumented runs record coverage for the target files and branch progress, but do not set an arbitrary repository-wide percentage. Every intended deep branch family—exports, descriptor resolution, section mapping, relocation parsing, coverage partition, approval matching, stream end/loss, retention and replay—must have evidence of execution. A campaign stuck at the DOS or JSON front door is incomplete.
5. **Retention and replay:** deterministic production-limit packs pass whole-sample, byte-budget, health, snapshot stability and JSONL/case replay properties. Failures preserve earlier valid samples and produce appropriate error/Unknown health at the session boundary. Do not require recovery and continued decoding after a malformed stream; closing with retained evidence is the intended behavior.
6. **Determinism and final separation:** each minimized finding has a stable named regression, seed/generator recipe, input hash, expected behavior and source fingerprint. Replay the final minimized corpus twice with identical acceptance/classification. Final variants run after a documented freeze; report first-run outcomes, failures and any restart honestly.
7. **Existing compatibility preserved:** run the relevant Python integrity/manifest/stream/window/session tests, the three existing native CTests and the native/continuous export-replay smoke journeys after any production fixes. Reuse the established compatibility matrix where layout behavior changed. Do not repeat the ten-minute performance campaign unless a fix affects the producer, buffering, lifecycle or retention cost. Report exact commands and results in the future milestone evidence.

The future result should state “bounded parser and evidence-consistency testing on the listed owned layouts” and list the actual domains, instrumentation and limits. It must not claim whole-process verification, arbitrary PE compatibility, resistance to a privileged adversary, complete absence of bugs, real-cheat accuracy, historical continuity outside the retained window, or a new performance/leak-freedom result.

## Recommended implementation order after authorization

First add the two counterexamples as deterministic replay regressions, then make the narrow C1/C2 validation corrections. Clarify the precedence and staleness wording without changing measured-range semantics. Build the three bounded harnesses and their independent oracles, run development, freeze, and execute the held-back synthetic phase once. Preserve raw local paths/identities in private scratch only and publish a sanitized report with corpus/source fingerprints. There is no need for a new subsystem to resolve the findings in this review.

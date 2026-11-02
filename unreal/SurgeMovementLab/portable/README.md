# Portable shared-math checks

These small, dependency-free C++17 checks include the actual gameplay helper
`Source/SurgeMovementLab/SurviveSim.h`. They do not contain a second implementation
of its pathfinder, dash integrator, swept-clearance helper, or capture budget.

Run from the project directory using the already installed Microsoft compiler:

```powershell
pwsh -NoProfile -File scripts/check-portable.ps1
```

The reviewable runner uses installed MSVC 14.44.35207 and Windows SDK 10.0.26100.0
directly. PowerShell 7 or newer supplies process-tree termination on timeout.
It changes only child-process environment variables. It installs,
repairs, downloads, deletes, or configures nothing. Compilation and the short test
process each have a 60-second limit (configurable to 5–120 seconds), with at most
ten additional seconds for process-tree shutdown and output draining. Every attempt
creates a unique `Saved/Verification/portable-<timestamp>-<suffix>` directory;
invocation metadata and source/compiler hashes, compiler output, test output,
result metadata, source/runner snapshots, and any produced binaries remain there,
including on failure. The runner rejects a result if sources change during checks.
Output and compiler temporary files stay inside that project directory.

Coverage includes direct and detoured routes, independently sampled avoidance of
both fixed obstacles expanded by the requested radius, invalid endpoints and
radii, fixed-speed dash range/time boundaries and uneven frame partitions,
relative swept crossings/tangency/stationary motion, caller-selected blink
landing semantics, and capture row/byte limits including integer overflow.
Invalid clearance is positive infinity: callers must treat it as unavailable,
not serialize it or report a successful dodge.

This validates shared mathematical behavior and C++17 compilation. It does not
validate Unreal headers/UHT, engine compilation, actor/collision integration,
capture serialization, live timing, frame behavior, rendering, or playability.
The helper's blink test supplies the landing point as both player endpoints;
actual gameplay must select that discontinuous-motion rule correctly.

The October 26, 2026 local run passed **227 checks with zero failures** using
MSVC compiler file version 19.44.35229.0, C++17, `/W4`, and `/WX`. Its preserved
record is `Saved/Verification/portable-20261026-014304-942-0e8955d9`; invocation
and result records agree on shared-header SHA256
`FFCAAA6B8B9818568F4D3B6DA97334D775EEAD2149FDA6B6EB5E4E70EC1BC871`.

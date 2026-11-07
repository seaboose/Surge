# Native compatibility and limits

Surge measures ranges declared by its owned DLL. A versioned manifest binds the
module fingerprint, x64 layout, checked ranges, and executable exclusions.
Approval applies to that complete manifest and exact module build.

The parser rejects unsupported versions, malformed or overlapping declarations,
writable executable sections, and loader fixups touching checked ranges. The
owned DLLs disable incremental linking. The parser does not discover arbitrary
optimized C++ function boundaries or follow export jump thunks.

Legacy case and approval formats remain readable. A legacy approval does not
authorize a new versioned manifest. A changed module or coverage declaration
requires review and explicit approval; collection never approves it automatically.

Unchecked bytes, changes between samples, fabricated local evidence, and a
compromised collector remain outside these guarantees. The small controlled
demonstration is not an estimate of real-world cheat detection accuracy.

Build prerequisites and collection commands are in [native/README.md](../native/README.md).
The separate validation kit contains the compatibility matrix, controlled
scenarios, and historical results for their identified source versions.

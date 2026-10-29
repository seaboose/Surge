# Opening design and local case library acceptance

Scope: local, owned evidence only. No additional collection targets or network access.

1. Opening uses Surge, concise purpose text, cyan signal art, and three stacked actions. Keyboard focus and small-window layouts remain usable. Try Demo retains the existing owned-process collection.
2. Save creates a named, independent library snapshot of analyzed evidence, settings, and findings. Existing snapshots are never silently overwritten. Failed saves do not publish a library entry.
3. Open verifies the saved case through the existing engine before replacing the workspace. Library entries survive restart.
4. Rename changes only the display name, preserving case bytes and evidence fingerprints. Names are bounded and are never filesystem paths.
5. Delete requires confirmation and removes only the selected managed case. Original imported evidence, external case files, and other library entries remain unchanged. An open investigation remains in memory.
6. Import copies a portable case into managed storage and verifies that copy before publishing it; failure leaves the workspace and library unchanged. Export verifies and writes an independent portable file without overwriting any existing file.
7. Renderer requests accept opaque identifiers, not paths. File dialogs select external import/export locations. Invalid IDs and linked managed entries are rejected.

Run a short test after each feature, then desktop integration and relevant existing regression checks. Preserve failures and report precisely which checks ran. This is not a new full qualification or fuzzing campaign.

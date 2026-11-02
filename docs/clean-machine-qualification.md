# Clean-machine procedure

A clean-machine check runs the packaged app in a separate Windows installation
without Unreal, Python, or Node development tools. The [validation page](validation.md)
records the completed guest test and its limits.

1. Prepare a fresh Windows VM or test PC. Record its OS, display driver, account
   privilege, VM tools, and whether the starting image was restored or newly installed.
2. Copy the release ZIP, matching manifest, and separate QA kit. Verify their hashes
   before extraction. The QA tooling must not become an application dependency.
3. Use `scripts/check_clean_machine.ps1` with its documented arguments to run the
   packaged gameplay/report and native/import workflows. Preserve its result directory.
4. Verify report export, saved-data reopening, partial recordings, missing-component
   startup controls, and that installed payload files stayed unchanged.
5. Copy the results back and verify their hashes. Keep raw paths and browser profiles
   private; publish a concise receipt with explicit redactions and test scope.

A failed or interrupted attempt remains failed or incomplete. Tool installation,
a prepared VM, or a host check alone is not a clean-machine pass. A clean-machine
pass is separate from human usability testing and detection-accuracy evaluation.

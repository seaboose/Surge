# How Surge works

The renderer displays a paged view of the investigation. The Electron main process owns native file dialogs, clipboard access, and the Python worker. The worker holds the datasets and returns bounded results over process pipes.

The renderer cannot choose arbitrary filesystem paths or run commands. Every request is checked against an allowed operation and the current workspace revision. Replacing data or changing settings invalidates stale findings and comparison results.

`engine.py` parses bounded inputs, validates configuration, fits reference profiles, applies rules, and saves reproducible cases. Numeric profiles use a median and scaled median absolute deviation. Grouped profiles require enough reference observations; unsupported groups use the global profile with an explicit gap.

`evaluation.py` loads a separate source-bound label file. Labels do not enter the detector. Unknown targets count as missed, and unresolved legitimate records remain visible. Per-group counts help expose regressions hidden by an overall score.

`desktop_worker.py` connects the engine to investigation views. `workflow.py` handles policies and alerts. `comparison.py`, `mapping_checks.py`, and `record_search.py` keep comparison, import guidance, and search independent of presentation.

Saved cases embed data, settings, and fingerprints. Opening a case recomputes its result before accepting it. Fingerprints detect content changes; they are not signatures or proof that the source is trustworthy.

The Python process runs with the user's OS permissions. Isolation from the renderer reduces exposure, but it is not an operating-system sandbox for untrusted files. See the security notes for the trust boundary.

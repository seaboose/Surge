# Detection evaluation

Surge accepts externally labeled data. The bundled software tests use synthetic fixtures to verify behavior; they do not measure real-world detection effectiveness.

The external benchmark used RT-IoT2022 from UCI with publisher labels. Reference, development, and successive holdout partitions excluded previously used projected vectors. The partitions still come from one capture, so they do not establish independence across sessions or environments.

The latest accepted policy uses duration and payload signals, protocol/service reference groups, and a threshold of 1.8. On the paired round-three holdout, false positives fell from 193 to 167 among 683 legitimate records. Misses stayed at one among 9,317 targets, with no previously detected target lost. Thing_Speak improved from 131 to 105 false positives; Wipro remained 13 of 13. The remaining noise is too high for deployment.

The subsequent development review targeted Wipro. The retained policy flagged all 15 Wipro development records. The closest reference-interval prototype reduced that count to 14 and total false positives from 175 to 125, but lost eight detections and left one legitimate record unresolved. It was rejected. No new policy was released, and the reserved holdout was not opened.

Compact outcome records live in [evaluation/](evaluation/). They include the SHA-256 fingerprints of the original result artifacts. The [evaluation evidence archive](../evidence/surge-evaluation-evidence.zip) contains the already-scored round-three cases, labels, reports, and a file manifest. Extract it, then run `python scripts/verify_evidence.py <extracted-folder>` to reproduce both complete evaluation reports. In Surge, open `candidate.case.json`, import `holdout.labels.json` in Evaluate, and compare against `baseline.case.json`.

The full local research archive retains the original source snapshots, labels, cases, reports, reservation records, and failed candidates. It has not been rewritten for this release. The fresh round-four reservation remains private and unopened. Raw records and machine-specific test output are not part of the source zip; the evidence zip is a separate optional download.

The scripts in `benchmarks/` preserve the evaluation protocol and synthetic regression checks. Historical scoring commands require their matching archive and frozen sources; they are not a generic dataset download command. Do not rerun spent holdouts or treat a new release source tree as the historical frozen candidate.

Protection of reserved data is procedural under a shared OS identity, not an access-control boundary. No result here establishes effectiveness against game cheats or AI attacks.

Source: B. S. and Nagapadma, R. (2023), [RT-IoT2022](https://archive.ics.uci.edu/dataset/942/rt-iot2022), DOI 10.24432/C5P338, licensed under CC BY 4.0. The adapter projects selected network-flow fields and stores labels separately.

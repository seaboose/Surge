"""Reserve an untouched vector-disjoint holdout without opening its labels.

This is procedural separation in a shared local workspace, not an OS security
boundary. Only the evaluation role runs this script. Inputs and labels are not
materialized until the candidate is frozen and authorized for final scoring.
"""

import csv
import io
import json
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from prepare_rt_iot2022 import ROOT, ARCHIVE_SHA, FIELDS, encoded, sha

OUT = ROOT / "refinement-2"
PRIOR = (
    "reference.json",
    "test.json",
    "refinement-1/development.json",
    "refinement-1/holdout.json",
)


def write_new(path, value):
    with path.open("xb") as stream:
        stream.write(encoded(value) + b"\n")


def excluded_vectors():
    return {
        sha(encoded({f: row[f] for f in FIELDS}))
        for name in PRIOR
        for row in json.loads((ROOT / name).read_text())
    }


def selection(salt, include_truth=False):
    raw = (ROOT / "source.zip").read_bytes()
    if sha(raw) != ARCHIVE_SHA:
        raise ValueError("Source archive fingerprint changed.")
    excluded = excluded_vectors()
    pool = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive, archive.open("RT_IOT2022") as stream:
        for position, row in enumerate(
            csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")), 1
        ):
            signals = {f: row[f] for f in FIELDS}
            vector = sha(encoded(signals))
            if vector in excluded:
                continue
            rank = sha(f"{salt}:{vector}:{position}".encode())
            item = (rank, position, vector, signals)
            if include_truth:
                item += (row["Attack_type"],)
            pool.append(item)
    if len(pool) < 10000:
        raise ValueError("Fewer than 10000 unused rows remain.")
    chosen = sorted(sorted(pool)[:10000], key=lambda r: r[1])
    membership = sha(encoded([(r[1], r[2]) for r in chosen]))
    return chosen, dict(
        eligible_rows=len(pool),
        excluded_vectors=len(excluded),
        selected_records=len(chosen),
        membership_sha256=membership,
    )


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT / "plan.json").exists():
        raise ValueError("Plan already exists; do not resample.")
    salt = "surge-refinement-2:" + secrets.token_hex(32)
    _, counts = selection(salt)
    plan = dict(
        schema="surge-refinement-plan-v1",
        created_at=datetime.now(timezone.utc).isoformat(),
        archive_sha256=ARCHIVE_SHA,
        projection=FIELDS,
        sampling_salt=salt,
        **counts,
        prior_files={n: sha((ROOT / n).read_bytes()) for n in PRIOR},
        baseline_files={p.name: sha(p.read_bytes()) for p in sorted((OUT / "baseline").glob("*"))},
        reference="../reference.json",
        development="../refinement-1/development.json",
        development_labels_sha256=sha((ROOT / "refinement-1/development.labels.json").read_bytes()),
        selection="Exclude all prior reference, test, development, and holdout projected vectors; choose 10000 lowest seeded SHA-256 row ranks, then source order. No labels or detector results used for selection.",
        acceptance=[
            "Strictly fewer false positives than current approved grouped baseline",
            "No increase in missed targets",
            "Zero previously detected targets newly missed",
            "No increase in legitimate Unknown outcomes to manufacture fewer false positives",
        ],
        subgroup_review="Report every publisher class, new/resolved false positives, recovered/newly missed targets, legitimate long-duration subset using original reference-only cutoff. Subgroup regressions remain visible.",
        holdout_rule="One frozen candidate only. Materialize and score only after security review and parent authorization. No holdout-guided retuning.",
        protection="Role separation, deferred materialization, immutable-by-convention hashes and exclusive creation. All agents share a local OS identity and public archive; this is not enforced access isolation.",
        limits="Same public IoT capture; fresh rows and full projected vectors, not independent capture sessions. Not anti-cheat or AI-attack validation.",
    )
    write_new(OUT / "plan.json", plan)
    print(
        json.dumps(
            dict(
                plan_sha256=sha((OUT / "plan.json").read_bytes()),
                **counts,
                labels_inspected=False,
                holdout_materialized=False,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

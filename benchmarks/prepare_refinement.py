"""Create fresh development/holdout inputs before detector selection."""

import csv, io, json, zipfile
from pathlib import Path
from prepare_rt_iot2022 import ROOT, ARCHIVE_SHA, FIELDS, FEATURES, NORMAL, ATTACK, encoded, sha

OUT = ROOT / "refinement-1"


def write(name, value):
    with (OUT / name).open("xb") as stream:
        stream.write(encoded(value) + b"\n")


def prepare():
    OUT.mkdir(exist_ok=False)
    raw = (ROOT / "source.zip").read_bytes()
    assert sha(raw) == ARCHIVE_SHA
    used = []
    for name in ("reference.json", "test.json"):
        used.extend(json.loads((ROOT / name).read_text()))
    exclude = {sha(encoded({f: r[f] for f in FIELDS})) for r in used}
    pools = {"development": [], "holdout": []}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive, archive.open("RT_IOT2022") as stream:
        for position, row in enumerate(
            csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")), 1
        ):
            signals = {f: row[f] for f in FIELDS}
            key = sha(encoded(signals))
            if key in exclude:
                continue
            part = (
                "development"
                if int(sha(b"surge-refinement-split-1:" + key.encode()), 16) % 2 == 0
                else "holdout"
            )
            rank = sha(f"surge-refinement-sample-1:{key}:{position}".encode())
            pools[part].append((rank, position, signals, row["Attack_type"], key))
    selections = {k: sorted(sorted(v)[:10000], key=lambda r: r[1]) for k, v in pools.items()}
    assert all(len(v) == 10000 for v in selections.values()), {k: len(v) for k, v in pools.items()}
    assert not ({r[4] for r in selections["development"]} & {r[4] for r in selections["holdout"]})
    partition = "Excludes previous reference/test source positions and identical projected vectors. Remaining vectors split by salted SHA-256 parity, sampled by independent salted row hash, 10000 each. Same capture; session independence is not established."
    for name, items in selections.items():
        write(name + ".json", [dict(source_record=p, **signals) for _, p, signals, _, _ in items])
        labels = []
        for n, (_, position, signals, truth, key) in enumerate(items, 1):
            assert truth in NORMAL | ATTACK
            labels.append(
                dict(
                    row=n,
                    truth="legitimate" if truth in NORMAL else "target",
                    group=truth,
                    note=f"Publisher Attack_type={truth}; original source record {position}.",
                )
            )
        write(
            name + ".labels.json",
            dict(
                schema="surge-labels-v1",
                source_sha256=sha((OUT / (name + ".json")).read_bytes()),
                provenance=dict(
                    author="RT-IoT2022 authors / UCI",
                    method="Publisher class labels, unchanged from archive; not independently re-audited.",
                    partition=partition,
                    purpose="development" if name == "development" else "holdout",
                    independent_of_detector=True,
                ),
                labels=labels,
            ),
        )
    write(
        "split.json",
        dict(
            archive_sha256=ARCHIVE_SHA,
            partition=partition,
            reference="../reference.json",
            reference_sha256=sha((ROOT / "reference.json").read_bytes()),
            prior_test_sha256=sha((ROOT / "test.json").read_bytes()),
            development_sha256=sha((OUT / "development.json").read_bytes()),
            holdout_sha256=sha((OUT / "holdout.json").read_bytes()),
            projection=FIELDS,
            excluded_vectors=len(exclude),
            overlap_vectors=0,
            development_records=10000,
            holdout_records=10000,
            acceptance="Freeze one candidate on development; accept on holdout only if false positives decrease and missed targets do not increase. No holdout-guided retuning.",
        ),
    )
    print(
        "Prepared 10000 development and 10000 holdout records; excluded old vectors; no cross-split vector overlap. Holdout outcomes not examined."
    )


if __name__ == "__main__":
    prepare()

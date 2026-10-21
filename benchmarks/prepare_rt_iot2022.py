"""Reproducible, offline preparation of the official UCI data archive.

No downloaded code is executed. No extraction of archive member paths occurs.
This adapter lives outside Surge runtime; imported files use its generic workflow.
"""

import csv
import io
import json
import hashlib
import math
from collections import Counter
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent / "rt-iot2022"
ARCHIVE_SHA = "bcaa24d62abbb1215be576d5cf9c02dfcb0bb7c4c2f5a00e03055afaa1ed109e"
FEATURES = [
    "flow_duration",
    "fwd_pkts_tot",
    "bwd_pkts_tot",
    "flow_pkts_per_sec",
    "fwd_pkts_payload.avg",
    "bwd_pkts_payload.avg",
]
FIELDS = ["proto", "service", "id.orig_p", "id.resp_p", *FEATURES]
NORMAL = {"MQTT_Publish", "Thing_Speak", "Wipro_bulb"}
ATTACK = {
    "DOS_SYN_Hping",
    "ARP_poisioning",
    "NMAP_UDP_SCAN",
    "NMAP_XMAS_TREE_SCAN",
    "NMAP_OS_DETECTION",
    "NMAP_TCP_scan",
    "DDOS_Slowloris",
    "Metasploit_Brute_Force_SSH",
    "NMAP_FIN_SCAN",
}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write(name, value):
    with (ROOT / name).open("xb") as file:
        file.write(encoded(value) + b"\n")


def prepare():
    raw = (ROOT / "source.zip").read_bytes()
    assert sha(raw) == ARCHIVE_SHA, "Archive changed; review the source before preparing new data."
    counts = Counter()
    reference = []
    candidates = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert [(i.filename, i.file_size) for i in archive.infolist()] == [("RT_IOT2022", 54781794)]
        with archive.open("RT_IOT2022") as file:
            reader = csv.DictReader(io.TextIOWrapper(file, encoding="utf-8-sig"))
            assert set(FIELDS + ["Attack_type"]) <= set(reader.fieldnames)
            for position, row in enumerate(reader, 1):
                truth = row["Attack_type"]
                assert truth in NORMAL | ATTACK
                counts[truth] += 1
                # Preserve original decimal text. The engine reads numeric strings.
                signals = {key: row[key] for key in FIELDS}
                for key in FEATURES:
                    assert math.isfinite(float(signals[key]))
                key = sha(encoded(signals))
                # All identical projected input vectors stay in one partition.
                partition = int(sha(b"surge-reference-v1:" + key.encode()), 16) % 10
                item = dict(source_record=position, **signals)
                if partition < 3:
                    if truth in NORMAL:
                        reference.append((key, position, item, truth))
                else:
                    rank = sha(f"surge-test-v1:{key}:{position}".encode())
                    candidates.append((rank, position, item, truth))
    assert sum(counts.values()) == 123117
    # Selection does not depend on detection outputs or test labels.
    test = sorted(sorted(candidates)[:10000], key=lambda r: r[1])
    reference = sorted(sorted(reference)[:10000], key=lambda r: r[1])
    assert len(test) == 10000 and len(reference) >= 5
    ref_inputs = {encoded({key: r[2][key] for key in FIELDS}) for r in reference}
    assert not any(encoded({key: r[2][key] for key in FIELDS}) in ref_inputs for r in test)
    reference_durations = sorted(float(row[2]["flow_duration"]) for row in reference)
    edge_cutoff = reference_durations[math.ceil(0.95 * len(reference_durations)) - 1]
    settings = dict(
        features=FEATURES,
        session=None,
        event_id="source_record",
        time=None,
        time_format="milliseconds",
        threshold=6,
        rules=[],
    )
    protocol = dict(
        dataset="RT-IoT2022",
        source_url="https://archive.ics.uci.edu/dataset/942/rt-iot2022",
        download_url="https://archive.ics.uci.edu/static/public/942/rt-iot2022.zip",
        citation="B. S. & Nagapadma, R. (2023). RT-IoT2022. UCI Machine Learning Repository. DOI:10.24432/C5P338.",
        license="CC BY 4.0; https://creativecommons.org/licenses/by/4.0/",
        archive_sha256=ARCHIVE_SHA,
        source_counts=dict(counts),
        selected_counts=dict(Counter(row[3] for row in test)),
        reference_counts=dict(Counter(row[3] for row in reference)),
        partition="SHA-256 of the 10 projected signal strings, without labels or IDs, keeps identical vectors together. Salted hash modulo 10: 0-2 reference candidates (normal only), 3-9 test candidates. Test rows use lowest 10000 independently salted row hashes, then original source order. No threshold fitting.",
        reference_records=len(reference),
        test_records=len(test),
        projected_input_overlap=0,
        settings=settings,
        legitimate_edge="Duration above reference-only 95th percentile, grouped by publisher normal class.",
        duration_edge_cutoff=edge_cutoff,
        limitations=[
            "Publisher labels are independent of Surge, not independently re-audited by us.",
            "Same testbed; no session, host, or temporal generalization claim. The provided file has no capture-session partition.",
            "Projection from 83 input features to 10 plus source position fits Surge limits; six numeric signals are preselected, not optimized.",
            "The UCI webpage normal-class counts/names do not fully match the archive. Actual class strings/counts are recorded here; no Amazon-Alexa rows exist in this archive.",
            "Controlled IoT network attacks do not validate game cheat or AI attack detection.",
            "A first-use benchmark sample, not a vendor standard score. Do not tune on these test outcomes and continue calling it untouched.",
        ],
    )
    # Persist the protocol and inputs before the evaluation command is run.
    write("protocol.json", protocol)
    write("reference.json", [row[2] for row in reference])
    write("test.json", [row[2] for row in test])
    write("policy.json", dict(schema="surge-policy-v1", settings=settings))
    labels = []
    for position, (_, original, item, category) in enumerate(test, 1):
        legitimate = category in NORMAL
        edge = legitimate and float(item["flow_duration"]) > edge_cutoff
        labels.append(
            dict(
                row=position,
                truth="legitimate" if legitimate else "target",
                group=category + (" · long duration" if edge else ""),
                note=f"Publisher Attack_type={category}; original CSV data record {original}. "
                + (
                    "Duration exceeds reference 95th percentile; this is an edge-case description, not the truth label."
                    if edge
                    else "Truth comes from publisher class, not Surge."
                ),
            )
        )
    write(
        "labels.json",
        dict(
            schema="surge-labels-v1",
            source_sha256=sha((ROOT / "test.json").read_bytes()),
            provenance=dict(
                author="B. S. Sharmila and Rohini Nagapadma (RT-IoT2022 / UCI)",
                method="Publisher Attack_type column. MQTT_Publish, Thing_Speak, Wipro_bulb mapped to legitimate; the nine documented attack classes mapped to target. Not manually re-audited. DOI:10.24432/C5P338.",
                partition=protocol["partition"]
                + " Same testbed; session independence is not established.",
                purpose="holdout",
                independent_of_detector=True,
            ),
            labels=labels,
        ),
    )
    print(
        json.dumps(
            dict(
                reference=len(reference),
                test=len(test),
                labels=dict(Counter(r["truth"] for r in labels)),
                classes=protocol["selected_counts"],
                duration_edge_cutoff=edge_cutoff,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    prepare()

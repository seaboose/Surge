"""Evidence contract for the fixed, bounded retention qualification cases."""

import hashlib
import json
import re


CASE_IDS = tuple(
    [f"count_{ranges}_{samples}" for ranges in (2, 3, 16) for samples in (499, 500, 501)]
    + [f"{kind}_{edge}" for kind in ("single", "aggregate") for edge in ("minus", "exact", "plus")]
    + ["multiple_evictions", "utf8", "empty"]
    + [f"import_{format}_{edge}" for format in ("json", "jsonl") for edge in ("minus", "exact", "plus")]
)

LIMITS = dict(
    max_samples=500,
    window_bytes=8 * 1024 * 1024,
    health_reserve_bytes=16 * 1024,
    row_reserve_bytes=512,
    accounting_budget=8 * 1024 * 1024 - 16 * 1024,
    import_bytes=16 * 1024 * 1024,
)


def bounded_integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid retention evidence integer")
    return value


def validate_evidence(data):
    """Require every named case twice, at fixed limits, with matching fingerprints."""
    if not isinstance(data, dict):
        raise ValueError("Missing retention evidence")
    if (
        data["schema"] != "surge-retention-v1"
        or data["status"] != "passed"
        or data["original_fuzzing_campaign"] != "incomplete"
        or data["repeatability"] != "passed"
    ):
        raise ValueError("Retention qualification incomplete")
    limits = data["limits"]
    if not isinstance(limits, dict) or set(limits) != set(LIMITS):
        raise ValueError("Missing retention limits")
    for key, expected in LIMITS.items():
        bounded_integer(limits[key], expected, expected)
    expected = {(name, repeat) for name in CASE_IDS for repeat in (1, 2)}
    bounded_integer(data["evaluations"], len(expected), len(expected))
    runs = data["runs"]
    if not isinstance(runs, list) or len(runs) != len(expected):
        raise ValueError("Missing retention evaluations")
    indexed = {}
    for row in runs:
        if not isinstance(row, dict) or row["status"] != "passed":
            raise ValueError("Retention evaluation did not pass")
        repeat = bounded_integer(row["repeat"], 1, 2)
        if not isinstance(row["id"], str):
            raise ValueError("Invalid retention identity")
        key = row["id"], repeat
        if key not in expected or key in indexed:
            raise ValueError("Unknown or duplicate retention evaluation")
        indexed[key] = row
        for field in ("input_sha256", "result_sha256"):
            if not isinstance(row[field], str) or not re.fullmatch(r"[a-f0-9]{64}", row[field]):
                raise ValueError("Invalid retention fingerprint")
        metrics = row["metrics"]
        if not isinstance(metrics, dict):
            raise ValueError("Missing retention measurements")
        encoded = json.dumps(metrics, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        if row["result_sha256"] != hashlib.sha256(encoded).hexdigest():
            raise ValueError("Retention measurements differ from their fingerprint")
        if row["id"].startswith("count_"):
            _, ranges, samples = row["id"].split("_")
            ranges, samples = int(ranges), int(samples)
            bounded_integer(metrics["ranges"], ranges, ranges)
            bounded_integer(metrics["samples"], samples, samples)
            retained = bounded_integer(metrics["retained"], 1, min(samples, 500))
            evicted = bounded_integer(metrics["evicted"], 0, samples - 1)
            if retained + evicted != samples or (ranges == 2 and retained != min(samples, 500)):
                raise ValueError("Retention sample conservation failed")
            bounded_integer(metrics["accounted_bytes"], 1, LIMITS["accounting_budget"])
            for field in ("json_bytes", "jsonl_bytes"):
                bounded_integer(metrics[field], 1, LIMITS["window_bytes"])
            if any(metrics[field] != "passed" for field in ("case_replay", "snapshot_stable", "replay")):
                raise ValueError("Retention replay or snapshot check incomplete")
        elif row["id"].startswith("import_"):
            label = row["id"].split("_")[-1]
            expected_bytes = LIMITS["import_bytes"] + {"minus": -1, "exact": 0, "plus": 1}[label]
            bounded_integer(metrics["bytes"], expected_bytes, expected_bytes)
            outcome = "rejected_at_byte_guard" if label == "plus" else "accepted"
            if metrics["outcome"] != outcome:
                raise ValueError("Import byte boundary outcome differs")
        else:
            budget = LIMITS["accounting_budget"]
            expected_metrics = {
                "single_minus": (2, 1, 1, budget - 1),
                "single_exact": (2, 1, 1, budget),
                "single_plus": (1, 1, 0, 1024),
                "aggregate_minus": (2, 2, 0, budget - 1),
                "aggregate_exact": (2, 2, 0, budget),
                "aggregate_plus": (2, 1, 1, budget - 4095),
                "multiple_evictions": (5, 3, 2, budget),
                "utf8": (3, 2, 1, budget - 3072),
                "empty": (1, 1, 0, 1024),
            }[row["id"]]
            for field, expected_value in zip(
                ("samples", "retained", "evicted", "accounted_bytes"), expected_metrics
            ):
                bounded_integer(metrics[field], expected_value, expected_value)
    if set(indexed) != expected:
        raise ValueError("Missing retention cases")
    for name in CASE_IDS:
        first, second = indexed[name, 1], indexed[name, 2]
        if any(first[field] != second[field] for field in ("input_sha256", "result_sha256")):
            raise ValueError("Retention repeatability failed")
    return data

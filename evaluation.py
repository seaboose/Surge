"""Evaluate frozen decisions against external labels; never feed truth to detection."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json

import engine

SCHEMA = "surge-labels-v1"
MAX_LABEL_BYTES = 8 * 1024 * 1024
OUTCOMES = ("Detected", "False positive", "Missed", "Clear", "Unresolved", "Unlabeled")


def text(value, field, limit=1000, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(
            f"Labels: {field} must be {'nonempty ' if not empty else ''}text, up to {limit} characters."
        )
    return value


def load(path, source):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_LABEL_BYTES + 1)
    if len(raw) > MAX_LABEL_BYTES:
        raise ValueError("Labels exceed the 8 MiB limit.")
    doc = engine.decode(raw.decode("utf-8-sig"))
    if (
        not isinstance(doc, dict)
        or set(doc) != {"schema", "source_sha256", "provenance", "labels"}
        or doc["schema"] != SCHEMA
    ):
        raise ValueError(
            "Use a surge-labels-v1 file. Save a label template for the current source."
        )
    if doc["source_sha256"] != source.digest:
        raise ValueError(
            "Labels belong to a different source. The full source fingerprint must match."
        )
    p = doc["provenance"]
    fields = {"author", "method", "partition", "purpose", "independent_of_detector"}
    if not isinstance(p, dict) or set(p) != fields:
        raise ValueError(
            "Labels need author, method, partition, purpose, and independent_of_detector provenance."
        )
    for key in ("author", "method", "partition"):
        text(p[key], f"provenance.{key}")
    if (
        p["purpose"] not in ("holdout", "development", "synthetic")
        or type(p["independent_of_detector"]) is not bool
    ):
        raise ValueError(
            "Label purpose must be holdout, development, or synthetic; independence must be true or false."
        )
    if not isinstance(doc["labels"], list) or len(doc["labels"]) > len(source.rows):
        raise ValueError("Labels must be a list with at most one entry per source record.")
    seen, groups = set(), set()
    for item in doc["labels"]:
        if not isinstance(item, dict) or set(item) != {"row", "truth", "group", "note"}:
            raise ValueError("Each label needs row, truth, group, and note.")
        row = item["row"]
        if type(row) is not int or not 1 <= row <= len(source.rows) or row in seen:
            raise ValueError(f"Labels: invalid or duplicate source record {row!r}.")
        seen.add(row)
        if item["truth"] not in ("legitimate", "target", None):
            raise ValueError(
                f"Labels: record {row} truth must be legitimate, target, or null (unlabeled)."
            )
        text(item["group"], f"record {row} group", 120, empty=item["truth"] is None)
        text(item["note"], f"record {row} note", empty=item["truth"] is None)
        if item["truth"] is not None:
            groups.add(item["group"])
    if len(groups) > 100:
        raise ValueError("Use at most 100 label groups.")
    return dict(document=doc, file=dict(name=Path(path).name, sha256=engine.sha(raw)))


def write_new(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > engine.MAX_CASE:
        raise ValueError("Evaluation output exceeds 64 MiB.")
    created = False
    path = Path(path)
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(raw)
            stream.flush()
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise


def template(source):
    return dict(
        schema=SCHEMA,
        source_sha256=source.digest,
        provenance=dict(
            author="", method="", partition="", purpose="development", independent_of_detector=False
        ),
        labels=[dict(row=i, truth=None, group="", note="") for i in range(1, len(source.rows) + 1)],
    )


def summarize(records):
    counts = {key: 0 for key in OUTCOMES}
    counts.update(Counter(r["outcome"] for r in records))
    positive = sum(r["truth"] == "target" for r in records)
    negative = sum(r["truth"] == "legitimate" for r in records)
    unresolved_targets = sum(r["truth"] == "target" and r["status"] == "Unknown" for r in records)

    # Missed includes unassessable targets: missing input must not improve recall.
    def rate(n, d):
        return dict(value=n / d if d else None, numerator=n, denominator=d)

    return dict(
        counts=counts,
        total=len(records),
        labeled=positive + negative,
        targets=positive,
        legitimate=negative,
        unresolved_targets=unresolved_targets,
        rates=dict(
            precision=rate(counts["Detected"], counts["Detected"] + counts["False positive"]),
            recall=rate(counts["Detected"], positive),
            false_positive=rate(counts["False positive"], negative),
            missed=rate(counts["Missed"], positive),
        ),
    )


def evaluate(source, reference, config, result, labels):
    if labels["document"]["source_sha256"] != source.digest:
        raise ValueError("Labels no longer match this source.")
    if reference and source.digest == reference.digest:
        raise ValueError("Reference and test data must be separate sources.")
    by_row = {item["row"]: item for item in labels["document"]["labels"]}
    records = []
    for record in result["records"]:
        label = by_row.get(record["row"], {})
        truth, status = label.get("truth"), record["status"]
        if truth is None:
            outcome = "Unlabeled"
        elif truth == "target":
            outcome = "Detected" if status == "Review" else "Missed"
        elif status == "Review":
            outcome = "False positive"
        else:
            outcome = "Unresolved" if status == "Unknown" else "Clear"
        records.append(
            dict(
                row=record["row"],
                truth=truth,
                group=label.get("group", ""),
                note=label.get("note", ""),
                status=status,
                outcome=outcome,
                gaps=bool(record["gaps"]),
            )
        )
    warnings = [
        "Label independence is supplied provenance, not verified by Surge.",
        "Rates describe this labeled sample, not deployment accuracy. Review means a detection lead, not a malicious verdict.",
    ]
    p = labels["document"]["provenance"]
    if p["purpose"] != "holdout" or not p["independent_of_detector"]:
        warnings.append(
            "Development or non-independent labels cannot establish holdout performance."
        )
    warnings.append(
        "If these results influence settings, use a new untouched holdout for the next effectiveness claim."
    )
    overlap = dict(exact_records=0, groups={})
    if reference:
        signatures = {engine.sha(engine.canonical(row).encode("utf-8")) for row in reference.rows}
        overlap["exact_records"] = sum(
            engine.sha(engine.canonical(row).encode("utf-8")) in signatures for row in source.rows
        )
        if overlap["exact_records"]:
            warnings.append(
                f"{overlap['exact_records']} test records exactly match reference records. Audit the partition; duplicates can be legitimate but do not prove independence."
            )
        roles = dict(config.get("context", {}))
        if config.get("session"):
            roles["Session"] = config["session"]
        for role, field in roles.items():
            refs = {
                engine.canonical(row[field])
                for row in reference.rows
                if row.get(field) not in (None, "")
            }
            tests = {
                engine.canonical(row[field])
                for row in source.rows
                if row.get(field) not in (None, "")
            }
            overlap["groups"][role] = len(refs & tests)
        if any(overlap["groups"].values()):
            warnings.append(
                "Reference and test data share mapped identities. Check session/user and time boundaries before claiming independent results."
            )
    else:
        warnings.append("Rules only: no reference profile is loaded.")
    summary = summarize(records)
    if summary["labeled"] < summary["total"]:
        warnings.append("Unlabeled records are excluded from rates. Coverage is shown separately.")
    if not summary["targets"] or not summary["legitimate"]:
        warnings.append(
            "Both target and legitimate examples are needed to assess both error types."
        )
    groups = {}
    for row in records:
        if row["truth"] is not None:
            groups.setdefault(row["group"], []).append(row)
    # Hash exact settings and decisions. Neither evidence nor labels are rewritten.
    return dict(
        schema="surge-evaluation-v1",
        created_utc=datetime.now(timezone.utc).isoformat(),
        source=source.manifest(),
        reference=reference.manifest() if reference else None,
        engine=result["engine"],
        settings=config,
        settings_sha256=engine.sha(engine.canonical(config).encode("utf-8")),
        result_sha256=engine.sha(engine.canonical(result).encode("utf-8")),
        labels=labels["file"],
        provenance=p,
        summary=summary,
        groups=[dict(group=g, **summarize(rows)) for g, rows in sorted(groups.items())],
        overlap=overlap,
        warnings=warnings,
        records=records,
        definitions=dict(
            detected="Target labeled record with Review.",
            false_positive="Legitimate labeled record with Review, including partial evidence.",
            missed="Target labeled record without Review, including Unknown.",
            clear="Legitimate labeled record with No finding; not a safety verdict.",
            unresolved="Legitimate labeled record with Unknown; not counted as clear.",
            rates="Recall and missed use all labeled targets; false positives use all labeled legitimate records; precision uses labeled Review records. Unlabeled records are excluded. Zero denominators are null, never zero.",
        ),
    )

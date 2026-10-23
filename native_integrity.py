"""Bounded native evidence conversion and automatic field-rule mapping.

Approval is a local operator decision, not cryptographic client attestation.
The JSONL export carries the exact baseline fingerprint used for that decision.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
import integrity_manifest as integrity

SCHEMA = "surge-native-integrity-v1"
BASELINE_SCHEMA = "surge-native-baselines-v1"


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def hex_bytes(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9a-f]{2}){1,64}", value):
        raise ValueError("Expected a bounded lowercase code-range hex value.")
    return bytes.fromhex(value)


def check_observation(row):
    if not isinstance(row, dict) or row.get("schema") != "native-code-range-v1":
        raise ValueError("Unsupported native observation.")
    expected = hex_bytes(row.get("reference_hex"))
    if (
        row.get("reference_sha256") != hashlib.sha256(expected).hexdigest()
        or row.get("range_size") != len(expected)
        or not isinstance(row.get("range_rva"), int)
        or isinstance(row["range_rva"], bool)
        or not 0 < row["range_rva"] < 512 * 1024 * 1024
        or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("module_sha256", "")))
    ):
        raise ValueError("Native range identity or hash is inconsistent.")
    if row.get("memory_status") not in ("complete", "failed", "not_loaded"):
        raise ValueError("Unsupported collection status.")
    if row["memory_status"] == "complete":
        if len(hex_bytes(row.get("observed_hex"))) != len(expected):
            raise ValueError("Incomplete observed code range.")
    elif row.get("observed_hex") is not None:
        raise ValueError("Failed collection must not claim observed bytes.")
    if (
        type(row.get("page_protection")) is not int
        or not 0 <= row["page_protection"] <= 0xFFFFFFFF
    ):
        raise ValueError("Invalid page protection.")
    for key in ("session_id", "phase", "captured_at"):
        if not isinstance(row.get(key), str) or not 0 < len(row[key]) <= 128:
            raise ValueError(f"Missing or invalid {key}.")
    return expected


RANGE_KEYS = ("range_name", "range_rva", "range_size", "reference_hex", "reference_sha256")
PHASES = ("initial", "sample", "restored")


def validate_manifest(ranges):
    if not isinstance(ranges, list) or not 2 <= len(ranges) <= 16:
        raise ValueError("Use 2 to 16 configured ranges.")
    seen = set()
    for entry in ranges:
        if not isinstance(entry, dict) or set(entry) != set(RANGE_KEYS):
            raise ValueError("Malformed range manifest.")
        name = entry["range_name"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)
            or name in seen
        ):
            raise ValueError("Range names must be unique bounded identifiers.")
        seen.add(name)
        check_observation(
            dict(
                entry,
                schema="native-code-range-v1",
                module_sha256="0" * 64,
                memory_status="complete",
                observed_hex=entry["reference_hex"],
                page_protection=32,
                session_id="manifest",
                phase="initial",
                captured_at="manifest",
            )
        )
    ordered = sorted(ranges, key=lambda r: r["range_rva"])
    if any(
        a["range_rva"] + a["range_size"] > b["range_rva"] for a, b in zip(ordered, ordered[1:])
    ):
        raise ValueError("Configured code ranges overlap.")
    return ranges


def validate_capture(capture):
    if not isinstance(capture, dict) or capture.get("schema") not in (
        "native-code-capture-v1",
        "native-code-capture-v2",
    ):
        raise ValueError("Unsupported capture format.")
    rows = capture.get("observations")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError("Capture must contain bounded observations.")
    for row in rows:
        check_observation(row)
    if capture["schema"] == "native-code-capture-v1":
        if "integrity_manifest" in capture:
            raise ValueError("Versioned integrity needs complete multi-range coverage.")
        return rows
    ranges = validate_manifest(capture.get("ranges"))
    if "integrity_manifest" in capture:
        for row in rows:
            integrity.validate(
                capture["integrity_manifest"],
                ranges,
                row["module_sha256"],
                row.get("module_size"),
            )
            if type(row.get("module_size")) is not int:
                raise ValueError("Versioned capture needs its module size.")
    if len(rows) != len(ranges) * len(PHASES):
        raise ValueError(
            "Capture is incomplete: every phase must report every configured range."
        )
    identity = (rows[0]["module_sha256"], rows[0]["session_id"], rows[0].get("pid"))
    seen = set()
    for row in rows:
        key = (row["phase"], row.get("range_name"))
        if key in seen or row["phase"] not in PHASES:
            raise ValueError("Duplicate or invalid phase/range.")
        seen.add(key)
        if (row["module_sha256"], row["session_id"], row.get("pid")) != identity:
            raise ValueError("Capture process or build identity changed.")
        expected = next((r for r in ranges if r["range_name"] == row.get("range_name")), None)
        if expected is None or any(row.get(k) != expected[k] for k in RANGE_KEYS):
            raise ValueError("Observed range differs from the configured manifest.")
    return rows


def coverage(rows):
    readable = [r for r in rows if r["memory_status"] == "complete"]
    return dict(
        coverage_expected_ranges=len(rows),
        coverage_read_ranges=len(readable),
        coverage_compared_ranges=sum(r["baseline_approved"] is True for r in readable),
        coverage_unavailable_ranges=len(rows) - len(readable),
        coverage_unapproved_ranges=sum(r["baseline_approved"] is False for r in rows),
        coverage_changed_ranges=sum(
            r["memory_matches"] is False or r["protection_matches"] is False for r in rows
        ),
        coverage_expected_bytes=sum(r["range_size"] for r in rows),
        coverage_read_bytes=sum(r["range_size"] for r in readable),
    )


def validate_coverage(rows):
    # Stream health records report collection loss, not measured code ranges.
    health = [r for r in rows if r.get("stream_health") is True]
    if health:
        from native_stream import validate_health

        for row in health:
            validate_health(row)
        rows = [r for r in rows if r.get("stream_health") is not True]
    marked = [r for r in rows if "range_manifest" in r]
    versioned = [
        r for r in rows if "integrity_manifest" in r or "integrity_manifest_sha256" in r
    ]
    if versioned and (len(versioned) != len(rows) or len(marked) != len(rows)):
        raise ValueError("Cannot mix versioned coverage and legacy observations.")
    if not marked:
        if any(any(k.startswith("coverage_") for k in r) for r in rows):
            raise ValueError("Coverage needs a range manifest.")
        return
    if len(marked) != len(rows):
        raise ValueError("Cannot mix declared coverage and legacy observations.")
    groups = {}
    for row in rows:
        encoded = row["range_manifest"]
        if not isinstance(encoded, str) or len(encoded) > 16384:
            raise ValueError("Invalid range manifest encoding.")
        manifest = validate_manifest(json.loads(encoded))
        if row.get("range_manifest_sha256") != digest(manifest):
            raise ValueError("Range manifest fingerprint differs.")
        if versioned:
            value = row.get("integrity_manifest")
            if not isinstance(value, str) or len(value) > 32768:
                raise ValueError("Invalid integrity manifest encoding.")
            declaration = integrity.validate(
                json.loads(value), manifest, row["module_sha256"], row.get("module_size")
            )
            if type(row.get("module_size")) is not int or row.get(
                "integrity_manifest_sha256"
            ) != digest(declaration):
                raise ValueError("Integrity manifest fingerprint or module size differs.")
        key = (
            row["session_id"],
            row["module_sha256"],
            row.get("stream_sequence", row["phase"]),
        )
        groups.setdefault(key, []).append(row)
    live = any("stream_sequence" in r for r in rows)
    if live:
        from native_stream import validate_export

        validate_export(rows, health)
    sessions = {}
    declarations = {}
    for session, module, phase in groups:
        sessions.setdefault((session, module), set()).add(phase)
        for row in groups[(session, module, phase)]:
            current = row.get("integrity_manifest_sha256")
            key = (session, module)
            if key in declarations and declarations[key] != current:
                raise ValueError("Integrity manifest changed within a session.")
            declarations[key] = current
    if not live and any(phases != set(PHASES) for phases in sessions.values()):
        raise ValueError("Coverage must include initial, sample and restored snapshots.")
    for group in groups.values():
        manifest = json.loads(group[0]["range_manifest"])
        if len(group) != len(manifest) or len({r["range_name"] for r in group}) != len(group):
            raise ValueError("Coverage is incomplete or contains duplicate ranges.")
        expected = {r["range_name"]: r for r in manifest}
        for row in group:
            spec = expected.get(row["range_name"])
            if (
                spec is None
                or row["range_manifest"] != group[0]["range_manifest"]
                or any(row[k] != spec[k] for k in RANGE_KEYS)
            ):
                raise ValueError("Coverage range identity differs.")
        totals = coverage(group)
        for row in group:
            if any(type(row.get(k)) is not int or row[k] != v for k, v in totals.items()):
                raise ValueError("Coverage totals differ from the observations.")


def validate_baselines(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "entries"}
        or value["schema"] != BASELINE_SCHEMA
    ):
        raise ValueError("Unsupported baseline registry.")
    entries = value["entries"]
    if not isinstance(entries, list) or len(entries) > 128:
        raise ValueError("Use at most 128 approved ranges.")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {
            "range_manifest_sha256",
            "range_name",
            "integrity_manifest_sha256",
        } != {
            "module_sha256",
            "range_rva",
            "range_size",
            "reference_hex",
            "reference_sha256",
            "approved_at",
            "reason",
        }:
            raise ValueError("Malformed approval entry.")
        if "integrity_manifest_sha256" in entry and (
            not re.fullmatch(r"[0-9a-f]{64}", str(entry["integrity_manifest_sha256"]))
            or "range_manifest_sha256" not in entry
            or "range_name" not in entry
        ):
            raise ValueError("Versioned approval needs complete manifest identity.")
        if "range_manifest_sha256" in entry or "range_name" in entry:
            if not re.fullmatch(
                r"[0-9a-f]{64}", str(entry.get("range_manifest_sha256", ""))
            ) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_]{0,63}", str(entry.get("range_name", ""))
            ):
                raise ValueError("Invalid approved manifest identity.")
        check_observation(
            dict(
                entry,
                schema="native-code-range-v1",
                memory_status="complete",
                observed_hex=entry["reference_hex"],
                page_protection=32,
                session_id="validation",
                phase="initial",
                captured_at=entry["approved_at"],
            )
        )
        if not isinstance(entry["reason"], str) or not 1 <= len(entry["reason"].strip()) <= 240:
            raise ValueError("An approval needs a short reason.")
        key = (
            entry["module_sha256"],
            entry["range_rva"],
            entry["range_size"],
            entry.get("integrity_manifest_sha256"),
        )
        if key in seen:
            raise ValueError("Duplicate baseline identity.")
        seen.add(key)
    return value


def approve(capture, registry, reason):
    validate_baselines(registry)
    rows = validate_capture(capture)
    multi = capture["schema"] == "native-code-capture-v2"
    if not multi and len(rows) != 3:
        raise ValueError("Approval requires a complete fresh clean capture.")
    for row in rows:
        check_observation(row)
        if (
            row.get("scenario") != "clean"
            or row["memory_status"] != "complete"
            or row["observed_hex"] != row["reference_hex"]
            or row["page_protection"] != 32
        ):
            raise ValueError("Only readable, unchanged, execute-read code can be approved.")
    keys = ("module_sha256", "range_rva", "range_size", "reference_hex", "reference_sha256")
    entries = []
    for first in (
        [
            next(
                r
                for r in rows
                if r["phase"] == "initial" and r["range_name"] == spec["range_name"]
            )
            for spec in capture["ranges"]
        ]
        if multi
        else rows[:1]
    ):
        entry = {k: first[k] for k in keys}
        related = (
            [r for r in rows if r.get("range_name") == first.get("range_name")]
            if multi
            else rows
        )
        if len(related) != 3 or any(any(row[k] != entry[k] for k in keys) for row in related):
            raise ValueError("Capture identity changed during approval.")
        if multi:
            entry.update(
                range_name=first["range_name"], range_manifest_sha256=digest(capture["ranges"])
            )
            if "integrity_manifest" in capture:
                entry["integrity_manifest_sha256"] = digest(capture["integrity_manifest"])
        entry.update(approved_at=datetime.now(timezone.utc).isoformat(), reason=reason)
        entries.append(entry)
    result = {"schema": BASELINE_SCHEMA, "entries": [*registry["entries"], *entries]}
    return validate_baselines(result)


def convert(capture, registry):
    validate_baselines(registry)
    rows = validate_capture(capture)
    multi = capture["schema"] == "native-code-capture-v2"
    result = [
        convert_observation(
            row,
            registry,
            capture["ranges"] if multi else None,
            capture.get("integrity_manifest"),
        )
        for row in rows
    ]
    if multi:
        for phase in PHASES:
            group = [r for r in result if r["phase"] == phase]
            attach_coverage(group, capture["ranges"], capture.get("integrity_manifest"))
        validate_coverage(result)
    return result


def convert_observation(row, registry, ranges=None, integrity_manifest=None):
    """Apply the same approval decision to one-shot and continuous observations."""
    check_observation(row)
    if "integrity_manifest" in row or "integrity_manifest_sha256" in row:
        raise ValueError("Raw observations must use their capture-level integrity manifest.")
    manifest_sha = None
    if integrity_manifest is not None:
        if type(row.get("module_size")) is not int:
            raise ValueError("Versioned observation needs its module size.")
        integrity.validate(
            integrity_manifest, ranges, row["module_sha256"], row.get("module_size")
        )
        manifest_sha = digest(integrity_manifest)
    entry = next(
        (
            e
            for e in registry["entries"]
            if all(e[k] == row[k] for k in ("module_sha256", "range_rva", "range_size"))
            and e.get("integrity_manifest_sha256") == manifest_sha
            and (
                (ranges is None and "range_manifest_sha256" not in e)
                or (
                    e.get("range_manifest_sha256") == digest(ranges)
                    and e.get("range_name") == row["range_name"]
                )
            )
        ),
        None,
    )
    complete = row["memory_status"] == "complete"
    approved = entry is not None
    expected = entry["reference_sha256"] if entry else None
    observed = hashlib.sha256(hex_bytes(row["observed_hex"])).hexdigest() if complete else None
    return dict(
        row,
        schema=SCHEMA,
        event_id=f"{row['phase']}:{row['range_name']}" if ranges else row["phase"],
        baseline_sha256=digest(registry),
        baseline_approved=approved,
        approval_reason=entry["reason"] if entry else "Build has no approved baseline",
        approved_at=entry["approved_at"] if entry else None,
        expected_sha256=expected,
        observed_sha256=observed,
        memory_matches=(observed == expected) if approved and complete else None,
        protection_matches=(row["page_protection"] == 32) if complete else None,
    )


def attach_coverage(rows, ranges, integrity_manifest=None):
    totals = coverage(rows)
    for row in rows:
        row.update(
            totals,
            range_manifest=json.dumps(ranges, sort_keys=True, separators=(",", ":")),
            range_manifest_sha256=digest(ranges),
        )
        if integrity_manifest is not None:
            row.update(
                integrity_manifest=json.dumps(
                    integrity_manifest, sort_keys=True, separators=(",", ":")
                ),
                integrity_manifest_sha256=digest(integrity_manifest),
            )


def default_policy(data):
    """Recognize only consistently marked exports; ordinary imports stay unchanged."""
    if not data.rows or not any(r.get("schema") == SCHEMA for r in data.rows):
        return None
    required = {
        "event_id",
        "session_id",
        "captured_at",
        "pid",
        "baseline_approved",
        "memory_matches",
        "protection_matches",
    }
    for row in data.rows:
        if row.get("schema") != SCHEMA or not required <= row.keys():
            raise ValueError("Native evidence cannot mix schemas or omit required fields.")
        for key in ("baseline_approved", "memory_matches", "protection_matches"):
            if row[key] is not None and type(row[key]) is not bool:
                raise ValueError(f"Native {key} must be true, false, or null.")
        if row.get("collection_error") is not None:
            if row.get("memory_status") != "failed" or any(
                row[k] is not None
                for k in ("baseline_approved", "memory_matches", "protection_matches")
            ):
                raise ValueError("Failed collection cannot claim a verdict.")
            continue
        check_observation(dict(row, schema="native-code-range-v1"))
        complete = row["memory_status"] == "complete"
        observed = (
            hashlib.sha256(hex_bytes(row["observed_hex"])).hexdigest() if complete else None
        )
        expected = row.get("expected_sha256")
        if row["baseline_approved"] is True:
            if not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
                raise ValueError("Approved evidence needs its expected hash.")
        elif expected is not None:
            raise ValueError("Unapproved evidence cannot claim an expected hash.")
        matches = (
            (observed == expected) if complete and row["baseline_approved"] is True else None
        )
        protection = row["page_protection"] == 32 if complete else None
        if (
            row.get("observed_sha256") != observed
            or row["memory_matches"] is not matches
            or row["protection_matches"] is not protection
        ):
            raise ValueError("Native derived verdict differs from its captured evidence.")
    validate_coverage(data.rows)
    return dict(
        features=[],
        session="session_id",
        event_id="event_id",
        time="captured_at",
        time_format="iso8601",
        threshold=6,
        context={"Process": "pid"},
        rules=[
            dict(
                name="Build is not approved",
                field="baseline_approved",
                op="eq",
                value=False,
                priority="Warning",
            ),
            dict(
                name="Code differs from approved baseline",
                field="memory_matches",
                op="eq",
                value=False,
                priority="Error",
            ),
            dict(
                name="Code page is not execute-read",
                field="protection_matches",
                op="eq",
                value=False,
                priority="Warning",
            ),
        ],
    )

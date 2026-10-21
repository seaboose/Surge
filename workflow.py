"""Portable policies and local alert output; input never specifies executable actions."""

from datetime import datetime, timezone
import json
from pathlib import Path

import engine

MAX_POLICY = 256 * 1024
POLICY_SCHEMA = "surge-policy-v1"


def _write_new(path, raw):
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


def load_policy(path, current, reference):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_POLICY + 1)
    if len(raw) > MAX_POLICY:
        raise ValueError("Policy exceeds 256 KiB.")
    try:
        policy = engine.decode(raw.decode("utf-8-sig"))
        if (
            not isinstance(policy, dict)
            or set(policy) != {"schema", "settings"}
            or policy["schema"] != POLICY_SCHEMA
        ):
            raise ValueError("Choose a Surge policy file.")
        engine.validate_config(policy["settings"], current, reference)
        return policy["settings"]
    except (UnicodeError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError("Policy is malformed or its fields do not match the loaded data.") from exc


def save_policy(path, current, reference, config):
    engine.validate_config(config, current, reference)
    raw = json.dumps(
        {"schema": POLICY_SCHEMA, "settings": config}, ensure_ascii=False, allow_nan=False, indent=2
    ).encode("utf-8")
    if len(raw) > MAX_POLICY:
        raise ValueError("Policy exceeds 256 KiB.")
    _write_new(path, raw)


def priority(record, config):
    """Priority is user policy, not a confidence score or inferred attack label."""
    levels = {r["name"]: r.get("priority", "Notice") for r in config["rules"]}
    found = [levels[e["name"]] if e["kind"] == "rule" else "Notice" for e in record["evidence"]]
    return max(found, key=engine.PRIORITIES.index) if found else None


def visible(record, config, minimum="All", hide_clear=True):
    if minimum != "All" and minimum not in engine.PRIORITIES:
        raise ValueError("Unknown priority filter.")
    # Collection/interpretation gaps must never disappear behind a priority cutoff.
    if record["gaps"]:
        return True
    if record["status"] == "No finding":
        return not hide_clear and minimum == "All"
    level = priority(record, config)
    return minimum == "All" or (
        level is not None and engine.PRIORITIES.index(level) >= engine.PRIORITIES.index(minimum)
    )


def context_values(source_row, config):
    return {
        role: {"field": field, "value": source_row.get(field)}
        for role, field in config.get("context", {}).items()
    }


def export_alerts(path, current, reference, config, result, minimum="All"):
    # Revalidate the snapshot, including sources and policy, before output.
    case = engine.case_document(current, reference, config, result)
    selected = [r for r in result["records"] if visible(r, config, minimum, hide_clear=True)]
    metadata = {
        "type": "export",
        "schema": "surge-alerts-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": current.manifest(),
        "reference": reference.manifest() if reference else None,
        "settings": config,
        "minimum_priority": minimum,
        "gaps_always_included": True,
        "alerts": len(selected),
        "case_payload_sha256": case["payload_sha256"],
        "meaning": "Policy priorities are not attack confidence. Imported context is unverified.",
    }
    chunks = [engine.canonical(metadata).encode("utf-8") + b"\n"]
    size = len(chunks[0])
    if size > engine.MAX_CASE:
        raise ValueError("Alert export exceeds 64 MiB. Use a smaller source.")
    for record in selected:
        source_row = current.rows[record["row"] - 1]
        alert = {
            "type": "alert",
            "priority": priority(record, config),
            **record,
            "context": context_values(source_row, config),
            "source_record": source_row,
        }
        raw = engine.canonical(alert).encode("utf-8") + b"\n"
        size += len(raw)
        if size > engine.MAX_CASE:
            raise ValueError("Alert export exceeds 64 MiB. Use a smaller source.")
        chunks.append(raw)
    _write_new(path, b"".join(chunks))
    return len(selected)

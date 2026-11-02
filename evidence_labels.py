"""Readable provenance and time without guessing the source clock."""

from datetime import datetime, timezone
import json


def time_label(record, config, original):
    field = config["time"]
    if not field:
        return "Not mapped"
    raw = json.dumps(original.get(field), ensure_ascii=False)
    if record["time_ms"] is None:
        return f"Unavailable · from {field}: {raw}"
    if config["time_format"] == "iso8601":
        # Parse the original value to preserve precision lost by float epoch time.
        value = datetime.fromisoformat(str(original[field]).replace("Z", "+00:00"))
        utc = value.astimezone(timezone.utc).isoformat().replace("+00:00", " UTC")
        return f"Absolute time · {utc}\nFrom {field}: {raw}"
    unit = "s" if config["time_format"] == "seconds" else "ms"
    origin = config.get("time_origin", "unspecified")
    if origin == "elapsed":
        return f"Elapsed time · {raw} {unit} since source clock start\nFrom {field} · no timezone"
    if origin == "unix":
        value = float(original[field]) / (1000 if unit == "ms" else 1)
        utc = datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", " UTC")
        return f"Absolute time · {utc}\nFrom {field}: {raw} {unit} · Unix epoch"
    return f"{raw} {unit} · origin not specified\nFrom {field}"


def source_label(source, reference=None):
    text = f"Data: {source.name}\nSHA-256: {source.digest[:12]}…"
    if reference:
        text += f"\nReference: {reference.name}"
    else:
        text += "\nReference: None"
    return text

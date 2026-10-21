"""Bounded file adapters, inspectable detection, and reproducible case files."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from import_errors import FieldFailure, ImportFailure, ImportIssue, MAX_ISSUES

VERSION = "0.1.0"
MAX_BYTES = 16 * 1024 * 1024
MAX_CASE = 64 * 1024 * 1024
MAX_ROWS = 10_000
MAX_FIELDS = 64
MAX_RULES = 32
PRIORITIES = ("Notice", "Warning", "Error", "Critical")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Nonfinite JSON number: {value}")


def decode(text):
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
    except (RecursionError, OverflowError) as exc:
        raise ValueError("JSON is too deeply nested or contains an unsupported number.") from exc


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def number(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) and abs(result) <= 1e100 else None


def _flatten(row, prefix="", depth=0):
    if not isinstance(row, dict) or depth > 4:
        raise FieldFailure(
            "Records must be objects with at most four nested object levels. Use one object per record and reduce deeper nesting.",
            prefix or None,
        )
    result = {}
    for key, value in row.items():
        if (
            not isinstance(key, str)
            or not key.strip()
            or len(key) > 120
            or any(ord(c) < 32 for c in key)
        ):
            raise FieldFailure(
                "Field names must be nonempty, at most 120 characters, and contain no control characters. Rename this field.",
                f"{prefix}.{key}" if prefix else key,
            )
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            nested = _flatten(value, name, depth + 1)
            if set(nested) & set(result):
                raise FieldFailure(
                    "Nested and dotted field names collide. Rename one field so each flattened name is unique.",
                    sorted(set(nested) & set(result))[0],
                )
            result.update(nested)
        elif isinstance(value, list):
            raise FieldFailure(
                "This field contains an array. Convert arrays to event records before import.", name
            )
        else:
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise FieldFailure("Use text, a number, true, false, or null.", name)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and number(value) is None
            ):
                raise FieldFailure(
                    "Unsupported numeric magnitude. Use a finite number between -1e100 and 1e100.",
                    name,
                )
            if len(str(value)) > 4096:
                raise FieldFailure(
                    "This value exceeds 4,096 characters. Shorten it or move the long content outside this dataset.",
                    name,
                )
            if name in result:
                raise FieldFailure(
                    "Nested and dotted field names collide. Rename one field so each flattened name is unique.",
                    name,
                )
            result[name] = value
        if len(result) > MAX_FIELDS:
            raise FieldFailure(
                "A record supports at most 64 fields. Reduce the selected source fields.", name
            )
    return result


@dataclass(frozen=True)
class Dataset:
    name: str
    format: str
    text: str
    digest: str
    fields: tuple[str, ...]
    rows: tuple[dict, ...]

    def manifest(self):
        return {
            "name": self.name,
            "format": self.format,
            "sha256": self.digest,
            "records": len(self.rows),
            "fields": list(self.fields),
        }


class _SourcePairs(dict):
    """Compact parsed object with the first duplicate's original position.

    Keep the first value and the duplicate boundary so validation reports the
    same first problem in source order, without retaining a tuple per field.
    """

    __slots__ = ("duplicate", "before_duplicate")

    def __init__(self, pairs):
        super().__init__()
        self.duplicate = None
        self.before_duplicate = None
        for key, value in pairs:
            if key in self:
                if self.duplicate is None:
                    self.duplicate = key
                    self.before_duplicate = len(self)
            else:
                self[key] = value


def _source_object(value, prefix="", depth=0):
    if not isinstance(value, _SourcePairs):
        return value
    if depth > 4:
        raise FieldFailure("Use at most four nested object levels. Reduce nesting here.", prefix)
    result = {}
    for index, (key, child) in enumerate(value.items()):
        if index == value.before_duplicate:
            path = f"{prefix}.{value.duplicate}" if prefix else value.duplicate
            raise FieldFailure(
                "Duplicate JSON key. Rename or remove the repeated key; values cannot be silently overwritten.",
                path,
            )
        path = f"{prefix}.{key}" if prefix else key
        result[key] = _source_object(child, path, depth + 1)
    if value.duplicate is not None:
        path = f"{prefix}.{value.duplicate}" if prefix else value.duplicate
        raise FieldFailure(
            "Duplicate JSON key. Rename or remove the repeated key; values cannot be silently overwritten.",
            path,
        )
    return result


def _decode_source(text):
    return json.loads(text, object_pairs_hook=_SourcePairs)


def parse_bytes(raw, name, format=None):
    def fail(message, **location):
        raise ImportFailure(name, [ImportIssue(message, **location)])

    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        fail("Choose a nonempty UTF-8 file no larger than 16 MiB.")
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 240
        or any(c in name for c in ("/", "\\", "\x00"))
    ):
        fail("A source name must be a plain filename.")
    format = format or Path(name).suffix.lower().lstrip(".")
    if format not in ("csv", "json", "jsonl", "ndjson"):
        fail("Supported files: CSV, JSON arrays, JSONL, and NDJSON. Choose one of these formats.")
    try:
        original = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(
            f"Invalid UTF-8 at byte {exc.start + 1}. Save the source as UTF-8 before importing it."
        )
    text = original.removeprefix("\ufeff")
    rows, issues = [], []
    record = 0
    source_fields = {}
    # Local, bounded sharing of immutable text. Never intern untrusted strings
    # globally or merge numeric/boolean/null values with their text forms.
    strings = {}

    def accept(value, line=None):
        nonlocal record
        record += 1
        if record > MAX_ROWS:
            fail(
                "Limit: 10,000 records per source. Split the source into smaller files.",
                record=record,
                line=line,
            )
        try:
            row = _flatten(_source_object(value))
            for field in row:
                if field not in source_fields and len(source_fields) >= MAX_FIELDS:
                    raise FieldFailure(
                        "A source supports at most 64 distinct fields. Reduce the source fields.",
                        field,
                    )
                source_fields[field] = None
            for field, value in row.items():
                if isinstance(value, str):
                    if len(strings) >= 256:
                        strings.clear()
                    row[field] = strings.setdefault(value, value)
            rows.append(row)
        except FieldFailure as exc:
            issues.append(ImportIssue(str(exc), record, line, field=exc.field))
        if len(issues) >= MAX_ISSUES:
            raise ImportFailure(name, issues, stopped=True)

    try:
        if format == "csv":
            reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            fields = next(reader, [])
            if not fields:
                fail("CSV requires a row of column names.", line=1)
            seen = {}
            for column, field in enumerate(fields, 1):
                if field in seen:
                    issues.append(
                        ImportIssue(
                            f"CSV requires unique column names. Columns {seen[field]} and {column} repeat this name. Rename one.",
                            line=1,
                            field=field,
                        )
                    )
                seen[field] = column
                try:
                    _flatten({field: ""})
                except FieldFailure as exc:
                    issues.append(ImportIssue(str(exc), line=1, field=exc.field))
                if len(issues) >= MAX_ISSUES:
                    raise ImportFailure(name, issues, stopped=True)
            if issues:
                raise ImportFailure(name, issues)
            while True:
                line = reader.line_num + 1
                try:
                    row = next(reader)
                except StopIteration:
                    break
                if not row:
                    continue
                if len(row) != len(fields):
                    record += 1
                    if record > MAX_ROWS:
                        fail(
                            "Limit: 10,000 records per source. Split the source into smaller files.",
                            record=record,
                            line=line,
                        )
                    issues.append(
                        ImportIssue(
                            f"Expected {len(fields)} values; found {len(row)}. Check delimiters and quote values containing commas. The affected field cannot be determined reliably.",
                            record,
                            line,
                        )
                    )
                    if len(issues) >= MAX_ISSUES:
                        raise ImportFailure(name, issues, stopped=True)
                else:
                    accept(dict(zip(fields, row)), line)
        elif format == "json":
            records = _decode_source(text)
            if isinstance(records, _SourcePairs):
                keys = list(records)
                if records.duplicate is not None:
                    fail(
                        "Duplicate JSON key. Rename or remove the repeated key.",
                        field=records.duplicate,
                    )
                if len(records) == 1 and keys[0] in ("events", "records"):
                    records = records[keys[0]]
            if not isinstance(records, list) or isinstance(records, _SourcePairs):
                fail('JSON must be an array, {"events": [...]}, or {"records": [...]}.')
            if len(records) > MAX_ROWS:
                fail("Limit: 10,000 records per source. Split the source into smaller files.")
            for index in range(len(records)):
                value = records[index]
                # Release the parsed pair tree as each validated row replaces it.
                # Original bytes/text remain in Dataset for exact case exports.
                records[index] = None
                accept(value)
        else:
            for line, content in enumerate(text.splitlines(), 1):
                if content.strip():
                    try:
                        value = _decode_source(content)
                    except json.JSONDecodeError as exc:
                        record += 1
                        if record > MAX_ROWS:
                            fail(
                                "Limit: 10,000 records per source. Split the source into smaller files.",
                                record=record,
                                line=line,
                            )
                        issues.append(
                            ImportIssue(
                                f"Invalid JSON: {exc.msg}. Check JSON punctuation and quotes.",
                                record,
                                line,
                                exc.colno,
                            )
                        )
                        if len(issues) >= MAX_ISSUES:
                            raise ImportFailure(name, issues, stopped=True)
                    else:
                        accept(value, line)
    except json.JSONDecodeError as exc:
        fail(
            f"Invalid JSON: {exc.msg}. Check JSON punctuation and quotes. Parsing stopped here; later records were not checked.",
            line=exc.lineno,
            column=exc.colno,
        )
    except csv.Error as exc:
        issues.append(
            ImportIssue(
                "Invalid CSV quoting or field size. Close quoted values and keep each value within 4,096 characters. Parsing stopped here.",
                record + 1,
                reader.line_num,
            )
        )
        raise ImportFailure(name, issues) from exc
    except (RecursionError, OverflowError) as exc:
        fail(
            "JSON is too deeply nested or contains an unsupported number. Reduce nesting or numeric magnitude."
        )
    except ValueError as exc:
        if isinstance(exc, ImportFailure):
            raise
        fail("JSON contains an unsupported number. Use finite numbers between -1e100 and 1e100.")
    if issues:
        raise ImportFailure(name, issues)
    if not rows:
        fail("A source must contain 1–10,000 records.")
    if not source_fields:
        fail("A source must contain 1–64 fields. Add named values to the records.")
    return Dataset(name, format, original, sha(raw), tuple(source_fields), tuple(rows))


def load_dataset(path):
    path = Path(path)
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ImportFailure(
            path.name,
            [
                ImportIssue(
                    "The file could not be read. Check that it still exists and that you have permission to open it."
                )
            ],
        ) from exc
    return parse_bytes(raw, path.name)


def numeric_fields(data):
    return [
        key for key in data.fields if any(number(row.get(key)) is not None for row in data.rows)
    ]


def validate_config(config, current, reference):
    required = {"features", "session", "event_id", "time", "time_format", "threshold", "rules"}
    if (
        not isinstance(config, dict)
        or not required <= set(config)
        or set(config) - required - {"context", "time_origin", "reference_by"}
    ):
        raise ValueError("Unsupported analysis settings.")
    if config.get("time_origin", "unspecified") not in ("unspecified", "elapsed", "unix"):
        raise ValueError("Choose elapsed time, Unix time, or unspecified origin.")
    context = config.get("context", {})
    if not isinstance(context, dict) or set(context) - {"User", "Host", "Process"}:
        raise ValueError("Context supports User, Host, and Process mappings.")
    if any(not isinstance(field, str) or field not in current.fields for field in context.values()):
        raise ValueError("A context field is absent from the incoming source.")
    features = config["features"]
    if not isinstance(features, list) or len(features) > 12 or len(set(features)) != len(features):
        raise ValueError("Select at most 12 distinct numeric signals.")
    for field in features:
        if not isinstance(field, str) or field not in current.fields:
            raise ValueError("A selected signal is absent from the incoming source.")
    metadata = []
    for role in ("session", "event_id", "time"):
        field = config[role]
        if field is not None:
            if not isinstance(field, str) or field not in current.fields:
                raise ValueError(f"Invalid {role} field.")
            metadata.append(field)
    if len(metadata) != len(set(metadata)) or set(features) & set(metadata):
        raise ValueError(
            "Signal, session, record ID, and timestamp roles must use different fields."
        )
    if config["time_format"] not in ("milliseconds", "seconds", "iso8601"):
        raise ValueError("Choose an explicit timestamp format.")
    if (
        isinstance(config["threshold"], bool)
        or not isinstance(config["threshold"], (int, float))
        or not 1 <= config["threshold"] <= 100
    ):
        raise ValueError("Deviation threshold must be between 1 and 100.")
    if features:
        if reference is None:
            raise ValueError("Load a separate reference dataset to interpret numeric deviations.")
        if reference.digest == current.digest:
            raise ValueError(
                "Reference and incoming files have identical content. Choose a separate reference."
            )
        if not set(features) <= set(reference.fields):
            raise ValueError("Reference and incoming data must share the selected signal names.")
    rules = config["rules"]
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise ValueError("Use at most 32 rules.")
    names = set()
    for rule in rules:
        required_rule = {"name", "field", "op", "value"}
        if (
            not isinstance(rule, dict)
            or not required_rule <= set(rule)
            or set(rule) - required_rule - {"priority"}
        ):
            raise ValueError("Rules require name, field, op, value, and an optional priority.")
        if rule.get("priority", "Notice") not in PRIORITIES:
            raise ValueError("Choose Notice, Warning, Error, or Critical priority.")
        if (
            not isinstance(rule["name"], str)
            or not rule["name"].strip()
            or len(rule["name"]) > 120
            or rule["name"] in names
        ):
            raise ValueError("Rule names must be unique and 1–120 characters.")
        names.add(rule["name"])
        if not isinstance(rule["field"], str) or rule["field"] not in current.fields:
            raise ValueError("A rule field is absent from the incoming source.")
        if rule["op"] not in ("gt", "ge", "lt", "le", "eq", "ne"):
            raise ValueError("Supported operators: gt, ge, lt, le, eq, ne.")
        if rule["op"] in ("gt", "ge", "lt", "le") and number(rule["value"]) is None:
            raise ValueError("Numeric comparisons require a finite numeric value.")
        if not isinstance(rule["value"], (str, int, float, bool)) or len(str(rule["value"])) > 4096:
            raise ValueError("Rule values must be bounded strings, numbers, or booleans.")
        if (
            isinstance(rule["value"], (int, float))
            and not isinstance(rule["value"], bool)
            and number(rule["value"]) is None
        ):
            raise ValueError(
                "Numeric rule values must be finite and within supported magnitude limits."
            )
    if not features and not rules:
        raise ValueError("Select numeric signals with a reference, or add a field rule.")
    by = config.get("reference_by", [])
    if (
        not isinstance(by, list)
        or len(by) > 2
        or any(not isinstance(f, str) for f in by)
        or len(set(by)) != len(by)
    ):
        raise ValueError("Choose at most two distinct reference group fields.")
    if by:
        if not features or reference is None:
            raise ValueError("Reference groups require numeric signals and a reference source.")
        if any(f not in current.fields or f not in reference.fields for f in by):
            raise ValueError("Reference group fields must exist in both sources.")
        if set(by) & (set(features) | set(metadata)):
            raise ValueError(
                "Reference group fields must differ from numeric signals and identity/time roles."
            )


def _identity(value, role):
    if (
        isinstance(value, bool)
        or value is None
        or not isinstance(value, (str, int, float))
        or not str(value).strip()
    ):
        raise ValueError(f"Selected {role} values must be nonempty text or numbers.")
    return str(value)


def _timestamp(value, format, origin="unspecified"):
    if format != "iso8601":
        result = number(value)
        if result is None or result < 0:
            raise ValueError("Numeric timestamps must be finite and nonnegative.")
        if origin == "unix":
            try:
                datetime.fromtimestamp(
                    result if format == "seconds" else result / 1000, timezone.utc
                )
            except (ValueError, OverflowError, OSError) as exc:
                raise ValueError("Unix time must resolve to a supported UTC date.") from exc
        return result * (1000 if format == "seconds" else 1)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("ISO timestamps need a timezone.")
        return dt.timestamp() * 1000
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError("ISO timestamps must include a valid date, time, and timezone.") from exc


def _rule(rule, row):
    left = row.get(rule["field"])
    if left is None or left == "":
        return None
    op, right = rule["op"], rule["value"]
    if op in ("gt", "ge", "lt", "le"):
        left, right = number(left), number(right)
        if left is None:
            return None
        return {
            "gt": lambda: left > right,
            "ge": lambda: left >= right,
            "lt": lambda: left < right,
            "le": lambda: left <= right,
        }[op]()
    # Explicit equality uses JSON scalar types; CSV values are strings.
    numeric_pair = all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in (left, right)
    )
    equal = left == right if numeric_pair else type(left) is type(right) and left == right
    return equal if op == "eq" else not equal


def reference_profiles(rows, features, minimum=5):
    profiles = {}
    for field in features:
        values = [n for row in rows if (n := number(row.get(field))) is not None]
        if len(values) < minimum:
            if minimum == 5:
                raise ValueError(
                    f"Reference signal {field} needs at least five valid numeric values."
                )
            return None
        center = statistics.median(values)
        mad = statistics.median(abs(v - center) for v in values)
        scale = mad * 1.4826
        fallback = scale == 0
        if fallback:
            scale = max(abs(center) * 0.01, 1e-9)
        profiles[field] = {
            "center": center,
            "scale": scale,
            "method": "relative tolerance" if fallback else "median absolute deviation",
            "valid_reference_rows": len(values),
            "missing_reference_rows": len(rows) - len(values),
        }
    return profiles


def reference_key(row, fields):
    values = [row.get(f) for f in fields]
    return None if any(v is None or v == "" for v in values) else canonical(values)


def profile_for_record(result, record, field):
    group = record.get("reference_group", {})
    if group.get("mode") == "matched":
        return result["group_profiles"][group["key"]]["profiles"].get(field, {})
    return result["profiles"].get(field, {})


def analyze(current, reference, config):
    validate_config(config, current, reference)
    profiles = reference_profiles(reference.rows if reference else (), config["features"])
    by = config.get("reference_by", [])
    group_profiles = {}
    if by:
        grouped = {}
        for row in reference.rows:
            key = reference_key(row, by)
            if key is not None:
                grouped.setdefault(key, []).append(row)
                if len(grouped) > 128:
                    raise ValueError("Reference groups exceed 128. Choose broader category fields.")
        for key, rows in grouped.items():
            group_profiles[key] = dict(
                count=len(rows), profiles=reference_profiles(rows, config["features"], 20)
            )
    records, seen, last = [], set(), {}
    for index, row in enumerate(current.rows, 1):
        session = (
            _identity(row.get(config["session"]), "session") if config["session"] else "all records"
        )
        event_id = (
            _identity(row.get(config["event_id"]), "record ID")
            if config["event_id"]
            else str(index)
        )
        if (session, event_id) in seen:
            raise ValueError(f"Duplicate record ID within session at record {index}.")
        seen.add((session, event_id))
        time = (
            _timestamp(
                row.get(config["time"]),
                config["time_format"],
                config.get("time_origin", "unspecified"),
            )
            if config["time"]
            else None
        )
        order_warning = time is not None and time < last.get(session, time)
        if time is not None:
            last[session] = max(last.get(session, time), time)
        evidence, gaps, scores = [], [], {}
        selected_profiles = profiles
        group_info = None
        if by:
            key = reference_key(row, by)
            group = group_profiles.get(key)
            matched = bool(group and group["profiles"])
            group_info = dict(
                key=key,
                values=[row.get(f) for f in by],
                fields=by,
                mode="matched" if matched else "global fallback",
                reference_rows=group["count"] if group else 0,
            )
            if matched:
                selected_profiles = group["profiles"]
            else:
                gaps.append(
                    "Reference group missing, unseen, or has fewer than 20 valid values per signal; global profile used"
                )
        for field, profile in selected_profiles.items():
            value = number(row.get(field))
            if value is None:
                gaps.append(f"{field}: numeric value unavailable")
                continue
            score = abs(value - profile["center"]) / profile["scale"]
            scores[field] = score
            if score >= config["threshold"]:
                evidence.append(
                    {
                        "kind": "deviation",
                        "field": field,
                        "value": value,
                        "reference_center": profile["center"],
                        "scale": profile["scale"],
                        "score": score,
                        "threshold": config["threshold"],
                        "method": profile["method"],
                    }
                )
        for rule in config["rules"]:
            matched = _rule(rule, row)
            if matched is None:
                gaps.append(f"{rule['name']}: rule input unavailable")
            elif matched:
                evidence.append(
                    {
                        "kind": "rule",
                        "name": rule["name"],
                        "field": rule["field"],
                        "value": row[rule["field"]],
                        "operator": rule["op"],
                        "expected": rule["value"],
                    }
                )
        if order_warning:
            gaps.append(
                "Timestamp precedes an earlier record in this session; input order was preserved"
            )
        status = "Review" if evidence else "Unknown" if gaps else "No finding"
        records.append(
            {
                "row": index,
                "session": session,
                "event_id": event_id,
                "time_ms": time,
                "status": status,
                "max_deviation": max(scores.values()) if scores else None,
                "scores": scores,
                "evidence": evidence,
                "gaps": gaps,
            }
        )
        if group_info is not None:
            records[-1]["reference_group"] = group_info
    counts = {
        status: sum(r["status"] == status for r in records)
        for status in ("Review", "Unknown", "No finding")
    }
    result = {
        "engine": VERSION,
        "method": "reference-deviation-and-field-rules-v1",
        "profiles": profiles,
        "records": records,
        "summary": {
            "total": len(records),
            **counts,
            "rows_with_gaps": sum(bool(r["gaps"]) for r in records),
        },
        "meaning": "Review leads and deviations, not proof of malicious behavior. No measured detection accuracy is available without independent labels.",
    }
    if by:
        result.update(
            method="grouped-reference-deviation-and-field-rules-v1", group_profiles=group_profiles
        )
    return result


def case_document(current, reference, config, result):
    # Recompute rather than allowing a caller to export a stale or invented result.
    if result != analyze(current, reference, config):
        raise ValueError(
            "Results do not match the current source and settings. Run the analysis again."
        )

    def source(data):
        return {**data.manifest(), "text": data.text} if data else None

    payload = {
        "current": source(current),
        "reference": source(reference),
        "config": config,
        "result": result,
    }
    return {
        "schema": "detection-workbench-case-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload_sha256": sha(canonical(payload).encode()),
        "payload": payload,
    }


def save_case(path, current, reference, config, result):
    doc = case_document(current, reference, config, result)
    raw = json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_CASE:
        raise ValueError("Case exceeds 64 MiB. Use a smaller source.")
    path = Path(path)
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(raw)
            stream.flush()
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise
    return {"name": path.name, "path": str(path.resolve()), "sha256": sha(raw)}


def open_case(path, *, with_manifest=False):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_CASE + 1)
    if len(raw) > MAX_CASE:
        raise ValueError("Case exceeds 64 MiB.")
    try:
        doc = decode(raw.decode("utf-8"))
        if (
            set(doc) != {"schema", "created_at", "payload_sha256", "payload"}
            or doc["schema"] != "detection-workbench-case-v1"
        ):
            raise ValueError("Unsupported case format.")
        payload = doc["payload"]
        if sha(canonical(payload).encode()) != doc["payload_sha256"]:
            raise ValueError("Case integrity check failed.")
        if set(payload) != {"current", "reference", "config", "result"}:
            raise ValueError("Unsupported case payload.")

        def restore(item):
            if item is None:
                return None
            if set(item) != {"name", "format", "sha256", "records", "fields", "text"}:
                raise ValueError("Unsupported source manifest.")
            data = parse_bytes(item["text"].encode("utf-8"), item["name"], item["format"])
            if data.manifest() != {k: v for k, v in item.items() if k != "text"}:
                raise ValueError("Source manifest does not match evidence.")
            return data

        current, reference = restore(payload["current"]), restore(payload["reference"])
        if current is None:
            raise ValueError("Case has no incoming source.")
        result = analyze(current, reference, payload["config"])
        if result != payload["result"]:
            raise ValueError(
                "Stored conclusions do not match recomputed evidence or engine version."
            )
        case = current, reference, payload["config"], result
        if with_manifest:
            return case, {
                "name": Path(path).name,
                "path": str(Path(path).resolve()),
                "sha256": sha(raw),
            }
        return case
    except (
        KeyError,
        TypeError,
        AttributeError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ) as exc:
        raise ValueError("Case is malformed or unsupported.") from exc

"""Presentation-only comparisons; no changes to detection or saved evidence."""

from dataclasses import dataclass
import json
import workflow
import engine
from evidence_labels import time_label

MISSING = object()
OPERATORS = {
    "gt": "greater than",
    "ge": "at least",
    "lt": "less than",
    "le": "at most",
    "eq": "equals",
    "ne": "does not equal",
}


def equivalent(left, right):
    if left is MISSING or right is MISSING:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(equivalent(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    return left == right


def display(value):
    if value is MISSING:
        return "Not present"
    if value is None:
        return "Not set"
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "\n".join(value) if value else "None"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return json.dumps(value, ensure_ascii=False)


@dataclass(frozen=True)
class Row:
    label: str
    current: str
    previous: str
    changed: bool


def paired(current_case, previous_case):
    """Source position identifies a record even when ID/session mappings change."""
    return current_case[0].digest == previous_case[0].digest and len(
        current_case[3]["records"]
    ) == len(previous_case[3]["records"])


def changed_records(current_case, previous_case):
    if not paired(current_case, previous_case):
        return []
    changes = []
    for current, previous in zip(current_case[3]["records"], previous_case[3]["records"]):
        kinds = []
        if current["status"] != previous["status"]:
            kinds.append("Result")
        if workflow.priority(current, current_case[2]) != workflow.priority(
            previous, previous_case[2]
        ):
            kinds.append("Priority")
        if (
            not equivalent(current["evidence"], previous["evidence"])
            or current["gaps"] != previous["gaps"]
        ):
            kinds.append("Reasons")
        if kinds:
            changes.append((current["row"], ", ".join(kinds)))
    return changes


def record_rows(current_case, previous_case, row):
    """Explain both decisions, including conditions that did not match."""
    if not paired(current_case, previous_case):
        raise ValueError("Different source data cannot be paired.")
    if not 1 <= row <= len(current_case[3]["records"]):
        raise ValueError("Record is outside the source.")
    source, reference, config, result = current_case
    old_source, old_reference, old_config, old_result = previous_case
    current, previous = result["records"][row - 1], old_result["records"][row - 1]
    raw, old_raw = source.rows[row - 1], old_source.rows[row - 1]
    output = []

    def add(label, left, right, formatter=display):
        output.append(Row(label, formatter(left), formatter(right), not equivalent(left, right)))

    add("Result", current["status"], previous["status"])
    add("Priority", workflow.priority(current, config), workflow.priority(previous, old_config))
    add("Gaps", current["gaps"], previous["gaps"])
    if "reference_group" in current or "reference_group" in previous:

        def group_label(group):
            if not group:
                return "Global profile"
            return (
                " · ".join(
                    f"{field}: {json.dumps(value, ensure_ascii=False)}"
                    for field, value in zip(group["fields"], group["values"])
                )
                + f"\n{group['mode']} · {group['reference_rows']} reference records"
            )

        add(
            "Reference group",
            current.get("reference_group"),
            previous.get("reference_group"),
            group_label,
        )
    for field in dict.fromkeys([*config["features"], *old_config["features"]]):
        add(
            f"{field} · observed",
            raw.get(field, MISSING),
            old_raw.get(field, MISSING),
            lambda v: display(v) if v is MISSING else json.dumps(v, ensure_ascii=False),
        )
        left, right = engine.profile_for_record(result, current, field), engine.profile_for_record(
            old_result, previous, field
        )
        add(f"{field} · median", left.get("center", MISSING), right.get("center", MISSING))
        add(
            f"{field} · deviation",
            current["scores"].get(field, MISSING),
            previous["scores"].get(field, MISSING),
            lambda v: f"{v:.2f}" if v is not MISSING else display(v),
        )
        add(
            f"{field} · review at",
            config["threshold"] if left else MISSING,
            old_config["threshold"] if right else MISSING,
        )

        def numeric_match(record, profile, settings):
            if not profile:
                return "Not configured"
            score = record["scores"].get(field)
            return (
                "Unavailable"
                if score is None
                else ("Matched" if score >= settings["threshold"] else "Not matched")
            )

        add(
            f"{field} · condition",
            numeric_match(current, left, config),
            numeric_match(previous, right, old_config),
        )
    rules = {r["name"]: r for r in config["rules"]}
    old_rules = {r["name"]: r for r in old_config["rules"]}
    for name in dict.fromkeys([*rules, *old_rules]):
        rule, old_rule = rules.get(name), old_rules.get(name)

        def explain(rule, values):
            if rule is None:
                return "Not configured"
            matched = engine._rule(rule, values)
            state = "Unavailable" if matched is None else ("Matched" if matched else "Not matched")
            return (
                f"{state}\n{rule['field']} {OPERATORS[rule['op']]} {json.dumps(rule['value'], ensure_ascii=False)}"
                f"\nObserved: {json.dumps(values.get(rule['field']), ensure_ascii=False)}"
                f"\nPriority: {rule.get('priority', 'Notice')}"
            )

        add(name, explain(rule, raw), explain(old_rule, old_raw))
    add("Source record", row, row)
    add("Record ID", current["event_id"], previous["event_id"])
    add("Session", current["session"], previous["session"])
    add("Time", time_label(current, config, raw), time_label(previous, old_config, old_raw))
    for role in ("User", "Host", "Process"):

        def context(settings, values):
            field = settings.get("context", {}).get(role)
            return (
                f"{json.dumps(values.get(field), ensure_ascii=False)}\nFrom {field}"
                if field
                else "Not mapped"
            )

        add(role, context(config, raw), context(old_config, old_raw))
    add("Data file", source.name, old_source.name)
    add("Data SHA-256", source.digest, old_source.digest)
    add(
        "Reference file",
        reference.name if reference else None,
        old_reference.name if old_reference else None,
    )
    add(
        "Reference SHA-256",
        reference.digest if reference else None,
        old_reference.digest if old_reference else None,
    )
    return output


def rows(current_case, previous_case):
    source, reference, config, result = current_case
    old_source, old_reference, old_config, old_result = previous_case
    output = []

    def add(label, left, right, format=display):
        output.append(Row(label, format(left), format(right), not equivalent(left, right)))

    for key, label in (
        ("Review", "Needs review"),
        ("Unknown", "Unknown"),
        ("No finding", "No finding"),
        ("total", "Records"),
        ("rows_with_gaps", "With gaps"),
    ):
        add(label, result["summary"][key], old_result["summary"][key])
    add("Threshold", config["threshold"], old_config["threshold"])
    add(
        "Numeric clock",
        config.get("time_origin", "unspecified"),
        old_config.get("time_origin", "unspecified"),
    )
    add("Reference groups", config.get("reference_by", []), old_config.get("reference_by", []))
    if "group_profiles" in result or "group_profiles" in old_result:
        add(
            "Usable reference groups",
            sum(bool(g["profiles"]) for g in result.get("group_profiles", {}).values()),
            sum(bool(g["profiles"]) for g in old_result.get("group_profiles", {}).values()),
        )
    for key, label in (
        ("features", "Values"),
        ("session", "Session field"),
        ("event_id", "ID field"),
        ("time", "Time field"),
        ("time_format", "Time format"),
    ):
        add(label, config[key], old_config[key])
    for role in ("User", "Host", "Process"):
        add(
            f"{role} field",
            config.get("context", {}).get(role),
            old_config.get("context", {}).get(role),
        )
    rules = {r["name"]: r for r in config["rules"]}
    old_rules = {r["name"]: r for r in old_config["rules"]}
    add("Rule order", list(rules), list(old_rules))
    for name in dict.fromkeys([*rules, *old_rules]):
        rule, old = rules.get(name, {}), old_rules.get(name, {})
        add(f"{name} · field", rule.get("field", MISSING), old.get("field", MISSING))
        add(
            f"{name} · condition",
            rule.get("op", MISSING),
            old.get("op", MISSING),
            lambda value: OPERATORS[value] if value is not MISSING else display(value),
        )
        # JSON quoting preserves the difference between text "7" and number 7.
        add(
            f"{name} · value",
            rule.get("value", MISSING),
            old.get("value", MISSING),
            lambda value: (
                display(value) if value is MISSING else json.dumps(value, ensure_ascii=False)
            ),
        )
        add(
            f"{name} · priority",
            rule.get("priority", "Notice") if rule else MISSING,
            old.get("priority", "Notice") if old else MISSING,
        )
    for field in dict.fromkeys([*result["profiles"], *old_result["profiles"]]):
        profile, old = result["profiles"].get(field, {}), old_result["profiles"].get(field, {})
        for key, label in (
            ("center", "median"),
            ("scale", "scale"),
            ("method", "method"),
            ("valid_reference_rows", "reference values"),
            ("missing_reference_rows", "missing values"),
        ):
            prefix = (
                "Global · " if "group_profiles" in result or "group_profiles" in old_result else ""
            )
            add(f"{prefix}{field} · {label}", profile.get(key, MISSING), old.get(key, MISSING))
    add("Data file", source.name, old_source.name)
    add("Data fingerprint", source.digest, old_source.digest)
    add(
        "Reference file",
        reference.name if reference else None,
        old_reference.name if old_reference else None,
    )
    add(
        "Reference fingerprint",
        reference.digest if reference else None,
        old_reference.digest if old_reference else None,
    )
    add("Engine", result["engine"], old_result["engine"])
    same = paired(current_case, previous_case)
    if same:
        changed_outcomes = sum(
            a["status"] != b["status"] for a, b in zip(result["records"], old_result["records"])
        )
        changed_priorities = sum(
            workflow.priority(a, config) != workflow.priority(b, old_config)
            for a, b in zip(result["records"], old_result["records"])
        )
        note = f"Same incoming evidence · {changed_outcomes:,} changed outcomes · {changed_priorities:,} changed priorities."
    else:
        note = "Different data · counts describe each file. Record outcomes are not paired."
    return note, output

"""Read-only preflight checks using the detector's identity, time, and rule semantics."""

from dataclasses import dataclass, field

import engine
from import_errors import label


@dataclass(frozen=True)
class Note:
    text: str
    level: str = "info"
    source: str | None = None
    fields: tuple[str, ...] = ()
    rows: tuple[int, ...] | None = None  # None means every record in this source.
    related: tuple[int, ...] = ()


@dataclass
class MappingReport:
    groups: dict = field(default_factory=dict)
    config_error: str = ""

    def add(self, group, text, level="info", *, source=None, fields=(), rows=None, related=()):
        self.groups.setdefault(group, []).append(
            Note(
                text,
                level,
                source,
                tuple(fields),
                None if rows is None else tuple(rows),
                tuple(related),
            )
        )

    @property
    def blocked(self):
        return bool(self.config_error) or any(
            note.level == "fix" for notes in self.groups.values() for note in notes
        )


def positions(indices):
    sample = ", ".join(str(index) for index in indices[:3])
    return f"{'Record' if len(indices) == 1 else 'Records'} {sample}" + (
        "…" if len(indices) > 3 else ""
    )


def check(current, reference, config):
    report = MappingReport()
    if current is None:
        return report
    config = dict(config)
    try:
        config["threshold"] = float(config["threshold"])
    except (ValueError, TypeError):
        config["threshold"] = None
    if config["threshold"] is None or not 1 <= config["threshold"] <= 100:
        report.add("threshold", "Fix · Enter a number from 1 to 100.", "fix")
    try:
        engine.validate_config(config, current, reference)
    except (ValueError, TypeError) as exc:
        report.config_error = str(exc)

    roles = {"session": "Session", "event_id": "Record ID", "time": "Time"}
    used = {}
    for group, title in roles.items():
        if config[group]:
            used.setdefault(config[group], []).append((group, title))
    for field_name in config["features"]:
        used.setdefault(field_name, []).append(("features", "Values to compare"))
    for field_name, mappings in used.items():
        if len(mappings) > 1:
            for group, _ in mappings:
                others = ", ".join(title for other, title in mappings if other != group)
                report.add(
                    group,
                    f"Fix · {label(field_name)} is also used for {others}. Choose a different field.",
                    "fix",
                    source="current",
                    fields=(field_name,),
                )

    identities = {}
    for group, title in roles.items():
        field_name = config[group]
        if field_name is None:
            defaults = {
                "session": "Optional · All records share one session.",
                "event_id": "Optional · Use positions in the file.",
                "time": "Optional · Use file order.",
            }
            report.add(group, defaults[group])
            identities[group] = [
                "all records" if group == "session" else str(i)
                for i in range(1, len(current.rows) + 1)
            ]
            continue
        if field_name not in current.fields:
            report.add(
                group,
                f"Fix · {label(field_name)} is absent from this file.",
                "fix",
                source="current",
                fields=(field_name,),
            )
            identities[group] = [None] * len(current.rows)
            continue
        values, invalid = [], []
        for index, row in enumerate(current.rows, 1):
            try:
                value = (
                    engine._timestamp(
                        row.get(field_name),
                        config["time_format"],
                        config.get("time_origin", "unspecified"),
                    )
                    if group == "time"
                    else engine._identity(row.get(field_name), title)
                )
            except ValueError:
                value = None
                invalid.append(index)
            values.append(value)
        identities[group] = values
        if invalid:
            repair = (
                "Choose the matching time format; every value needs a valid time."
                if group == "time"
                else "Use nonempty text or numbers for every record."
            )
            report.add(
                group,
                f"Fix · {len(invalid):,} invalid or missing. {positions(invalid)}. {repair}",
                "fix",
                source="current",
                fields=(field_name,),
                rows=invalid,
            )
        else:
            description = {
                "session": "have a session",
                "event_id": "have an ID",
                "time": "valid times",
            }[group]
            report.add(group, f"{len(values):,}/{len(values):,} {description}.")
        if group == "time":
            report.add(
                group,
                (
                    "ISO times need a timezone."
                    if config["time_format"] == "iso8601"
                    else (
                        "Elapsed since source clock start; no timezone."
                        if config.get("time_origin") == "elapsed"
                        else (
                            "Unix epoch; absolute time shown in UTC."
                            if config.get("time_origin") == "unix"
                            else "Units do not specify the clock origin."
                        )
                    )
                ),
            )

    seen, duplicates, last, backwards = {}, [], {}, []
    last_record, time_context = {}, set()
    for index, (session, identity, time) in enumerate(
        zip(identities["session"], identities["event_id"], identities["time"]), 1
    ):
        if session is None:
            continue
        if identity is not None:
            key = session, identity
            if key in seen:
                duplicates.append((index, seen[key]))
            else:
                seen[key] = index
        if config["time"] and time is not None:
            if time < last.get(session, time):
                backwards.append(index)
                time_context.add(last_record[session])
            if time >= last.get(session, time):
                last_record[session] = index
            last[session] = max(last.get(session, time), time)
    if duplicates:
        first, previous = duplicates[0]
        report.add(
            "event_id",
            f"Fix · Repeated IDs within a session: {len(duplicates):,}. Record {first} repeats record {previous}. Choose a unique ID or fix the source.",
            "fix",
            source="current",
            fields=tuple(f for f in (config["event_id"], config["session"]) if f),
            rows=[index for index, _ in duplicates],
            related=sorted({previous for _, previous in duplicates}),
        )
    if backwards:
        report.add(
            "time",
            f"Check · Times that move backward within a session: {len(backwards):,}. {positions(backwards)}. Analysis keeps these as gaps.",
            "check",
            source="current",
            fields=tuple(f for f in (config["time"], config["session"]) if f),
            rows=backwards,
            related=sorted(time_context),
        )

    if not config["features"]:
        report.add("features", "Choose values for numeric comparison, or use a rule.")
    for field_name in config["features"]:
        missing = [
            i for i, row in enumerate(current.rows, 1) if engine.number(row.get(field_name)) is None
        ]
        valid = len(current.rows) - len(missing)
        report.add("features", f"{label(field_name)} · {valid:,}/{len(current.rows):,} numeric.")
        if missing:
            report.add(
                "features",
                f"Check · {len(missing):,} missing or nonnumeric. {positions(missing)}. Analysis keeps gaps.",
                "check",
                source="current",
                fields=(field_name,),
                rows=missing,
            )
        if reference is None:
            report.add("features", f"Fix · Add a reference for {label(field_name)}.", "fix")
        elif field_name not in reference.fields:
            report.add(
                "features",
                f"Fix · Reference has no {label(field_name)}. Choose a shared field or another reference.",
                "fix",
                source="reference",
                fields=(field_name,),
            )
        else:
            ref_count = sum(
                engine.number(row.get(field_name)) is not None for row in reference.rows
            )
            if ref_count < 5:
                report.add(
                    "features",
                    f"Fix · Reference {label(field_name)} has {ref_count} usable values; needs at least 5.",
                    "fix",
                    source="reference",
                    fields=(field_name,),
                )
            elif ref_count < len(reference.rows):
                report.add(
                    "features",
                    f"Check · Reference {label(field_name)} uses {ref_count:,}/{len(reference.rows):,} values.",
                    "check",
                    source="reference",
                    fields=(field_name,),
                    rows=[
                        i
                        for i, row in enumerate(reference.rows, 1)
                        if engine.number(row.get(field_name)) is None
                    ],
                )
        if reference is not None and reference.digest == current.digest:
            report.add(
                "features",
                "Fix · Reference and incoming data are identical. Choose a separate reference.",
                "fix",
                source="reference",
                fields=(field_name,),
            )

    for rule in config["rules"]:
        field_name = rule["field"]
        if field_name not in current.fields:
            report.add(
                "rules",
                f"Fix · Rule {label(rule['name'])} uses absent field {label(field_name)}.",
                "fix",
                source="current",
                fields=(field_name,),
            )
        elif rule["op"] in ("gt", "ge", "lt", "le", "eq", "ne"):
            gaps = [i for i, row in enumerate(current.rows, 1) if engine._rule(rule, row) is None]
            if gaps:
                report.add(
                    "rules",
                    f"Check · {label(rule['name'])}: {len(gaps):,} unavailable values in {label(field_name)}. {positions(gaps)}.",
                    "check",
                    source="current",
                    fields=(field_name,),
                    rows=gaps,
                )
    for role, field_name in config.get("context", {}).items():
        if field_name not in current.fields:
            report.add(
                "context",
                f"Fix · {role} field {label(field_name)} is absent.",
                "fix",
                source="current",
                fields=(field_name,),
            )
        else:
            gaps = [i for i, row in enumerate(current.rows, 1) if row.get(field_name) in (None, "")]
            if gaps:
                report.add(
                    "context",
                    f"Check · {role} {label(field_name)}: {len(gaps):,} missing. {positions(gaps)}.",
                    "check",
                    source="current",
                    fields=(field_name,),
                    rows=gaps,
                )
    by = config.get("reference_by", [])
    if by and not report.config_error and reference is not None:
        grouped = {}
        for row in reference.rows:
            key = engine.reference_key(row, by)
            if key is not None:
                counts = grouped.setdefault(key, [0] * len(config["features"]))
                for i, field_name in enumerate(config["features"]):
                    counts[i] += engine.number(row.get(field_name)) is not None
        if len(grouped) > 128:
            report.add(
                "reference_by",
                "Fix · More than 128 reference groups. Choose broader category fields.",
                "fix",
                source="reference",
                fields=by,
            )
        else:
            supported = {key for key, counts in grouped.items() if all(n >= 20 for n in counts)}
            affected = [
                i
                for i, row in enumerate(current.rows, 1)
                if engine.reference_key(row, by) not in supported
            ]
            if affected:
                report.add(
                    "reference_by",
                    f"Check · {len(affected):,} records have missing, unseen, or undersized reference groups. Global profiles will be used with gaps.",
                    "check",
                    source="current",
                    fields=by,
                    rows=affected,
                )
    return report

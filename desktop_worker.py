"""Local desktop protocol. Detection and evidence formats remain owned by Python.

Only the Electron main process launches this worker. Paths are supplied by native
dialogs in that process, never by the renderer. No sockets or executable policies.
"""

from __future__ import annotations

import copy
from array import array
from dataclasses import asdict, replace
import json
import sys
from pathlib import Path

import chart
import comparison
import engine
import evaluation
import investigation
import mapping_checks
import record_search
import workflow
import native_integrity
import native_stream
from evidence_labels import source_label, time_label
from import_errors import ImportFailure

PROTOCOL = 1
MAX_REQUEST = 512 * 1024


def display(value):
    # Keep exact Python integers and JSON scalar types out of JavaScript numbers.
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def default_config():
    return dict(
        features=[],
        session=None,
        event_id=None,
        time=None,
        time_format="milliseconds",
        threshold=6,
        rules=[],
    )


def short_reason(record):
    native_reasons = {
        "Code differs from approved baseline": "Code changed",
        "Build is not approved": "Build not approved",
        "Code page is not execute-read": "Page protection changed",
    }
    phrases = {
        "gt": "above limit",
        "ge": "at or above limit",
        "lt": "below limit",
        "le": "at or below limit",
        "eq": "matches rule",
        "ne": "differs from rule",
    }
    reasons = list(
        dict.fromkeys(
            (
                native_reasons.get(e["name"], f"{e['field']} {phrases[e['operator']]}")
                if e["kind"] == "rule"
                else f"{e['field']} outside reference range"
            )
            for e in record["evidence"]
        )
    )
    if not reasons:
        return "Input needs attention" if record["gaps"] else "No configured condition matched"
    return reasons[0] + (f" · +{len(reasons)-1} reasons" if len(reasons) > 1 else "")


def compact_spans(text, query):
    """Cache code-point offsets as packed integers, not Python tuple objects."""
    return array(
        "I", (offset for span in record_search.match_spans(text, query) for offset in span)
    )


def share_verified_source(data, candidates):
    """Reuse immutable source content only after open_case has fully verified it."""
    if data is not None:
        for known in candidates:
            if known is not None and data.format == known.format and data.text == known.text:
                # Keep the compared source's own name and manifest identity.
                return replace(data, text=known.text, fields=known.fields, rows=known.rows)
    return data


class Workspace:
    def __init__(self):
        self.current = self.reference = self.result = self.previous = None
        self.config = default_config()
        self.revision = 0
        self.index = {}
        self.report = mapping_checks.MappingReport()
        self.notes = []
        self.chart_cache = self.comparison_cache = self.inspection_cache = None
        self.current_case = self.previous_file = None
        self.source_paths = {"current": None, "reference": None}
        self.labels = self.evaluation_cache = None
        self.capture = None

    def close(self):
        if self.capture:
            self.capture.stop()

    def inspect_capture(self):
        rows = self.capture.snapshot()
        if not rows:
            raise ValueError("Waiting for the first collection sample.")
        raw = ("\n".join(engine.canonical(row) for row in rows) + "\n").encode("utf-8")
        data = engine.parse_bytes(raw, f"our-app-{self.capture.build}.jsonl")
        config = native_integrity.default_policy(data)
        result = engine.analyze(data, None, config)
        # Publish a complete snapshot together; collection keeps its own window.
        self.current, self.reference, self.config = data, None, config
        self.labels = self.current_case = None
        self.source_paths = {"current": None, "reference": None}
        self.invalidate()
        self.result = result
        self.index = investigation.search_index(data, config, result)
        return self.snapshot()

    def invalidate(self, report=None):
        self.evaluation_cache = None
        self.revision += 1
        self.result = self.previous = None
        self.previous_file = None
        if self.current_case:
            self.current_case = dict(self.current_case, modified=True)
        self.index = {}
        self.chart_cache = self.comparison_cache = self.inspection_cache = None
        self.report = (
            report
            if report is not None
            else mapping_checks.check(self.current, self.reference, self.config)
        )
        self.notes = [
            dict(group=group, **asdict(note))
            for group, notes in self.report.groups.items()
            for note in notes
        ]

    def require_revision(self, args):
        if type(args.get("revision")) is not int or args["revision"] != self.revision:
            raise ValueError("Data or settings changed. Select the record again.")

    def require_result(self):
        if self.result is None:
            raise ValueError("Analyze the current settings first.")

    def snapshot(self):
        return dict(
            protocol=PROTOCOL,
            revision=self.revision,
            current=self.current.manifest() if self.current else None,
            reference=self.reference.manifest() if self.reference else None,
            numeric=engine.numeric_fields(self.current) if self.current else [],
            config=self.config,
            rules_text=json.dumps(self.config["rules"], ensure_ascii=False, indent=2),
            notes=self.notes,
            blocked=self.report.blocked,
            config_error=self.report.config_error,
            summary=self.result["summary"] if self.result else None,
            case_file=self.current_case,
            labels=self.labels["file"] if self.labels else None,
            numeric_evidence=bool(
                self.result
                and any(
                    e["kind"] == "deviation"
                    for r in self.result["records"]
                    for e in r["evidence"]
                )
            ),
            meaning=self.result["meaning"] if self.result else "",
            capture=self.capture.status() if self.capture else None,
        )

    def case(self):
        self.require_result()
        return self.current, self.reference, self.config, self.result

    def selection(self, args):
        self.require_revision(args)
        source = args.get("source", "current")
        if source not in ("current", "reference"):
            raise ValueError("Unknown source.")
        data = getattr(self, source)
        row = args.get("row")
        if data is None or type(row) is not int or not 1 <= row <= len(data.rows):
            raise ValueError("Select an available record.")
        return data, data.rows[row - 1]

    def preview_scope(self, args):
        note_id = args.get("note")
        if note_id is None:
            return (
                self.current,
                list(range(1, len(self.current.rows) + 1)),
                [],
                (),
                None,
                "current",
            )
        if type(note_id) is not int or not 0 <= note_id < len(self.notes):
            raise ValueError("Mapping warning is no longer available.")
        note = self.notes[note_id]
        if note["source"] not in ("current", "reference"):
            raise ValueError("This note has no linked source.")
        data = getattr(self, note["source"])
        if data is None:
            raise ValueError("Source is not loaded.")
        affected = (
            list(note["rows"])
            if note["rows"] is not None
            else list(range(1, len(data.rows) + 1))
        )
        return data, affected, list(note["related"]), note["fields"], note, note["source"]

    def dispatch(self, method, args):
        if not isinstance(args, dict):
            raise ValueError("Invalid request.")
        if method == "state":
            return self.snapshot()
        if method == "native_start":
            if set(args) != {"build"}:
                raise ValueError("Choose an owned build only.")
            if self.capture and self.capture.status()["state"] == "running":
                raise ValueError("Stop the current collection first.")
            if self.capture:
                self.capture.stop()
            self.capture = native_stream.NativeSession(args["build"])
            return dict(
                capture=self.capture.status(),
                message="Collection started. Inspect to review a snapshot.",
            )
        if method in ("native_status", "native_snapshot", "native_stop", "native_export"):
            if set(args) - ({"path"} if method == "native_export" else set()):
                raise ValueError("Unexpected collection setting.")
            if method == "native_status":
                return dict(capture=self.capture.status() if self.capture else None)
            if not self.capture:
                raise ValueError("Start collection first.")
            if method == "native_stop":
                self.capture.stop()
                return self.inspect_capture() if self.capture.snapshot() else self.snapshot()
            if method == "native_snapshot":
                return self.inspect_capture()
            rows = self.capture.snapshot()
            if not rows:
                raise ValueError("There are no observations to export yet.")
            raw = "\n".join(engine.canonical(row) for row in rows) + "\n"
            with Path(args["path"]).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(raw)
            return dict(
                capture=self.capture.status(),
                message="Collection exported. Older samples beyond the retained window are excluded.",
            )
        if method == "import":
            role = args.get("role")
            if role not in ("current", "reference"):
                raise ValueError("Unknown import role.")
            data = engine.load_dataset(args["path"])
            native_policy = native_integrity.default_policy(data) if role == "current" else None
            setattr(self, role, data)
            self.source_paths[role] = str(Path(args["path"]).resolve())
            if role == "current":
                self.labels = None
                self.config = native_policy or default_config()
                self.current_case = None
            self.invalidate()
            return self.snapshot()
        if method == "open":
            (current, reference, config, result), case_file = engine.open_case(
                args["path"], with_manifest=True
            )
            self.current, self.reference, self.config = current, reference, config
            self.labels = None
            self.invalidate()
            self.result = result
            self.current_case = case_file
            self.source_paths = {"current": None, "reference": None}
            self.index = investigation.search_index(current, config, result)
            return self.snapshot()
        self.require_revision(args)
        if not self.current:
            raise ValueError("Import data or open a case first.")
        if method == "configure":
            config = copy.deepcopy(args["config"])
            # Rules travel as text, preserving integers beyond JS's exact range.
            config["rules"] = engine.decode(args["rules_text"])
            try:
                config["threshold"] = float(config["threshold"])
            except (ValueError, TypeError):
                config["threshold"] = None
            required = set(default_config())
            if (
                not isinstance(config, dict)
                or not required <= set(config)
                or set(config) - required - {"context", "time_origin", "reference_by"}
            ):
                raise ValueError("Unsupported settings.")
            # Invalid mapping choices may be displayed by preflight, but malformed
            # rule structures must not enter the workspace.
            if not isinstance(config["features"], list) or any(
                not isinstance(x, str) for x in config["features"]
            ):
                raise ValueError("Invalid selected fields.")
            if not isinstance(config["rules"], list):
                raise ValueError("Rules must be a JSON array.")
            by = config.get("reference_by", [])
            if (
                not isinstance(by, list)
                or len(by) > 2
                or any(not isinstance(f, str) for f in by)
                or len(set(by)) != len(by)
            ):
                raise ValueError("Choose at most two distinct reference group fields.")
            trial = dict(
                config,
                features=[],
                session=None,
                event_id=None,
                time=None,
                threshold=6,
                reference_by=[],
            )
            if config.get("time_origin", "unspecified") not in (
                "unspecified",
                "elapsed",
                "unix",
            ):
                raise ValueError("Invalid numeric clock meaning.")
            if trial["rules"]:
                engine.validate_config(trial, self.current, self.reference)
            elif config.get("context"):
                if (
                    not isinstance(config["context"], dict)
                    or set(config["context"]) - {"User", "Host", "Process"}
                    or any(v not in self.current.fields for v in config["context"].values())
                ):
                    raise ValueError("Invalid context mapping.")
            report = mapping_checks.check(self.current, self.reference, config)
            self.config = config
            self.invalidate(report)
            return self.snapshot()
        if method == "policy_load":
            config = workflow.load_policy(args["path"], self.current, self.reference)
            self.config = config
            self.invalidate()
            return self.snapshot()
        if method == "policy_save":
            workflow.save_policy(args["path"], self.current, self.reference, self.config)
            return {"message": "Policy saved."}
        if method == "analyze":
            result = engine.analyze(self.current, self.reference, self.config)
            self.result = result
            self.evaluation_cache = None
            self.chart_cache = self.comparison_cache = None
            self.index = investigation.search_index(self.current, self.config, result)
            return self.snapshot()
        if method == "labels_template":
            evaluation.write_new(args["path"], evaluation.template(self.current))
            return {
                "message": "Blank labels saved. Have an independent reviewer label the source without detection results."
            }
        if method == "labels_load":
            self.require_result()
            labels = evaluation.load(args["path"], self.current)
            # Commit only a fully validated file. Changing labels cannot change detections.
            self.labels = labels
            self.evaluation_cache = None
            self.revision += 1
            return self.snapshot()
        if method in ("evaluation", "evaluation_save"):
            self.require_result()
            if not self.labels:
                return {"available": False}
            if self.evaluation_cache is None:
                self.evaluation_cache = evaluation.evaluate(
                    self.current, self.reference, self.config, self.result, self.labels
                )
            report = self.evaluation_cache
            if method == "evaluation_save":
                evaluation.write_new(args["path"], report)
                return {
                    "message": "Evaluation saved. Keep the case and original labels to reproduce it."
                }
            outcome = args.get("outcome", "All")
            group = args.get("group", "")
            if (
                outcome not in ("All", *evaluation.OUTCOMES)
                or not isinstance(group, str)
                or len(group) > 120
            ):
                raise ValueError("Choose an available evaluation filter.")
            rows = [
                r
                for r in report["records"]
                if (outcome == "All" or r["outcome"] == outcome)
                and (not group or r["group"] == group)
            ]
            page = bounded_int(args.get("page", 0), 0, max((len(rows) - 1) // 100, 0))
            return dict(
                available=True,
                **{k: v for k, v in report.items() if k != "records"},
                rows=rows[page * 100 : (page + 1) * 100],
                total=len(rows),
                page=page,
            )
        if method == "preview":
            data, affected, related, fields, note, source = self.preview_scope(args)
            positions = sorted(set(affected) | set(related))
            page = bounded_int(args.get("page", 0), 0, max((len(positions) - 1) // 100, 0))
            order = list(dict.fromkeys([*fields, *data.fields]))
            items = []
            for row in positions[page * 100 : (page + 1) * 100]:
                values = data.rows[row - 1]
                items.append(
                    dict(
                        row=row,
                        related=row not in affected,
                        values=[
                            ("Missing" if f not in values else display(values[f]))[:160]
                            for f in order
                        ],
                    )
                )
            return dict(
                source=source,
                manifest=data.manifest(),
                fields=order,
                marked=list(fields),
                rows=items,
                total=len(positions),
                affected=len(affected),
                page=page,
                note=note,
            )
        if method == "inspect":
            data, values = self.selection(args)
            query = bounded_text(args.get("query", ""), 4096)
            fields = list(data.fields)
            if args.get("note") is not None:
                scoped, _, _, marked, _, source = self.preview_scope(args)
                if source != args.get("source", "current"):
                    raise ValueError("The warning belongs to another source.")
                fields = list(dict.fromkeys([*marked, *fields]))
            key = (args.get("source", "current"), args["row"], query, args.get("note"))
            if self.inspection_cache is None or self.inspection_cache[0] != key:
                found = []
                for field in fields:
                    value = display(values[field]) if field in values else "Missing"
                    names = compact_spans(field, query)
                    spans = compact_spans(value, query)
                    if not query or names or spans:
                        found.append(
                            dict(
                                field=field,
                                value=value,
                                present=field in values,
                                names=names,
                                spans=spans,
                            )
                        )
                self.inspection_cache = (
                    key,
                    found,
                    sum(len(f["names"]) + len(f["spans"]) for f in found) // 2,
                )
            _, found, total = self.inspection_cache
            selected = bounded_int(args.get("match", 0), 0, max(total - 1, 0))
            # Bound highlight metadata and DOM nodes, never the underlying values.
            first = selected // 200 * 200
            last = first + 200
            output, matches, offset = [], [], 0
            for item in found:
                item = dict(item)
                for part, attr, text in (
                    ("name", "names", item["field"]),
                    ("value", "spans", item["value"]),
                ):
                    hits = item[attr]
                    count = len(hits) // 2
                    begin, end = max(0, first - offset), max(0, min(count, last - offset))
                    item[attr] = [(hits[p * 2], hits[p * 2 + 1]) for p in range(begin, end)]
                    for position in range(begin, end):
                        start, finish = hits[position * 2], hits[position * 2 + 1]
                        matches.append(
                            dict(
                                index=offset + position,
                                field=item["field"],
                                part=part,
                                start=start,
                                end=finish,
                                text=text[start:finish],
                            )
                        )
                    offset += count
                output.append(item)
            if args.get("note") is None:
                affected = list(range(1, len(data.rows) + 1))
            else:
                _, affected, _, _, _, _ = self.preview_scope(args)
            row = args["row"]
            return dict(
                fields=output,
                matches=matches,
                match_total=total,
                row=row,
                source=args.get("source", "current"),
                manifest=data.manifest(),
                has_previous=any(r < row for r in affected),
                has_next=any(r > row for r in affected),
                related=row not in affected,
                position=affected.index(row) + 1 if row in affected else None,
                affected=len(affected),
            )
        if method == "record_step":
            data, affected, related, fields, note, source = self.preview_scope(args)
            step = args.get("step")
            if step not in (-1, 1):
                raise ValueError("Invalid direction.")
            row = args.get("row", 0)
            candidates = (
                [r for r in affected if r > row]
                if step == 1
                else [r for r in affected if r < row]
            )
            target = (candidates[0] if step == 1 else candidates[-1]) if candidates else None
            positions = sorted(set(affected) | set(related))
            return dict(
                row=target,
                page=positions.index(target) // 100 if target else None,
                source=source,
            )
        if method == "copy":
            data, values = self.selection(args)
            scope = args.get("scope")
            if scope == "record":
                return {"text": json.dumps(values, ensure_ascii=False, indent=2)}
            if scope == "value":
                if args.get("field") not in values:
                    raise ValueError("This field is missing; there is no value to copy.")
                return {"text": display(values[args["field"]])}
            if scope == "match":
                inspected = self.dispatch("inspect", args)
                index = bounded_int(args.get("match"), 0, inspected["match_total"] - 1)
                return {
                    "text": next(m["text"] for m in inspected["matches"] if m["index"] == index)
                }
            raise ValueError("Choose a copy scope.")
        if method == "findings":
            self.require_result()
            query = bounded_text(args.get("query", ""), 4096)
            minimum, hide = args.get("minimum", "All"), args.get("hide", True)
            selected, hidden_gaps, outside = [], 0, False
            reveal = args.get("reveal")
            for record in self.result["records"]:
                match = investigation.matches(self.index[record["row"]], query)
                hidden_gaps += bool(record["gaps"]) and not match
                visible = match and workflow.visible(record, self.config, minimum, hide)
                if record["row"] == reveal:
                    outside = not visible
                if record["row"] != reveal and not visible:
                    continue
                selected.append(
                    dict(
                        row=record["row"],
                        status=record["status"],
                        priority=workflow.priority(record, self.config),
                        numeric_evidence=any(
                            e["kind"] == "deviation" for e in record["evidence"]
                        ),
                        reason=short_reason(record),
                    )
                )
            page = bounded_int(args.get("page", 0), 0, max((len(selected) - 1) // 100, 0))
            if args.get("locate") in [r["row"] for r in selected]:
                page = (
                    next(i for i, r in enumerate(selected) if r["row"] == args["locate"]) // 100
                )
            return dict(
                rows=selected[page * 100 : (page + 1) * 100],
                total=len(selected),
                page=page,
                hidden_gaps=hidden_gaps,
                outside=outside,
            )
        if method == "evidence":
            self.require_result()
            data, raw = self.selection(args)
            if data is not self.current:
                raise ValueError("Findings belong to incoming data.")
            record = self.result["records"][args["row"] - 1]
            groups = {}
            for item in record["evidence"]:
                groups.setdefault(item["field"], []).append(item)
            signal = chart.signal(record)
            if signal is not None and signal not in groups:
                groups[signal] = [
                    dict(
                        kind="measurement",
                        score=record["scores"][signal],
                        threshold=self.config["threshold"],
                        **engine.profile_for_record(self.result, record, signal),
                    )
                ]
            output = []
            for field, items in groups.items():
                lines = []
                for item in items:
                    if item["kind"] == "rule":
                        lines.append(
                            dict(
                                text=f"Matched: {item['name']}\nCondition: {comparison.OPERATORS[item['operator']]} {display(item['expected'])}",
                                details="",
                            )
                        )
                    else:
                        center = item.get("reference_center", item.get("center"))
                        qualifier = (
                            "Below review at" if item["kind"] == "measurement" else "Review at"
                        )
                        lines.append(
                            dict(
                                text=f"Deviation: {item['score']!r} · {qualifier}: {item['threshold']}\nReference median: {center!r}",
                                details=f"Scale: {item['scale']!r} · Method: {item['method']}",
                            )
                        )
                output.append(dict(field=field, value=display(raw[field]), lines=lines))
            if raw.get("schema") == native_integrity.SCHEMA:
                native_labels = {
                    "memory_matches": ("Code", "Changed", "Matches baseline"),
                    "baseline_approved": ("Build", "Not approved", "Approved"),
                    "protection_matches": ("Page protection", "Changed", "Matches baseline"),
                }
                for group in output:
                    if group["field"] in native_labels:
                        field = group["field"]
                        label, changed, matched = native_labels[field]
                        group["field"] = label
                        group["value"] = (
                            matched
                            if raw[field] is True
                            else changed if raw[field] is False else "Unavailable"
                        )
                        for line in group["lines"]:
                            line["details"] = (
                                f"{field}: {display(raw[field])}\n{line['text']}\n{line['details']}".strip()
                            )
                            line["text"] = (
                                "Review this observation; it does not establish malicious behavior."
                            )
                output.insert(
                    0,
                    dict(
                        field="Code hash",
                        value=raw.get("observed_sha256") or "Unavailable",
                        lines=[
                            dict(
                                text=f"Expected: {raw.get('expected_sha256') or 'No approved baseline'}\nCollection: {raw.get('memory_status')}",
                                details=f"Range: {raw.get('range_name', 'Unavailable')} · RVA: {raw.get('range_rva', 'Unavailable')} · Bytes: {raw.get('range_size', 'Unavailable')}\nBaseline SHA-256: {raw.get('baseline_sha256')}\n{raw.get('approval_reason', raw.get('collection_error', ''))}\nLocal observations and operator approvals are not proof of a trustworthy client or malicious behavior.",
                            )
                        ],
                    ),
                )
                if "coverage_expected_ranges" in raw:
                    scope = ""
                    scope_details = ""
                    if "integrity_manifest" in raw:
                        declaration = engine.decode(raw["integrity_manifest"])
                        scope = (
                            f"\n{declaration['checked_bytes']}/{declaration['executable_bytes']} "
                            "executable bytes in scope."
                        )
                        scope_details = (
                            "\n"
                            + native_integrity.integrity.describe(declaration)
                            + f"\nIntegrity manifest SHA-256: {raw['integrity_manifest_sha256']}"
                        )
                    output.append(
                        dict(
                            field="Coverage",
                            value=f"{raw['coverage_read_ranges']}/{raw['coverage_expected_ranges']} ranges read",
                            lines=[
                                dict(
                                    text=f"Range: {raw['range_name']}\n{raw['coverage_compared_ranges']} compared with approval; {raw['coverage_unavailable_ranges']} unavailable; {raw['coverage_unapproved_ranges']} unapproved; {raw['coverage_changed_ranges']} changed."
                                    + scope,
                                    details=f"{raw['coverage_read_bytes']}/{raw['coverage_expected_bytes']} configured bytes read. Covers only the declared ranges, not the entire DLL or process.\nManifest SHA-256: {raw['range_manifest_sha256']}"
                                    + scope_details,
                                )
                            ],
                        )
                    )
                if "stream_sequence" in raw or raw.get("stream_health"):
                    output.append(
                        dict(
                            field="Collection",
                            value=(
                                f"Sample {raw['stream_sequence']}"
                                if "stream_sequence" in raw
                                else "Incomplete"
                            ),
                            lines=[
                                dict(
                                    text=raw.get("collection_error")
                                    or f"Elapsed: {raw['stream_elapsed_ms']:g} ms · Interval: {raw['stream_interval_ms']} ms",
                                    details=f"{raw.get('stream_dropped_samples', 0)} samples lost in transport; {raw.get('stream_evicted_samples', 0)} older samples removed from the retained window. Changes between samples or outside configured ranges may not be observed.",
                                )
                            ],
                        )
                    )
            return dict(
                row=record["row"],
                event_id=record["event_id"],
                session=record["session"],
                status=record["status"],
                priority=workflow.priority(record, self.config),
                groups=output,
                gaps=record["gaps"],
                time=time_label(record, self.config, raw),
                reference_group=record.get("reference_group"),
                context=[
                    dict(role=role, field=item["field"], value=display(item["value"]))
                    for role, item in workflow.context_values(raw, self.config).items()
                ],
                source=data.manifest(),
                reference=self.reference.manifest() if self.reference else None,
                values=[dict(field=k, value=display(v)) for k, v in raw.items()],
                numeric=bool(record["scores"]),
                numeric_evidence=any(e["kind"] == "deviation" for e in record["evidence"]),
            )
        if method == "chart":
            self.require_result()
            width = bounded_int(args.get("width", 600), 180, 2400)
            if self.chart_cache is None or self.chart_cache[0] != width:
                self.chart_cache = width, [
                    asdict(p)
                    for p in chart.points(
                        self.result["records"], width, self.config["threshold"]
                    )
                ]
            points = self.chart_cache[1]
            row = args.get("row")
            selected = None
            if type(row) is int and 1 <= row <= len(self.result["records"]):
                record = self.result["records"][row - 1]
                field = chart.signal(record)
                if field:
                    score = record["scores"][field]
                    selected = dict(
                        row=row,
                        field=field,
                        value=display(self.current.rows[row - 1][field]),
                        score=repr(score),
                        x=chart.x_for_row(row, len(self.current.rows), width),
                        y=chart.BASE_Y - min(score / self.config["threshold"], 2) * 28,
                    )
            return dict(points=points, selected=selected, threshold=self.config["threshold"])
        if method == "chart_step":
            self.require_result()
            row, step = args.get("row", 0), args.get("step")
            if step not in (-1, 1):
                raise ValueError("Invalid direction.")
            rows = [r["row"] for r in self.result["records"] if r["scores"]]
            candidates = (
                [r for r in rows if r > row] if step == 1 else [r for r in rows if r < row]
            )
            return {
                "row": (candidates[0] if step == 1 else candidates[-1]) if candidates else None
            }
        if method in ("save", "alerts", "compare", "comparison", "details"):
            self.require_result()
            if method == "save":
                self.current_case = engine.save_case(args["path"], *self.case())
                self.comparison_cache = None
                return dict(
                    message="Case saved with original evidence and verified findings.",
                    case_file=self.current_case,
                )
            if method == "alerts":
                count = workflow.export_alerts(
                    args["path"], *self.case(), args.get("minimum", "All")
                )
                return {
                    "message": f"Exported {count} alerts. Gaps included; search does not filter exports."
                }
            if method == "compare":
                previous, previous_file = engine.open_case(args["path"], with_manifest=True)
                candidates = (self.current, self.reference)
                self.previous = (
                    share_verified_source(previous[0], candidates),
                    share_verified_source(previous[1], candidates),
                    *previous[2:],
                )
                self.previous_file = previous_file
                self.comparison_cache = None
            if method in ("compare", "comparison"):
                if not self.previous:
                    return {
                        "note": "Choose a saved case to compare.",
                        "rows": [],
                        "changes": [],
                        "paired": False,
                    }
                if self.comparison_cache is None:
                    note, rows = comparison.rows(self.case(), self.previous)
                    self.comparison_cache = dict(
                        note=note,
                        rows=rows,
                        changes=comparison.changed_records(self.case(), self.previous),
                        paired=comparison.paired(self.case(), self.previous),
                        sources=[
                            source_label(self.current, self.reference),
                            source_label(*self.previous[:2]),
                        ],
                    )
                cached = self.comparison_cache
                rows = cached["rows"]
                if args.get("row") is not None:
                    rows = comparison.record_rows(self.case(), self.previous, args["row"])
                elif args.get("changes_only"):
                    rows = [r for r in rows if r.changed]
                counts = {
                    kind: sum(kind in reason.split(", ") for _, reason in cached["changes"])
                    for kind in ("Result", "Priority", "Reasons")
                }
                return dict(
                    cached,
                    rows=[asdict(r) for r in rows],
                    counts=counts,
                    cases=[self.current_case, self.previous_file],
                    provenance=[
                        dict(
                            data=self.current.manifest(),
                            reference=self.reference.manifest() if self.reference else None,
                            paths=self.source_paths,
                        ),
                        dict(
                            data=self.previous[0].manifest(),
                            reference=self.previous[1].manifest() if self.previous[1] else None,
                            paths={"current": None, "reference": None},
                        ),
                    ],
                )
            if method == "details":
                return dict(
                    source=self.current.manifest(),
                    reference=self.reference.manifest() if self.reference else None,
                    settings=json.dumps(self.config, ensure_ascii=False, indent=2),
                    profiles=json.dumps(
                        (
                            dict(
                                global_profiles=self.result["profiles"],
                                groups=self.result["group_profiles"],
                            )
                            if "group_profiles" in self.result
                            else self.result["profiles"]
                        ),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    summary=self.result["summary"],
                    engine=self.result["engine"],
                    meaning=self.result["meaning"],
                )
        raise ValueError("Unsupported operation.")


def bounded_int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Position is outside the available range.")
    return value


def bounded_text(value, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("Search text is too long.")
    return value


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    workspace = Workspace()
    try:
        serve(workspace)
    finally:
        workspace.close()


def serve(workspace):
    while True:
        line = sys.stdin.buffer.readline(MAX_REQUEST + 1)
        if not line:
            break
        if len(line) > MAX_REQUEST:
            break  # Framing is no longer trustworthy.
        request_id = None
        try:
            request = engine.decode(line.decode("utf-8"))
            request_id = request["id"]
            if request.get("protocol") != PROTOCOL:
                raise ValueError("Desktop protocol version mismatch.")
            value = workspace.dispatch(request["method"], request.get("args", {}))
            reply = dict(id=request_id, ok=True, value=value)
        except Exception as exc:
            reply = dict(
                id=request_id,
                ok=False,
                error=str(exc),
                import_error=isinstance(exc, ImportFailure),
            )
        sys.stdout.write(json.dumps(reply, ensure_ascii=True, allow_nan=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

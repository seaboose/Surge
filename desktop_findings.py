"""Presentation of findings, native evidence and numeric charts.

Workspace owns analyzed results and view caches. These handlers project evidence
for display without changing detection or saved evidence.
"""

from dataclasses import asdict

import chart
import comparison
import engine
import investigation
import native_integrity
import workflow
from desktop_values import bounded_int, bounded_text, display, step_row
from evidence_labels import time_label


def short_reason(record, raw=None):
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
        if record["gaps"]:
            return "Input needs attention"
        if raw and raw.get("schema") == native_integrity.SCHEMA:
            if raw.get("stream_health"):
                return "Collection evidence incomplete"
            if raw.get("memory_status") != "complete":
                return "Range read incomplete"
            if raw.get("baseline_approved") is not True:
                return "No recorded approved reference"
            if raw.get("memory_matches") is False:
                return "Code differs from approved reference"
            if raw.get("protection_matches") is False:
                return "Page protection differs from approved reference"
            if (
                raw.get("memory_matches") is True
                and raw.get("protection_matches") is True
                and record.get("status") == "No finding"
            ):
                return "Matched approved reference"
            return "Comparison inconclusive"
        return "Input needs attention" if record["gaps"] else "No configured condition matched"
    return reasons[0] + (f" · +{len(reasons)-1} reasons" if len(reasons) > 1 else "")


def native_observation_explanation(row, status):
    """Explain this validated record; never turn absent evidence into a match."""
    if row.get("schema") != native_integrity.SCHEMA:
        return None
    if row.get("stream_health"):
        return "Collection reported missing or incomplete evidence. This notice is not a code-range observation."
    if row.get("memory_status") != "complete":
        text = "This range could not be read completely; its comparison is inconclusive."
    elif row.get("baseline_approved") is not True:
        text = "This range has no recorded approved reference; an approved match cannot be established."
    elif row.get("memory_matches") is False:
        text = "This range's code differed from its recorded approved reference. Review the change."
    elif row.get("protection_matches") is False:
        text = "This range's page protection differed from its recorded approved reference. Review the change."
    elif row.get("memory_matches") is True and row.get("protection_matches") is True:
        text = "This range matched its recorded approved reference for code and page protection. The range was read completely."
    else:
        text = "The evidence does not establish a complete match for this range."
    if (
        row.get("stream_final_dropped")
        or row.get("stream_evicted_samples")
        or row.get("collection_error")
    ):
        text += " Collection also reports missing or incomplete evidence."
    if status == "Review":
        text += " The configured analysis flags this record for review."
    elif status == "Unknown":
        text += " The configured analysis remains inconclusive."
    return text


def handle(workspace, method, args):
    """Handle an explicitly routed operation after Workspace admission checks."""
    if method == "findings":
        workspace.require_result()
        query = bounded_text(args.get("query", ""), 4096)
        minimum, hide = args.get("minimum", "All"), args.get("hide", True)
        selected, hidden_gaps, outside = [], 0, False
        reveal = args.get("reveal")
        for record in workspace.result["records"]:
            match = investigation.matches(workspace.index[record["row"]], query)
            hidden_gaps += bool(record["gaps"]) and not match
            visible = match and workflow.visible(record, workspace.config, minimum, hide)
            if record["row"] == reveal:
                outside = not visible
            if record["row"] != reveal and not visible:
                continue
            selected.append(
                dict(
                    row=record["row"],
                    status=record["status"],
                    priority=workflow.priority(record, workspace.config),
                    numeric_evidence=any(e["kind"] == "deviation" for e in record["evidence"]),
                    reason=short_reason(record, workspace.current.rows[record["row"] - 1]),
                )
            )
        page = bounded_int(args.get("page", 0), 0, max((len(selected) - 1) // 100, 0))
        if args.get("locate") in [r["row"] for r in selected]:
            page = next(i for i, r in enumerate(selected) if r["row"] == args["locate"]) // 100
        return dict(
            rows=selected[page * 100 : (page + 1) * 100],
            total=len(selected),
            page=page,
            hidden_gaps=hidden_gaps,
            outside=outside,
        )
    if method == "evidence":
        workspace.require_result()
        data, raw = workspace.selection(args)
        if data is not workspace.current:
            raise ValueError("Findings belong to incoming data.")
        record = workspace.result["records"][args["row"] - 1]
        groups = {}
        for item in record["evidence"]:
            groups.setdefault(item["field"], []).append(item)
        signal = chart.signal(record)
        if signal is not None and signal not in groups:
            groups[signal] = [
                dict(
                    kind="measurement",
                    score=record["scores"][signal],
                    threshold=workspace.config["threshold"],
                    **engine.profile_for_record(workspace.result, record, signal),
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
            priority=workflow.priority(record, workspace.config),
            groups=output,
            explanation=native_observation_explanation(raw, record["status"]),
            gaps=record["gaps"],
            time=time_label(record, workspace.config, raw),
            reference_group=record.get("reference_group"),
            context=[
                dict(role=role, field=item["field"], value=display(item["value"]))
                for role, item in workflow.context_values(raw, workspace.config).items()
            ],
            source=data.manifest(),
            reference=workspace.reference.manifest() if workspace.reference else None,
            values=[dict(field=k, value=display(v)) for k, v in raw.items()],
            numeric=bool(record["scores"]),
            numeric_evidence=any(e["kind"] == "deviation" for e in record["evidence"]),
        )
    if method == "chart":
        workspace.require_result()
        width = bounded_int(args.get("width", 600), 180, 2400)
        if workspace.chart_cache is None or workspace.chart_cache[0] != width:
            workspace.chart_cache = width, [
                asdict(p)
                for p in chart.points(workspace.result["records"], width, workspace.config["threshold"])
            ]
        points = workspace.chart_cache[1]
        row = args.get("row")
        selected = None
        if type(row) is int and 1 <= row <= len(workspace.result["records"]):
            record = workspace.result["records"][row - 1]
            field = chart.signal(record)
            if field:
                score = record["scores"][field]
                selected = dict(
                    row=row,
                    field=field,
                    value=display(workspace.current.rows[row - 1][field]),
                    score=repr(score),
                    x=chart.x_for_row(row, len(workspace.current.rows), width),
                    y=chart.BASE_Y - min(score / workspace.config["threshold"], 2) * 28,
                )
        return dict(points=points, selected=selected, threshold=workspace.config["threshold"])
    if method == "chart_step":
        workspace.require_result()
        rows = [r["row"] for r in workspace.result["records"] if r["scores"]]
        return {"row": step_row(rows, args.get("row", 0), args.get("step"))}
    raise ValueError("Unsupported operation.")

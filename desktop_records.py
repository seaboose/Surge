"""Raw-record previews, bounded search highlights and exact copying.

Workspace owns selection and caches. Its dispatcher checks revision and loaded
source before calling this module; records remain original evidence.
"""

import json

from desktop_values import bounded_int, bounded_text, compact_spans, display, step_row


def handle(workspace, method, args):
    """Handle an explicitly routed operation after Workspace admission checks."""
    if method == "preview":
        data, affected, related, fields, note, source = workspace.preview_scope(args)
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
        data, values = workspace.selection(args)
        query = bounded_text(args.get("query", ""), 4096)
        fields = list(data.fields)
        if args.get("note") is not None:
            scoped, _, _, marked, _, source = workspace.preview_scope(args)
            if source != args.get("source", "current"):
                raise ValueError("The warning belongs to another source.")
            fields = list(dict.fromkeys([*marked, *fields]))
        key = (args.get("source", "current"), args["row"], query, args.get("note"))
        if workspace.inspection_cache is None or workspace.inspection_cache[0] != key:
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
            workspace.inspection_cache = (
                key,
                found,
                sum(len(f["names"]) + len(f["spans"]) for f in found) // 2,
            )
        _, found, total = workspace.inspection_cache
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
            _, affected, _, _, _, _ = workspace.preview_scope(args)
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
        data, affected, related, fields, note, source = workspace.preview_scope(args)
        target = step_row(affected, args.get("row", 0), args.get("step"))
        positions = sorted(set(affected) | set(related))
        return dict(
            row=target,
            page=positions.index(target) // 100 if target else None,
            source=source,
        )
    if method == "copy":
        data, values = workspace.selection(args)
        scope = args.get("scope")
        if scope == "record":
            return {"text": json.dumps(values, ensure_ascii=False, indent=2)}
        if scope == "value":
            if args.get("field") not in values:
                raise ValueError("This field is missing; there is no value to copy.")
            return {"text": display(values[args["field"]])}
        if scope == "match":
            inspected = workspace.dispatch("inspect", args)
            index = bounded_int(args.get("match"), 0, inspected["match_total"] - 1)
            return {
                "text": next(m["text"] for m in inspected["matches"] if m["index"] == index)
            }
        raise ValueError("Choose a copy scope.")
    raise ValueError("Unsupported operation.")

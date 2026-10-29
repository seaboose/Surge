"""Case persistence, comparison and provenance views for the desktop.

Workspace retains the active and previous cases. Engine and workflow continue to
own verification and exclusive output publication.
"""

from dataclasses import asdict, replace
import json

import comparison
import engine
import workflow
from evidence_labels import source_label


def share_verified_source(data, candidates):
    """Reuse immutable source content only after open_case has fully verified it."""
    if data is not None:
        for known in candidates:
            if known is not None and data.format == known.format and data.text == known.text:
                # Keep the compared source's own name and manifest identity.
                return replace(data, text=known.text, fields=known.fields, rows=known.rows)
    return data


def handle(workspace, method, args):
    """Handle an explicitly routed operation after Workspace admission checks."""
    if method in ("save", "alerts", "compare", "comparison", "details"):
        workspace.require_result()
        if method == "save":
            workspace.current_case = engine.save_case(args["path"], *workspace.case())
            workspace.comparison_cache = None
            return dict(
                message="Case saved with original evidence and verified findings.",
                case_file=workspace.current_case,
            )
        if method == "alerts":
            count = workflow.export_alerts(
                args["path"], *workspace.case(), args.get("minimum", "All")
            )
            return {
                "message": f"Exported {count} alerts. Gaps included; search does not filter exports."
            }
        if method == "compare":
            previous, previous_file = engine.open_case(args["path"], with_manifest=True)
            candidates = (workspace.current, workspace.reference)
            workspace.previous = (
                share_verified_source(previous[0], candidates),
                share_verified_source(previous[1], candidates),
                *previous[2:],
            )
            workspace.previous_file = previous_file
            workspace.comparison_cache = None
        if method in ("compare", "comparison"):
            if not workspace.previous:
                return {
                    "note": "Choose a saved case to compare.",
                    "rows": [],
                    "changes": [],
                    "paired": False,
                }
            if workspace.comparison_cache is None:
                note, rows = comparison.rows(workspace.case(), workspace.previous)
                workspace.comparison_cache = dict(
                    note=note,
                    rows=rows,
                    changes=comparison.changed_records(workspace.case(), workspace.previous),
                    paired=comparison.paired(workspace.case(), workspace.previous),
                    sources=[
                        source_label(workspace.current, workspace.reference),
                        source_label(*workspace.previous[:2]),
                    ],
                )
            cached = workspace.comparison_cache
            rows = cached["rows"]
            if args.get("row") is not None:
                rows = comparison.record_rows(workspace.case(), workspace.previous, args["row"])
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
                cases=[workspace.current_case, workspace.previous_file],
                provenance=[
                    dict(
                        data=workspace.current.manifest(),
                        reference=workspace.reference.manifest() if workspace.reference else None,
                        paths=workspace.source_paths,
                    ),
                    dict(
                        data=workspace.previous[0].manifest(),
                        reference=workspace.previous[1].manifest() if workspace.previous[1] else None,
                        paths={"current": None, "reference": None},
                    ),
                ],
            )
        if method == "details":
            return dict(
                source=workspace.current.manifest(),
                reference=workspace.reference.manifest() if workspace.reference else None,
                settings=json.dumps(workspace.config, ensure_ascii=False, indent=2),
                profiles=json.dumps(
                    (
                        dict(
                            global_profiles=workspace.result["profiles"],
                            groups=workspace.result["group_profiles"],
                        )
                        if "group_profiles" in workspace.result
                        else workspace.result["profiles"]
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
                summary=workspace.result["summary"],
                engine=workspace.result["engine"],
                meaning=workspace.result["meaning"],
            )
    raise ValueError("Unsupported operation.")

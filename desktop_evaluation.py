"""Independent label loading and evaluation views for the desktop.

Labels and evaluation caches belong to Workspace and cannot change detections.
"""

import evaluation
from desktop_values import bounded_int


def handle(workspace, method, args):
    """Handle an explicitly routed operation after Workspace admission checks."""
    if method == "labels_template":
        evaluation.write_new(args["path"], evaluation.template(workspace.current))
        return {
            "message": "Blank labels saved. Have an independent reviewer label the source without detection results."
        }
    if method == "labels_load":
        workspace.require_result()
        labels = evaluation.load(args["path"], workspace.current)
        # Commit only a fully validated file. Changing labels cannot change detections.
        workspace.labels = labels
        workspace.evaluation_cache = None
        workspace.revision += 1
        return workspace.snapshot()
    if method in ("evaluation", "evaluation_save"):
        workspace.require_result()
        if not workspace.labels:
            return {"available": False}
        if workspace.evaluation_cache is None:
            workspace.evaluation_cache = evaluation.evaluate(
                workspace.current, workspace.reference, workspace.config, workspace.result, workspace.labels
            )
        report = workspace.evaluation_cache
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
    raise ValueError("Unsupported operation.")

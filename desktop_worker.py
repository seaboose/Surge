"""Local desktop protocol. Detection and evidence formats remain owned by Python.

Only the Electron main process launches this worker. Paths are supplied by native
dialogs in that process, never by the renderer. No sockets or executable policies.
"""

from __future__ import annotations

import copy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

import engine
import investigation
import mapping_checks
import workflow
import native_integrity
import native_stream
from import_errors import ImportFailure

import desktop_cases
import desktop_evaluation
import desktop_findings
import desktop_records

# Preserve helper and module exports used by regression tools and integrations.
import chart
import record_search
from desktop_cases import share_verified_source
from desktop_values import compact_spans

PROTOCOL = 1
MAX_REQUEST = 512 * 1024


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


def demo_summary(rows, summary):
    """Describe only the inspected evidence, never the live collection status."""
    observations = [r for r in rows if not r.get("stream_health")]
    expected = (
        bool(observations)
        and len(observations) == len(rows)
        and all(
            r.get("memory_status") == "complete"
            and all(
                r.get(k) is True
                for k in ("baseline_approved", "memory_matches", "protection_matches")
            )
            for r in observations
        )
        and summary.get("No finding") == len(rows)
        and all(summary.get(k) == 0 for k in ("Review", "Unknown", "rows_with_gaps"))
    )
    return dict(
        expected=expected,
        ranges=len(
            {
                (r.get("module_sha256"), r.get("range_name"), r.get("range_rva"))
                for r in observations
            }
        ),
        review=summary.get("Review", 0),
        unknown=summary.get("Unknown", 0),
    )


def observation_counts(rows):
    """Count the viewed stream rows, never the moving collector window."""
    observations = [r for r in rows if not r.get("stream_health")]
    if not observations or any(type(r.get("stream_sequence")) is not int for r in observations):
        return None
    samples = {}
    for row in observations:
        key = (row.get("session_id"), row["stream_sequence"])
        samples[key] = samples.get(key, 0) + 1
    sizes = set(samples.values())
    return dict(
        samples=len(samples),
        observations=len(observations),
        notices=len(rows) - len(observations),
        ranges_per_sample=next(iter(sizes)) if len(sizes) == 1 else None,
    )


def saved_evidence_summary(data, result):
    """Summarize verified saved native evidence, without a live-session claim.

    Case verification recomputes the configured analysis. Native validation also
    checks derived verdicts against the captured bytes and coverage declarations,
    even when a saved policy no longer contains the usual integrity rules.
    """
    if native_integrity.default_policy(data) is None:
        return None
    return demo_summary(data.rows, result["summary"])


class Workspace:
    def __init__(self, *, survive_data_root=None, packaged=False, game_window=None):
        if type(packaged) is not bool:
            raise ValueError("Packaged runtime must be explicitly boolean.")
        self.survive_data_root = survive_data_root
        self.packaged = packaged
        from survive_study import validate_game_window
        self.game_window = validate_game_window(game_window)
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
        self.inspected_capture = None
        self.saved_result = None
        self.survive = None

    def close(self):
        if self.capture:
            self.capture.stop()
        if self.survive:
            self.survive.close()

    def inspect_capture(self):
        rows = self.capture.snapshot()
        if not rows:
            raise ValueError("Waiting for the first collection sample.")
        raw = ("\n".join(engine.canonical(row) for row in rows) + "\n").encode("utf-8")
        data = engine.parse_bytes(raw, f"our-app-{self.capture.build}.jsonl")
        config = native_integrity.default_policy(data)
        result = engine.analyze(data, None, config)
        index = investigation.search_index(data, config, result)
        observations = [row for row in rows if not row.get("stream_health")]
        # Derive the inspected endpoint from these exact validated rows, never
        # from status(), which can already describe a newer collection sample.
        last = observations[-1] if observations else {}
        inspected_capture = dict(
            session_id=last.get("session_id"),
            capture_state=last.get("stream_capture_state"),
            final_sequence=last.get("stream_final_sequence"),
            captured_at=last.get("captured_at"),
            inspected_at=datetime.now(timezone.utc).isoformat(),
            records=len(observations),
            samples=len({row["stream_sequence"] for row in observations}),
        )
        # Publish a complete snapshot together; collection keeps its own window.
        self.current, self.reference, self.config = data, None, config
        self.labels = self.current_case = None
        self.source_paths = {"current": None, "reference": None}
        self.invalidate()
        self.result = result
        self.index = index
        self.inspected_capture = inspected_capture
        return self.snapshot()

    def invalidate(self, report=None):
        self.saved_result = None
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
                    e["kind"] == "deviation" for r in self.result["records"] for e in r["evidence"]
                )
            ),
            meaning=self.result["meaning"] if self.result else "",
            capture=self.capture.status() if self.capture else None,
            inspected_capture=self.inspected_capture,
            saved_result=self.saved_result,
            observation_counts=(
                observation_counts(self.current.rows)
                if self.current and self.result and (self.inspected_capture or self.saved_result)
                else None
            ),
            demo_result=(
                demo_summary(self.current.rows, self.result["summary"])
                if self.inspected_capture and self.current and self.result
                else None
            ),
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
            list(note["rows"]) if note["rows"] is not None else list(range(1, len(data.rows) + 1))
        )
        return data, affected, list(note["related"]), note["fields"], note, note["source"]

    def dispatch(self, method, args):
        if not isinstance(args, dict):
            raise ValueError("Invalid request.")
        if isinstance(method, str) and method.startswith("survive_"):
            from survive_workspace import SurviveWorkspace
            if self.survive is None:
                self.survive = SurviveWorkspace(survive_data_root=self.survive_data_root, packaged=self.packaged, game_window=self.game_window)
            return self.survive.dispatch(method, args)
        if method == "state":
            return self.snapshot()
        if method == "library_verify":
            engine.open_case(args["path"])
            return {"verified": True}
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
                self.inspected_capture = None
                self.labels = None
                self.config = native_policy or default_config()
                self.current_case = None
            self.invalidate()
            return self.snapshot()
        if method == "open":
            (current, reference, config, result), case_file = engine.open_case(
                args["path"], with_manifest=True
            )
            saved_result = saved_evidence_summary(current, result)
            self.current, self.reference, self.config = current, reference, config
            self.inspected_capture = None
            self.labels = None
            self.invalidate()
            self.result = result
            self.current_case = case_file
            self.saved_result = saved_result
            self.source_paths = {"current": None, "reference": None}
            self.index = investigation.search_index(current, config, result)
            return self.snapshot()
        self.require_revision(args)
        if not self.current:
            raise ValueError("Import data or open a case first.")
        if method == "library_snapshot":
            self.require_result()
            engine.save_case(args["path"], *self.case())
            return {"saved": True}
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
        if method in ("labels_template", "labels_load", "evaluation", "evaluation_save"):
            return desktop_evaluation.handle(self, method, args)
        if method in ("preview", "inspect", "record_step", "copy"):
            return desktop_records.handle(self, method, args)
        if method in ("findings", "evidence", "chart", "chart_step"):
            return desktop_findings.handle(self, method, args)
        if method in ("save", "alerts", "compare", "comparison", "details"):
            return desktop_cases.handle(self, method, args)
        raise ValueError("Unsupported operation.")


def main(*, survive_data_root=None, packaged=False, game_window=None):
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    workspace = Workspace(survive_data_root=survive_data_root, packaged=packaged, game_window=game_window)
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

"""Narrow desktop orchestration for owned Survive recording and study sessions.

Renderer requests contain identifiers and bounded choices, never paths, commands,
process IDs or detector parameters. Recording and trial labels stay independent
of the ordinary Surge investigation workspace.
"""
from __future__ import annotations

import re

PROFILES = {"survive-lucian-practice-v1", "survive-lucian-reference-v1"}
MODES = {"human", "scripted", "mixed", "speed_probe"}
PHASES = {"practice", "development", "held-out"}
FIELDS = {
    "survive_sources": set(),
    "survive_start": {"source_id", "profile_id"},
    "survive_status": {"after"},
    "survive_stop": set(),
    "survive_sessions": set(),
    "survive_open": {"recording_id"},
    "survive_record": {"recording_id", "seq"},
    "survive_trials": set(),
    "survive_trial_start": {"mode", "seed", "profile_id", "participant", "phase"},
    "survive_report": set(),
    "survive_study_freeze": set(),
    "survive_adjudicate": {"trial_id", "expected_mechanical_violation", "note"},
    "survive_investigations": set(),
    "survive_investigation_create": {"title", "author"},
    "survive_investigation_open": {"investigation_id", "revision"},
    "survive_investigation_save": {"investigation_id", "expected_revision", "title", "author", "change_reason", "status", "sections"},
    "survive_investigation_attach": {"investigation_id", "expected_revision", "recording_id", "seq", "constraint_id", "author", "change_reason"},
    "survive_investigation_resolve": {"investigation_id", "evidence_id", "revision"},
    "survive_investigation_export": {"investigation_id", "revision"},
}


def identifier(value, name):
    pattern = r"[0-9a-fA-F]{32}" if name == "source identifier" else r"[0-9a-f]{32}"
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError("Invalid " + name + ".")
    return value


def validate(method, args):
    if method not in FIELDS or not isinstance(args, dict) or set(args) - FIELDS[method]:
        raise ValueError("Unsupported Survive request or setting.")
    required = FIELDS[method] - ({"after"} if method == "survive_status" else set())
    if not required <= set(args):
        raise ValueError("Missing Survive setting.")
    if "profile_id" in args and (not isinstance(args["profile_id"], str) or args["profile_id"] not in PROFILES):
        raise ValueError("Select a reviewed Survive profile.")
    if "source_id" in args and args["source_id"] != "next":
        identifier(args["source_id"], "source identifier")
    for key in ("recording_id", "trial_id", "investigation_id"):
        if key in args:
            identifier(args[key], key)
    if "after" in args and (type(args["after"]) is not int or not 0 <= args["after"] <= 10000):
        raise ValueError("Invalid recording cursor.")
    if "seq" in args and (type(args["seq"]) is not int or not 0 <= args["seq"] < 10000):
        raise ValueError("Invalid record sequence.")
    if "mode" in args and (not isinstance(args["mode"], str) or args["mode"] not in MODES):
        raise ValueError("Choose a supported study mode.")
    if "phase" in args and (not isinstance(args["phase"], str) or args["phase"] not in PHASES):
        raise ValueError("Choose practice, development or held-out collection.")
    if "seed" in args and (type(args["seed"]) is not int or not 0 <= args["seed"] <= 2147483647):
        raise ValueError("Seed must be a nonnegative 32-bit integer.")
    if "participant" in args and (not isinstance(args["participant"], str) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", args["participant"])):
        raise ValueError("Use a short participant alias containing letters, numbers, _ or -.")
    if "expected_mechanical_violation" in args and (not isinstance(args["expected_mechanical_violation"], str) or args["expected_mechanical_violation"] not in {"yes", "no", "unknown"}):
        raise ValueError("Choose yes, no or unknown for the independent assessment.")
    if "note" in args and (not isinstance(args["note"], str) or len(args["note"]) > 500 or
                           any(ord(c) < 32 and c not in "\n\t" for c in args["note"])):
        raise ValueError("Assessment note must be at most500 readable characters.")
    if method.startswith("survive_investigation"):
        for key, limit in (("title", 120), ("author", 80), ("change_reason", 500)):
            if key in args:
                value = args[key]
                if (not isinstance(value, str) or not value.strip() or len(value) > limit
                        or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
                    raise ValueError("Invalid investigation " + key + ".")
        for key in ("expected_revision", "revision"):
            if key in args and not (key == "revision" and args[key] is None):
                if type(args[key]) is not int or not 1 <= args[key] <= 256:
                    raise ValueError("Invalid investigation revision.")
        if "status" in args and (not isinstance(args["status"], str) or args["status"] not in {"draft", "reviewed"}):
            raise ValueError("Choose draft or reviewed.")
        if "evidence_id" in args and (not isinstance(args["evidence_id"], str) or not re.fullmatch(r"E(?:[1-9]|[12][0-9]|3[0-2])", args["evidence_id"])):
            raise ValueError("Invalid evidence reference.")
        if "constraint_id" in args and args["constraint_id"] is not None:
            value = args["constraint_id"]
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_:.-]{1,160}", value):
                raise ValueError("Invalid constraint reference.")
        if "sections" in args:
            sections = args["sections"]
            if not isinstance(sections, dict) or set(sections) != {"question", "observations", "hypothesis", "conclusion", "next_steps"}:
                raise ValueError("Use the five supported investigation sections.")
            for value in sections.values():
                if (not isinstance(value, str) or len(value) > 4000
                        or any((ord(c) < 32 and c not in "\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
                    raise ValueError("Investigation sections must contain at most4000 readable characters each.")


class SurviveWorkspace:
    def __init__(self, capture=None, study=None, investigations=None, *, bridge_factory=None,
                 survive_data_root=None, packaged=False, game_window=None):
        from survive_runtime import RuntimeLayout
        self.runtime = RuntimeLayout(saved_root=survive_data_root, packaged=packaged)
        from survive_study import validate_game_window
        self.game_window = validate_game_window(game_window)
        self._capture = capture
        self._study = study
        self._investigations = investigations
        self._bridge_factory = bridge_factory
        self._bridge = None

    @property
    def investigations(self):
        if self._investigations is None:
            from survive_investigations import InvestigationManager
            self._investigations = InvestigationManager(self.capture, self.runtime.data_path("Investigations"))
        return self._investigations

    @property
    def capture(self):
        if self._capture is None:
            from survive_capture import CaptureManager
            if self.runtime.packaged:
                self.runtime.identity()
                self.runtime.verify_assets()
            self._capture = CaptureManager(self.runtime.data_path("Telemetry"), self.runtime.data_path("SurgeRecordings"))
        return self._capture

    @property
    def study(self):
        if self._study is None:
            from survive_study import StudyManager
            self._study = StudyManager(runtime=self.runtime, game_window=self.game_window)
        return self._study

    def close(self):
        try:
            if self._capture is not None:
                self._capture.close()
        finally:
            try:
                if self._bridge is not None:
                    self._bridge.close()
            finally:
                if self._study is not None:
                    self._study.close()

    def _with_trial(self, value):
        return dict(value, trial=self._study.status().get("trial") if self._study is not None else None)

    def dispatch(self, method, args):
        validate(method, args)
        if method == "survive_investigations":
            return self.investigations.list()
        investigation_methods = {
            "survive_investigation_create": "create",
            "survive_investigation_open": "open",
            "survive_investigation_save": "save",
            "survive_investigation_attach": "attach",
            "survive_investigation_resolve": "resolve",
            "survive_investigation_export": "export",
        }
        if method in investigation_methods:
            return getattr(self.investigations, investigation_methods[method])(**args)
        if method == "survive_sources":
            return {"sources": self.capture.sources()}
        if method == "survive_start":
            return self.capture.start(args["source_id"], args["profile_id"])
        if method == "survive_status":
            return self._with_trial(self.capture.status(args.get("after", 0)))
        if method == "survive_stop":
            return self._with_trial(self.capture.stop())
        if method == "survive_sessions":
            return {"sessions": self.capture.sessions()}
        if method == "survive_open":
            return self.capture.open(args["recording_id"])
        if method == "survive_record":
            return self.capture.record(args["recording_id"], args["seq"])
        if method == "survive_trials":
            return {"trials": self.study.trials()}
        if method == "survive_trial_start":
            previous = self.study.status().get("trial")
            if previous and previous.get("process_state") == "running":
                raise ValueError("The owned game is still running. Finish that round before launching another.")
            if self._bridge is not None:
                self._bridge.close()
                self._bridge = None
            # Arm the watcher before launch so a fast first game tick cannot be
            # missed. A failed launch preserves an explicitly incomplete attempt.
            self.capture.start("next", args["profile_id"])
            launched_here = False
            try:
                launched = self.study.start(**args)
                launched_here = True
                trial = launched["trial"]
                current = self.capture.status()
                self.study.bind_recording(trial["trial_id"], current["capture"]["recording_id"])
                if self._bridge_factory is None:
                    from survive_recorder_bridge import RecorderBridge
                    factory = RecorderBridge
                else:
                    factory = self._bridge_factory
                self._bridge = factory(self.capture, self.study, trial["trial_id"])
                self._bridge.start()
                return self._with_trial(current)
            except Exception:
                try:
                    self.capture.stop()
                finally:
                    try:
                        if self._bridge is not None:
                            self._bridge.close()
                            self._bridge = None
                    finally:
                        if launched_here:
                            self.study.close()
                raise
        if method == "survive_study_freeze":
            return self.study.freeze()
        if method == "survive_adjudicate":
            return self.study.adjudicate(**args)
        if method == "survive_report":
            # Verify at most four uncached sessions per refresh so a large
            # archive cannot monopolize recording controls. Cached summaries
            # still recheck retained hashes. Labels never enter the adapter.
            verified = self.capture.verified_summaries(max_new=4)
            return dict(self.study.report(verified["recordings"]),
                        rejected_recordings=verified["rejected"],
                        pending_recordings=verified["pending"])
        raise ValueError("Unsupported Survive operation.")

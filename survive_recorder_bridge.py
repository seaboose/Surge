"""Bounded status/control bridge for this manager's one owned game trial.

The game may request only that its associated recorder stop. This channel never
changes game state, source telemetry, detection inputs or study labels. It is a
local unsigned convenience channel, not evidence of authentic player input.
"""
from __future__ import annotations

import os
import threading
import time
import uuid

from survive_capture import _directory, _encoded, _json, _read, _regular


class RecorderBridge:
    def __init__(self, capture, study, trial_id, *, poll_seconds=.25):
        self.capture, self.study, self.trial_id = capture, study, trial_id
        self.session = capture.active
        if self.session is None:
            raise ValueError("The owned trial has no recorder.")
        self.recording_id = self.session.recording_id
        self.folder = _directory(study._trial_path(trial_id))
        binding = _json(_read(self.folder / "recording.json", 4096))
        if binding.get("trial_id") != trial_id or binding.get("recording_id") != self.recording_id:
            raise ValueError("The recording bridge must match the saved trial binding.")
        self.poll_seconds = poll_seconds
        self.event = threading.Event()
        self.heartbeat = 0
        self.request_seen = False
        self.error = None
        self.exited_at = None
        self.thread = None

    def _snapshot(self):
        with self.session.lock:
            value = self.session._capture()
        health = value["health"]
        return {"schema": "survive-recorder-status-v1", "trial_id": self.trial_id,
                "recording_id": self.recording_id, "session_id": value["session_id"],
                "heartbeat": self.heartbeat, "state": value["state"],
                "elapsed_s": value["elapsed_s"], "source_elapsed_s": value["source_elapsed_s"],
                "records": value["records"], "stale_s": health["stale_s"],
                "sequence_gaps": health["sequence_gaps"], "parse_errors": health["parse_errors"],
                "pending_bytes": health["pending_bytes"], "error": health["error"] or self.error,
                "stop_requested": self.request_seen, "analysis_state": value["analysis_state"]}

    def _publish(self):
        _directory(self.folder)
        target = self.folder / "recorder-status.json"
        if target.exists() or target.is_symlink():
            _regular(target)
        pending = self.folder / (".recorder-" + uuid.uuid4().hex + ".pending")
        raw = _encoded(self._snapshot())
        if len(raw) > 4096:
            raise ValueError("Recorder status exceeds its bound.")
        try:
            with pending.open("xb") as output:
                output.write(raw)
            _directory(self.folder)
            if target.exists() or target.is_symlink():
                _regular(target)
            os.replace(pending, target)
        finally:
            if pending.exists():
                pending.unlink()
        self.heartbeat += 1

    def _stop_request(self):
        request = self.folder / "recorder-stop.json"
        if self.request_seen or (not request.exists() and not request.is_symlink()):
            return
        value = _json(_read(request, 2048))
        if (not isinstance(value, dict) or set(value) != {"schema", "trial_id", "recording_id", "command"}
                or value != {"schema": "survive-recorder-control-v1", "trial_id": self.trial_id,
                             "recording_id": self.recording_id, "command": "stop_recording"}):
            raise ValueError("Recorder stop request does not match this owned trial.")
        self.request_seen = True
        # Retain the exact session object: a late request can never stop a later
        # recording selected in the desktop interface.
        with self.session.lock:
            if self.session.state not in {"waiting", "recording"}:
                return
            self.session.stop_reason = "game_operator_stop"
        self.session.stop()

    def tick(self):
        errors = []
        try:
            self._stop_request()
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(str(exc)[:200])
        try:
            trial = self.study.status().get("trial")
            running = trial and trial.get("trial_id") == self.trial_id and trial.get("process_state") == "running"
            if not running:
                self.exited_at = self.exited_at or time.monotonic()
                if time.monotonic() - self.exited_at >= 2:
                    with self.session.lock:
                        active = self.session.state in {"waiting", "recording"}
                        if active:
                            self.session.stop_reason = "owned_game_exited"
                    if active:
                        self.session.stop()
        except (OSError, ValueError, RuntimeError) as exc:
            # Failure becomes a visible health warning; it never stops gameplay
            # or permits an invalid request to control a recording.
            errors.append(str(exc)[:200])
        self.error = errors[0] if errors else None
        self._publish()

    def start(self):
        self._publish()
        self.thread = threading.Thread(target=self._run, name="SurviveRecorderBridge", daemon=True)
        self.thread.start()

    def _run(self):
        while not self.event.wait(self.poll_seconds):
            try:
                self.tick()
            except (OSError, ValueError, RuntimeError) as exc:
                # A blocked status path leaves the last heartbeat stale, which
                # the game displays as unavailable instead of claiming health.
                self.error = str(exc)[:200]
            if self.exited_at and time.monotonic() - self.exited_at >= 3:
                return

    def close(self):
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=6)
            if self.thread.is_alive():
                raise RuntimeError("Recorder bridge did not stop within its deadline.")
        try:
            self._publish()
        except (OSError, ValueError):
            pass  # Missing final status ages out in the game; no healthy fallback.

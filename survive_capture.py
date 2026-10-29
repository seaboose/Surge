"""Bounded local Survive recorder and reproducible analyst snapshots.

Only the owned lab's GUID-named files are sources. Recording copies exact bytes;
it never controls the game or invents a terminal game event. Trial labels are
external to this module and never reach the movement detector.
"""
from __future__ import annotations

import builtins
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time
import types
import uuid

import engine

ROOT = Path(__file__).resolve().parent
LAB = ROOT / "unreal" / "SurgeMovementLab"
TELEMETRY = LAB / "telemetry"
MAX_BYTES = 4 * 1024 * 1024
MAX_ROWS = 10000
MAX_LINE = 4096
MAX_RESPONSE = 4 * 1024 * 1024
MAX_ENTRIES = 2000
GUID = re.compile(r"^[a-fA-F0-9]{32}$")
RECORDING = re.compile(r"^[a-f0-9]{32}$")
PROFILE_IDS = frozenset({"survive-lucian-practice-v1", "survive-lucian-reference-v1"})
_ADAPTER_LOCK = threading.Lock()
_ADAPTERS = None


class _TransientSourceRead(Exception):
    """A short-lived game append lock; output errors never use this path."""


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _encoded(value):
    return (json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON number")


def _json(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_reject_constant)


def _read(path, maximum):
    _directory(path.parent)
    before = _regular(path)
    with path.open("rb") as source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("File identity changed while opening it")
        value = source.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("File exceeds its recording limit")
    return value


def _regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("Source must be a regular local file, not a link")
    return info


def _directory(path, *, create=False):
    # Check existing ancestors before creating anything, so a junction in Saved
    # cannot redirect a recorder write outside the selected local root.
    path = path.absolute()
    for ancestor in reversed((path, *path.parents)):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if ancestor.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked recording directories are not supported")
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Recording directory ancestor is not a directory")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("Recording directory is unavailable or linked")
    info = path.lstat()
    if getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Linked recording directories are not supported")
    return path.resolve()


def _adapters():
    """Load trusted legacy scripts privately, without changing sys.path/modules."""
    global _ADAPTERS
    with _ADAPTER_LOCK:
        if _ADAPTERS is not None:
            return _ADAPTERS
        loaded = {}
        for name in ("prepare", "prepare_v2", "prepare_v3", "audit_v3"):
            source = TELEMETRY / (name + ".py")
            module = types.ModuleType("_surge_survive_" + name)
            module.__file__ = str(source)
            source_raw = _read(source, 256 * 1024)
            module.__source_sha256__ = _sha(source_raw)
            original_import = builtins.__import__

            def local_import(import_name, globals=None, locals=None, fromlist=(), level=0):
                if level == 0 and import_name in loaded:
                    return loaded[import_name]
                return original_import(import_name, globals, locals, fromlist, level)

            module.__dict__["__builtins__"] = dict(vars(builtins), __import__=local_import)
            exec(compile(source_raw, str(source), "exec"), module.__dict__)
            loaded[name] = module
        _ADAPTERS = loaded
        return loaded


def _analysis_identity():
    identity = {}
    for name, module in _adapters().items():
        current = _sha(_read(TELEMETRY / (name + ".py"), 256 * 1024))
        if current != module.__source_sha256__:
            raise ValueError("Survive adapter changed; restart Surge before recording or reviewing")
        identity[name + ".py"] = current
    identity["engine.py"] = _sha(_read(Path(engine.__file__), 1024 * 1024))
    return identity


def _profile(profile_id):
    if profile_id not in PROFILE_IDS:
        raise ValueError("Choose a reviewed Survive profile")
    profile = _adapters()["prepare_v3"].load_profile(profile_id)
    raw = _read(LAB / "profiles" / (profile_id + ".json"), 128 * 1024)
    if _sha(raw) != profile["file_sha256"]:
        raise ValueError("Profile changed while opening the recording")
    policy = _read(TELEMETRY / "survive-policy.json", 64 * 1024)
    return profile, raw, policy


def _analysis(raw, profile, policy_raw):
    adapter = _adapters()["prepare_v3"]
    rows = adapter.load_rows(raw, profile)
    derived = adapter.derive_rows(rows, profile)
    derived_raw = ("\n".join(json.dumps(row, allow_nan=False, separators=(",", ":")) for row in derived) + "\n").encode()
    result = engine.analyze(engine.parse_bytes(derived_raw, "survive.jsonl"), None, _json(policy_raw))
    if len(result["records"]) != len(derived):
        raise ValueError("Movement analysis returned inconsistent record counts")
    constraints = [dict(row, status=assessed["status"]) for row, assessed in zip(derived, result["records"])]
    summary = _adapters()["audit_v3"].summarize(rows, profile)
    counts = {name: sum(row["status"] == name for row in constraints) for name in ("Review", "Unknown", "No finding")}
    return {"constraints": constraints, "summary": summary, "result": result, "counts": counts}, derived_raw


class PrefixValidator:
    """Validate authentic rows incrementally; never add a synthetic run_end."""
    def __init__(self, profile, source_id):
        self.profile, self.source_id = profile, source_id
        self.previous = None
        self.sample_tick = None
        self.rows = 0
        self.terminal = False

    def accept(self, row):
        adapter = _adapters()["prepare_v3"]
        legacy = _adapters()["prepare_v2"]
        if not isinstance(row, dict) or set(row) != adapter.FIELDS or row.get("schema") != "survive-v3":
            raise ValueError("Unsupported v3 schema or fields")
        if self.terminal:
            raise ValueError("Records follow the terminal game event")
        if type(row["seq"]) is not int or row["seq"] != self.rows:
            raise ValueError("Missing, duplicated or reordered source sequence")
        if not isinstance(row["session_id"], str) or not GUID.fullmatch(row["session_id"]):
            raise ValueError("Invalid source session ID")
        if row["session_id"].lower() != self.source_id.lower():
            raise ValueError("Session ID differs from the selected source")
        if row["profile_id"] != self.profile["id"]:
            raise ValueError("Source profile differs from the selected policy")
        if not isinstance(row["event"], str) or row["event"] not in adapter.EVENTS:
            raise ValueError("Unsupported source event")
        if not isinstance(row["movement_mode"], str) or row["movement_mode"] not in {"walking", "dash", "blink", "other", "ended"}:
            raise ValueError("Unsupported movement mode")
        for key in ("detail", "related_id"):
            if not isinstance(row[key], str) or len(row[key]) > 80 or not row[key].isascii():
                raise ValueError("Invalid event context")
        for key in legacy.NUMERIC | adapter.EXTRA_NUMERIC:
            value = row[key]
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e10:
                raise ValueError("Invalid numeric source field")
        if not 0 <= row["elapsed_s"] <= 60.1 or not 0 <= row["delta_s"] <= 60 or not 0 <= row["monotonic_s"] <= 86400:
            raise ValueError("Source time exceeds capture bounds")
        if type(row["server_tick"]) is not int or not 0 <= row["server_tick"] <= 1e9:
            raise ValueError("Invalid server tick")
        if type(row["clearance_valid"]) is not bool or row["baseline_threat"] not in ("yes", "no", "unknown"):
            raise ValueError("Invalid threat availability")
        for key in ("path_radius_cm", "hit_radius_cm", "visual_radius_cm"):
            if abs(row[key] - self.profile["movement"][key]) > .01:
                raise ValueError("Source geometry differs from the selected profile")
        if self.previous:
            if row["event"] == "run_start":
                raise ValueError("A new game session cannot replace this recording")
            for key in ("elapsed_s", "monotonic_s", "server_tick"):
                if row[key] < self.previous[key]:
                    raise ValueError("Source clock moved backwards")
        elif row["event"] != "run_start":
            raise ValueError("Selected source does not begin with run_start")
        if row["event"] == "sample":
            if self.sample_tick is not None and row["server_tick"] <= self.sample_tick:
                raise ValueError("Sample ticks are not increasing")
            self.sample_tick = row["server_tick"]
        if row["event"] == "run_end":
            if row["detail"] not in {"completed", "restart", "disconnect", "capture_limit", "write_failure"}:
                raise ValueError("Unknown game completion reason")
            if row["detail"] == "completed" and row["elapsed_s"] < 59.9:
                raise ValueError("Completed game ended before 60 seconds")
            self.terminal = True
        self.rows += 1
        self.previous = row


class _Session:
    def __init__(self, manager, source_id, profile_id):
        self.manager = manager
        self.profile, self.profile_raw, self.policy_raw = _profile(profile_id)
        self.analysis_inputs = _analysis_identity()
        self.recording_id = uuid.uuid4().hex
        self.directory = manager.recording_root / self.recording_id
        _directory(manager.recording_root)
        self.directory.mkdir(exist_ok=False)
        _directory(self.directory)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.started = time.monotonic()
        self.finished = None
        self.finalized = False
        self.finalization_failed = False
        self.created_utc = _utc()
        self.source_id = None if source_id == "next" else source_id
        self.discovery = {s["source_id"].lower() for s in manager.sources()} if source_id == "next" else set()
        self.provenance = "new_source_from_byte_zero" if source_id == "next" else "selected_source_backfill_from_byte_zero"
        self.rows = []
        self.observed = b""
        self.pending = b""
        self.identity = None
        self.validator = None
        self.last_receive = self.started
        self.state = "waiting" if self.source_id is None else "recording"
        self.stop_reason = None
        self.error = None
        self.parse_errors = 0
        self.sequence_gaps = 0
        self.analysis = None
        self.analysis_state = "pending"
        self.source_completion = None
        self.receipts = []
        self.raw_stream = self.receipt_stream = None
        try:
            self.raw_stream = (self.directory / "source.jsonl").open("xb")
            self.receipt_stream = (self.directory / "receipts.jsonl").open("xb")
            for name, raw in (("profile.json", self.profile_raw), ("policy.json", self.policy_raw)):
                with (self.directory / name).open("xb") as output:
                    output.write(raw)
            with (self.directory / "started.json").open("xb") as output:
                output.write(_encoded({"schema": "survive-recording-start-v1", "recording_id": self.recording_id,
                                       "created_utc": self.created_utc, "profile_id": profile_id, "provenance": self.provenance}))
            self.thread = threading.Thread(target=self._run, name="survive-recorder-" + self.recording_id[:8], daemon=True)
            self.thread.start()
        except Exception:
            for stream in (self.raw_stream, self.receipt_stream):
                if stream is not None:
                    stream.close()
            # The exclusive folder is retained without a final manifest.
            raise

    def _source(self):
        if self.source_id is None:
            fresh = [s for s in self.manager.sources() if s["source_id"].lower() not in self.discovery]
            if not fresh:
                return None
            if len(fresh) != 1:
                raise ValueError("More than one new source appeared; select the intended session explicitly")
            self.source_id = fresh[0]["source_id"]
            self.state = "recording"
        return self.manager._source_path(self.source_id)

    def _consume(self):
        try:
            source = self._source()
            if source is None:
                return
            info = _regular(source)
            identity = (info.st_dev, info.st_ino)
            if self.identity is not None and identity != self.identity:
                raise ValueError("Selected source was replaced")
            self.identity = identity
            value = _read(source, self.manager.max_bytes)
        except (PermissionError, BlockingIOError) as exc:
            raise _TransientSourceRead() from exc
        if not value.startswith(self.observed):
            raise ValueError("Selected source was truncated or rewritten")
        delta = value[len(self.observed):]
        if not delta:
            return
        receipt = {"offset_start": len(self.observed), "offset_end": len(value),
                   "received_elapsed_s": time.monotonic() - self.started, "received_utc": _utc()}
        self.raw_stream.write(delta)
        self.raw_stream.flush()
        os.fsync(self.raw_stream.fileno())
        self.receipt_stream.write(_encoded(receipt))
        self.receipt_stream.flush()
        self.receipts.append(receipt)
        self.observed = value
        self.pending += delta
        self.last_receive = time.monotonic()
        if self.validator is None:
            self.validator = PrefixValidator(self.profile, self.source_id)
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            if not line or len(line) > MAX_LINE or len(self.rows) >= self.manager.max_rows:
                raise ValueError("Empty, oversized or excessive source records")
            row = _json(line)
            if isinstance(row, dict) and type(row.get("seq")) is int and row["seq"] > len(self.rows):
                self.sequence_gaps += row["seq"] - len(self.rows)
            self.validator.accept(row)
            self.rows.append(row)
        if len(self.pending) > MAX_LINE:
            raise ValueError("Unterminated source record exceeds its line limit")
        if self.validator.terminal:
            if self.pending:
                raise ValueError("Bytes follow the terminal game event")
            self.source_completion = self.rows[-1]["detail"]
            if _analysis_identity() != self.analysis_inputs:
                raise ValueError("Analysis code changed during recording")
            self.analysis, derived = _analysis(self.observed, self.profile, self.policy_raw)
            with (self.directory / "surge.jsonl").open("xb") as output:
                output.write(derived)
            with (self.directory / "analysis.json").open("xb") as output:
                output.write(_encoded(self.analysis))
            self.analysis_state = "complete"
            self.state = "complete"
            self.stop_reason = "source_run_end"

    def _run(self):
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    try:
                        self._consume()
                    except _TransientSourceRead:
                        # The game briefly owns the append handle on Windows.
                        pass
                    if self.state == "complete":
                        break
                    if time.monotonic() - self.started > self.manager.max_seconds:
                        self.state = "stopped"
                        self.stop_reason = "recording_time_limit"
                        break
                self.stop_event.wait(self.manager.poll_seconds)
            with self.lock:
                if self.state not in {"complete", "failed"}:
                    self.state = "stopped"
                    self.stop_reason = self.stop_reason or "operator_stop"
                    self.analysis_state = "unavailable"
        except Exception as exc:
            with self.lock:
                self.error = str(exc)[:300]
                self.parse_errors += isinstance(exc, ValueError)
                self.state = "failed"
                self.stop_reason = "source_or_recording_error"
                self.analysis_state = "unavailable"
        finally:
            with self.lock:
                self.finished = time.monotonic()
                failures = []
                for stream in (self.raw_stream, self.receipt_stream):
                    try:
                        stream.flush()
                        os.fsync(stream.fileno())
                    except Exception as exc:
                        failures.append(str(exc))
                    finally:
                        try:
                            stream.close()
                        except Exception as exc:
                            failures.append(str(exc))
                try:
                    # Preserve any prefix actually written before an I/O error,
                    # including unvalidated trailing bytes, without retrying it.
                    self.observed = _read(self.directory / "source.jsonl", self.manager.max_bytes)
                    if failures:
                        self.state = "failed"
                        self.error = "Recording flush failed: " + failures[0][:200]
                        self.analysis_state = "unavailable"
                        self.analysis = None
                    self._save_manifest()
                    self.finalized = True
                except Exception as exc:
                    self.finalization_failed = True
                    self.state = "failed"
                    self.error = "Recording finalization failed: " + str(exc)[:200]
                    self.analysis_state = "unavailable"

    def _capture(self, *, for_manifest=False):
        finalizing = self.state in {"complete", "stopped", "failed"} and not (self.finalized or self.finalization_failed or for_manifest)
        return {"recording_id": self.recording_id, "state": "recording" if finalizing else self.state,
                "source_id": self.source_id, "session_id": self.rows[0]["session_id"] if self.rows else None,
                "profile_id": self.profile["id"], "profile_sha256": _sha(self.profile_raw),
                "source_sha256": _sha(self.observed), "records": len(self.rows), "bytes": len(self.observed),
                "elapsed_s": max(0., (self.finished or time.monotonic()) - self.started),
                "source_elapsed_s": self.rows[-1]["elapsed_s"] if self.rows else None,
                "completion": self.source_completion, "stop_reason": self.stop_reason,
                "analysis_state": "pending" if finalizing else self.analysis_state, "created_utc": self.created_utc,
                "finalizing": finalizing, "finalized": self.finalized or for_manifest,
                "provenance": self.provenance, "authenticity": "local_unsigned_not_attested",
                "health": {"sequence_gaps": self.sequence_gaps, "parse_errors": self.parse_errors,
                           "stale_s": max(0., (self.finished or time.monotonic()) - self.last_receive),
                           "pending_bytes": len(self.pending), "error": self.error}}

    def _save_manifest(self):
        names = ["source.jsonl", "receipts.jsonl", "profile.json", "policy.json", "started.json"]
        if self.analysis is not None:
            names += ["surge.jsonl", "analysis.json"]
        hashes = {name: _sha(_read(self.directory / name, 16 * 1024 * 1024)) for name in names}
        manifest = {"schema": "survive-recording-v1", "capture": self._capture(for_manifest=True), "files_sha256": hashes,
                    "analysis_inputs_sha256": self.analysis_inputs,
                    "limits": "Local unsigned exact-byte recording. Observer start/stop is separate from game lifecycle. Labels are external; no physical input authenticity is inferred."}
        temporary = self.directory / "manifest.pending"
        with temporary.open("xb") as output:
            output.write(_encoded(manifest))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.directory / "manifest.json")

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("Recorder did not finish within its stop deadline")


def _response(capture, rows, analysis, after=0):
    if type(after) is not int or not 0 <= after <= len(rows):
        raise ValueError("Invalid event cursor")
    analysis = analysis if capture["analysis_state"] == "complete" else None
    page = rows[after:after + 256]
    sample_keys = ("seq", "elapsed_s", "x_cm", "y_cm", "z_cm", "movement_mode", "server_tick", "delta_s", "monotonic_s")
    samples = [{key: row[key] for key in sample_keys} for row in rows if row["event"] == "sample"]
    events = [row for row in rows if row["event"] != "sample"]
    constraints = analysis["constraints"] if analysis else []
    view = {"samples": samples, "events": events, "constraints": constraints,
            "analysis": {"state": capture["analysis_state"], "counts": analysis["counts"] if analysis else None},
            "summary": analysis["summary"] if analysis else None,
            "metadata": {"schema": "survive-v3", "profile_id": capture["profile_id"],
                         "profile_sha256": capture["profile_sha256"], "session_id": capture["session_id"],
                         "source_clock": "game_elapsed_seconds", "input_observation": "server_commands_only",
                         "authenticity": "local_unsigned_not_attested", "display_truncated": False}}
    result = {"capture": capture, "records": page, "next_cursor": after + len(page), "view": view}
    # Retention on disk is complete. Only an oversized display projection is
    # reduced, with explicit counts; never use the reduced view for analysis.
    for key in ("events", "samples", "constraints"):
        while len(_encoded(result)) > MAX_RESPONSE and len(view[key]) > 128:
            view[key] = view[key][len(view[key]) // 2:]
            view["metadata"]["display_truncated"] = True
    if len(_encoded(result)) > MAX_RESPONSE:
        view["summary"] = None
        view["metadata"]["display_truncated"] = True
    if len(_encoded(result)) > MAX_RESPONSE:
        raise ValueError("Display response exceeds its byte limit")
    view["metadata"]["total_samples"] = len(samples)
    view["metadata"]["total_events"] = len(events)
    view["metadata"]["total_constraints"] = len(constraints)
    return copy.deepcopy(result)


class CaptureManager:
    def __init__(self, source_root=None, recording_root=None, *, poll_seconds=.2,
                 max_seconds=600., max_bytes=MAX_BYTES, max_rows=MAX_ROWS):
        source = Path(source_root) if source_root is not None else LAB / "Saved" / "Telemetry"
        recording = Path(recording_root) if recording_root is not None else LAB / "Saved" / "SurgeRecordings"
        self.source_root = _directory(source, create=True)
        self.recording_root = _directory(recording, create=True)
        if source_root is None and not self.source_root.is_relative_to(ROOT):
            raise ValueError("Owned source escaped the workspace")
        if recording_root is None and not self.recording_root.is_relative_to(ROOT):
            raise ValueError("Recording output escaped the workspace")
        if not .01 <= poll_seconds <= 5 or not 0 < max_seconds <= 600:
            raise ValueError("Invalid recorder timing limits")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES or type(max_rows) is not int or not 1 <= max_rows <= MAX_ROWS:
            raise ValueError("Invalid recorder size limits")
        self.poll_seconds, self.max_seconds = poll_seconds, max_seconds
        self.max_bytes, self.max_rows = max_bytes, max_rows
        self.active = None
        self._opened = None
        self._verified = {}
        self._verification_rejections = {}

    def _source_path(self, source_id):
        if not isinstance(source_id, str) or not GUID.fullmatch(source_id):
            raise ValueError("Choose a source from the owned session list")
        _directory(self.source_root)
        path = self.source_root / (source_id + ".jsonl")
        if path.parent.resolve() != self.source_root:
            raise ValueError("Source escaped the owned directory")
        _regular(path)
        return path

    def sources(self):
        _directory(self.source_root)
        result = []
        with os.scandir(self.source_root) as entries:
            for count, entry in enumerate(entries):
                if count >= MAX_ENTRIES:
                    raise ValueError("Too many source directory entries; archive old sessions first")
                path = Path(entry.path)
                if path.suffix.lower() != ".jsonl" or not GUID.fullmatch(path.stem):
                    continue
                try:
                    info = _regular(path)
                except (OSError, ValueError):
                    continue
                result.append({"source_id": path.stem, "filename": path.name, "bytes": info.st_size,
                               "modified_utc": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()})
        return sorted(result, key=lambda row: (row["modified_utc"], row["source_id"]), reverse=True)

    def start(self, source_id="next", profile_id="survive-lucian-practice-v1"):
        if self.active and self.active.thread.is_alive():
            raise ValueError("Stop the current Survive recording first")
        if source_id != "next":
            self._source_path(source_id)
        _directory(self.recording_root)
        self.active = _Session(self, source_id, profile_id)
        return self.status()

    def status(self, after=0):
        if self.active is None:
            return {"capture": None, "records": [], "next_cursor": 0, "view": None}
        with self.active.lock:
            return _response(self.active._capture(), self.active.rows, self.active.analysis, after)

    poll = status

    def stop(self):
        if self.active is None:
            raise ValueError("Start a Survive recording first")
        self.active.stop()
        return self.status()

    def close(self):
        if self.active:
            self.active.stop()

    def _unverified_entry(self, recording_id, reason):
        """Inventory failed attempts without opening redirected or unbounded data."""
        item = {"recording_id": recording_id, "created_utc": None, "state": "interrupted",
                "session_id": None, "profile_id": None, "records": None, "bytes": None,
                "completion": None, "analysis_state": "unavailable", "verified": False,
                "review_status": "Unknown", "inventory_error": str(reason)[:300]}
        directory = self.recording_root / recording_id
        try:
            _directory(directory)
            item["created_utc"] = datetime.fromtimestamp(directory.stat().st_mtime, timezone.utc).isoformat()
            try:
                item["bytes"] = _regular(directory / "source.jsonl").st_size
            except (ValueError, OSError):
                pass
            try:
                started = _json(_read(directory / "started.json", 8192))
                if (isinstance(started, dict) and started.get("schema") == "survive-recording-start-v1"
                        and started.get("recording_id") == recording_id):
                    if started.get("profile_id") in PROFILE_IDS:
                        item["profile_id"] = started["profile_id"]
                    if isinstance(started.get("created_utc"), str) and len(started["created_utc"]) <= 80:
                        item["created_utc"] = started["created_utc"]
            except (ValueError, OSError, TypeError):
                pass
        except (ValueError, OSError):
            item["state"] = "unreadable"
        item["retained_bytes"] = item["bytes"]
        return item

    def _unverified_error(self, recording_id, reason):
        item = self._unverified_entry(recording_id, reason)
        retained = str(item["bytes"]) if item["bytes"] is not None else "an unknown number of"
        return ValueError("Recording is Unknown: final manifest is missing or unreadable; " + retained
                          + " source bytes remain retained. Verified opening is unavailable. " + str(reason)[:160])

    def sessions(self):
        _directory(self.recording_root)
        result = []
        with os.scandir(self.recording_root) as entries:
            for count, entry in enumerate(entries):
                if count >= MAX_ENTRIES:
                    raise ValueError("Too many recording directory entries")
                if not RECORDING.fullmatch(entry.name):
                    continue
                directory = Path(entry.path)
                if self.active and self.active.recording_id == entry.name and self.active.thread.is_alive():
                    with self.active.lock:
                        active = self.active._capture()
                    if not active["finalized"]:
                        result.append(dict(active, verified=False, in_progress=True, review_status="Unknown"))
                        continue
                try:
                    _directory(directory)
                    manifest = _json(_read(directory / "manifest.json", 128 * 1024))
                    if not isinstance(manifest, dict) or manifest.get("schema") != "survive-recording-v1" or not isinstance(manifest.get("capture"), dict):
                        raise ValueError("Unsupported or corrupt recording manifest")
                    item = manifest["capture"]
                    if (item.get("recording_id") != entry.name or item.get("state") not in {"complete", "stopped", "failed"}
                            or not isinstance(item.get("created_utc"), str) or len(item["created_utc"]) > 80):
                        raise ValueError("Unsupported or corrupt recording metadata")
                    fields = ("recording_id", "created_utc", "state", "session_id", "profile_id", "records", "bytes", "completion", "analysis_state")
                    if any(not isinstance(item.get(key), (str, int, float, type(None))) for key in fields):
                        raise ValueError("Invalid recording metadata type")
                    result.append(dict({key: item.get(key) for key in fields}, verified=False))
                except (ValueError, OSError, TypeError) as exc:
                    result.append(self._unverified_entry(entry.name, exc))
        return sorted(result, key=lambda row: row.get("created_utc") or "", reverse=True)

    def open(self, recording_id):
        if not isinstance(recording_id, str) or not RECORDING.fullmatch(recording_id):
            raise ValueError("Invalid recording identifier")
        _directory(self.recording_root)
        directory = self.recording_root / recording_id
        if _directory(directory).parent != self.recording_root:
            raise ValueError("Recording escaped its directory")
        try:
            manifest_raw = _read(directory / "manifest.json", 128 * 1024)
            manifest = _json(manifest_raw)
            if (not isinstance(manifest, dict) or manifest.get("schema") != "survive-recording-v1"
                    or not isinstance(manifest.get("capture"), dict) or manifest["capture"].get("recording_id") != recording_id):
                raise ValueError("Unsupported recording manifest")
        except (ValueError, OSError) as exc:
            raise self._unverified_error(recording_id, exc) from exc
        expected_names = {"source.jsonl", "receipts.jsonl", "profile.json", "policy.json", "started.json"}
        capture = manifest["capture"]
        if capture.get("state") not in {"complete", "stopped", "failed"} or capture.get("analysis_state") not in {"complete", "unavailable"}:
            raise ValueError("Recording is not finalized")
        if capture.get("source_id") is not None and (not isinstance(capture["source_id"], str) or not GUID.fullmatch(capture["source_id"])):
            raise ValueError("Invalid saved source identifier")
        if capture.get("analysis_state") == "complete":
            expected_names |= {"surge.jsonl", "analysis.json"}
        if not isinstance(manifest.get("files_sha256"), dict) or set(manifest["files_sha256"]) != expected_names:
            raise ValueError("Unexpected recording files")
        files = {}
        for name, expected in manifest["files_sha256"].items():
            maximum = MAX_BYTES if name == "source.jsonl" else 16 * 1024 * 1024
            files[name] = _read(directory / name, maximum)
            if not isinstance(expected, str) or _sha(files[name]) != expected:
                raise ValueError("Recording bytes differ from the saved fingerprint")
        profile, profile_raw, policy_raw = _profile(capture.get("profile_id"))
        if files["profile.json"] != profile_raw or files["policy.json"] != policy_raw:
            raise ValueError("Saved profile or policy differs from reviewed local bytes")
        source_id = capture.get("source_id")
        rows = []
        raw = files["source.jsonl"]
        if type(capture.get("records")) is not int or not 0 <= capture["records"] <= MAX_ROWS:
            raise ValueError("Invalid saved record count")
        validator = PrefixValidator(profile, source_id) if source_id else None
        validation_error = None
        for line in raw.splitlines(keepends=True):
            if capture.get("state") == "failed" and len(rows) >= capture["records"]:
                break
            if not line.endswith(b"\n"):
                break
            try:
                if validator is None or len(line) > MAX_LINE + 1 or len(rows) >= MAX_ROWS:
                    raise ValueError("Invalid saved source prefix")
                row = _json(line)
                validator.accept(row)
                rows.append(row)
            except (ValueError, TypeError) as exc:
                validation_error = str(exc)
                break
        if len(rows) != capture.get("records") or _sha(raw) != capture.get("source_sha256") or len(raw) != capture.get("bytes"):
            raise ValueError("Saved recording totals differ from source bytes")
        if capture.get("profile_sha256") != _sha(profile_raw):
            raise ValueError("Saved profile fingerprint differs from reviewed bytes")
        if capture.get("session_id") != (rows[0]["session_id"] if rows else None):
            raise ValueError("Saved session identity differs from source records")
        if validation_error and capture.get("state") != "failed":
            raise ValueError("Invalid source was not marked failed")
        analysis = None
        if capture.get("analysis_state") == "complete":
            if capture.get("state") != "complete" or not rows or rows[-1]["event"] != "run_end" or capture.get("completion") != rows[-1]["detail"]:
                raise ValueError("Saved completion differs from source lifecycle")
            if manifest.get("analysis_inputs_sha256") != _analysis_identity():
                raise ValueError("Saved analysis uses a different adapter; versioned reanalysis is required")
            analysis, derived = _analysis(raw, profile, policy_raw)
            if files["surge.jsonl"] != derived or files["analysis.json"] != _encoded(analysis):
                raise ValueError("Saved analysis does not reproduce under the current adapter")
        elif validator and validator.terminal and capture.get("state") != "failed":
            raise ValueError("Completed source lacks a reproducible analysis")
        elif capture.get("completion") is not None and capture.get("state") != "failed":
            raise ValueError("Partial recording claims game completion")
        capture = dict(capture, reopened=True)
        self._opened = {"recording_id": recording_id, "rows": rows,
                        "hashes": dict(manifest["files_sha256"], **{"manifest.json": _sha(manifest_raw)})}
        self._remember_verified(capture, analysis, self._opened["hashes"])
        return _response(capture, rows, analysis)

    review = open

    def _remember_verified(self, capture, analysis, hashes):
        if len(self._verified) >= MAX_ENTRIES:
            self._verified.pop(next(iter(self._verified)))
        recording_id = capture["recording_id"]
        self._verified[recording_id] = {
            "hashes": dict(hashes), "analysis_identity": _analysis_identity(),
            "summary": {"capture": copy.deepcopy(capture), "view": {
                "analysis": {"state": capture["analysis_state"], "counts": copy.deepcopy(analysis["counts"]) if analysis else None},
                "summary": {"run_quality": copy.deepcopy(analysis["summary"].get("run_quality")) if analysis else None}}}}
        self._verification_rejections.pop(recording_id, None)

    def _verification_stamp(self, recording_id):
        # Rejected evidence stays Unknown while unchanged. This cheap stamp is
        # only an invalidation hint for rejection, never evidence verification.
        directory = self.recording_root / recording_id
        _directory(directory)
        result = []
        for name in ("manifest.json", "source.jsonl", "receipts.jsonl", "started.json", "profile.json", "policy.json", "surge.jsonl", "analysis.json"):
            try:
                info = _regular(directory / name)
                result.append((name, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns))
            except FileNotFoundError:
                result.append((name, None))
        return result

    def _verify_files(self, recording_id, hashes, message):
        """Recheck retained bytes before serving either cached summary or raw row."""
        directory = self.recording_root / recording_id
        _directory(directory)
        for name, expected in hashes.items():
            maximum = MAX_BYTES if name == "source.jsonl" else 16 * 1024 * 1024
            if _sha(_read(directory / name, maximum)) != expected:
                raise ValueError(message)

    def _check_verified(self, recording_id, cached, identity):
        if cached["analysis_identity"] != identity:
            raise ValueError("Analysis code changed since verification; versioned reanalysis is required")
        self._verify_files(recording_id, cached["hashes"], "Recording changed since verification")
        _, profile_raw, policy_raw = _profile(cached["summary"]["capture"]["profile_id"])
        if _sha(profile_raw) != cached["hashes"]["profile.json"] or _sha(policy_raw) != cached["hashes"]["policy.json"]:
            raise ValueError("Reviewed profile or policy changed since verification")

    def verified_summaries(self, max_new=4):
        """Verify a bounded batch; retain only thin report data in this cache."""
        if type(max_new) is not int or not 0 <= max_new <= 4:
            raise ValueError("Verification batch must contain zero to four recordings")
        sessions = self.sessions()
        present = {item["recording_id"] for item in sessions}
        self._verified = {key: value for key, value in self._verified.items() if key in present}
        self._verification_rejections = {key: value for key, value in self._verification_rejections.items() if key in present}
        identity = _analysis_identity()
        result = {"recordings": [], "rejected": [], "pending": []}
        attempted = 0
        for session in sessions:
            recording_id = session["recording_id"]
            if session.get("in_progress"):
                result["pending"].append(recording_id)
                continue
            error, stamp = session.get("inventory_error"), None
            try:
                if error:
                    raise ValueError("Recording is Unknown: " + error)
                stamp = self._verification_stamp(recording_id)
                rejected = self._verification_rejections.get(recording_id)
                if rejected and rejected["stamp"] == stamp and rejected["identity"] == identity:
                    raise ValueError(rejected["error"])
                cached = self._verified.get(recording_id)
                if cached is not None:
                    self._check_verified(recording_id, cached, identity)
                else:
                    if attempted >= max_new:
                        result["pending"].append(recording_id)
                        continue
                    attempted += 1
                    # Report verification must not change the saved raw-row
                    # inspector selection or any active observer.
                    selected = self._opened
                    try:
                        self.open(recording_id)
                    finally:
                        self._opened = selected
                    cached = self._verified[recording_id]
                result["recordings"].append(copy.deepcopy(cached["summary"]))
            except (ValueError, OSError, TypeError, KeyError) as exc:
                self._verified.pop(recording_id, None)
                error = str(exc)[:300]
                if stamp is not None:
                    self._verification_rejections[recording_id] = {"stamp": stamp, "identity": identity, "error": error}
                result["rejected"].append({"recording_id": recording_id, "error": error, "bytes": session.get("bytes")})
        return result

    def record(self, recording_id, seq):
        """Return one exact source row, never a display projection."""
        if not isinstance(recording_id, str) or not RECORDING.fullmatch(recording_id):
            raise ValueError("Invalid recording identifier")
        if type(seq) is not int or not 0 <= seq < MAX_ROWS:
            raise ValueError("Invalid source sequence")
        if self.active and self.active.recording_id == recording_id:
            with self.active.lock:
                if seq >= len(self.active.rows):
                    raise ValueError("Source sequence is not available")
                return {"recording_id": recording_id, "seq": seq, "record": copy.deepcopy(self.active.rows[seq])}
        if self._opened is None or self._opened["recording_id"] != recording_id:
            self.open(recording_id)
        # A pinned saved view cannot silently outlive changes to its source or
        # analysis. Recheck bytes before serving a cached raw row; no reanalysis
        # or full response is needed for ordinary selection changes.
        self._verify_files(recording_id, self._opened["hashes"], "Recording changed since it was opened")
        if seq >= len(self._opened["rows"]):
            raise ValueError("Source sequence is not available")
        return {"recording_id": recording_id, "seq": seq, "record": copy.deepcopy(self._opened["rows"][seq])}

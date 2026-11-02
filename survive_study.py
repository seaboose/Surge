"""Owned Survive trial launcher and external study labels; never detector input.

All production paths/executables are fixed locally. Renderer-facing callers pass
bounded choices and opaque IDs. Test roots/process factories are constructor-only.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

from survive_runtime import RuntimeLayout, safe_path, file_hash

ROOT = Path(__file__).resolve().parent
MODES = {"human", "scripted", "mixed", "speed_probe"}
PHASES = {"practice", "development", "held-out"}
PROFILES = {"survive-lucian-practice-v1", "survive-lucian-reference-v1"}
DEVELOPMENT_SEEDS = [1337, 2027, 4242]
HELD_OUT_SEEDS = [9001, 9007, 9011]
MAX_TRIALS = 256
MAX_LOG_BYTES = 16 * 1024 * 1024
MIXED_WINDOWS = [[15, 20], [35, 40]]


def utc():
    return datetime.now(timezone.utc).isoformat()


def validate_game_window(value):
    """Validate numeric presentation supplied by the trusted desktop bootstrap."""
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {"x", "y", "width", "height"}
            or any(type(item) is not int for item in value.values())
            or abs(value["x"]) > 100000 or abs(value["y"]) > 100000
            or not 320 <= value["width"] <= 16384 or not 180 <= value["height"] <= 16384):
        raise ValueError("Invalid trusted game window coordinates.")
    return dict(value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", value):
        raise ValueError("Expected an opaque 32-character trial/recording identifier.")
    return value.lower()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path, limit=256 * 1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Study record is missing, linked or oversized.")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite study JSON.")))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate study JSON field.")
        result[key] = value
    return result


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()


def _stop_owned_process(process):
    """Stop the retained Popen handle; never locate another game process."""
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class StudyManager:
    def __init__(self, root=None, engine_root=None, *, popen_factory=None, max_duration=180., monitor=True, headless=False, runtime=None, game_window=None):
        self.runtime = runtime or RuntimeLayout(root=root or ROOT)
        self.root, self.lab = self.runtime.root, self.runtime.lab
        self.directory = self.runtime.data_path("StudyTrials")
        self.actions = self.runtime.data_path("StudyActions")
        self.engine_root = Path(engine_root or "C:/Program Files/Epic Games/UE_5.8").resolve()
        self._popen = popen_factory or subprocess.Popen
        if type(max_duration) not in (int, float) or not 1 <= max_duration <= 300:
            raise ValueError("Trial wall-time bound must be 1–300 seconds.")
        self.max_duration = float(max_duration)
        self.monitor = monitor
        if type(headless) is not bool:
            raise ValueError("Headless verification must be explicitly boolean.")
        self.headless = headless
        self.game_window = validate_game_window(game_window)
        self._lock = threading.RLock()
        self._process = None
        self._trial_id = None

    def _safe(self, path, base=None):
        base = base or (self.runtime.saved if path.absolute().is_relative_to(self.runtime.saved) else self.root)
        return safe_path(path, base)

    def _prepare(self):
        for path in (self.directory, self.actions):
            self._safe(path)
            path.mkdir(parents=True, exist_ok=True)
            self._safe(path)

    def _trial_path(self, trial_id):
        return self._safe(self.directory / identifier(trial_id))

    def _manifest(self, trial_id):
        trial_id = identifier(trial_id)
        value = read_json(self._trial_path(trial_id) / "trial.json")
        if not isinstance(value, dict) or value.get("schema") != "survive-study-trial-v1" or value.get("trial_id") != trial_id:
            raise ValueError("Invalid study manifest.")
        self._validate(value["mode"], value["seed"], value["profile_id"], value["phase"], value["participant"])
        return value

    @staticmethod
    def _validate(mode, seed, profile_id, phase, participant):
        if not all(isinstance(value, str) for value in (mode, profile_id, phase)) or mode not in MODES or profile_id not in PROFILES or phase not in PHASES:
            raise ValueError("Choose a supported study mode, profile and phase.")
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise ValueError("Seed must be a nonnegative 32-bit integer.")
        if not isinstance(participant, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", participant):
            raise ValueError("Use a short participant alias with letters, numbers, _ or -.")

    def _fingerprint(self, game_identity=None):
        if self.runtime.packaged:
            result = dict((game_identity or self.runtime.verify_game())["files_sha256"])
            result.update(self.runtime.verify_assets())
            for name in ("engine.py", "survive_capture.py", "survive_study.py", "survive_runtime.py"):
                result[name] = file_hash(self._safe(self.root / name), 1024 * 1024)
            return result
        files = [self.root / name for name in ("engine.py", "survive_capture.py", "survive_study.py")]
        files += sorted((self.lab / "Source").rglob("*.cpp")) + sorted((self.lab / "Source").rglob("*.h"))
        files += sorted((self.lab / "Config").glob("*.ini"))
        files += [self.lab / "SurgeMovementLab.uproject", self.lab / "Binaries/Win64/UnrealEditor-SurgeMovementLab.dll"]
        files += [self.lab / "profiles" / (profile + ".json") for profile in sorted(PROFILES)]
        files += [self.lab / "telemetry" / name for name in
                  ("prepare.py", "prepare_v2.py", "prepare_v3.py", "audit_v3.py", "analyze_v3.py", "survive-policy.json")]
        hashes = {}
        if len(files) > 512:
            raise ValueError("Too many study freeze inputs.")
        for path in files:
            self._safe(path)
            if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Build and analysis inputs must exist before freezing the study.")
            hashes[path.relative_to(self.root).as_posix()] = digest(path.read_bytes())
        return hashes

    def freeze(self):
        with self._lock:
            self._prepare()
            if self._process is not None and self._process.poll() is None:
                raise ValueError("Finish the active trial before freezing a study.")
            path = self.directory / "freeze.json"
            current = self._fingerprint()
            if path.exists():
                value = read_json(path, limit=4 * 1024 * 1024)
                if value.get("files_sha256") != current:
                    raise ValueError("The frozen study differs from current inputs. Preserve it and use a separately reviewed study root.")
            else:
                value = {"schema": "survive-study-freeze-v1", "created_utc": utc(),
                         "development_seeds": DEVELOPMENT_SEEDS, "held_out_seeds": HELD_OUT_SEEDS,
                         "files_sha256": current,
                         "scope": "Mechanical detection study. Labels remain external; human input and data authenticity are not attested."}
                write_new(path, value)
            return {"freeze": {"created_utc": value["created_utc"], "sha256": digest(path.read_bytes()),
                               "held_out_seeds": HELD_OUT_SEEDS, "inputs": len(current)}}

    def start(self, mode, seed, profile_id, participant="player", phase="development", exit_after_round=True):
        self._validate(mode, seed, profile_id, phase, participant)
        if self.headless and (mode == "human" or phase != "practice"):
            raise ValueError("Headless verification is restricted to non-human practice trials.")
        if type(exit_after_round) is not bool or not exit_after_round:
            raise ValueError("Study trials must end after one round; start another trial for repetition.")
        with self._lock:
            self._prepare()
            if self._process is not None and self._process.poll() is None:
                raise ValueError("An owned Survive trial is still running.")
            if len(list(self.directory.glob("*/trial.json"))) >= MAX_TRIALS:
                raise ValueError("This study reached its 256-trial bound. Preserve it before starting a new study.")
            game_identity = None
            if phase == "held-out":
                frozen = read_json(self.directory / "freeze.json", limit=4 * 1024 * 1024)
                if self.runtime.packaged:
                    game_identity = self.runtime.verify_game()
                if frozen.get("schema") != "survive-study-freeze-v1" or frozen.get("files_sha256") != self._fingerprint(game_identity):
                    raise ValueError("Freeze the current build/profile/analysis before held-out trials; frozen inputs cannot drift.")
                if seed not in HELD_OUT_SEEDS:
                    raise ValueError("Choose a reserved held-out seed: 9001, 9007 or 9011.")
            elif seed in HELD_OUT_SEEDS:
                raise ValueError("This seed is reserved for held-out collection.")
            profile_path = self._safe(self.lab / "profiles" / (profile_id + ".json"))
            if not profile_path.is_file() or profile_path.stat().st_size > 128 * 1024:
                raise ValueError("Owned profile is missing or exceeds its reviewed size bound.")
            if self.runtime.packaged:
                self.runtime.verify_assets()
                # Held-out launch already verified the same files for its freeze.
                # Reuse only within this call; every new trial verifies again.
                game_identity = game_identity or self.runtime.verify_game()
                executable = module = game_identity["executable"]
                launch_prefix = [str(executable)]
                cwd = executable.parent
                self.runtime.data_path("Unreal").mkdir(parents=True, exist_ok=True)
                self._safe(self.runtime.data_path("Unreal"), self.runtime.saved)
            else:
                executable = self.engine_root / "Engine/Binaries/Win64" / ("UnrealEditor-Cmd.exe" if self.headless else "UnrealEditor.exe")
                if not executable.is_file() or executable.is_symlink():
                    raise ValueError("The fixed Unreal 5.8 executable is unavailable.")
                project = self._safe(self.lab / "SurgeMovementLab.uproject")
                module = self._safe(self.lab / "Binaries/Win64/UnrealEditor-SurgeMovementLab.dll")
                if not project.is_file() or not module.is_file():
                    raise ValueError("Build the owned Survive project before starting a trial.")
                if project.stat().st_size > 1024 * 1024 or module.stat().st_size > 32 * 1024 * 1024:
                    raise ValueError("Owned project/module exceeds its reviewed size bound.")
                launch_prefix = [str(executable), str(project)]
                cwd = self.lab
            trial_id = uuid.uuid4().hex
            folder = self._trial_path(trial_id)
            folder.mkdir(exist_ok=False)
            command = launch_prefix + ["/Engine/Maps/Entry?game=/Script/SurgeMovementLab.LabGameMode",
                       "-game", "-nosplash", "-NoEpicPortal", "-NoLiveCoding",
                       "-SurviveStudyMode=" + mode, "-SurviveStudyTrial=" + trial_id,
                       "-SurviveStudyExitAfterRound", "-SurviveSeed=" + str(seed),
                       "-abslog=" + str(folder / "engine.log"), "-ExecCmds=t.MaxFPS 60"]
            if self.runtime.packaged:
                command += ["-SurviveSavedDir=" + str(self.runtime.saved),
                            "-UserDir=" + str(self.runtime.data_path("Unreal")), "-nocrashreports"]
            if self.headless:
                command += ["-NullRHI", "-unattended", "-NoShaderCompile", "-nosound", "-nocrashreports"]
            else:
                window = self.game_window or {"width": 1280, "height": 720}
                command += ["-windowed", f"-ResX={window['width']}", f"-ResY={window['height']}"]
                if self.game_window is not None:
                    command += [f"-WinX={window['x']}", f"-WinY={window['y']}"]
            if profile_id == "survive-lucian-reference-v1":
                command.append("-SurviveReferenceCooldowns")
            if mode == "speed_probe":
                command += ["-SurviveSmoke", "-SurviveSpeedProbe"]
            manifest = {"schema": "survive-study-trial-v1", "trial_id": trial_id, "created_utc": utc(),
                        "mode": mode, "seed": seed, "profile_id": profile_id, "phase": phase, "participant": participant,
                        "round_seconds": 60, "wall_time_limit_seconds": self.max_duration,
                        "mixed_script_windows_s": MIXED_WINDOWS if mode == "mixed" else [],
                        "expected_mechanical_violation": "unknown", "label_source": "operator_asserted_workflow",
                        "execution_context": "headless_scripted_verification" if self.headless else "rendered_desktop",
                        "manual_input_available": not self.headless,
                        "physical_input_verified": False, "detector_labels_used": False,
                        "study_actions": "StudyActions/" + trial_id + ".jsonl",
                        "module_sha256": file_hash(module),
                        "profile_sha256": digest(profile_path.read_bytes()),
                        "command": command,
                        "limits": ["Mode is external study context, not detector evidence or proof of physical human input.",
                                   "Mixed means scripted windows plus available manual control; idle manual windows remain idle.",
                                   "Legal scripted actions can satisfy every mechanical rule; No finding does not demonstrate automation detection."]}
            manifest["runtime_kind"] = "standalone" if self.runtime.packaged else "editor"
            if game_identity:
                manifest["game_manifest_sha256"] = game_identity["manifest_sha256"]
                manifest["game_configuration"] = game_identity["configuration"]
                manifest["engine_version"] = game_identity["engine_version"]
            write_new(folder / "trial.json", manifest)
            try:
                process = self._popen(command, cwd=str(cwd), shell=False, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            except Exception as exc:
                write_new(folder / "process-result.json", {"state": "launch_failed", "finished_utc": utc(), "error": type(exc).__name__})
                raise ValueError("The owned game could not start; its failed trial manifest was preserved.") from exc
            self._process, self._trial_id = process, trial_id
            try:
                write_new(folder / "process-start.json", {"pid": process.pid, "started_utc": utc(), "owner": "this_study_manager"})
            except OSError as exc:
                if process.poll() is None:
                    _stop_owned_process(process)
                self._process, self._trial_id = None, None
                raise ValueError("The trial start receipt could not be saved; the owned process was stopped.") from exc
            if self.monitor:
                threading.Thread(target=self._monitor, args=(trial_id, process), daemon=True, name="SurviveStudyBound").start()
            return {"trial": self._public(manifest)}

    def _monitor(self, trial_id, process):
        started = time.monotonic()
        folder = self._trial_path(trial_id)
        state = "exited"
        while process.poll() is None:
            log = folder / "engine.log"
            if time.monotonic() - started > self.max_duration:
                state = "wall_time_limit"
                break
            if log.exists() and log.stat().st_size > MAX_LOG_BYTES:
                state = "log_byte_limit"
                break
            time.sleep(.25)
        if process.poll() is None:
            _stop_owned_process(process)
        with self._lock:
            result_path = folder / "process-result.json"
            if not result_path.exists():
                write_new(result_path, {"state": state, "finished_utc": utc(), "exit_code": process.returncode,
                                        "owned_process_only": True})

    def bind_recording(self, trial_id, recording_id):
        with self._lock:
            self._manifest(trial_id)
            value = {"schema": "survive-study-binding-v1", "trial_id": identifier(trial_id),
                     "recording_id": identifier(recording_id), "created_utc": utc()}
            write_new(self._trial_path(trial_id) / "recording.json", value)
            return {"trial": self._public(self._manifest(trial_id))}

    def _public(self, manifest):
        trial_id = manifest["trial_id"]
        folder = self._trial_path(trial_id)
        public = {key: manifest[key] for key in
                  ("trial_id", "created_utc", "mode", "seed", "profile_id", "phase", "participant",
                   "round_seconds", "mixed_script_windows_s", "physical_input_verified", "limits", "profile_sha256", "module_sha256")}
        # Preserve early study manifests without inventing an execution context.
        public["execution_context"] = manifest.get("execution_context", "unknown_legacy")
        public["manual_input_available"] = manifest.get("manual_input_available")
        binding = folder / "recording.json"
        public["recording_id"] = identifier(read_json(binding)["recording_id"]) if binding.exists() else None
        result = folder / "process-result.json"
        public["process_state"] = (read_json(result)["state"] if result.exists() else
                                   "running" if self._trial_id == trial_id and self._process is not None and self._process.poll() is None
                                   else "not_observed")
        public["adjudication"] = self._label(trial_id)
        return public

    def status(self):
        with self._lock:
            return {"trial": self._public(self._manifest(self._trial_id)) if self._trial_id else None}

    def close(self):
        """Stop only the process launched by this manager when its owner closes."""
        with self._lock:
            process, trial_id = self._process, self._trial_id
            if process is None or process.poll() is not None:
                return
            _stop_owned_process(process)
            result_path = self._trial_path(trial_id) / "process-result.json"
            if not result_path.exists():
                write_new(result_path, {"state": "owner_closed", "finished_utc": utc(), "exit_code": process.returncode,
                                        "owned_process_only": True})

    def trials(self):
        with self._lock:
            self._prepare()
            paths = sorted(self.directory.glob("*/trial.json"), reverse=True)
            if len(paths) > MAX_TRIALS:
                raise ValueError("Study trial inventory exceeds its bound.")
            return sorted([self._public(self._manifest(path.parent.name)) for path in paths], key=lambda row: row["created_utc"], reverse=True)

    def adjudicate(self, trial_id, expected_mechanical_violation, note=""):
        if not isinstance(expected_mechanical_violation, str) or expected_mechanical_violation not in {"yes", "no", "unknown"} or not isinstance(note, str) or len(note) > 500:
            raise ValueError("Choose yes/no/unknown and a note of at most 500 characters.")
        if any(ord(c) < 32 and c not in "\n\t" for c in note):
            raise ValueError("The assessment note contains control characters.")
        with self._lock:
            manifest = self._manifest(trial_id)
            directory = self._safe(self._trial_path(trial_id) / "adjudications")
            directory.mkdir(exist_ok=True)
            if len(list(directory.glob("*.json"))) >= 64:
                raise ValueError("This trial reached its 64-assessment history limit.")
            value = {"schema": "survive-study-adjudication-v1", "trial_id": identifier(trial_id),
                     "created_utc": utc(), "expected_mechanical_violation": expected_mechanical_violation,
                     "note": note, "source": "operator_asserted", "detector_input": False}
            name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + uuid.uuid4().hex[:8] + ".json"
            write_new(directory / name, value)
            return {"trial": self._public(manifest)}

    def _label(self, trial_id):
        folder = self._safe(self._trial_path(trial_id) / "adjudications")
        paths = sorted(folder.glob("*.json")) if folder.exists() else []
        if len(paths) > 64:
            raise ValueError("Too many assessment revisions.")
        if not paths:
            return {"expected_mechanical_violation": "unknown", "source": "not_labeled", "note": ""}
        label = read_json(self._safe(paths[-1]))
        if label.get("schema") != "survive-study-adjudication-v1" or label.get("trial_id") != identifier(trial_id) or label.get("expected_mechanical_violation") not in {"yes", "no", "unknown"}:
            raise ValueError("Invalid independent assessment record.")
        return {key: label[key] for key in ("expected_mechanical_violation", "source", "note", "created_utc")}

    def _association(self, trial, capture):
        """Bind a workflow label to recorded runtime identity, never by filename timing alone."""
        path = self._safe(self.actions / (trial["trial_id"] + ".jsonl"))
        try:
            if not path.is_file() or path.stat().st_size > 256 * 1024:
                return {"state": "unverified", "reason": "runtime action journal unavailable or oversized"}
            raw = path.read_bytes()
            if not raw or not raw.endswith(b"\n"):
                return {"state": "unverified", "reason": "runtime journal incomplete"}
            lines = raw.decode("utf-8").splitlines()
            if len(lines) > 1000:
                raise ValueError("runtime journal exceeds row bound")
            fields = {"schema", "trial_id", "session_id", "mode", "event", "elapsed_s", "window", "action", "source_kind"}
            events = {"session_start", "session_end", "session_changed", "process_or_world_end", "window_start", "window_end",
                      "action_requested", "smoke_action_requested", "speed_probe_begin", "speed_probe_end"}
            rows = []
            active_window = -1
            for line in lines:
                if len(line) > 2048:
                    raise ValueError("oversized runtime journal row")
                row = json.loads(line, object_pairs_hook=unique_object)
                if (not isinstance(row, dict) or set(row) != fields or row["schema"] != "survive-study-actions-v1" or
                        identifier(row["trial_id"]) != trial["trial_id"] or row["mode"] != trial["mode"] or
                        row["event"] not in events or row["source_kind"] != "owned-engine-study-driver" or
                        identifier(row["session_id"]) != identifier(capture.get("session_id")) or
                        type(row["elapsed_s"]) not in (int, float) or not math.isfinite(row["elapsed_s"]) or not 0 <= row["elapsed_s"] <= 65 or
                        type(row["window"]) not in (int, float) or row["window"] not in {-1, 0, 1} or
                        type(row["action"]) not in (int, float) or row["action"] not in {-1, 0, 1, 2, 3, 4, 5}):
                    raise ValueError("runtime journal identity or event mismatch")
                if rows and row["elapsed_s"] < rows[-1]["elapsed_s"]:
                    raise ValueError("runtime journal clock decreases")
                if rows and rows[-1]["event"] in {"session_end", "session_changed", "process_or_world_end"}:
                    raise ValueError("runtime journal continued after its terminal event")
                if row["event"] == "window_start":
                    if active_window >= 0 or trial["mode"] not in {"scripted", "mixed"} or row["window"] < 0:
                        raise ValueError("invalid automation window start")
                    active_window = int(row["window"])
                if row["event"] == "action_requested":
                    if trial["mode"] not in {"scripted", "mixed"} or active_window < 0 or row["window"] != active_window:
                        raise ValueError("automated action outside a recorded control window")
                    if trial["mode"] == "mixed":
                        lower, upper = MIXED_WINDOWS[active_window]
                        if not lower <= row["elapsed_s"] < upper:
                            raise ValueError("mixed action outside the declared script schedule")
                if row["event"] == "window_end":
                    if active_window != row["window"] or active_window < 0:
                        raise ValueError("automation window end without its start")
                    active_window = -1
                if row["event"] in {"smoke_action_requested", "speed_probe_begin", "speed_probe_end"} and trial["mode"] != "speed_probe":
                    raise ValueError("speed-probe action in another study mode")
                rows.append(row)
            if rows[0]["event"] != "session_start" or sum(r["event"] == "session_start" for r in rows) != 1:
                raise ValueError("runtime journal lacks one initial session identity")
            return {"state": "matched", "reason": None, "sha256": digest(raw), "records": len(rows),
                    "session_id": capture["session_id"], "runtime_end_observed": rows[-1]["event"] == "session_end",
                    "scripted_action_requests": sum(r["event"] in {"action_requested", "smoke_action_requested"} for r in rows)}
        except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
            return {"state": "unverified", "reason": str(exc)}

    def report(self, recordings):
        if not isinstance(recordings, list) or len(recordings) > MAX_TRIALS:
            raise ValueError("Provide at most 256 verified recording summaries.")
        by_id = {}
        for recording in recordings:
            if not isinstance(recording, dict) or not isinstance(recording.get("capture"), dict):
                raise ValueError("Expected verified recording summaries.")
            capture = recording["capture"]
            recording_id = identifier(capture.get("recording_id"))
            if recording_id in by_id:
                raise ValueError("A recording cannot count twice in a study report.")
            by_id[recording_id] = recording
        trial_inventory = self.trials()
        session_uses = {}
        for trial in trial_inventory:
            session_id = by_id.get(trial["recording_id"], {}).get("capture", {}).get("session_id")
            if isinstance(session_id, str) and re.fullmatch(r"[0-9a-fA-F]{32}", session_id):
                session_id = session_id.lower()
                session_uses[session_id] = session_uses.get(session_id, 0) + 1
        groups, trials = {}, []
        confusion = dict(true_positive=0, false_positive=0, true_negative=0, false_negative=0, excluded_trials=0)
        seen_recordings = set()
        for trial in trial_inventory:
            rid = trial["recording_id"]
            if rid and rid in seen_recordings:
                raise ValueError("Multiple trials refer to the same recording; resolve association before reporting.")
            if rid:
                seen_recordings.add(rid)
            recording = by_id.get(rid, {})
            capture = recording.get("capture", {})
            analysis = (recording.get("view") or {}).get("analysis") or {}
            if not isinstance(analysis, dict):
                raise ValueError("Invalid verified analysis summary.")
            counts = analysis.get("counts") or {}
            if not isinstance(counts, dict):
                raise ValueError("Invalid verified constraint counts.")
            counts = {key: counts.get(key, 0) for key in ("Review", "Unknown", "No finding")}
            if any(type(v) is not int or not 0 <= v <= 10000 for v in counts.values()):
                raise ValueError("Invalid verified constraint counts.")
            association = self._association(trial, capture)
            if association["state"] == "matched" and session_uses.get(capture["session_id"].lower(), 0) > 1:
                association = dict(association, state="unverified", reason="one runtime session is associated with multiple trials")
            identity_matches = (capture.get("profile_id") == trial["profile_id"] and
                                capture.get("profile_sha256") == trial["profile_sha256"] and association["state"] == "matched")
            complete = capture.get("completion") == "completed" and analysis.get("state") == "complete" and identity_matches and association.get("runtime_end_observed")
            eligible = counts["Review"] + counts["No finding"]
            expected = trial["adjudication"]["expected_mechanical_violation"]
            prediction = counts["Review"] > 0
            included = (complete and eligible > 0 and expected in {"yes", "no"} and trial["phase"] != "practice" and
                        trial["execution_context"] == "rendered_desktop")
            if included:
                confusion[("true_positive" if prediction else "false_negative") if expected == "yes" else
                          ("false_positive" if prediction else "true_negative")] += 1
            else:
                confusion["excluded_trials"] += 1
            key = (trial["mode"], trial["participant"], trial["phase"], trial["profile_id"], trial["profile_sha256"], trial["module_sha256"], trial["execution_context"])
            group = groups.setdefault(key, dict(condition=key[0], participant=key[1], phase=key[2], profile_id=key[3],
                         profile_sha256=key[4], module_sha256=key[5], execution_context=key[6], unverified_sessions=0,
                         sessions=0, complete_sessions=0, review_sessions=0, unknown_sessions=0, records=0,
                         review_records=0, unknown_records=0, no_finding_records=0))
            group["sessions"] += 1
            group["complete_sessions"] += complete
            group["review_sessions"] += prediction and identity_matches
            group["unknown_sessions"] += not complete or counts["Unknown"] > 0
            group["unverified_sessions"] += not identity_matches
            if identity_matches:
                group["records"] += sum(counts.values())
                group["review_records"] += counts["Review"]
                group["unknown_records"] += counts["Unknown"]
                group["no_finding_records"] += counts["No finding"]
            trials.append(dict(trial_id=trial["trial_id"], recording_id=rid, condition=trial["mode"],
                               participant=trial["participant"], phase=trial["phase"], execution_context=trial["execution_context"], complete=complete,
                               counts=counts, mechanical_review=prediction if eligible and identity_matches else None,
                               source_association=association,
                               expected_mechanical_violation=expected, included_in_confusion=included,
                               exclusion_reason=None if included else "practice, unlabeled, incomplete, unavailable or no eligible intervals"))
        negatives = confusion["false_positive"] + confusion["true_negative"]
        positives = confusion["true_positive"] + confusion["false_negative"]
        confusion["false_positive_rate"] = confusion["false_positive"] / negatives if negatives else None
        confusion["false_negative_rate"] = confusion["false_negative"] / positives if positives else None
        confusion["labeled_negative_sessions"] = negatives
        confusion["labeled_positive_sessions"] = positives
        return {"schema": "survive-study-report-v1", "created_utc": utc(), "groups": list(groups.values()),
                "trials": trials, "confusion": confusion,
                "unassociated_recordings": len(set(by_id) - seen_recordings),
                "duplicate_source_sessions": sum(uses > 1 for uses in session_uses.values()),
                "limits": ["Measures mechanical-rule review at session level, not scripting/cheating accuracy.",
                           "Expected labels are independent operator assertions, not proof of human input or integrity.",
                           "Practice, headless, duplicate, incomplete, unlabeled and unsupported sessions are excluded from confusion denominators.",
                           "Interval records are correlated; report counts of independent sessions separately.",
                           "Legal automation may produce No finding. Mixed manual windows may contain no human input.",
                           "Live pending results and recording corruption cannot become clean comparisons."]}

"""Bind retained unattended Survive smoke-run records to their exact capture.

Local hashes establish byte agreement, not authenticity or a rendered playtest.
This helper reads saved files only and never launches or interrogates a process.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re

from prepare import unique_object
from prepare_v2 import MAX_BYTES
from prepare_v3 import PROFILE_IDS, load_profile, load_rows

MAX_RECORD_BYTES = 128 * 1024
MAX_CONTEXT_BYTES = 256 * 1024
PROFILE = "survive-lucian-practice-v1"
SCHEMA = "survive-runtime-context-v1"
RECORDS = ("invocation.json", "result.json", "capture-evidence.json", "inputs-before.json", "inputs-after.json")
MODULE = "Binaries/Win64/UnrealEditor-SurgeMovementLab.dll"
MAP_ARGUMENT = "/Engine/Maps/Entry?game=/Script/SurgeMovementLab.LabGameMode"
FIELDS = {"schema", "session_id", "profile_id", "profile_sha256", "capture_sha256", "capture_bytes", "capture_rows",
          "capture_completion", "engine_version", "module_sha256", "executable_sha256", "runner_sha256",
          "project_descriptor_sha256", "source_config_sha256", "source_records_sha256", "inputs_unchanged",
          "driver", "mode", "rendering", "input_scheme", "map", "map_sha256", "build_sha256",
          "camera_and_viewport", "requested_max_fps", "measured_fps", "operator_actions_are_external", "authenticity", "limits"}
LIMITS = ["Retained local unsigned records; hashes establish byte agreement, not authenticity.",
          "NullRHI and automated handlers do not validate rendering, cursor projection, human input or League equivalence.",
          "The60FPS cap was requested; this context does not claim a measured frame rate.",
          "Module and source/config hashes do not establish a whole-build or map fingerprint."]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bounded(path, limit):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Oversized retained runtime record: " + Path(path).name)
    return raw


def _json(raw):
    # PowerShell records may contain a UTF-8 BOM. Preserve the exact original
    # bytes for hashing while decoding both permitted UTF-8 forms explicitly.
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON number")))


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("Invalid runtime SHA-256")
    return value.lower()


def _version(value):
    required = {"MajorVersion", "MinorVersion", "PatchVersion", "Changelist", "CompatibleChangelist",
                "IsLicenseeVersion", "IsPromotedBuild", "BranchName"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Unexpected recorded engine version fields")
    if any(type(value[key]) is not int or not 0 <= value[key] <= 1e10 for key in required - {"BranchName"}):
        raise ValueError("Invalid recorded engine version")
    if not isinstance(value["BranchName"], str) or not 1 <= len(value["BranchName"]) <= 128:
        raise ValueError("Invalid recorded engine branch")
    return value


def _input_manifest(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 256:
        raise ValueError("Expected bounded runtime input manifest")
    result = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("Invalid runtime input entry")
        path = item["path"]
        if not isinstance(path, str) or not 1 <= len(path) <= 256:
            raise ValueError("Invalid runtime input path")
        windows = PureWindowsPath(path)
        normalized = windows.as_posix()
        if windows.is_absolute() or windows.drive or ".." in windows.parts or normalized in result:
            raise ValueError("Runtime input paths must be unique and relative")
        if not (normalized.startswith(("Source/", "Config/")) or normalized in {MODULE, "SurgeMovementLab.uproject"}):
            raise ValueError("Unexpected runtime input path")
        result[normalized] = _hash(item["sha256"])
    if MODULE not in result or "SurgeMovementLab.uproject" not in result or not any(p.startswith("Source/") for p in result) or not any(p.startswith("Config/") for p in result):
        raise ValueError("Runtime input manifest lacks module/project/source/config records")
    return result


def create_context(verification_directory, *, profile_id=PROFILE):
    """Derive context solely from this smoke runner's saved records/snapshot."""
    # The caller selects reviewed limits before raw evidence is read. Incoming
    # profile_id fields never choose the policy or enable reference cooldowns.
    profile = load_profile(profile_id)
    directory = Path(verification_directory)
    record_bytes = {name: read_bounded(directory / name, MAX_RECORD_BYTES) for name in RECORDS}
    values = {name: _json(raw) for name, raw in record_bytes.items()}
    invocation, result, evidence = (values[name] for name in RECORDS[:3])
    if not all(isinstance(value, dict) for value in (invocation, result, evidence)):
        raise ValueError("Expected runtime record objects")
    mode = invocation.get("mode")
    if (mode not in {"Smoke", "SpeedProbe"} or result.get("mode") != mode or result.get("status") != "passed"
            or type(result.get("exit_code")) is not int or result["exit_code"] != 0 or result.get("timed_out") is not False
            or result.get("error") is not None or result.get("capture") != evidence):
        raise ValueError("Runtime records do not describe one successful smoke capture")
    if invocation.get("source_kind") != "unreal-smoke-driver" or evidence.get("source_kind") != "unreal-smoke-driver" or evidence.get("operator_actions_are_external") is not True:
        raise ValueError("Expected external-action Unreal smoke records")
    if "expected_profile_id" in invocation and invocation["expected_profile_id"] != profile["id"]:
        raise ValueError("Recorded expected profile differs from the caller's selected profile")
    args = invocation.get("arguments")
    if not isinstance(args, list) or not 1 <= len(args) <= 64 or any(not isinstance(arg, str) or len(arg) > 2048 for arg in args):
        raise ValueError("Invalid smoke invocation arguments")
    if not {MAP_ARGUMENT, "-NullRHI", "-game", "-SurviveSmoke", "-unattended", "-ExecCmds=t.MaxFPS 60"}.issubset(args):
        raise ValueError("Smoke invocation does not establish the expected map/driver/NullRHI/requested cap")
    reference = profile["id"] == "survive-lucian-reference-v1"
    if (("-SurviveSpeedProbe" in args) != (mode == "SpeedProbe")
            or args.count("-SurviveReferenceCooldowns") != int(reference)):
        raise ValueError("Smoke invocation mode/profile conflict")
    before = _input_manifest(values["inputs-before.json"])
    after = _input_manifest(values["inputs-after.json"])
    if before != after or before[MODULE] != _hash(invocation.get("module_sha256")):
        raise ValueError("Runtime inputs changed or module fingerprints disagree")
    raw = read_bounded(directory / "capture.jsonl", MAX_BYTES)
    rows = load_rows(raw, profile)
    seeds = [arg.split("=", 1)[1] for arg in args if arg.startswith("-SurviveSeed=")]
    if len(seeds) != 1 or not re.fullmatch(r"-?\d{1,10}", seeds[0]) or int(seeds[0]) != rows[0]["a"]:
        raise ValueError("Smoke invocation seed differs from capture")
    if (_hash(evidence.get("sha256")) != digest(raw) or evidence.get("bytes") != len(raw)
            or evidence.get("rows") != len(rows) or evidence.get("session_id") != rows[0]["session_id"]
            or evidence.get("events") != dict(Counter(row["event"] for row in rows))
            or evidence.get("terminal_reason") != rows[-1]["detail"] or evidence.get("elapsed_s") != rows[-1]["elapsed_s"]
            or rows[-1]["detail"] != "completed"):
        raise ValueError("Smoke evidence metadata differs from exact capture")
    context = {"schema": SCHEMA, "session_id": rows[0]["session_id"], "profile_id": profile["id"],
               "profile_sha256": profile["file_sha256"], "capture_sha256": digest(raw), "capture_bytes": len(raw),
               "capture_rows": len(rows), "capture_completion": rows[-1]["detail"],
               "engine_version": _version(invocation.get("engine_version")), "module_sha256": before[MODULE],
               "executable_sha256": _hash(invocation.get("executable_sha256")),
               "runner_sha256": _hash(invocation.get("runner_sha256")),
               "project_descriptor_sha256": before["SurgeMovementLab.uproject"],
               "source_config_sha256": {path: sha for path, sha in sorted(before.items()) if path.startswith(("Source/", "Config/"))},
               "source_records_sha256": {name: digest(value) for name, value in record_bytes.items()},
               "inputs_unchanged": True, "driver": "unreal-smoke-driver", "mode": mode,
               "rendering": "NullRHI", "input_scheme": "automated-game-command-handlers", "map": "/Engine/Maps/Entry",
               "map_sha256": None, "build_sha256": None, "camera_and_viewport": None,
               "requested_max_fps": 60, "measured_fps": None, "operator_actions_are_external": True,
               "authenticity": "local-records-not-attested", "limits": LIMITS}
    encoded = (json.dumps(context, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()
    validate_context(encoded, raw, rows, profile)
    return encoded


def validate_context(context_raw, capture_raw, rows, profile):
    """Validate external context without adding anything to detector input."""
    if not isinstance(context_raw, bytes) or len(context_raw) > MAX_CONTEXT_BYTES:
        raise ValueError("Expected bounded runtime-context bytes")
    context = _json(context_raw)
    if not isinstance(context, dict) or set(context) != FIELDS or context.get("schema") != SCHEMA:
        raise ValueError("Unsupported runtime-context fields/schema")
    expected = {"session_id": rows[0]["session_id"], "profile_id": profile["id"], "profile_sha256": profile["file_sha256"],
                "capture_sha256": digest(capture_raw), "capture_bytes": len(capture_raw), "capture_rows": len(rows),
                "capture_completion": rows[-1]["detail"], "inputs_unchanged": True, "driver": "unreal-smoke-driver",
                "rendering": "NullRHI", "input_scheme": "automated-game-command-handlers", "map": "/Engine/Maps/Entry",
                "map_sha256": None, "build_sha256": None, "camera_and_viewport": None, "requested_max_fps": 60,
                "measured_fps": None, "operator_actions_are_external": True, "authenticity": "local-records-not-attested",
                "limits": LIMITS}
    if any(context[key] != value or type(context[key]) is not type(value) for key, value in expected.items()):
        raise ValueError("Runtime context does not bind this exact capture/profile or supported smoke scope")
    if context["mode"] not in {"Smoke", "SpeedProbe"}:
        raise ValueError("Unsupported runtime context mode")
    _version(context["engine_version"])
    for key in ("module_sha256", "executable_sha256", "runner_sha256", "project_descriptor_sha256"):
        _hash(context[key])
    records = context["source_records_sha256"]
    if not isinstance(records, dict) or set(records) != set(RECORDS):
        raise ValueError("Runtime context lacks exact runner-record fingerprints")
    for value in records.values(): _hash(value)
    inputs = context["source_config_sha256"]
    if not isinstance(inputs, dict) or not 1 <= len(inputs) <= 254:
        raise ValueError("Invalid runtime source/config fingerprints")
    _input_manifest([{"path": path, "sha256": sha} for path, sha in inputs.items()]
                    + [{"path": MODULE, "sha256": context["module_sha256"]},
                       {"path": "SurgeMovementLab.uproject", "sha256": context["project_descriptor_sha256"]}])
    return context


def write_context(verification_directory, output, *, profile_id=PROFILE):
    raw = create_context(verification_directory, profile_id=profile_id)
    with Path(output).open("xb") as target:
        target.write(raw)
    return {"path": str(Path(output).resolve()), "sha256": digest(raw), "bytes": len(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verification_directory", type=Path)
    parser.add_argument("output", type=Path, help="New runtime-context.json; parent must exist")
    parser.add_argument("--profile", choices=sorted(PROFILE_IDS), default=PROFILE,
                        help="Explicit expected reviewed profile; reference also requires the retained invocation flag")
    args = parser.parse_args()
    print(json.dumps(write_context(args.verification_directory, args.output, profile_id=args.profile)))


if __name__ == "__main__":
    main()

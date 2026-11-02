"""Explicit, bounded runtime inputs for the combined Surge/Survive package.

The cooked game is a separately built artifact. Nothing is inferred from a
developer's Saved directory, caches, editor installation or old verification runs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time

GAME_LIMITS = dict(manifest_bytes=4 * 1024**2, files=5000,
                   expanded_bytes=2 * 1024**3, file_bytes=1024**3)
COMBINED_LIMITS = dict(archive_bytes=1536 * 1024**2, expanded_bytes=3 * 1024**3,
                       files=15000, total_seconds=3600)
RUNTIME_ASSETS = (
    "telemetry/prepare.py", "telemetry/prepare_v2.py", "telemetry/prepare_v3.py",
    "telemetry/audit_v3.py", "telemetry/survive-policy.json",
    "profiles/survive-lucian-practice-v1.json",
    "profiles/survive-lucian-reference-v1.json",
)
FORBIDDEN_PARTS = frozenset({".git", ".venv", ".vs", "node_modules", "__pycache__",
                           "source", "intermediate", "saved", "deriveddatacache",
                           "tests", "test", "verification", "_recovery", "checkpoints"})
FORBIDDEN_SUFFIXES = frozenset({".pdb", ".cpp", ".h", ".hpp", ".c", ".cs", ".py",
                              ".pyc", ".obj", ".lib", ".exp", ".log", ".ilk", ".zip",
                              ".jsonl", ".uproject", ".target", ".modules"})


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_member(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 512
            or any(ord(character) < 32 for character in value)):
        raise ValueError("Invalid standalone game path")
    path = PurePosixPath(value)
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
                *[f"LPT{i}" for i in range(1, 10)]}
    if (path.is_absolute() or str(path) != value or "\\" in value or ":" in value
            or any(part in (".", "..") or part.endswith((".", " "))
                   or part.split(".")[0].upper() in reserved for part in path.parts)):
        raise ValueError("Unsafe standalone game path")
    return path


def no_link(path):
    for part in (path, *path.parents):
        info = part.lstat()
        if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked standalone game inputs are not supported")
    return path


def regular(path):
    no_link(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Standalone game input is not a regular file")
    return info


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate standalone manifest field")
        result[key] = value
    return result


def copy_exact(source, target, expected_bytes):
    """Exclusive bounded copy; a growing input cannot consume unbounded disk."""
    remaining = expected_bytes
    with source.open("rb") as incoming, target.open("xb") as output:
        while remaining:
            raw = incoming.read(min(remaining, 1024 * 1024))
            if not raw:
                raise ValueError("Runtime input shortened while copying")
            output.write(raw)
            remaining -= len(raw)
        if incoming.read(1):
            raise ValueError("Runtime input grew while copying")


def validate_game(stage, deadline):
    stage = no_link(Path(stage).absolute())
    manifest_path = stage / "game-manifest.json"
    if regular(manifest_path).st_size > GAME_LIMITS["manifest_bytes"]:
        raise ValueError("Standalone manifest exceeds its limit")
    with manifest_path.open("rb") as stream:
        raw = stream.read(GAME_LIMITS["manifest_bytes"] + 1)
    if len(raw) > GAME_LIMITS["manifest_bytes"]:
        raise ValueError("Standalone manifest grew beyond its limit")
    manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite game manifest")))
    if (not isinstance(manifest, dict) or manifest.get("schema") != "survive-standalone-game-v1"
            or manifest.get("standalone") is not True
            or manifest.get("configuration") != "Shipping"
            or manifest.get("platform") != "Win64"
            or not isinstance(manifest.get("engine_version"), str)
            or len(manifest["engine_version"]) > 64):
        raise ValueError("Unsupported standalone game manifest")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not 1 <= len(entries) <= GAME_LIMITS["files"]:
        raise ValueError("Standalone game file-count limit exceeded")
    declared, folded = {}, set()
    total = 0
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise ValueError("Invalid standalone game file declaration")
        path = safe_member(item["path"])
        if (str(path).casefold() in folded or type(item["bytes"]) is not int
                or not 0 <= item["bytes"] <= GAME_LIMITS["file_bytes"]
                or not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
            raise ValueError("Invalid or duplicate standalone game file")
        if (set(part.casefold() for part in path.parts) & FORBIDDEN_PARTS
                or path.suffix.casefold() in FORBIDDEN_SUFFIXES
                or path.name.casefold().startswith("manifest_")):
            raise ValueError("Development or private file in standalone payload: " + str(path))
        total += item["bytes"]
        if total > GAME_LIMITS["expanded_bytes"]:
            raise ValueError("Standalone game expanded-size limit exceeded")
        declared[str(path)] = item
        folded.add(str(path).casefold())
    executable = str(safe_member(manifest.get("entry_executable")))
    exe = PurePosixPath(executable)
    if (executable not in declared or exe.parts[:3] != ("SurgeMovementLab", "Binaries", "Win64")
            or exe.name != "SurgeMovementLab-Win64-Shipping.exe"):
        raise ValueError("Standalone game entry point is not the owned game")
    licenses = manifest.get("licenses")
    if (not isinstance(licenses, list) or not licenses or len(licenses) > GAME_LIMITS["files"]
            or not all(isinstance(name, str) and name in declared for name in licenses)
            or len(set(licenses)) != len(licenses)):
        raise ValueError("Standalone runtime licences are missing")
    game = no_link(stage / "game")
    actual = set()
    for folder, directories, names in os.walk(game, followlinks=False):
        if time.monotonic() >= deadline:
            raise TimeoutError("Standalone game verification deadline")
        for name in directories:
            no_link(Path(folder) / name)
        for name in names:
            path = Path(folder) / name
            relative = path.relative_to(game).as_posix()
            if relative not in declared:
                raise ValueError("Undeclared standalone game file: " + relative)
            info = regular(path)
            item = declared[relative]
            if info.st_size != item["bytes"] or digest(path) != item["sha256"]:
                raise ValueError("Standalone game file identity mismatch: " + relative)
            actual.add(relative)
    if actual != set(declared):
        raise ValueError("Standalone game file set differs from its manifest")
    return manifest, raw, game


def copy_runtime(stage, app, source_root, deadline):
    manifest, raw, game = validate_game(stage, deadline)
    destination = app / "survive-game"
    destination.mkdir(exist_ok=False)
    for item in manifest["files"]:
        if time.monotonic() >= deadline:
            raise TimeoutError("Standalone game copying deadline")
        source = regular(game / item["path"])
        if source.st_size != item["bytes"]:
            raise ValueError("Standalone game changed before copying")
        target = destination / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_exact(game / item["path"], target, item["bytes"])
        if target.stat().st_size != item["bytes"] or digest(target) != item["sha256"]:
            raise ValueError("Standalone game changed while copying")
    manifest_target = app / "survive-game-manifest.json"
    with manifest_target.open("xb") as output:
        output.write(raw)
    descriptor = dict(schema="surge-survive-runtime-v1", game_root="survive-game",
                      game_executable=manifest["entry_executable"],
                      game_manifest="survive-game-manifest.json",
                      game_manifest_sha256=hashlib.sha256(raw).hexdigest())
    with (app / "survive-runtime.json").open("x", encoding="utf-8") as output:
        json.dump(descriptor, output, indent=2)
        output.write("\n")
    assets = {}
    for relative in RUNTIME_ASSETS:
        source = source_root / "unreal/SurgeMovementLab" / relative
        expected_bytes = regular(source).st_size
        if expected_bytes > 1024 * 1024:
            raise ValueError("Survive analysis asset exceeds its limit")
        target = app / "unreal/SurgeMovementLab" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_exact(source, target, expected_bytes)
        assets[relative] = digest(target)
        if assets[relative] != digest(source):
            raise ValueError("Survive analysis asset changed while copying")
    return dict(game_manifest_sha256=descriptor["game_manifest_sha256"],
                game_executable="survive-game/" + manifest["entry_executable"],
                engine_version=manifest["engine_version"], configuration=manifest["configuration"],
                files=len(manifest["files"]), bytes=sum(item["bytes"] for item in manifest["files"]),
                assets_sha256=assets, licenses=manifest["licenses"])

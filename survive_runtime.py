"""Trusted packaged-game identity and separate user-data paths.

Renderer requests never select these paths. Local hashes establish consistency,
not publisher signatures or client attestation. Source development keeps its
existing editor workflow; packaged mode has no editor fallback.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parent
MAX_MANIFEST = 4 * 1024 * 1024
MAX_FILES = 5000
MAX_GAME_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024 * 1024
ADAPTERS = ("prepare.py", "prepare_v2.py", "prepare_v3.py", "audit_v3.py")
PROFILES = ("survive-lucian-practice-v1", "survive-lucian-reference-v1")
EXECUTABLES = {"SurgeMovementLab/Binaries/Win64/SurgeMovementLab-Win64-Shipping.exe"}


def no_links(path):
    for current in (path, *path.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked Survive application or data paths are not supported.")


def safe_path(path, base):
    path, base = Path(path).absolute(), Path(base).absolute()
    if not path.is_relative_to(base):
        raise ValueError("Survive path escapes its owned directory.")
    no_links(path)
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError("Survive path escapes its owned directory.")
    return path


def relative_path(value):
    if (not isinstance(value, str) or not value or len(value) > 512
            or value.startswith("/") or "\\" in value or ":" in value
            or any(part in {"", ".", ".."} or part.endswith((".", " ")) for part in value.split("/"))
            or any(ord(char) < 32 for char in value)):
        raise ValueError("Invalid bundled Survive path.")
    return value


def file_hash(path, maximum=MAX_FILE_BYTES):
    no_links(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= maximum:
        raise ValueError("Bundled Survive file is missing, linked or oversized.")
    with path.open("rb") as stream:
        value = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Bundled Survive file changed while being verified.")
    return value


def read_identity(path, maximum):
    no_links(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise ValueError("Bundled Survive identity is missing or oversized.")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("Bundled Survive identity exceeds its size limit.")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate bundled Survive identity field.")
            result[key] = value
        return result
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Invalid identity number.")))


class RuntimeLayout:
    def __init__(self, root=None, saved_root=None, *, packaged=False):
        if type(packaged) is not bool:
            raise ValueError("Packaged runtime selection must be explicit.")
        self.root = Path(root or ROOT).absolute()
        no_links(self.root)
        self.root = self.root.resolve()
        self.lab = self.root / "unreal/SurgeMovementLab"
        self.packaged = packaged
        if packaged and (saved_root is None or not Path(saved_root).is_absolute()):
            raise ValueError("Packaged Survive needs its explicit Windows user-data directory.")
        if saved_root is not None and str(saved_root).startswith(("\\\\", "//")):
            raise ValueError("Survive user data must use a local directory.")
        self.saved = Path(saved_root).absolute() if saved_root is not None else self.lab / "Saved"
        no_links(self.saved)
        self.saved = self.saved.resolve()
        if packaged and (self.saved.is_relative_to(self.root) or self.root.is_relative_to(self.saved)):
            raise ValueError("Survive user data must remain separate from the installed application.")

    def data_path(self, name):
        if name not in {"Telemetry", "SurgeRecordings", "StudyTrials", "StudyActions", "Investigations", "Unreal"}:
            raise ValueError("Unknown Survive data directory.")
        return safe_path(self.saved / name, self.saved)

    def identity(self):
        if not self.packaged:
            raise ValueError("A standalone identity is only available in the packaged application.")
        try:
            descriptor = read_identity(safe_path(self.root / "survive-runtime.json", self.root), 16 * 1024)
            expected = {"schema", "game_root", "game_executable", "game_manifest", "game_manifest_sha256"}
            if (not isinstance(descriptor, dict) or set(descriptor) != expected
                    or descriptor["schema"] != "surge-survive-runtime-v1"
                    or descriptor["game_root"] != "survive-game"
                    or descriptor["game_manifest"] != "survive-game-manifest.json"
                    or not isinstance(descriptor["game_manifest_sha256"], str)
                    or not re.fullmatch(r"[a-f0-9]{64}", descriptor["game_manifest_sha256"])):
                raise ValueError("Invalid bundled Survive runtime descriptor.")
            executable = relative_path(descriptor["game_executable"])
            if executable not in EXECUTABLES:
                raise ValueError("Bundled Survive entry point must be the owned game executable.")
            manifest_path = safe_path(self.root / descriptor["game_manifest"], self.root)
            if file_hash(manifest_path, MAX_MANIFEST) != descriptor["game_manifest_sha256"]:
                raise ValueError("Bundled Survive manifest does not match its runtime identity.")
            manifest = read_identity(manifest_path, MAX_MANIFEST)
            if (not isinstance(manifest, dict) or manifest.get("schema") != "survive-standalone-game-v1"
                    or manifest.get("standalone") is not True or manifest.get("platform") != "Win64"
                    or manifest.get("entry_executable") != executable
                    or manifest.get("configuration") != "Shipping"
                    or not isinstance(manifest.get("engine_version"), str)
                    or not 1 <= len(manifest["engine_version"]) <= 64
                    or not isinstance(manifest.get("files"), list)
                    or not 1 <= len(manifest["files"]) <= MAX_FILES):
                raise ValueError("Invalid bundled Survive game manifest.")
            names, total = set(), 0
            for item in manifest["files"]:
                if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
                    raise ValueError("Invalid bundled Survive file identity.")
                name = relative_path(item["path"])
                if (name.casefold() in names or type(item["bytes"]) is not int
                        or not 0 <= item["bytes"] <= MAX_FILE_BYTES
                        or not isinstance(item["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
                    raise ValueError("Duplicate or invalid bundled Survive file identity.")
                names.add(name.casefold())
                total += item["bytes"]
            if executable.casefold() not in names or total > MAX_GAME_BYTES:
                raise ValueError("Bundled Survive file inventory is incomplete or exceeds its bound.")
            return descriptor, manifest
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("The bundled Survive game is unavailable. Extract a complete release into a new folder.") from exc

    def verify_game(self):
        descriptor, manifest = self.identity()
        game = safe_path(self.root / descriptor["game_root"], self.root)
        hashes = {}
        try:
            for item in manifest["files"]:
                path = safe_path(game / item["path"], game)
                if path.stat().st_size != item["bytes"] or file_hash(path) != item["sha256"]:
                    raise ValueError("A bundled Survive file has changed. Extract a complete release into a new folder.")
                hashes["survive-game/" + item["path"]] = item["sha256"]
            executable = safe_path(game / descriptor["game_executable"], game)
            for name in ("survive-runtime.json", "survive-game-manifest.json"):
                hashes[name] = file_hash(self.root / name, MAX_MANIFEST)
        except OSError as exc:
            raise ValueError("A bundled Survive file is missing. Extract a complete release into a new folder.") from exc
        return {"executable": executable, "files_sha256": hashes,
                "manifest_sha256": descriptor["game_manifest_sha256"],
                "configuration": manifest["configuration"], "engine_version": manifest["engine_version"]}

    def verify_assets(self):
        paths = [self.lab / "telemetry" / name for name in (*ADAPTERS, "survive-policy.json")]
        paths += [self.lab / "profiles" / (name + ".json") for name in PROFILES]
        try:
            return {path.relative_to(self.root).as_posix(): file_hash(safe_path(path, self.root), 512 * 1024)
                    for path in paths}
        except OSError as exc:
            raise ValueError("Survive analysis assets are missing. Extract a complete release into a new folder.") from exc

"""Build a cooked standalone Shipping game with no developer payload.

Uses the already installed Unreal toolchain only. Build/cook output and local
reports remain outside game/. The portable manifest contains relative paths and
hashes; explicit owned study controls are ordinary project runtime functionality.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

LAB = Path(__file__).resolve().parents[1]
MAX_FILES = 5000
MAX_TOTAL = 2 * 1024**3
MAX_FILE = 1024**3
MAX_LOG = 64 * 1024**2
FORBIDDEN_PARTS = {"source", "intermediate", "saved", "deriveddatacache", ".git", "tests", "__pycache__"}
FORBIDDEN_SUFFIXES = {".pdb", ".cpp", ".h", ".hpp", ".cs", ".py", ".obj", ".lib", ".exp", ".log", ".target", ".modules"}


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)


def source_manifest():
    paths = [LAB / "SurgeMovementLab.uproject", Path(__file__).resolve()]
    paths += [p for base in ("Source", "Config") for p in (LAB / base).rglob("*") if p.is_file()]
    return {p.relative_to(LAB).as_posix(): digest(p) for p in sorted(paths)}


def inventory(directory):
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked game payload refused")
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > MAX_FILE:
            raise ValueError("Game file exceeds one GiB")
        files.append({"path": path.relative_to(directory).as_posix(), "bytes": size, "sha256": digest(path)})
        if len(files) > MAX_FILES or sum(item["bytes"] for item in files) > MAX_TOTAL:
            raise ValueError("Game payload exceeds reviewed bounds")
    return files


def run(args):
    engine = args.engine.resolve()
    attempt = LAB / "Saved/Standalone" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    attempt.mkdir(parents=True, exist_ok=False)
    version = json.loads((engine / "Engine/Build/Build.version").read_text())
    before = source_manifest()
    report = {"schema": "survive-standalone-build-v1", "status": "incomplete", "started_utc": datetime.now(timezone.utc).isoformat(),
              "engine": str(engine), "source_files_sha256": before, "timeout_seconds": args.timeout, "steps": []}
    process = None
    started = time.monotonic()
    try:
        dotnet = engine / "Engine/Binaries/ThirdParty/DotNet/10.0/win-x64/dotnet.exe"
        automation = engine / "Engine/Binaries/DotNET/AutomationTool/AutomationTool.dll"
        project = LAB / "SurgeMovementLab.uproject"
        for required in (dotnet, automation, project, engine / "Engine/Build/InstalledBuild.txt"):
            if not required.is_file():
                raise ValueError("Required installed build input missing: " + str(required))
        archive = attempt / "uat-archive"
        command = [str(dotnet), str(automation), "BuildCookRun", "-installed", "-nop4", "-unattended", "-utf8output",
                   "-project=" + str(project), "-platform=Win64", "-clientconfig=Shipping", "-build", "-cook", "-stage",
                   "-pak", "-iostore", "-archive", "-archivedirectory=" + str(archive), "-map=/Engine/Maps/Entry",
                   "-nocompileeditor", "-nodebuginfo", "-NoBootstrapExe",
                   "-applocaldirectory=" + str(engine / "Engine/Binaries/ThirdParty/AppLocalDependencies"),
                   "-ubtargs=-WaitMutex -NoUBA -NoXGE -NoFASTBuild -NoSNDBS -MaxParallelActions=4 -NoEngineChanges"]
        report["command"] = command
        write(attempt / "invocation.json", report)
        env = os.environ.copy()
        env.update(DOTNET_ROOT=str(dotnet.parent), DOTNET_MULTILEVEL_LOOKUP="0", DOTNET_ROLL_FORWARD="LatestMajor",
                   DOTNET_CLI_HOME=str(attempt / "dotnet-home"), DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
        for name in ("CL", "_CL_", "LINK", "_LINK_"):
            env.pop(name, None)
        log = attempt / "build-cook.log"
        print(json.dumps({"attempt": str(attempt), "phase": "build-cook-stage"}), flush=True)
        with log.open("xb") as stream:
            process = subprocess.Popen(command, cwd=automation.parent, env=env, stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            report["owned_pid"] = process.pid
            while process.poll() is None:
                if time.monotonic() - started > args.timeout or log.stat().st_size > MAX_LOG:
                    raise TimeoutError("Bounded build/cook exceeded time or log limit")
                time.sleep(1)
        report["uat_exit_code"] = process.returncode
        if process.returncode:
            raise ValueError("BuildCookRun failed; inspect build-cook.log")
        if source_manifest() != before:
            raise ValueError("Source changed during build/cook")
        staged = archive / "Windows"
        if not staged.is_dir():
            raise ValueError("Expected archived Windows runtime tree missing")
        game = attempt / "game"
        game.mkdir()
        excluded = []
        for path in sorted(staged.rglob("*")):
            if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError("Linked staged path refused")
            if not path.is_file():
                continue
            relative = path.relative_to(staged)
            if (any(part.casefold() in FORBIDDEN_PARTS for part in relative.parts)
                    or path.suffix.casefold() in FORBIDDEN_SUFFIXES or path.name.startswith("Manifest_")):
                excluded.append(relative.as_posix())
                continue
            target = game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        executable = "SurgeMovementLab/Binaries/Win64/SurgeMovementLab-Win64-Shipping.exe"
        if not (game / executable).is_file():
            raise ValueError("Direct standalone game executable missing")
        if any(path.name != Path(executable).name for path in game.rglob("*.exe")):
            raise ValueError("Unexpected executable in the standalone game payload")
        for name in ("vcruntime140.dll", "msvcp140.dll"):
            if not (game / Path(executable).parent / name).is_file():
                raise ValueError("App-local runtime dependency missing: " + name)
        licenses = game / "licenses"
        licenses.mkdir()
        (licenses / "Survive-NOTICES.txt").write_text(
            "Survive is an original gameplay telemetry lab.\n"
            "Unreal Engine is a trademark or registered trademark of Epic Games, Inc. in the United States of America and elsewhere.\n"
            "Unreal Engine, Copyright 1998 - 2026, Epic Games, Inc. All rights reserved.\n"
            "Unreal Engine is distributed under the Unreal Engine End User License Agreement, not the project's MIT licence.\n"
            "https://www.unrealengine.com/eula/unreal\n"
            "Bundled engine third-party licence notices are preserved below; inclusion does not imply every optional component is active.\n"
            "Shipping configuration includes explicit local study controls; developer source, symbols, tests and private recordings are excluded.\n",
            encoding="utf-8")
        engine_licenses = engine / "Engine/Source/ThirdParty/Licenses"
        for path in sorted(engine_licenses.iterdir()):
            if path.is_file():
                shutil.copy2(path, licenses / (path.name + ".txt"))
        shutil.copy2(LAB.parents[1] / "LICENSE", licenses / "Surge-MIT.txt")
        files = inventory(game)
        manifest = {"schema": "survive-standalone-game-v1", "standalone": True, "engine_version": ".".join(str(version[k]) for k in ("MajorVersion", "MinorVersion", "PatchVersion")),
                    "engine_changelist": version["Changelist"], "configuration": "Shipping", "platform": "Win64",
                    "entry_executable": executable, "source_files_sha256": before, "files": files,
                    "licenses": [item["path"] for item in files if item["path"].startswith("licenses/")],
                    "scope": "Cooked standalone Shipping game; no installed Unreal editor needed. Explicit owned study drivers remain available."}
        write(attempt / "game-manifest.json", manifest)
        if (attempt / "game-manifest.json").stat().st_size > 4 * 1024**2:
            raise ValueError("Game manifest exceeds four MiB")
        report.update(status="passed", game=str(game), manifest=str(attempt / "game-manifest.json"),
                      files=len(files), bytes=sum(item["bytes"] for item in files), excluded_stage_files=excluded,
                      manifest_sha256=digest(attempt / "game-manifest.json"))
    except Exception as error:
        report.update(status="failed", error=str(error), error_type=type(error).__name__)
    finally:
        if process is not None and process.poll() is None:
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            process.wait(timeout=10)
        report["elapsed_s"] = time.monotonic() - started
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write(attempt / "build-report.json", report)
        print(json.dumps({"status": report["status"], "attempt": str(attempt), "error": report.get("error")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=Path("C:/Program Files/Epic Games/UE_5.8"))
    parser.add_argument("--timeout", type=int, choices=range(60, 3601), default=2400)
    raise SystemExit(run(parser.parse_args()))

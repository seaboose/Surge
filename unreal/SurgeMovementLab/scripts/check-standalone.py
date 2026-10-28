"""Bounded owned-game standalone check with separate data and module-path proof."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

LAB = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in root.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--mode", choices=("scripted", "speed_probe"), default="scripted")
    args = parser.parse_args()
    build = args.build.resolve()
    if not build.is_relative_to(LAB / "Saved/Standalone"):
        raise ValueError("Use a freshly built owned standalone attempt")
    manifest = json.loads((build / "game-manifest.json").read_text())
    game = build / "game"
    expected = {item["path"]: item["sha256"] for item in manifest["files"]}
    assert inventory(game) == expected
    executable = (game / manifest["entry_executable"]).resolve()
    assert executable.is_relative_to(game) and executable.name == "SurgeMovementLab-Win64-Shipping.exe"
    assert manifest["configuration"] == "Shipping"
    attempt = LAB / "Saved/Verification" / ("standalone-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    data = attempt / "data"
    data.mkdir(parents=True, exist_ok=False)
    trial = uuid.uuid4().hex
    report = {"schema": "survive-standalone-check-v1", "status": "incomplete", "build_manifest_sha256": sha(build / "game-manifest.json"),
              "configuration": manifest["configuration"], "trial_id": trial, "human_baseline": False,
              "mode": args.mode, "scope": "Owned standalone headless practice, not rendered or human input validation."}
    command = [str(executable), "/Engine/Maps/Entry?game=/Script/SurgeMovementLab.LabGameMode", "-NullRHI", "-unattended", "-nosound",
               "-nosplash", "-NoEpicPortal", "-nocrashreports", "-NoShaderCompile", "-SurviveStudyMode=" + args.mode, "-SurviveStudyTrial=" + trial,
               "-SurviveStudyExitAfterRound", "-SurviveSeed=1337", "-SurviveSavedDir=" + str(data), "-UserDir=" + str(data / "Unreal"),
               "-abslog=" + str(data / "engine.log"), "-ExecCmds=t.MaxFPS 60"]
    if args.mode == "speed_probe":
        command += ["-SurviveSmoke", "-SurviveSpeedProbe"]
    env = os.environ.copy()
    windows_buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetWindowsDirectoryW(windows_buffer, len(windows_buffer)):
        raise OSError("Windows system directory could not be resolved")
    windows_root = Path(windows_buffer.value)
    env["SystemRoot"] = str(windows_root)
    env["WINDIR"] = str(windows_root)
    env["PATH"] = str(windows_root / "System32")
    env.pop("UE_ENGINE_DIRECTORY", None)
    started = time.monotonic()
    process = None
    try:
        with (attempt / "console.log").open("xb") as output:
            process = subprocess.Popen(command, cwd=executable.parent, env=env, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            report.update(pid=process.pid, executable=str(executable), executable_sha256=sha(executable))
            print(json.dumps({"attempt": str(attempt), "pid": process.pid}), flush=True)
            snapshots = []
            for checkpoint in (10, 40):
                while time.monotonic() - started < checkpoint and process.poll() is None:
                    time.sleep(.25)
                if process.poll() is not None:
                    raise ValueError("Standalone game exited before the timed module observation")
                powershell = windows_root / "System32/WindowsPowerShell/v1.0/powershell.exe"
                script = ("$ErrorActionPreference='Stop'; $owned=Get-Process -Id " + str(process.pid)
                          + "; @{modules=@($owned.Modules | ForEach-Object { $_.FileName });"
                          + "tcp=@(Get-NetTCPConnection -OwningProcess " + str(process.pid) + " -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State);"
                          + "udp=@(Get-NetUDPEndpoint -OwningProcess " + str(process.pid) + " -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort)} | ConvertTo-Json -Depth 4 -Compress")
                result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script], check=True,
                                        capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
                network = json.loads(result.stdout)
                modules = network["modules"]
                assert isinstance(modules, list) and 1 <= len(modules) <= 512
                outside = [name for name in modules if not Path(name).resolve().is_relative_to(game)
                           and not Path(name).resolve().is_relative_to(windows_root)]
                if outside:
                    raise ValueError("Non-package/non-Windows modules loaded: " + repr(outside))
                assert not network["tcp"] and not network["udp"], network
                snapshots.append({"elapsed_wall_s": time.monotonic() - started, **network})
            report["module_snapshots"] = snapshots
            process.wait(timeout=max(1, 145 - (time.monotonic() - started)))
        report["exit_code"] = process.returncode
        assert process.returncode == 0
        captures = list((data / "Telemetry").glob("*.jsonl"))
        assert len(captures) == 1
        rows = [json.loads(line) for line in captures[0].read_text(encoding="utf-8-sig").splitlines()]
        assert rows[0]["event"] == "run_start" and rows[-1]["event"] == "run_end"
        assert rows[-1]["detail"] == "completed" and rows[-1]["elapsed_s"] == 60
        assert all(row["seq"] == i for i, row in enumerate(rows))
        journal = data / "StudyActions" / (trial + ".jsonl")
        actions = [json.loads(line) for line in journal.read_text().splitlines()]
        assert actions and all(row["trial_id"] == trial and row["session_id"] == rows[0]["session_id"] for row in actions)
        if args.mode == "speed_probe":
            assert {"speed_probe_begin", "speed_probe_end"}.issubset({row["event"] for row in actions})
        assert inventory(game) == expected
        assert (data / "Unreal/Saved").is_dir()
        report.update(status="passed", rows=len(rows), source_game_s=rows[-1]["elapsed_s"], source_sha256=sha(captures[0]),
                      study_actions=len(actions), source_path=str(captures[0]), package_files_unchanged=True,
                      all_modules_from_package_or_windows=True, unreal_saved_under_user_data=True)
        report["no_owned_tcp_or_udp_endpoints_at_observed_times"] = True
    except Exception as error:
        report.update(status="failed", error=str(error), error_type=type(error).__name__)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        report["elapsed_wall_s"] = time.monotonic() - started
        with (attempt / "result.json").open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
        print(json.dumps({"status": report["status"], "report": str(attempt / "result.json"), "error": report.get("error")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded real Windows launcher check; refuse existing user profiles."""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

try:
    from .release_files import ROOT, source_files
except ImportError:
    from release_files import ROOT, source_files


TOTAL_SECONDS = 90
STARTUP_SECONDS = 30
SHUTDOWN_SECONDS = 15


def utc():
    return datetime.now(timezone.utc).isoformat()


def identity(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(source_files(root=root))
    }


def preconditions(root, appdata):
    profile = appdata / "surge-desktop"
    if os.path.lexists(profile):
        raise RuntimeError("Refusing to open an existing ordinary Surge profile.")
    package = json.loads((root / "desktop/package.json").read_text(encoding="utf-8"))
    if package.get("name") != "surge-desktop":
        raise RuntimeError("Unexpected application name; profile isolation is not established.")
    for relative in (
        "Start-Surge.cmd",
        "Start-Surge.ps1",
        "desktop/main.cjs",
        "desktop/dist/index.html",
        "desktop/node_modules/electron/dist/electron.exe",
        ".venv/Scripts/python.exe",
    ):
        if not (root / relative).is_file():
            raise RuntimeError(f"Required setup file is missing: {relative}")
    return profile


def ordinary_appdata():
    # Resolve the Windows known folder rather than trusting a changed APPDATA
    # environment variable to isolate Electron's ordinary profile.
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.SHGetFolderPathW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR]
    location = ctypes.create_unicode_buffer(32768)
    result = shell.SHGetFolderPathW(None, 0x001A, None, 0, location)
    if result != 0 or not location.value:
        raise RuntimeError(f"Cannot establish the ordinary Windows application-data folder: {result}.")
    return Path(location.value)


def process_inventory(root, remaining):
    # Only return paths owned by this extraction; other process command lines
    # are neither collected nor included in the evidence report.
    env = os.environ.copy()
    env["SURGE_TEST_ELECTRON"] = str(root / "desktop/node_modules/electron/dist/electron.exe")
    env["SURGE_TEST_PYTHON"] = str(root / ".venv/Scripts/python.exe")
    query = (
        "$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.ExecutablePath -eq $env:SURGE_TEST_ELECTRON -or "
        "$_.ExecutablePath -eq $env:SURGE_TEST_PYTHON } | "
        "Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", query],
        env=env,
        capture_output=True,
        timeout=max(0.1, min(5, remaining)),
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    value = json.loads(result.stdout.decode("utf-8-sig").strip() or "[]")
    return value if isinstance(value, list) else [value]


class OwnedJob:
    """A kernel-enforced process boundary, established before the launch gate."""

    def __init__(self):
        class Basic(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", Basic),
                ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def owned_window(pid):
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = []

    def collect(handle, _):
        actual = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(actual))
        if actual.value == pid and user.IsWindowVisible(handle):
            title = ctypes.create_unicode_buffer(256)
            user.GetWindowTextW(handle, title, len(title))
            if title.value == "Surge":
                found.append({"handle": int(handle), "pid": pid, "title": title.value})
        return True

    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    if not user.EnumWindows(callback_type(collect), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return found


def close_window(window):
    # Revalidate ownership immediately before sending only WM_CLOSE.
    if window not in owned_window(window["pid"]):
        raise RuntimeError("Owned application window disappeared before shutdown.")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    if not user.PostMessageW(window["handle"], 0x0010, 0, 0):
        raise ctypes.WinError(ctypes.get_last_error())


def observe(processes, root):
    electron = str(root / "desktop/node_modules/electron/dist/electron.exe").lower()
    python = str(root / ".venv/Scripts/python.exe").lower()
    main = [p for p in processes if p["ExecutablePath"].lower() == electron and "--type=" not in (p["CommandLine"] or "")]
    if len(main) != 1:
        return None
    pid = main[0]["ProcessId"]
    workers = [p for p in processes if p["ExecutablePath"].lower() == python and p["ParentProcessId"] == pid and "desktop_worker" in (p["CommandLine"] or "")]
    # Chromium renderer may have an intermediate process; prove ancestry.
    descendants = {pid}
    while True:
        updated = descendants | {p["ProcessId"] for p in processes if p["ParentProcessId"] in descendants}
        if updated == descendants:
            break
        descendants = updated
    renderers = [p for p in processes if p["ProcessId"] in descendants and "--type=renderer" in (p["CommandLine"] or "")]
    windows = owned_window(pid)
    if len(windows) == 1 and workers and renderers:
        return {"window": windows[0], "processes": processes}
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.application_root.resolve()
    artifacts = ROOT / "verification/qualification" / f"launcher-{uuid.uuid4().hex[:12]}" / "artifacts"
    artifacts.mkdir(parents=True)
    report = {
        "status": "failed", "started": utc(), "application_root": str(root),
        "criteria": {f"L{i}": "not_run" for i in range(1, 6)},
        "human_acceptance": "pending", "native_dialogs": "not_run",
        "limitations": [
            "Window/process liveness only; no rendered-screen or native-dialog assertions.",
            "Same automated operator, not unfamiliar-tester acceptance.",
            "No live capture, broader fuzzing, endurance, or hostile-host claim.",
        ],
        "forced_cleanup": False,
    }
    began = time.monotonic()
    deadline = began + TOTAL_SECONDS
    launcher = job = initial = None
    log = None
    try:
        if os.name != "nt":
            raise RuntimeError("This acceptance check requires Windows.")
        profile = preconditions(root, ordinary_appdata())
        initial = identity(root)
        report["source_sha256"] = initial
        report["profile"] = str(profile)
        if process_inventory(root, deadline - time.monotonic()):
            raise RuntimeError("Refusing to launch while this extraction already has application processes.")
        report["criteria"]["L1"] = "passed"
        env = os.environ.copy()
        for key in ("SURGE_PYTHON", "PYTHONHOME", "PYTHONPATH", "PYTHONOPTIMIZE", "NODE_OPTIONS"):
            env.pop(key, None)
        env["ELECTRON_RUN_AS_NODE"] = "1"
        env["SURGE_TEST_LAUNCHER"] = str(root / "Start-Surge.cmd")
        gate = artifacts.parent / "launch-gate"
        env["SURGE_TEST_LAUNCH_GATE"] = str(gate)
        command = [
            "powershell.exe", "-NoProfile", "-Command",
            "while (!(Test-Path -LiteralPath $env:SURGE_TEST_LAUNCH_GATE)) { Start-Sleep -Milliseconds 50 }; & $env:SURGE_TEST_LAUNCHER; exit $LASTEXITCODE",
        ]
        report["entrypoint"] = "Start-Surge.cmd"
        report["inherited_electron_run_as_node"] = "1"
        job = OwnedJob()
        log = (artifacts / "launcher.log").open("wb")
        launcher = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            job.assign(launcher)
        except BaseException:
            launcher.kill()  # Still behind gate; no application was launched.
            raise
        gate.write_text("owned job assigned\n", encoding="utf-8")
        startup_deadline = min(deadline, time.monotonic() + STARTUP_SECONDS)
        stable_since = None
        observation = None
        while time.monotonic() < startup_deadline:
            if launcher.poll() not in (None, 0):
                raise RuntimeError(f"Start-Surge.cmd exited {launcher.returncode}.")
            processes = process_inventory(root, deadline - time.monotonic())
            observation = observe(processes, root)
            report["last_observation"] = {"processes": processes, "ready": observation is not None}
            if observation:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= 3 and launcher.poll() == 0:
                    break
            else:
                stable_since = None
            time.sleep(0.2)
        else:
            raise RuntimeError("Real launcher did not reach stable window/worker/renderer readiness within 30 seconds.")
        report["launcher_exit_code"] = launcher.returncode
        report["criteria"]["L2"] = "passed"
        if not profile.is_dir():
            raise RuntimeError("Expected fresh ordinary profile was not created.")
        report["observation"] = observation
        report["startup_seconds"] = round(time.monotonic() - began, 3)
        report["criteria"]["L3"] = "passed"
        close_window(observation["window"])
        shutdown_began = time.monotonic()
        shutdown_deadline = min(deadline, shutdown_began + SHUTDOWN_SECONDS)
        while time.monotonic() < shutdown_deadline:
            if not process_inventory(root, deadline - time.monotonic()):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Application processes survived the 15-second graceful-shutdown limit.")
        report["shutdown_seconds"] = round(time.monotonic() - shutdown_began, 3)
        report["criteria"]["L4"] = "passed"
        report["status"] = "passed"
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if report["criteria"]["L1"] == "not_run":
            report["criteria"]["L1"] = "failed"
            report["launch_attempted"] = launcher is not None
        print(report["error"], file=sys.stderr)
    finally:
        if job:
            if report["criteria"]["L4"] != "passed" and launcher is not None:
                report["forced_cleanup"] = True
            job.close()
        if launcher:
            try:
                launcher.wait(timeout=5)
            except subprocess.TimeoutExpired:
                launcher.kill()
                launcher.wait(timeout=5)
                report["status"] = "failed"
                report["forced_cleanup"] = True
        if log:
            log.close()
        if initial is not None:
            try:
                report["source_unchanged"] = identity(root) == initial
                if not report["source_unchanged"]:
                    report["status"] = "failed"
                    report["error"] = "Application source changed during launcher check."
            except BaseException as error:
                report["status"] = "failed"
                report["error"] = f"Source recheck failed: {error}"
        report["criteria"]["L5"] = "passed" if report.get("source_unchanged") else "not_run"
        report["finished"] = utc()
        report["elapsed_seconds"] = round(time.monotonic() - began, 3)
        if report["elapsed_seconds"] > TOTAL_SECONDS:
            report["status"] = "failed"
            report["error"] = "Total launcher-check limit exceeded."
        (artifacts / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "artifacts": str(artifacts)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

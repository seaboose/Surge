"""Bounded consumer of an immutable Windows package; never builds or approves it."""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import re
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zipfile

try:
    from .check_launcher import OwnedJob, ordinary_appdata
    from .survive_package import COMBINED_LIMITS
except ImportError:
    from check_launcher import OwnedJob, ordinary_appdata
    from survive_package import COMBINED_LIMITS

ROOT = Path(__file__).resolve().parents[1]
LIMITS = dict(total_seconds=600, action_seconds=30, shutdown_seconds=15,
              startup_failure_seconds=10, archive_bytes=256 * 1024**2,
              expanded_bytes=768 * 1024**2, files=10000, input_bytes=256 * 1024,
              log_bytes=20 * 1024**2, evidence_bytes=128 * 1024**2)
STEPS = ("package_identity", "extract_primary", "packaged_journey", "extract_replacement",
         "packaged_replacement", "approval_mismatch", "missing_runtime", "missing_backend",
         "missing_sample", "immutable_payloads")
HARNESS = ("scripts/check_windows_package.py", "desktop/packaged.test.cjs",
           "scripts/check_launcher.py", "scripts/verify_windows_consumer.py", "scripts/release_files.py",
           "scripts/windows_owned_processes.py", "scripts/survive_package.py")


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def zone_identifier(path):
    """Inspect only presence/ZoneId; never retain download URLs from the ADS."""
    try:
        with open(str(path) + ":Zone.Identifier", "rb") as stream:
            raw = stream.read(8193)
    except FileNotFoundError:
        return {"present": False, "zone_id": None, "inspection": "absent"}
    except OSError:
        return {"present": None, "zone_id": None, "inspection": "unavailable"}
    if len(raw) > 8192:
        return {"present": True, "zone_id": None, "inspection": "over_read_bound"}
    match = re.search(rb"(?mi)^ZoneId\s*=\s*([0-4])\s*$", raw)
    return {"present": True, "zone_id": int(match[1]) if match else None, "inspection": "read"}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_record(path, base):
    path = Path(path)
    return dict(path=path.relative_to(base).as_posix(), bytes=path.stat().st_size, sha256=digest(path))


def safe_member(name):
    p = PurePosixPath(name)
    if (not name or "\\" in name or p.is_absolute() or str(p) != name
            or any(x in ("", ".", "..") or ":" in x or x.endswith((" ", ".")) for x in p.parts)
            or any(x.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]} for x in p.parts)):
        raise ValueError("Unsafe package entry name.")
    return p


def verify_package(archive, manifest):
    if manifest.get("schema") != "surge-windows-package-v1":
        raise ValueError("Unexpected package manifest schema.")
    kind = manifest.get("package_kind", "surge")
    if kind not in {"surge", "surge-survive"}:
        raise ValueError("Unexpected package component kind.")
    # Only these reviewed fixed limits may change with the declared product.
    # A manifest-supplied limits object can never authorize an arbitrary expansion.
    bounds = {**LIMITS, **COMBINED_LIMITS} if kind == "surge-survive" else LIMITS
    expected_archive = manifest["archive"]
    if archive.stat().st_size > bounds["archive_bytes"]:
        raise ValueError(f"Package ZIP exceeds {bounds['archive_bytes'] // 1024**2} MiB.")
    if archive.stat().st_size != expected_archive["bytes"] or digest(archive) != expected_archive["sha256"]:
        raise ValueError("Package ZIP identity mismatch.")
    entries = manifest["files"]
    if not 1 <= len(entries) <= bounds["files"]:
        raise ValueError("Package file-count limit exceeded.")
    declared = {}
    for entry in entries:
        name = str(safe_member(entry["path"]))
        if name.casefold() in {k.casefold() for k in declared} or type(entry["bytes"]) is not int or entry["bytes"] < 0:
            raise ValueError("Duplicate or invalid manifest file.")
        declared[name] = entry
    if sum(x["bytes"] for x in entries) > bounds["expanded_bytes"]:
        raise ValueError(f"Expanded package exceeds {bounds['expanded_bytes'] // 1024**2} MiB.")
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        if len(infos) != len(entries):
            raise ValueError("Package entry set differs from manifest.")
        seen = set()
        for info in infos:
            name = str(safe_member(info.filename))
            if name not in declared or name.casefold() in seen or info.is_dir() or info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Unsupported or duplicate ZIP member.")
            seen.add(name.casefold())
            if info.file_size != declared[name]["bytes"]:
                raise ValueError("Package expanded length mismatch.")
            with source.open(info) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != declared[name]["sha256"]:
                raise ValueError("Package member digest mismatch.")
    required = {"Surge.exe", "resources/python/python.exe", "resources/app/desktop_worker.py",
                "resources/app/desktop/main.cjs", "resources/app/native/build/surge_owned_app.exe",
                "resources/app/native/baselines.json", "resources/app/package-identity.json"}
    if kind == "surge-survive":
        survive = manifest.get("survive")
        if not isinstance(survive, dict):
            raise ValueError("Standalone game identity missing from manifest.")
        if not isinstance(survive.get("game_executable"), str):
            raise ValueError("Standalone game entry point missing from manifest.")
        game_executable = safe_member(survive["game_executable"])
        if game_executable.parts[0] != "survive-game" or game_executable.suffix != ".exe":
            raise ValueError("Invalid standalone game entry point.")
        required.add("resources/app/" + str(game_executable))
        required.update({"resources/app/survive_runtime.py", "resources/app/survive-runtime.json",
                         "resources/app/survive-game-manifest.json",
                         "resources/app/unreal/SurgeMovementLab/telemetry/prepare.py",
                         "resources/app/unreal/SurgeMovementLab/telemetry/prepare_v2.py",
                         "resources/app/unreal/SurgeMovementLab/telemetry/prepare_v3.py",
                         "resources/app/unreal/SurgeMovementLab/telemetry/audit_v3.py",
                         "resources/app/unreal/SurgeMovementLab/telemetry/survive-policy.json",
                         "resources/app/unreal/SurgeMovementLab/profiles/survive-lucian-practice-v1.json",
                         "resources/app/unreal/SurgeMovementLab/profiles/survive-lucian-reference-v1.json"})
    if not required <= set(declared):
        raise ValueError("Required bundled component missing from manifest.")
    return dict(files=len(entries), expanded_bytes=sum(x["bytes"] for x in entries),
                crc="passed", sha256=expected_archive["sha256"], package_kind=kind)


def extract_verified(archive, target):
    # Called only after exact bounded inventory/digest validation; exclusive writes.
    target.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            relative = safe_member(info.filename)
            output = target.joinpath(*relative.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with source.open(info) as incoming, output.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, 1024 * 1024)


def verify_payload(root, manifest):
    actual = {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}
    expected = {x["path"]: x for x in manifest["files"]}
    if actual.keys() != expected.keys():
        raise ValueError("Packaged payload file set changed.")
    for name, file in actual.items():
        if file.is_symlink() or file.stat().st_size != expected[name]["bytes"] or digest(file) != expected[name]["sha256"]:
            raise ValueError(f"Packaged payload changed: {name}")
    return {"unchanged": True, "files": len(actual)}


def restricted_environment(temporary):
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "USERNAME", "USERDOMAIN", "HOMEDRIVE", "HOMEPATH", "SURGE_PRESENTATION"}}
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if not system_root and os.name == "nt":
        buffer = ctypes.create_unicode_buffer(32768)
        get_windows_directory = ctypes.WinDLL("kernel32", use_last_error=True).GetWindowsDirectoryW
        get_windows_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
        get_windows_directory.restype = wintypes.UINT
        length = get_windows_directory(buffer, len(buffer))
        if not 0 < length < len(buffer):
            raise RuntimeError("The Windows system directory could not be resolved.")
        system_root = buffer.value
    windows = Path(system_root or r"C:\Windows")
    for key in list(env):
        if key.upper() in {"SYSTEMROOT", "WINDIR"}:
            del env[key]
    env.update(SYSTEMROOT=str(windows), WINDIR=str(windows))
    env.update(PATH=os.pathsep.join(map(str, (windows / "System32", windows))),
               TEMP=str(temporary), TMP=str(temporary),
               SURGE_PYTHON=str(temporary / "invalid-override" / "python.exe"),
               PYTHONHOME=str(temporary / "invalid-home"), PYTHONPATH=str(temporary / "invalid-path"))
    return env


def token_identity(pid):
    kernel, advapi = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    process = kernel.OpenProcess(0x1000, False, pid)
    token = wintypes.HANDLE()
    if not process:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not advapi.OpenProcessToken(process, 8, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        elevated, size = wintypes.DWORD(), wintypes.DWORD()
        if not advapi.GetTokenInformation(token, 20, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"pid": pid, "token_elevated": bool(elevated.value)}
    finally:
        if token:
            kernel.CloseHandle(token)
        kernel.CloseHandle(process)


def owned_processes(application):
    command = [sys.executable, "-I", "-B", str(ROOT / "scripts/windows_owned_processes.py"),
               "--application", str(application.resolve())]
    result = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=5,
                            check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    value = json.loads(result.stdout)
    if not isinstance(value, list):
        raise ValueError("Owned process inspector did not return a complete list.")
    return value


def run_owned(command, folder, env, deadline, gate=None, application=None):
    log = folder / "console.log"
    job = OwnedJob()
    process = None
    started = time.monotonic()
    observed = None
    failure = None
    try:
        with log.open("wb") as output:
            process = subprocess.Popen(command, cwd=folder, env=env, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                job.assign(process)
            except BaseException:
                process.kill()
                raise
            if gate:
                gate.write_text("assigned\n", encoding="utf-8")
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Consumer total/step deadline exceeded.")
                if sum(p.stat().st_size for p in folder.parent.rglob("*.log")) > LIMITS["log_bytes"]:
                    raise ValueError("Consumer log limit exceeded.")
                identity_file = folder / "process-identity.json"
                if application and observed is None and identity_file.exists():
                    try:
                        identity = json.loads(identity_file.read_text(encoding="utf-8"))
                        observed = {"main": token_identity(identity["pid"]), "worker": token_identity(identity["runtime"]["workerPid"]), "processes": owned_processes(application)}
                        write_json(folder / "actual-processes.json", observed)
                    except (OSError, json.JSONDecodeError):
                        pass  # A partly written file is retried while the app is alive.
                time.sleep(0.1)
            code = process.returncode
            if code:
                raise RuntimeError(f"Consumer command exited {code}.")
            if application:
                if observed is None:
                    raise RuntimeError("Actual packaged process token/path evidence was not observed.")
                survivors = owned_processes(application)
                if survivors:
                    raise RuntimeError("Owned application processes survived graceful shutdown.")
        return dict(exit_code=code, seconds=round(time.monotonic() - started, 3), observation=observed, survivors=[])
    except BaseException as error:
        failure = f"{type(error).__name__}: {error}"
        raise
    finally:
        running = process is not None and process.poll() is None
        if running:
            process.kill()
        job.close()
        if process:
            process.wait(timeout=5)
        write_json(folder / "supervisor.json", {"status": "failed" if failure else "passed", "error": failure, "forced_cleanup": running, "exit_code": process.returncode if process else None, "elapsed_seconds": round(time.monotonic() - started, 3)})


def dialog_for(pid, observed=None):
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user.EnumChildWindows.argtypes = [wintypes.HWND, callback, wintypes.LPARAM]
    found = []

    def text(handle):
        value = ctypes.create_unicode_buffer(8192)
        user.GetWindowTextW(handle, value, len(value))
        return value.value

    def window(handle, _):
        actual = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(actual))
        if actual.value != pid:
            return True
        title = text(handle)
        if observed is not None:
            item = {"pid": pid, "handle": int(handle), "title": title[:256]}
            if item not in observed and len(observed) < 32:
                observed.append(item)
        if title == "Surge could not start":
            children = []

            def child(item, _):
                children.append({"handle": int(item), "text": text(item)})
                return True

            user.EnumChildWindows(handle, callback(child), 0)
            found.append({"handle": int(handle), "title": text(handle), "children": children})
        return True

    user.EnumWindows(callback(window), 0)
    return found


def dialog_accessible_text(handle, remaining):
    """Read only descendants of the already verified owned native dialog."""
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    env = dict(os.environ, SURGE_OWNED_DIALOG=str(handle))
    command = "$OutputEncoding=[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding $false; Add-Type -AssemblyName UIAutomationClient; Add-Type -AssemblyName UIAutomationTypes; $root=[System.Windows.Automation.AutomationElement]::FromHandle([intptr][long]$env:SURGE_OWNED_DIALOG); $items=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition); @($items | ForEach-Object { $_.Current.Name }) | ConvertTo-Json -Compress"
    result = subprocess.run([str(powershell), "-NoProfile", "-Command", command], capture_output=True, env=env, timeout=max(0.1, min(3, remaining)), check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    names = json.loads(result.stdout.decode("utf-8-sig").strip() or "[]")
    return names if isinstance(names, list) else [names]


def retain_startup_diagnostic(profile, folder):
    """Keep the owned failure log even when no actionable dialog was observed."""
    source = profile / "logs/startup.jsonl"
    try:
        with source.open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            return {"inspection": "over_read_bound", "copied": False}
        (folder / "startup.jsonl").write_bytes(raw)
        return {"inspection": "read", "copied": True, "bytes": len(raw)}
    except FileNotFoundError:
        return {"inspection": "absent", "copied": False}
    except OSError as error:
        return {"inspection": "unavailable", "copied": False,
                "error_type": type(error).__name__}


def startup_control(application, profile, folder, env, error_code, deadline):
    began = time.monotonic()
    deadline = min(deadline, began + LIMITS["startup_failure_seconds"])
    # The harmless test helper waits for job assignment before starting the real
    # packaged entry. CREATE_NO_WINDOW hides its console, not the app's dialog.
    gate = folder / "gate"
    launcher_env = dict(env)
    helper = "import pathlib,subprocess,sys,time\ngate=pathlib.Path(sys.argv[1])\nwhile not gate.exists(): time.sleep(.02)\nsys.exit(subprocess.call([sys.argv[2], '--user-data-dir='+sys.argv[3]]))"
    command = [sys.executable, "-I", "-B", "-c", helper, str(gate), str(application / "Surge.exe"), str(profile)]
    job, process, dialog = OwnedJob(), None, None
    result = {"status": "failed", "expected_error_code": error_code}
    observations = {"polls": 0, "owned_process_ids": [], "windows": [],
                    "max_processes": 32, "max_windows": 32}
    try:
        with (folder / "console.log").open("wb") as log:
            process = subprocess.Popen(command, cwd=folder, env=launcher_env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                job.assign(process)
            except BaseException:
                process.kill()
                raise
            gate.write_text("assigned", encoding="utf-8")
            while time.monotonic() < deadline:
                observations["polls"] += 1
                candidates = owned_processes(application)
                for candidate in candidates:
                    pid = candidate["ProcessId"]
                    if pid not in observations["owned_process_ids"] and len(observations["owned_process_ids"]) < 32:
                        observations["owned_process_ids"].append(pid)
                    dialogs = dialog_for(pid, observations["windows"])
                    if dialogs:
                        dialog = dialogs[0]
                        result["process"] = token_identity(candidate["ProcessId"])
                        result["dialog"] = dialog
                        dialog["accessible_names"] = dialog_accessible_text(dialog["handle"], deadline - time.monotonic())
                        write_json(folder / "native-dialog-observed.json", dialog)
                        combined = "\n".join(dialog["accessible_names"])
                        if "Diagnostic:" in combined:
                            break
                if dialog and "Diagnostic:" in "\n".join(dialog.get("accessible_names", [])):
                    break
                if process.poll() is not None:
                    raise RuntimeError("Package exited without the required actionable error dialog.")
                time.sleep(0.05)
            if dialog is None:
                raise TimeoutError("Startup error dialog exceeded 10 seconds.")
            combined = "\n".join(dialog.get("accessible_names", []))
            if "Diagnostic:" not in combined or not any(word in combined.lower() for word in ("extract", "download", "reinstall", "package")):
                raise ValueError("Startup error lacks actionable repair and diagnostic guidance.")
            buttons = [x for x in dialog["children"] if x["text"].replace("&", "") == "Close"]
            if len(buttons) != 1:
                raise ValueError("Expected exactly one owned Close button.")
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user.PostMessageW(buttons[0]["handle"], 0x00F5, 0, 0)
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            result["exit_code"] = process.returncode
            if process.returncode != 1:
                raise ValueError("Missing-component startup must exit 1.")
            logs = list(profile.rglob("startup.jsonl"))
            if len(logs) != 1:
                raise ValueError("Expected one bounded startup diagnostic.")
            diagnostic = logs[0].read_text(encoding="utf-8")
            if len(diagnostic.encode("utf-8")) > 65536 or error_code not in diagnostic:
                raise ValueError("Startup diagnostic missing expected sanitized error code.")
            shutil.copyfile(logs[0], folder / "startup.jsonl")
            if owned_processes(application):
                raise ValueError("Owned startup-control process survived shutdown.")
            result["status"] = "passed"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        job.close()
        if process:
            process.wait(timeout=5)
        if result["status"] != "passed":
            observations["startup_diagnostic"] = retain_startup_diagnostic(profile, folder)
        write_json(folder / "startup-observations.json", observations)
        result["seconds"] = round(time.monotonic() - began, 3)
        if result["seconds"] > LIMITS["startup_failure_seconds"]:
            result["status"] = "failed"
        write_json(folder / "results.json", result)
    if result["status"] != "passed":
        raise TimeoutError("Startup control exceeded its original 10-second limit.")
    return result


def execute_steps(steps, report, save):
    """Fail closed, retain prior checks, and explicitly mark dependent work not run."""
    for name, action in steps:
        item = next(x for x in report["steps"] if x["name"] == name)
        started = time.monotonic()
        try:
            item["evidence"] = action()
            item["status"] = "passed"
        except Exception as error:
            item.update(status="failed", error=f"{type(error).__name__}: {error}")
            report["error"] = item["error"]
            return False
        finally:
            item["seconds"] = round(time.monotonic() - started, 3)
            save()
    return True


def verify_evidence(report_path, manifest, expected_failure=False):
    """Portable read-only check; reject missing checks, drift, and changed artifacts."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    report_path = Path(report_path)
    base = report_path.parent
    report = json.loads(report_path.read_text(encoding="utf-8"))
    require(report.get("schema") == "surge-windows-package-consumer-v1", "Unknown consumer report schema.")
    require(report.get("limits") == LIMITS, "Consumer limits changed.")
    require(0 <= report["elapsed_seconds"] <= LIMITS["total_seconds"], "Consumer elapsed time exceeded.")
    require(report["archive"] == manifest["archive"] and report["source"] == manifest["source"], "Consumer package/source identity differs.")
    require(report["manifest_sha256"] == digest(base / "package-manifest.json"), "Copied package manifest digest differs.")
    require(json.loads((base / "package-manifest.json").read_text(encoding="utf-8")) == manifest, "Copied manifest contents differ.")
    require([x["name"] for x in report["steps"]] == list(STEPS), "Consumer steps missing or reordered.")
    inventory = report["evidence_files"]
    names = [x["path"] for x in inventory]
    require(len(names) == len(set(names)), "Duplicate evidence entry.")
    actual = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and p != report_path}
    require(set(names) == actual, "Evidence file inventory differs.")
    for item in inventory:
        safe_member(item["path"])
        require(file_record(base / item["path"], base) == item, "Evidence digest/length differs: " + item["path"])
    require(sum(x["bytes"] for x in inventory) + report.get("retained_profile_bytes", 0) <= LIMITS["evidence_bytes"], "Evidence/profile size limit exceeded.")
    require(sum(x["bytes"] for x in inventory if x["path"].endswith(".log")) <= LIMITS["log_bytes"], "Log size limit exceeded.")
    require([x["path"] for x in report["harness_source"]] == ["harness-source/" + x for x in HARNESS], "Frozen consumer harness source incomplete.")
    require(all(file_record(base / x["path"], base) == x for x in report["harness_source"]), "Frozen harness source identity changed.")
    require(report["harness_source_unchanged"] is True, "Consumer harness changed while running.")
    if manifest["source"]["dirty"] is False:
        require(report["harness_source_matches_package"] is True and all(manifest["source"]["files"].get(x["path"].removeprefix("harness-source/")) == x["sha256"] for x in report["harness_source"]), "Clean hosted harness differs from package source candidate.")
    if expected_failure:
        require(report["status"] == "failed" and report.get("failure_probe") == "verified_expected_failure", "Expected failing probe was not retained as failed.")
        require([x["status"] for x in report["steps"]] == ["passed", "failed"] + ["not_run"] * (len(STEPS) - 2), "Failure probe allowed dependent checks.")
        receipt = json.loads((base / "failure-probe-receipt.json").read_text())
        failure = json.loads((base / "failure-probe/supervisor.json").read_text())
        timeout = json.loads((base / "timeout-probe/supervisor.json").read_text())
        require(receipt["status"] == "verified_expected_failure" and receipt["exit_code"] == 73 and receipt["timeout_seconds"] == 1, "Failure receipt differs.")
        require(failure["status"] == "failed" and failure["exit_code"] == 73, "Process failure was hidden.")
        require(timeout["status"] == "failed" and timeout["forced_cleanup"] is True and "TimeoutError" in timeout["error"] and timeout["exit_code"] != 0, "Actual timeout/cleanup was not demonstrated.")
        require(receipt["marker"] in (base / "failure-probe/console.log").read_text() and receipt["timeout_marker"] in (base / "timeout-probe/console.log").read_text(), "Actual failure/timeout helper did not run.")
        return {"status": "verified_expected_failure", "archive_sha256": manifest["archive"]["sha256"], "evidence_files": len(inventory)}
    require(report["status"] == "passed" and all(x["status"] == "passed" for x in report["steps"]), "Consumer steps did not all pass.")
    require(report["criteria"] == {f"W{i}": "passed" for i in range(2, 7)}, "Consumer criteria incomplete.")
    for mode, count in (("journey", 12), ("replacement", 7), ("mismatch", 4)):
        ui = json.loads((base / mode / "results.json").read_text(encoding="utf-8"))
        require(ui["schema"] == "surge-packaged-ui-v1" and ui["mode"] == mode and ui["status"] == "passed", "Packaged UI report did not pass.")
        require(len(ui["checks"]) == count and len({x["name"] for x in ui["checks"]}) == count and all(x["status"] == "passed" and x.get("milliseconds", 0) <= 30000 for x in ui["checks"]), "UI check missing, failed, or over action limit.")
        require(ui["checks"][-1]["name"] == "graceful shutdown" and ui["renderer_errors"] == [], "UI cleanup/error checks incomplete.")
        observed = json.loads((base / mode / "actual-processes.json").read_text(encoding="utf-8"))
        identity = ui["identity"]
        require(observed["main"]["pid"] == identity["pid"] and observed["worker"]["pid"] == identity["runtime"]["workerPid"], "Observed process identity differs.")
        require(type(observed["main"]["token_elevated"]) is bool and type(observed["worker"]["token_elevated"]) is bool, "Actual process token not recorded.")
        require(identity["runtime"]["packaged"] is True and identity["runtime"]["ready"] is True, "Packaged readiness not established.")
        require(identity["runtime"]["pythonVersion"] == manifest["runtimes"]["python"]["version"] and identity["versions"]["electron"] == manifest["runtimes"]["electron"]["version"], "Actual bundled runtime versions differ.")
        if mode in ("journey", "mismatch"):
            name = "exact bundled demo approval and stopped capture" if mode == "journey" else "mismatched owned approval never becomes approved"
            evidence = next(x["evidence"] for x in ui["checks"] if x["name"] == name)
            require(len(evidence["sample_running"]) == 1 and evidence["sample_running"][0]["ParentProcessId"] == identity["runtime"]["workerPid"] and evidence["sample_stopped"] == [], "Actual owned sample start/stop was not established.")
        supervisor = json.loads((base / mode / "supervisor.json").read_text())
        require(supervisor["status"] == "passed" and supervisor["exit_code"] == 0 and supervisor["forced_cleanup"] is False, "UI supervisor did not close cleanly.")
    before, after = [json.loads((base / f"case-fingerprints-{which}.json").read_text()) for which in ("before", "after")]
    require(bool(before) and before == after, "Saved case contents changed during replacement.")
    for name, code in (("missing_runtime", "SURGE_BUNDLED_PYTHON_MISSING"), ("missing_backend", "SURGE_BACKEND_MISSING"), ("missing_sample", "SURGE_SAMPLE_MISSING")):
        result = json.loads((base / name / "results.json").read_text())
        require(result["status"] == "passed" and result["expected_error_code"] == code and result["exit_code"] == 1 and result["seconds"] <= LIMITS["startup_failure_seconds"], "Startup failure control incomplete.")
        messages = [json.loads(line) for line in (base / name / "startup.jsonl").read_text().splitlines()]
        require(messages and any(x["code"] == code for x in messages), "Expected startup diagnostic missing.")
        require(all(set(x) == {"time", "phase", "status", "code", "version", "mode"} for x in messages), "Diagnostic contains fields outside the allowlist.")
    return {"status": "passed", "archive_sha256": manifest["archive"]["sha256"], "evidence_files": len(inventory), "criteria": report["criteria"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "verification/qualification")
    parser.add_argument("--node", type=Path)
    parser.add_argument("--ordinary-profile", action="store_true")
    parser.add_argument("--probe-failure", action="store_true")
    args = parser.parse_args(argv)
    folder = args.output_root.resolve() / ("windows-consumer-" + uuid.uuid4().hex[:12])
    artifacts, workspace = folder / "artifacts", folder / "workspace"
    artifacts.mkdir(parents=True)
    workspace.mkdir()
    report = dict(schema="surge-windows-package-consumer-v1", status="failed", started=utc(), limits=LIMITS,
                  criteria={f"W{i}": "not_run" for i in range(2, 7)},
                  steps=[dict(name=name, status="not_run") for name in STEPS], human_acceptance="pending",
                  limitations=["Automated owned-fixture check, not unfamiliar-user acceptance.", "Native file dialogs select owned fixtures through main-process substitution.", "Hosted tools are present; application lookup and runtime paths are isolated, not physically absent.", "Identical ZIP folder replacement is not cross-version migration, an installer, or power-loss testing.", "No Authenticode/SmartScreen reputation or pristine physical Windows desktop claim.", "Separate standard-user hosted account launch is not verified; actual child token elevation is recorded."])
    began, manifest = time.monotonic(), None
    deadline = began + LIMITS["total_seconds"]
    save = lambda: write_json(artifacts / "report.json", report)
    save()
    try:
        if os.name != "nt":
            raise RuntimeError("Windows consumer required.")
        archive = args.package.resolve()
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report.update(source=manifest["source"], archive=manifest["archive"], manifest_sha256=digest(args.manifest))
        shutil.copyfile(args.manifest, artifacts / "package-manifest.json")
        report["download_metadata"] = {"archive": zone_identifier(archive), "primary_executable": None,
                                       "smartscreen": "Not separately exercised; programmatic file delivery and direct test launch do not establish browser download warning/reputation behavior."}
        report["harness_source"] = []
        for relative in HARNESS:
            destination = artifacts / "harness-source" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
            report["harness_source"].append(file_record(destination, artifacts))
        source_files = manifest["source"].get("files", {})
        report["harness_source_matches_package"] = all(source_files.get(relative) == digest(ROOT / relative) for relative in HARNESS)
        report["environment"] = dict(hosted=os.environ.get("GITHUB_ACTIONS") == "true", runner_os=os.environ.get("RUNNER_OS"), platform=platform.platform(), windows_version=platform.version(), image=os.environ.get("ImageVersion"), token_elevated=token_identity(os.getpid())["token_elevated"], profile_mode="ordinary" if args.ordinary_profile else "owned_explicit")
        if args.probe_failure:
            verify_package(archive, manifest)
            report["steps"][0]["status"] = "passed"
            report["steps"][1].update(status="failed", error="Declared owned supervisor failure marker; exit 73.")
            report["error"] = report["steps"][1]["error"]
            probe = artifacts / "failure-probe"
            probe.mkdir()
            try:
                run_owned([sys.executable, "-I", "-B", "-c", "import sys; print('SURGE_PACKAGE_FAILURE_PROBE'); sys.exit(73)"], probe, os.environ.copy(), min(deadline, time.monotonic() + 10))
            except RuntimeError as error:
                if "exited 73" not in str(error):
                    raise
            else:
                raise ValueError("Failure probe did not propagate its failing process exit.")
            timeout_probe = artifacts / "timeout-probe"
            timeout_probe.mkdir()
            try:
                run_owned([sys.executable, "-I", "-B", "-u", "-c", "import time; print('SURGE_PACKAGE_TIMEOUT_PROBE', flush=True); time.sleep(30)"], timeout_probe, os.environ.copy(), min(deadline, time.monotonic() + 1))
            except TimeoutError:
                pass
            else:
                raise ValueError("Timeout probe did not propagate its deadline failure.")
            report["failure_probe"] = "verified_expected_failure"
            write_json(artifacts / "failure-probe-receipt.json", dict(status="verified_expected_failure", marker="SURGE_PACKAGE_FAILURE_PROBE", exit_code=73, timeout_marker="SURGE_PACKAGE_TIMEOUT_PROBE", timeout_seconds=1, later_steps="not_run", limitation="Supervised child failure/timeout only; not runner loss, cancellation, or artifact service outage."))
            return 1
        node = (args.node or Path(shutil.which("node") or "")).resolve()
        if not node.is_file():
            raise ValueError("An absolute test-harness Node executable is required.")
        profile = ordinary_appdata() / "surge-desktop" if args.ordinary_profile else workspace / "owned profile"
        if os.path.lexists(profile):
            raise RuntimeError("Refusing an existing profile; no user cases may be touched.")
        temporary = workspace / "temporary"
        temporary.mkdir()
        unrelated = workspace / "unrelated working directory"
        unrelated.mkdir()
        app_env = restricted_environment(temporary)
        report["application_environment"] = app_env
        report["profile"] = str(profile)
        fixtures = artifacts / "fixtures"
        fixtures.mkdir()
        raw = fixtures / "owned.jsonl"
        raw.write_bytes(b'{"reading":10}\n{"reading":90}\n')
        policy = fixtures / "owned.policy.json"
        write_json(policy, {"schema": "surge-policy-v1", "settings": {"features": [], "session": None, "event_id": None, "time": None, "time_format": "milliseconds", "threshold": 6, "rules": [{"name": "Owned reading limit", "field": "reading", "op": "gt", "value": 50}]}})
        existing = fixtures / "existing-source.case.json"
        shutil.copyfile(ROOT / "demos/native/approved-update.case.json", existing)
        published = json.loads((ROOT / "demos/native/expected.json").read_text(encoding="utf-8"))["cases"][0]
        if digest(existing) != published["sha256"]:
            raise ValueError("Existing source-format fixture identity changed.")
        if any(p.stat().st_size > LIMITS["input_bytes"] for p in fixtures.iterdir()):
            raise ValueError("Owned input exceeds 256 KiB.")
        primary, replacement, controls = (workspace / name for name in ("first extraction é", "replacement folder 日本", "failure controls"))
        retained = artifacts / "retained.json"
        base = dict(profile=str(profile), profile_mode=report["environment"]["profile_mode"], cwd=str(unrelated), app_env=app_env, raw_source=str(raw), raw_sha256=digest(raw), policy=str(policy), existing_case=str(existing), existing_sha256=digest(existing), existing_summary={"total": len(published["outcomes"]), **{s: published["outcomes"].count(s) for s in ("Review", "Unknown", "No finding")}}, exported=str(fixtures / "portable.case.json"), retained=str(retained), sample_ranges=len(manifest["sample"]["entries"]) if isinstance(manifest["sample"]["entries"], list) else manifest["sample"]["entries"], python_version=manifest["runtimes"]["python"]["version"], electron_version=manifest["runtimes"]["electron"]["version"])
        base.update(inspector_python=sys.executable, process_inspector=str(ROOT / "scripts/windows_owned_processes.py"))
        before_cases = {}

        def ui(mode, application, name, alternate_profile=None):
            output = artifacts / name
            output.mkdir()
            config = dict(base, mode=mode, application=str(application), executable=str(application / "Surge.exe"), output=str(output), gate=str(output / "gate"))
            if alternate_profile:
                config.update(profile=str(alternate_profile), profile_mode="owned_explicit")
            write_json(output / "config.json", config)
            result = run_owned([str(node), str(ROOT / "desktop/packaged.test.cjs"), str(output / "config.json")], output, os.environ.copy(), deadline, Path(config["gate"]), application)
            ui_report = json.loads((output / "results.json").read_text(encoding="utf-8"))
            if ui_report.get("schema") != "surge-packaged-ui-v1" or ui_report.get("status") != "passed" or any(x["status"] != "passed" for x in ui_report["checks"]):
                raise ValueError("Packaged UI report did not pass.")
            return {"supervisor": result, "report": file_record(output / "results.json", artifacts), "log": file_record(output / "console.log", artifacts)}

        def journey():
            report["download_metadata"]["primary_executable"] = zone_identifier(primary / "Surge.exe")
            result = ui("journey", primary, "journey")
            before_cases.update({p.relative_to(profile).as_posix(): digest(p) for p in (profile / "cases").rglob("*") if p.is_file()})
            write_json(artifacts / "case-fingerprints-before.json", before_cases)
            return result

        def reopen():
            result = ui("replacement", replacement, "replacement")
            after = {p.relative_to(profile).as_posix(): digest(p) for p in (profile / "cases").rglob("*") if p.is_file()}
            write_json(artifacts / "case-fingerprints-after.json", after)
            if after != before_cases:
                raise ValueError("Case library contents changed during folder replacement.")
            return result

        def mismatch():
            extract_verified(archive, controls)
            registry = controls / "resources/app/native/baselines.json"
            original = registry.read_bytes()
            value = json.loads(original)
            for entry in value["entries"]:
                entry["module_sha256"] = "0" * 64
            write_json(registry, value)
            try:
                return ui("mismatch", controls, "mismatch", workspace / "mismatch profile")
            finally:
                registry.write_bytes(original)

        def missing(name, relative, code):
            output = artifacts / name
            output.mkdir()
            component = controls / relative
            hidden = component.with_name(component.name + ".owned-test-unavailable")
            component.rename(hidden)
            try:
                return startup_control(controls, workspace / (name + " profile"), output, app_env, code, deadline)
            finally:
                hidden.rename(component)

        steps = [("package_identity", lambda: verify_package(archive, manifest)),
                 ("extract_primary", lambda: extract_verified(archive, primary)),
                 ("packaged_journey", journey),
                 ("extract_replacement", lambda: extract_verified(archive, replacement)),
                 ("packaged_replacement", reopen),
                 ("approval_mismatch", mismatch),
                 ("missing_runtime", lambda: missing("missing_runtime", "resources/python/python.exe", "SURGE_BUNDLED_PYTHON_MISSING")),
                 ("missing_backend", lambda: missing("missing_backend", "resources/app/desktop_worker.py", "SURGE_BACKEND_MISSING")),
                 ("missing_sample", lambda: missing("missing_sample", "resources/app/native/build/surge_owned_app.exe", "SURGE_SAMPLE_MISSING")),
                 ("immutable_payloads", lambda: {"primary": verify_payload(primary, manifest), "replacement": verify_payload(replacement, manifest), "restored_controls": verify_payload(controls, manifest)})]
        if execute_steps(steps, report, save):
            report["status"] = "passed"
        passed = {x["name"] for x in report["steps"] if x["status"] == "passed"}
        for criterion, required in {"W2": {"packaged_journey"}, "W3": {"packaged_journey", "approval_mismatch"}, "W4": {"packaged_journey", "packaged_replacement"}, "W5": {"packaged_replacement", "immutable_payloads"}, "W6": {"missing_runtime", "missing_backend", "missing_sample"}}.items():
            report["criteria"][criterion] = "passed" if required <= passed else "not_completed"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        report["finished"] = utc()
        report["elapsed_seconds"] = round(time.monotonic() - began, 3)
        if report.get("harness_source"):
            report["harness_source_unchanged"] = all(digest(ROOT / item["path"].removeprefix("harness-source/")) == item["sha256"] for item in report["harness_source"])
            if not report["harness_source_unchanged"]:
                report.update(status="failed", error="Consumer harness source changed during this attempt.")
        profiles = [p for p in workspace.iterdir() if p.is_dir() and "profile" in p.name]
        if args.ordinary_profile and 'profile' in locals() and profile.exists():
            profiles.append(profile)
        report["retained_profile_bytes"] = sum(p.stat().st_size for directory in profiles for p in directory.rglob("*") if p.is_file())
        files = [p for p in artifacts.rglob("*") if p.is_file() and p.name not in ("report.json", "report.json.tmp")]
        report["evidence_files"] = [file_record(p, artifacts) for p in sorted(files)]
        if sum(p.stat().st_size for p in files) + report["retained_profile_bytes"] > LIMITS["evidence_bytes"] or sum(p.stat().st_size for p in files if p.suffix == ".log") > LIMITS["log_bytes"] or report["elapsed_seconds"] > LIMITS["total_seconds"]:
            report.update(status="failed", error="Original evidence/time bound exceeded.")
        save()
        print(json.dumps({"status": report["status"], "report": str(artifacts / "report.json")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

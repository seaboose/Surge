"""Read Windows process identity for only the owned package's executable paths."""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import time

INSPECTION_SECONDS = 5
NAMES = frozenset(("surge.exe", "python.exe", "surge_owned_app.exe",
                   "surgemovementlab.exe", "surgemovementlab-win64-development.exe",
                   "surgemovementlab-win64-shipping.exe"))
ERROR_NO_MORE_FILES = 18
ERROR_INVALID_PARAMETER = 87
STILL_ACTIVE = 259
INVALID_HANDLE = ctypes.c_void_p(-1).value


class ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


def kernel_api():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        function = getattr(api, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        function.restype = wintypes.BOOL
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.QueryFullProcessImageNameW.restype = wintypes.BOOL
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def image_path(api, pid):
    handle = api.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION only.
    if not handle:
        error = ctypes.get_last_error()
        if error == ERROR_INVALID_PARAMETER:
            return None  # PID ended between snapshot and handle acquisition.
        raise OSError(error, "Cannot inspect a relevant process; ownership is unverified.")
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            error = ctypes.get_last_error()
            exit_code = wintypes.DWORD()
            if api.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value != STILL_ACTIVE:
                return None
            raise OSError(error, "Cannot read a live relevant process image; ownership is unverified.")
        return buffer.value
    finally:
        api.CloseHandle(handle)


def processes_owned_by(application, *, api=None, clock=time.monotonic):
    """No WMI startup; fail closed on incomplete inspection within the same 5s."""
    if os.name != "nt":
        raise RuntimeError("Windows process inspection required.")
    deadline = clock() + INSPECTION_SECONDS
    root = os.path.normcase(str(Path(application).resolve())) + os.sep
    api = api or kernel_api()
    snapshot = api.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS.
    if not snapshot or snapshot == INVALID_HANDLE:
        raise OSError(ctypes.get_last_error(), "Cannot establish a process snapshot.")
    result = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        available = api.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            if clock() >= deadline:
                raise TimeoutError("Owned process inspection exceeded its 5-second limit.")
            # Only these names can be the package components under inspection.
            # Other process paths and command lines are neither queried nor kept.
            if entry.szExeFile.casefold() in NAMES:
                image = image_path(api, entry.th32ProcessID)
                if image and os.path.normcase(image).startswith(root):
                    result.append({"ProcessId": entry.th32ProcessID,
                                   "ParentProcessId": entry.th32ParentProcessID,
                                   "ExecutablePath": image})
            available = api.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != ERROR_NO_MORE_FILES:
            raise OSError(ctypes.get_last_error(), "Process snapshot enumeration was incomplete.")
        if clock() >= deadline:
            raise TimeoutError("Owned process inspection exceeded its 5-second limit.")
        return result
    finally:
        api.CloseHandle(snapshot)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = processes_owned_by(args.application)
    except Exception as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 1
    print(json.dumps(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

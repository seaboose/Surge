"""Windows process-tree memory sampler for isolated desktop benchmarks only."""

import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import sys
import time


class Entry(c.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("usage", w.DWORD),
        ("pid", w.DWORD),
        ("heap", c.c_size_t),
        ("module", w.DWORD),
        ("threads", w.DWORD),
        ("parent", w.DWORD),
        ("priority", w.LONG),
        ("flags", w.DWORD),
        ("name", w.WCHAR * 260),
    ]


class Memory(c.Structure):
    _fields_ = [("size", w.DWORD), ("faults", w.DWORD)] + [
        (name, c.c_size_t)
        for name in (
            "peak_working_set",
            "working_set",
            "peak_paged",
            "paged",
            "peak_nonpaged",
            "nonpaged",
            "pagefile",
            "peak_pagefile",
            "private",
        )
    ]


kernel = c.WinDLL("kernel32", use_last_error=True)
psapi = c.WinDLL("psapi", use_last_error=True)
kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [w.HANDLE, c.POINTER(Entry)]
kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel.OpenProcess.restype = w.HANDLE
kernel.CloseHandle.argtypes = [w.HANDLE]
psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, c.POINTER(Memory), w.DWORD]


def processes(root):
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == c.c_void_p(-1).value:
        raise c.WinError(c.get_last_error())
    entries = {}
    try:
        entry = Entry(size=c.sizeof(Entry))
        more = kernel.Process32FirstW(handle, c.byref(entry))
        while more:
            entries[entry.pid] = (entry.parent, entry.name)
            more = kernel.Process32NextW(handle, c.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    chosen = {root} if root in entries else set()
    while True:
        children = {pid for pid, (parent, _) in entries.items() if parent in chosen}
        if children <= chosen:
            break
        chosen |= children
    result = []
    for pid in sorted(chosen):
        handle = kernel.OpenProcess(0x410, False, pid)
        if not handle:
            result.append(dict(pid=pid, error=c.get_last_error()))
            continue
        try:
            memory = Memory(size=c.sizeof(Memory))
            if psapi.GetProcessMemoryInfo(handle, c.byref(memory), memory.size):
                result.append(
                    dict(
                        pid=pid,
                        name=entries[pid][1],
                        private=memory.private,
                        working_set=memory.working_set,
                    )
                )
            else:
                result.append(dict(pid=pid, error=c.get_last_error()))
        finally:
            kernel.CloseHandle(handle)
    return result


if __name__ == "__main__":
    root, output, stage_file, stop_file = int(sys.argv[1]), *map(Path, sys.argv[2:5])
    duration = min(1800, max(1, int(sys.argv[5]))) if len(sys.argv) > 5 else 180
    start = time.perf_counter()
    with output.open("w", encoding="utf-8") as stream:
        while not stop_file.exists() and time.perf_counter() - start < duration:
            phase = stage_file.read_text(encoding="utf-8") if stage_file.exists() else "startup"
            items = processes(root)
            stream.write(
                json.dumps(
                    dict(
                        ms=round((time.perf_counter() - start) * 1000), phase=phase, processes=items
                    )
                )
                + "\n"
            )
            stream.flush()
            time.sleep(0.1)

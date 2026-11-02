"""One owned Python worker gated behind a verified Windows job memory limit."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from run_stream_model import ROOT, MEMORY_LIMIT, EXTENDED, kernel, check_windows, canonical


def run(worker, recipe, folder, seconds=5):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    request = dict(recipe=recipe, folder=str(folder))
    (folder / "request.json").write_bytes(canonical(request))
    result = dict(status="failed", timeout_seconds=seconds, process_memory_limit=MEMORY_LIMIT,
                  recipe_sha256=hashlib.sha256(canonical(recipe)).hexdigest(), timed_out=False)
    api, job, child = kernel(), None, None
    started = time.monotonic()
    try:
        job = api.CreateJobObjectW(None, None); check_windows(job)
        limits = EXTENDED()
        limits.BasicLimitInformation.LimitFlags = 0x100 | 0x2000
        limits.ProcessMemoryLimit = MEMORY_LIMIT
        check_windows(api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        with (folder / "stdout.log").open("wb") as out, (folder / "stderr.log").open("wb") as err:
            child = subprocess.Popen([sys.executable, "-B", str(ROOT / worker)], cwd=ROOT,
                                     stdin=subprocess.PIPE, stdout=out, stderr=err,
                                     env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            check_windows(api.AssignProcessToJobObject(job, wintypes.HANDLE(int(child._handle))))
            confirmed = EXTENDED()
            check_windows(api.QueryInformationJobObject(job, 9, ctypes.byref(confirmed),
                                                       ctypes.sizeof(confirmed), None))
            assert confirmed.ProcessMemoryLimit == MEMORY_LIMIT
            assert confirmed.BasicLimitInformation.LimitFlags & 0x100
            result["job_limit_verified"] = True
            child.stdin.write(canonical(request) + b"\n"); child.stdin.close()
            try: child.wait(timeout=max(0.001, seconds - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                result["timed_out"] = True; child.kill(); child.wait(timeout=3)
        peak = EXTENDED()
        check_windows(api.QueryInformationJobObject(job, 9, ctypes.byref(peak), ctypes.sizeof(peak), None))
        result.update(exit_code=child.returncode, peak_private_bytes=peak.PeakProcessMemoryUsed,
                      seconds=round(time.monotonic() - started, 6))
        assert 0 < peak.PeakProcessMemoryUsed <= MEMORY_LIMIT
        assert not result["timed_out"] and child.returncode == 0
        raw = (folder / "stdout.log").read_bytes()
        assert len(raw) <= 10 * 1024 * 1024
        payload = json.loads(raw)
        assert payload["status"] == "passed" and payload["recipe_sha256"] == result["recipe_sha256"]
        assert payload["result_sha256"] == hashlib.sha256(canonical(payload["result"])).hexdigest()
        result.update(status="passed", payload=payload)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if child and child.poll() is None: child.kill(); child.wait(timeout=3)
        if job: api.CloseHandle(job)
        result.setdefault("seconds", round(time.monotonic() - started, 6))
        (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result

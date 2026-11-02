"""Windows owned-app reliability checks and full-desktop resource measurements.

Run --phase faults first, then --phase desktop (about eleven minutes).
Raw evidence stays in ignored verification/electron folders. No local approval
registry is changed. The measurement harness is excluded from process totals.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine
import native_integrity as native
import native_stream
from native_capture import collect
from scripts.test_native_stream import OwnedProcess, analyze, resources


def percentile(values, fraction=0.95):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def fingerprints():
    paths = [
        ROOT / p
        for p in (
            "native_stream.py",
            "native_integrity.py",
            "integrity_manifest.py",
            "engine.py",
            "desktop_worker.py",
            "desktop/main.cjs",
            "desktop/src/main.jsx",
            "desktop/reliability.cjs",
            "scripts/measure_reliability.py",
            "docs/performance-reliability.md",
        )
    ]
    paths += sorted((ROOT / "native").glob("*.cpp"))
    paths += sorted((ROOT / "native").glob("*.hpp"))
    paths += sorted((ROOT / "native/build").glob("*.exe"))
    paths += sorted((ROOT / "native/build").glob("*.dll"))
    return {
        str(p.relative_to(ROOT)).replace("\\", "/"): {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "lf_sha256": (
                hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                if p.suffix not in (".exe", ".dll")
                else None
            ),
        }
        for p in paths
    }


def environment():
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
    ) as key:
        cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0]
    return dict(
        windows=platform.platform(),
        python=platform.python_version(),
        logical_processors=os.cpu_count(),
        cpu=cpu,
    )


def wait_samples(session, count):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if session.status()["samples"] >= count:
            return
        time.sleep(0.02)
    raise AssertionError("Owned session did not resume in five seconds")


def faults(report):
    registry = native.approve(
        collect("v1", "clean"),
        dict(schema=native.BASELINE_SCHEMA, entries=[]),
        "Explicit in-memory approval for controlled reliability trials",
    )
    latencies = []
    with OwnedProcess(interval=500) as child:
        decoder = native_stream.StreamDecoder(registry)
        decoder.accept(child.frame())

        def next_sample(boundary):
            while True:
                frame = child.frame()
                rows = decoder.accept(frame)
                if rows and frame["sequence"] >= boundary:
                    return rows

        next_sample(1)
        for trial in range(10):
            boundary = child.command("change-primary")
            start = time.perf_counter()
            rows = next_sample(boundary)
            # A standalone retained sample declares earlier omitted samples.
            snapshot = native_stream.snapshot_rows(
                [rows], evicted=rows[0]["stream_sequence"] - 1, final_sequence=decoder.sequence
            )
            result = analyze(snapshot)
            latency = (time.perf_counter() - start) * 1000
            assert result["records"][0]["status"] == "Review", result["summary"]
            assert rows[0]["memory_matches"] is False
            latencies.append(latency)
            boundary = child.command("restore")
            restored = next_sample(boundary)
            assert all(r["memory_matches"] is True for r in restored)
    report["detection_ms"] = latencies
    report["checks"]["persistent_change_latency"] = max(latencies) <= 1500
    with OwnedProcess(interval=100, duration=20000, read=False) as child:
        usage = []
        for _ in range(4):
            time.sleep(2)
            usage.append(resources(child.process))
        child.start_reader(child.process.stdout, child.frames, True)
        child.process.stdin.write(b"stop\n")
        child.process.stdin.flush()
        decoder = native_stream.StreamDecoder(registry)
        groups = []
        while frame := child.frame():
            rows = decoder.accept(frame)
            if rows:
                groups.append(rows)
        assert child.process.wait(timeout=5) == 0
        assert decoder.ended and decoder.dropped_samples > 0
        snapshot = native_stream.snapshot_rows(
            groups, dropped=decoder.dropped_samples, final_sequence=decoder.sequence
        )
        result = analyze(snapshot)
        assert result["summary"]["Unknown"] == 1
        report["backpressure"] = dict(
            dropped=decoder.dropped_samples,
            received=len(groups),
            measurements=usage,
            summary=result["summary"],
        )
        report["checks"]["slow_consumer"] = max(u["private_bytes"] for u in usage) < 32 * 1024**2
    session = native_stream.NativeSession("v1", registry)
    try:
        wait_samples(session, 2)
        ntdll = ctypes.WinDLL("ntdll")
        for name in ("NtSuspendProcess", "NtResumeProcess"):
            function = getattr(ntdll, name)
            function.argtypes = [wintypes.HANDLE]
            function.restype = ctypes.c_long
        # Suspend ONLY the child created by this session, never a discovered PID.
        handle = wintypes.HANDLE(int(session.process._handle))
        assert ntdll.NtSuspendProcess(handle) == 0
        try:
            time.sleep(6)
            stale = session.snapshot()
            assert analyze(stale)["summary"]["Unknown"] == 1
            count = session.status()["samples"]
        finally:
            assert ntdll.NtResumeProcess(handle) == 0
        wait_samples(session, count + 2)
        assert session.status()["error"] is None
        session.process.kill()
        assert session.closed.wait(5)
        failed = session.snapshot()
        assert session.status()["state"] == "failed"
        result = analyze(failed)
        assert result["summary"]["Unknown"] == 1
        assert all(r["memory_matches"] is True for r in failed if not r.get("stream_health"))
        report["stall_and_crash"] = dict(
            stale_unknown=1,
            recovered=True,
            crash_summary=result["summary"],
            reader_exited=not session.reader.is_alive(),
        )
        report["checks"]["stall_recovery_crash"] = not session.reader.is_alive()
    finally:
        session.stop()


def desktop(report, folder):
    samples = report["resources"] = []
    with (folder / "node-stderr.log").open("w", encoding="utf-8") as errors:
        child = subprocess.Popen(
            ["node", str(ROOT / "desktop/reliability.cjs"), str(folder)],
            cwd=ROOT / "desktop",
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            encoding="utf-8",
        )
        for line in child.stdout:
            event = json.loads(line)
            if event["type"] == "resources":
                readings = []
                for process in event.pop("processes"):
                    try:
                        readings.append(
                            dict(process, **resources(SimpleNamespace(pid=process["pid"])))
                        )
                    except OSError as error:
                        report.setdefault("measurement_errors", []).append(str(error))
                event["readings"] = readings
                event["private_bytes"] = sum(r["private_bytes"] for r in readings)
                samples.append(event)
            else:
                print(json.dumps(event), flush=True)
        code = child.wait(timeout=10)
    data = json.loads((folder / "desktop.json").read_text())
    report["desktop"] = data
    if code or not data.get("passed"):
        raise AssertionError(data.get("error", "Desktop measurement failed"))
    active = [s for s in samples if s["phase"] == "capture" and s["capture"]["state"] == "running"]

    def median_window(low, high):
        return statistics.median(s["private_bytes"] for s in active if low <= s["elapsed"] <= high)

    cpu = 0
    previous = {}
    for sample in active:
        for reading in sample["readings"]:
            pid = reading["pid"]
            if pid in previous:
                cpu += max(0, reading["cpu_seconds"] - previous[pid])
            previous[pid] = reading["cpu_seconds"]
    cpu_percent = cpu / (active[-1]["elapsed"] - active[0]["elapsed"]) * 100
    growth = median_window(540, 600) - median_window(300, 360)
    before = next(s for s in samples if s["phase"] == "before_cycles")
    after = next(s for s in samples if s["phase"] == "after_cycles")
    cycle_growth = after["private_bytes"] - before["private_bytes"]
    capture = data["final_capture"]
    report["metrics"] = dict(
        cpu_percent_one_core=cpu_percent,
        peak_sampled_private_bytes=max(s["private_bytes"] for s in active),
        steady_private_growth_bytes=growth,
        cycle_private_growth_bytes=cycle_growth,
        sample_gap_p95_ms=percentile(data["gaps_ms"]),
        sample_gap_max_ms=max(data["gaps_ms"]),
        resource_samples=len(active),
        resource_max_gap_seconds=max(
            b["elapsed"] - a["elapsed"] for a, b in zip(active, active[1:])
        ),
    )
    report["checks"].update(
        complete_capture=capture["samples"] >= 1000
        and capture["dropped_samples"] == 0
        and data["capture_seconds"] <= 615,
        bounded_window=capture["records"] <= 1000
        and data["export_bytes"] <= 8 * 1024**2
        and len(data["health"]) == 1
        and data["summary"]["Unknown"] == 1,
        memory=report["metrics"]["peak_sampled_private_bytes"] < 1024**3 and growth <= 64 * 1024**2,
        cpu=cpu_percent < 15,
        cadence=percentile(data["gaps_ms"]) <= 750 and max(data["gaps_ms"]) <= 2500,
        responsiveness=all(
            o["ms"] <= 3000
            for o in data["operations"]
            if o["method"] in ("native_snapshot", "native_export", "native_stop")
        ),
        restarts=len(data["cycles"]) == 20
        and all(c["first_sample_ms"] <= 3000 and c["exit_wait_ms"] <= 5000 for c in data["cycles"]),
        cycle_memory=cycle_growth <= 64 * 1024**2,
        shutdown=data["shutdown_ms"] <= 5000,
        no_errors=not data["errors"] and not report.get("measurement_errors"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("faults", "desktop"), required=True)
    args = parser.parse_args()
    folder = (
        ROOT / "verification/electron" / ("reliability-" + args.phase + "-" + uuid.uuid4().hex[:8])
    )
    folder.mkdir(parents=True)
    report = dict(
        schema="surge-reliability-v1",
        phase=args.phase,
        started_utc=datetime.now(timezone.utc).isoformat(),
        environment=environment(),
        fingerprints=fingerprints(),
        checks={},
    )
    print(f"Evidence: {folder}", flush=True)
    try:
        faults(report) if args.phase == "faults" else desktop(report, folder)
        report["passed"] = all(report["checks"].values())
    except Exception as error:
        report["passed"] = False
        report["error"] = repr(error)
        raise
    finally:
        (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "checks": report["checks"]}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

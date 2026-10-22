"""Independent, bounded checks of the owned application's continuous evidence.

Control actions and expected outcomes live in this runner, never in detector inputs.
The results measure software behavior in our fixture, not real-cheat effectiveness.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import random
import statistics
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import desktop_worker
import engine
import native_integrity as native
import native_stream
from native_capture import collect


class OwnedProcess:
    def __init__(self, build="v1", duration=60000, interval=100, read=True):
        self.process = subprocess.Popen(
            [
                str(ROOT / "native/build/surge_owned_app.exe"),
                "--build",
                build,
                "--interval-ms",
                str(interval),
                "--duration-ms",
                str(duration),
                "--test-controls",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.frames = queue.Queue()
        self.acks = queue.Queue()
        self.threads = []
        self.start_reader(self.process.stderr, self.acks, False)
        if read:
            self.start_reader(self.process.stdout, self.frames, True)

    def start_reader(self, stream, output, parse):
        def run():
            try:
                while line := stream.readline(65537):
                    if len(line) > 65536:
                        raise ValueError("Producer exceeded its frame size bound")
                    text = line.decode("utf-8").strip()
                    output.put(json.loads(text) if parse else text)
            except Exception as error:
                output.put(error)
            finally:
                output.put(None)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.threads.append(thread)

    def frame(self, timeout=5):
        value = self.frames.get(timeout=timeout)
        if isinstance(value, Exception):
            raise value
        return value

    def command(self, name):
        self.process.stdin.write((name + "\n").encode("ascii"))
        self.process.stdin.flush()
        return self.ack(name)

    def ack(self, name):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = self.acks.get(timeout=max(0.01, deadline - time.monotonic()))
            if isinstance(value, Exception):
                raise value
            if value is None:
                raise AssertionError(f"Producer exited before acknowledging {name}")
            parts = value.split()
            if len(parts) == 3 and parts[:2] == ["ack", name]:
                return int(parts[2])
        raise AssertionError(f"No acknowledgement for {name}")

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=5)
        self.process.stdin.close()
        for thread in self.threads:
            thread.join(timeout=2)
        for stream in (self.process.stdout, self.process.stderr):
            stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def resources(process):
    """Measure the child itself, without requiring a third-party process package."""

    class Memory(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
                "PrivateUsage",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Memory),
        wintypes.DWORD,
    ]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    handle = kernel.OpenProcess(0x1000 | 0x10, False, process.pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        memory = Memory()
        memory.cb = ctypes.sizeof(memory)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        seconds = (
            sum((value.dwHighDateTime << 32) | value.dwLowDateTime for value in times[2:]) / 1e7
        )
        return dict(
            cpu_seconds=seconds,
            working_set_bytes=memory.WorkingSetSize,
            peak_working_set_bytes=memory.PeakWorkingSetSize,
            private_bytes=memory.PrivateUsage,
        )
    finally:
        kernel.CloseHandle(handle)


def analyze(rows):
    data = engine.parse_bytes(
        ("\n".join(engine.canonical(row) for row in rows) + "\n").encode(), "stream.jsonl"
    )
    return engine.analyze(data, None, native.default_policy(data))


def captured_window(rows, state="running", sequence=None, dropped=None):
    groups = []
    for row in rows:
        if not groups or groups[-1][0]["stream_sequence"] != row["stream_sequence"]:
            groups.append([])
        groups[-1].append(row)
    return native_stream.snapshot_rows(
        groups,
        state=state,
        dropped=rows[-1]["stream_dropped_samples"] if dropped is None else dropped,
        final_sequence=rows[-1]["stream_sequence"] if sequence is None else sequence,
    )


def run(output, soak_seconds=15):
    if os.name != "nt":
        raise RuntimeError("These owned-app integration checks require Windows.")
    folder = output / ("stream-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True)
    registry = native.approve(
        collect("v1", "clean"),
        {"schema": native.BASELINE_SCHEMA, "entries": []},
        "Independent stream check of reviewed fixture v1",
    )
    both = native.approve(
        collect("v2", "clean"), registry, "Independent stream check of legitimate update v2"
    )
    report = dict(
        scope="Owned-app synthetic software validation; not real-cheat accuracy",
        seed=uuid.uuid4().hex,
        checks=[],
        false_positives=0,
        missed_changes=0,
        clean_range_observations=0,
        changed_range_observations=0,
        unavailable_range_observations=0,
    )
    rng = random.Random(report["seed"])
    all_rows = []
    sessions = set()

    def assess(rows, expected, name):
        statuses = [row["status"] for row in analyze(captured_window(rows))["records"]][
            -len(expected) :
        ]
        assert statuses == expected, (name, statuses, expected)
        for status, wanted in zip(statuses, expected):
            if wanted == "No finding":
                report["clean_range_observations"] += 1
                report["false_positives"] += status == "Review"
            elif wanted == "Unknown":
                report["unavailable_range_observations"] += 1
            elif name not in ("unapproved update",):
                report["changed_range_observations"] += 1
                report["missed_changes"] += status != "Review"

    for build, approvals, name in (
        ("v1", registry, "approved v1"),
        ("v2", registry, "unapproved update"),
        ("v2", both, "approved update"),
    ):
        decoder = native_stream.StreamDecoder(approvals)
        rows_saved = []
        with OwnedProcess(build) as child:
            ready = child.frame()
            assert ready["type"] == "ready"
            decoder.accept(ready)

            def next_sample(boundary=1):
                while True:
                    frame = child.frame()
                    assert frame is not None, "Unexpected producer exit"
                    rows = decoder.accept(frame)
                    if frame["type"] == "sample":
                        rows_saved.extend(rows)
                        if frame["sequence"] >= boundary:
                            return rows, frame

            rows, _ = next_sample()
            session = rows[0]["session_id"]
            assert session not in sessions, "Process restart reused a session identity"
            sessions.add(session)
            assess(
                rows_saved,
                ["Review"] * 2 if name == "unapproved update" else ["No finding"] * 2,
                name,
            )
            if name != "unapproved update":
                for action, expected in (
                    ("change-primary", ["Review", "No finding"]),
                    ("restore", ["No finding", "No finding"]),
                    ("change-outside", ["No finding", "No finding"]),
                    ("restore", ["No finding", "No finding"]),
                    ("change-secondary", ["No finding", "Review"]),
                    ("restore", ["No finding", "No finding"]),
                    ("unreadable", ["Unknown", "No finding"]),
                    ("restore", ["No finding", "No finding"]),
                    ("unload", ["Unknown", "Unknown"]),
                    ("load", ["No finding", "No finding"]),
                ):
                    # Fresh timing schedule independent of collector output or detector verdict.
                    time.sleep(rng.uniform(0.11, 0.23))
                    sent = time.perf_counter()
                    boundary = child.command(action)
                    observed, frame = next_sample(boundary)
                    latency = (time.perf_counter() - sent) * 1000
                    assess(rows_saved, expected, action)
                    report["checks"].append(
                        dict(
                            build=build,
                            action=action,
                            sequence=frame["sequence"],
                            statuses=expected,
                            command_to_observation_ms=round(latency, 3),
                        )
                    )
                # Both controls are applied before the next scheduled snapshot.
                # This deliberately demonstrates a sampling blind spot, not a detection success.
                child.process.stdin.write(b"change-primary\nrestore\n")
                child.process.stdin.flush()
                changed_at = child.ack("change-primary")
                restored_at = child.ack("restore")
                assert changed_at == restored_at
                _, frame = next_sample(restored_at)
                assess(rows_saved, ["No finding", "No finding"], "between-sample change")
                report["checks"].append(
                    dict(
                        build=build,
                        action="between-sample change",
                        sequence=frame["sequence"],
                        expected_limitation="not observed",
                    )
                )
            child.process.stdin.write(b"stop\n")
            child.process.stdin.flush()
            while frame := child.frame():
                rows_saved.extend(decoder.accept(frame))
            assert child.process.wait(timeout=5) == 0
        rows_saved = captured_window(
            rows_saved, "stopped", decoder.sequence, decoder.dropped_samples
        )
        all_rows.extend(rows_saved)
        report["checks"].append(dict(build=build, action=name, rows=len(rows_saved)))
        # Each collection is replayed as its own immutable source, as it is in Surge.
        stem = name.replace(" ", "-")
        evidence = folder / (stem + ".jsonl")
        evidence.write_text(
            "\n".join(engine.canonical(row) for row in rows_saved) + "\n", encoding="utf-8"
        )
        workspace = desktop_worker.Workspace()
        workspace.dispatch("import", dict(role="current", path=str(evidence)))
        result = engine.analyze(workspace.current, None, workspace.config)
        case = folder / (stem + ".case.json")
        engine.save_case(case, workspace.current, None, workspace.config, result)
        assert engine.open_case(case)[3] == result
    report["replay_records"] = len(all_rows)

    # A deliberately paused reader forces the finite producer queue to drop observations.
    with OwnedProcess(duration=20000, read=False) as child:
        time.sleep(7)
        blocked_usage = resources(child.process)
        child.start_reader(child.process.stdout, child.frames, True)
        child.process.stdin.write(b"stop\n")
        child.process.stdin.flush()
        decoder = native_stream.StreamDecoder(registry)
        sequences = []
        groups = []
        end = None
        while frame := child.frame(timeout=5):
            rows = decoder.accept(frame)
            if frame["type"] == "sample":
                sequences.append(frame["sequence"])
                groups.append(rows)
            elif frame["type"] == "end":
                end = frame
        assert child.process.wait(timeout=5) == 0
        assert (
            end is not None and end["dropped_samples"] > 0
        ), "Slow consumer did not expose sample loss"
        assert (
            end["sequence"] - len(sequences) == end["dropped_samples"]
        ), "Tail loss was not accounted for"
        exported = native_stream.snapshot_rows(
            groups, dropped=end["dropped_samples"], final_sequence=end["sequence"]
        )
        findings = analyze(exported)
        assert (
            findings["records"][-1]["status"] == "Unknown"
        ), "Lost observations were represented as clean"
        assert exported[-1]["stream_health"] is True
        (folder / "paused-reader.jsonl").write_text(
            "\n".join(engine.canonical(row) for row in exported) + "\n", encoding="utf-8"
        )
        report["backpressure"] = dict(
            generated=end["sequence"],
            received=len(sequences),
            dropped=end["dropped_samples"],
            **blocked_usage,
        )

    # Duration-limited sustained collection gives reproducible cost measurements, not a leak-proof claim.
    with OwnedProcess(duration=soak_seconds * 1000) as child:
        decoder = native_stream.StreamDecoder(registry)
        measurements, elapsed, usage = [], [], []
        started = time.monotonic()
        end = None
        while frame := child.frame(timeout=5):
            rows = decoder.accept(frame)
            if frame["type"] == "sample":
                elapsed.append(frame["elapsed_ms"])
                measurements.extend(row["collection_ms"] for row in rows)
                if len(elapsed) % 10 == 1:
                    usage.append(
                        dict(
                            resources(child.process),
                            measured_after_seconds=time.monotonic() - started,
                        )
                    )
                assert all(row["memory_matches"] is True for row in rows)
            elif frame["type"] == "end":
                end = frame
        assert child.process.wait(timeout=5) == 0
        assert end is not None and end["reason"] == "limit" and end["dropped_samples"] == 0
        assert (
            len(elapsed) >= soak_seconds * 7
        ), "Collector failed to sustain its configured interval"
        wall = time.monotonic() - started
        ordered = sorted(measurements)
        report["sustained"] = dict(
            seconds=round(wall, 3),
            samples=len(elapsed),
            interval_ms=100,
            observed_samples_per_second=round(len(elapsed) / wall, 3),
            median_sample_gap_ms=statistics.median(b - a for a, b in zip(elapsed, elapsed[1:])),
            max_sample_gap_ms=max(b - a for a, b in zip(elapsed, elapsed[1:])),
            median_range_collection_ms=statistics.median(ordered),
            p95_range_collection_ms=ordered[max(0, int(len(ordered) * 0.95) - 1)],
            cpu_percent_one_core=round(
                (usage[-1]["cpu_seconds"] - usage[0]["cpu_seconds"])
                / (usage[-1]["measured_after_seconds"] - usage[0]["measured_after_seconds"])
                * 100,
                3,
            ),
            first_private_bytes=usage[0]["private_bytes"],
            last_private_bytes=usage[-1]["private_bytes"],
            peak_working_set_bytes=max(item["peak_working_set_bytes"] for item in usage),
        )

    # EOF and closed output are explicit lifecycle tests, not detection cases.
    with OwnedProcess() as child:
        assert child.frame()["type"] == "ready"
        child.process.stdin.close()
        assert child.process.wait(timeout=5) == 0
    with OwnedProcess(read=False) as child:
        child.process.stdout.close()
        assert child.process.wait(timeout=6) != 0
    report["checks"].extend(
        [
            dict(action="stdin EOF stops owned app"),
            dict(action="closed consumer stops owned app"),
        ]
    )
    report["limits"] = [
        "Only the two configured routines are covered; other bytes are outside coverage.",
        "Changes wholly between samples may be missed; this is periodic observation.",
        "The collector and evidence are locally controlled and unsigned, not remote attestation.",
        "This bounded run does not establish long-term leak freedom or real-cheat detection accuracy.",
    ]
    (folder / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output / "latest-stream.json").write_text(
        json.dumps({"folder": folder.name}), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "native/captures")
    parser.add_argument("--soak-seconds", type=int, default=15)
    args = parser.parse_args()
    if not 5 <= args.soak_seconds <= 300:
        parser.error("Use 5 to 300 seconds for bounded sustained checks.")
    run(args.output, args.soak_seconds)

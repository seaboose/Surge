"""Bounded continuous capture of Surge's own application over inherited pipes.

There is no process discovery, arbitrary executable path, or automatic approval.
The reader owns collection state; investigation takes explicit immutable snapshots.
"""

from collections import deque
from datetime import datetime, timezone
import copy
import math
import os
import re
from pathlib import Path
import subprocess
import threading
import time

import engine
import native_integrity as native

ROOT = Path(__file__).resolve().parent
STREAM_SCHEMA = "surge-native-stream-v1"
MAX_LINE = 32768
MAX_SAMPLES = 500
MAX_WINDOW_BYTES = 8 * 1024 * 1024
HEALTH_RESERVE_BYTES = 16 * 1024
SNAPSHOT_ROW_RESERVE_BYTES = 512


def integer(value, low=0, high=10_000_000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid stream counter.")
    return value


def finite(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 610000:
        raise ValueError("Invalid elapsed collection time.")
    return value


def utc(value):
    if not isinstance(value, str):
        raise ValueError("A collection timestamp needs a timezone.")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid collection timestamp.") from exc
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("Collection timestamps must use UTC.")


def live_identity(row):
    """One process/build contract for live samples and their exported replay."""
    integer(row.get("pid"), 1, 0xFFFFFFFF)
    # Creation FILETIME is an opaque decimal identity, not an ISO timestamp.
    # Keep the live protocol's existing string/integer representation support.
    if not re.fullmatch(r"[0-9]{1,20}", str(row.get("process_started", ""))):
        raise ValueError("Invalid process creation identity.")
    if row.get("build") not in ("v1", "v2"):
        raise ValueError("Unsupported live build identity.")
    return tuple(
        row.get(k) for k in ("session_id", "pid", "module_sha256", "process_started", "build")
    )


def convert_frame(frame, ranges, registry, integrity_manifest=None):
    """Convert a complete sample without exposing test actions to detection."""
    native.validate_manifest(ranges)
    native.validate_baselines(registry)
    sequence = integer(frame.get("sequence"), 1)
    elapsed = finite(frame.get("elapsed_ms"))
    dropped = integer(frame.get("dropped_samples"))
    observations = frame.get("observations")
    if not isinstance(observations, list) or len(observations) != len(ranges):
        raise ValueError("A sample must include every configured range.")
    specs = {r["range_name"]: r for r in ranges}
    seen = set()
    identity = None
    result = []
    for raw in observations:
        native.check_observation(raw)
        name = raw.get("range_name")
        if name not in specs or name in seen or raw.get("phase") != "live":
            raise ValueError("Invalid live range identity.")
        if any(raw.get(k) != specs[name][k] for k in native.RANGE_KEYS):
            raise ValueError("Live range differs from its manifest.")
        if "scenario" in raw:
            raise ValueError("Scenario labels cannot enter continuous collection.")
        seen.add(name)
        utc(raw.get("captured_at"))
        current = live_identity(raw)
        if identity is not None and current != identity:
            raise ValueError("Process identity changed within a sample.")
        identity = current
        if integrity_manifest is not None and type(raw.get("module_size")) is not int:
            raise ValueError("Versioned observation needs its module size.")
        row = native.convert_observation(raw, registry, ranges, integrity_manifest)
        row.update(
            event_id=f"{sequence}:{name}",
            stream_sequence=sequence,
            stream_elapsed_ms=elapsed,
            stream_dropped_samples=dropped,
        )
        result.append(row)
    native.attach_coverage(result, ranges, integrity_manifest)
    return result


class StreamDecoder:
    """Strict framing and continuity checks, independent of subprocess handling."""

    def __init__(self, registry):
        self.registry = copy.deepcopy(native.validate_baselines(registry))
        self.ranges = None
        self.integrity_manifest = None
        self.build = None
        self.sequence = self.dropped_samples = 0
        self.elapsed_ms = -1
        self.ended = False
        self.identity = None
        self.interval_ms = None
        self.duration_ms = None

    def accept(self, frame):
        if not isinstance(frame, dict) or frame.get("schema") != STREAM_SCHEMA or self.ended:
            raise ValueError("Unsupported or closed collection stream.")
        kind = frame.get("type")
        if kind == "ready":
            if self.ranges is not None or frame.get("build") not in ("v1", "v2"):
                raise ValueError("Unexpected stream start.")
            self.ranges = copy.deepcopy(native.validate_manifest(frame.get("ranges")))
            if "integrity_manifest" in frame:
                self.integrity_manifest = copy.deepcopy(
                    native.integrity.validate(frame["integrity_manifest"], self.ranges)
                )
            self.interval_ms = integer(frame.get("interval_ms"), 100, 5000)
            self.duration_ms = integer(frame.get("duration_ms"), 100, 600000)
            self.build = frame["build"]
            return []
        if self.ranges is None:
            raise ValueError("Collection did not declare its ranges.")
        sequence = integer(frame.get("sequence"))
        dropped = integer(frame.get("dropped_samples"))
        if dropped < self.dropped_samples:
            raise ValueError("Collection loss counter decreased.")
        if kind == "sample":
            if (
                sequence <= self.sequence
                or sequence - self.sequence - 1 != dropped - self.dropped_samples
            ):
                raise ValueError("Collection sequence gap is not accounted for.")
            if finite(frame.get("elapsed_ms")) < self.elapsed_ms:
                raise ValueError("Monotonic collection time went backwards.")
            rows = convert_frame(frame, self.ranges, self.registry, self.integrity_manifest)
            first = rows[0]
            identity = live_identity(first)
            if first["build"] != self.build or (
                self.identity is not None and identity != self.identity
            ):
                raise ValueError("Collection process or build changed without a new session.")
            self.identity = identity
            self.elapsed_ms = frame["elapsed_ms"]
            for row in rows:
                row["stream_interval_ms"] = self.interval_ms
        elif kind == "end":
            if (
                frame.get("reason") not in ("stopped", "limit")
                or sequence - self.sequence != dropped - self.dropped_samples
            ):
                raise ValueError("Collection ending does not account for all samples.")
            self.ended = True
            rows = []
        else:
            raise ValueError("Unknown collection frame.")
        self.sequence, self.dropped_samples = sequence, dropped
        return rows


def validate_health(row):
    if (
        row.get("stream_health") is not True
        or row.get("memory_status") != "failed"
        or not isinstance(row.get("collection_error"), str)
        or not row["collection_error"]
        or len(row["collection_error"]) > 1000
        or any(
            row.get(k) is not None
            for k in ("baseline_approved", "memory_matches", "protection_matches")
        )
    ):
        raise ValueError("Collection health cannot claim a code verdict.")
    integer(row.get("stream_dropped_samples"))
    integer(row.get("stream_evicted_samples"))
    utc(row.get("captured_at"))


def validate_export(rows, health):
    """A retained window may omit older samples only when the omission is declared."""
    groups = {}
    identity = None
    for row in rows:
        if (
            row.get("phase") != "live"
            or not {
                "stream_sequence",
                "stream_capture_state",
                "stream_final_sequence",
                "stream_final_dropped",
            }
            <= row.keys()
        ):
            raise ValueError("Cannot mix live and one-shot collection.")
        sequence = integer(row["stream_sequence"], 1)
        integer(row.get("stream_interval_ms"), 100, 5000)
        finite(row.get("stream_elapsed_ms"))
        integer(row.get("stream_dropped_samples"))
        integer(row.get("stream_evicted_samples", 0))
        utc(row.get("captured_at"))
        current = live_identity(row) + tuple(
            row.get(k)
            for k in (
                "baseline_sha256",
                "range_manifest_sha256",
                "integrity_manifest_sha256",
                "stream_evicted_samples",
            )
        )
        if identity is not None and current != identity:
            raise ValueError("Live export changed collection identity.")
        identity = current
        if row.get("event_id") != f"{sequence}:{row.get('range_name')}":
            raise ValueError("Live record identity differs from its sequence.")
        groups.setdefault(sequence, []).append(row)
    previous = None
    for sequence, group in groups.items():
        first = group[0]
        if any(
            any(
                r.get(k) != first.get(k)
                for k in ("stream_elapsed_ms", "stream_dropped_samples", "stream_interval_ms")
            )
            for r in group
        ):
            raise ValueError("A sample has inconsistent stream counters.")
        if previous is None:
            if (
                sequence - 1
                != first.get("stream_evicted_samples", 0) + first["stream_dropped_samples"]
            ):
                raise ValueError("The beginning of the collection window is missing.")
        elif (
            sequence <= previous["stream_sequence"]
            or first["stream_dropped_samples"] < previous["stream_dropped_samples"]
            or sequence - previous["stream_sequence"] - 1
            != first["stream_dropped_samples"] - previous["stream_dropped_samples"]
            or first["stream_elapsed_ms"] < previous["stream_elapsed_ms"]
        ):
            raise ValueError("Live export has an unexplained gap or clock reversal.")
        previous = first
    if health and rows:
        if len(health) != 1 or health[0]["session_id"] != rows[0]["session_id"]:
            raise ValueError("Collection health belongs to a different session.")
        if health[0]["stream_dropped_samples"] < previous["stream_dropped_samples"] or health[
            0
        ]["stream_evicted_samples"] != rows[0].get("stream_evicted_samples", 0):
            raise ValueError("Collection health counters disagree.")
    if rows and any("stream_capture_state" in r for r in rows):
        first = rows[0]
        state = first.get("stream_capture_state")
        final = integer(first.get("stream_final_sequence"))
        lost = integer(first.get("stream_final_dropped"))
        if state not in ("running", "stopped", "failed") or any(
            any(
                r.get(k) != first.get(k)
                for k in (
                    "stream_capture_state",
                    "stream_final_sequence",
                    "stream_final_dropped",
                )
            )
            for r in rows
        ):
            raise ValueError("Collection snapshot ending is inconsistent.")
        if (
            final - previous["stream_sequence"] != lost - previous["stream_dropped_samples"]
            or lost < previous["stream_dropped_samples"]
        ):
            raise ValueError("Collection snapshot ending has missing samples.")
        if (state == "failed" or lost or first.get("stream_evicted_samples", 0)) and not health:
            raise ValueError("Incomplete collection needs its health record.")
        if health and health[0]["stream_dropped_samples"] != lost:
            raise ValueError("Collection ending and health loss counters differ.")


def snapshot_rows(
    groups,
    state="stopped",
    evicted=0,
    dropped=0,
    error=None,
    session_id=None,
    baseline_sha256=None,
    final_sequence=None,
):
    rows = [
        dict(r, stream_evicted_samples=evicted, stream_capture_state=state)
        for group in groups
        for r in group
    ]
    last = rows[-1]["stream_sequence"] if rows else 0
    for row in rows:
        row.update(
            stream_final_sequence=last if final_sequence is None else final_sequence,
            stream_final_dropped=dropped,
        )
    if error or evicted or dropped:
        message = error or "Collection window is incomplete."
        message += f" {dropped} samples lost in transport; {evicted} older samples removed from the retained window."
        rows.append(
            dict(
                schema=native.SCHEMA,
                event_id="collection-health",
                session_id=session_id or (rows[0]["session_id"] if rows else "unavailable"),
                captured_at=datetime.now(timezone.utc).isoformat(),
                pid=None,
                baseline_approved=None,
                memory_matches=None,
                protection_matches=None,
                memory_status="failed",
                collection_error=message[:1000],
                stream_health=True,
                stream_dropped_samples=dropped,
                stream_evicted_samples=evicted,
                baseline_sha256=baseline_sha256
                or (rows[0]["baseline_sha256"] if rows else None),
            )
        )
    return rows


class SampleWindow:
    """Keep full samples within both the count limit and a replayable byte budget."""

    def __init__(self):
        self.groups = deque()
        self.sizes = deque()
        self.encoded_bytes = self.evicted = self.samples = 0

    def append(self, rows):
        # Encode only the incoming group. The allowance covers snapshot counters
        # and separators; a separate reserve covers the single health record.
        size = sum(
            len(engine.canonical(row).encode("utf-8")) + 1 + SNAPSHOT_ROW_RESERVE_BYTES
            for row in rows
        )
        budget = MAX_WINDOW_BYTES - HEALTH_RESERVE_BYTES
        if not rows or size > budget:
            raise ValueError("Collection sample exceeds the retained evidence size limit.")
        while self.groups and (
            len(self.groups) >= MAX_SAMPLES or self.encoded_bytes + size > budget
        ):
            self.groups.popleft()
            self.encoded_bytes -= self.sizes.popleft()
            self.evicted += 1
        self.groups.append(rows)
        self.sizes.append(size)
        self.encoded_bytes += size
        self.samples += 1


class NativeSession:
    """One fixed child, one draining thread, and a bounded window of full samples."""

    def __init__(self, build="v1", registry=None):
        if build not in ("v1", "v2"):
            raise ValueError("Choose build v1 or v2.")
        if registry is None:
            path = ROOT / "native/baselines.json"
            if path.exists():
                with path.open("rb") as stream:
                    raw = stream.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ValueError("Baseline registry is too large.")
                registry = engine.decode(raw.decode("utf-8"))
            else:
                registry = dict(schema=native.BASELINE_SCHEMA, entries=[])
        self.decoder = StreamDecoder(registry)
        self.build = build
        self.lock = threading.Lock()
        self.window = SampleWindow()
        self.retained_sequence = self.retained_dropped = 0
        self.error = None
        self.state = "running"
        self.last_received = time.monotonic()
        self.started = self.last_received
        self.closed = threading.Event()
        self.ready = threading.Event()
        executable = ROOT / "native/build/surge_owned_app.exe"
        if not executable.is_file():
            raise ValueError("Build the owned app first. See native/README.md.")
        self.process = subprocess.Popen(
            [str(executable), "--build", build],
            cwd=executable.parent,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.reader = threading.Thread(target=self._read, name="surge-collection", daemon=True)
        try:
            self.reader.start()
        except Exception:
            self.process.kill()
            self.process.wait(timeout=3)
            for pipe in (self.process.stdout, self.process.stdin):
                try:
                    pipe.close()
                except (OSError, ValueError):
                    pass
            raise

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE or not line.endswith(b"\n"):
                    raise ValueError("Collection frame exceeded its limit or was truncated.")
                frame = engine.decode(line.decode("utf-8"))
                with self.lock:
                    rows = self.decoder.accept(frame)
                    self.last_received = time.monotonic()
                    self.ready.set()
                    if rows:
                        self.window.append(rows)
                    # If retaining a sample fails, the prior window still has a
                    # consistent ending and the failure becomes Unknown health.
                    self.retained_sequence = self.decoder.sequence
                    self.retained_dropped = self.decoder.dropped_samples
            code = self.process.wait(timeout=3)
            if code or not self.decoder.ended:
                raise ValueError("Collection disconnected before a complete ending.")
        except Exception as exc:
            with self.lock:
                self.error = str(exc)[:700]
            if self.process.poll() is None:
                try:
                    self.process.kill()
                    self.process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        finally:
            for pipe in (self.process.stdout, self.process.stdin):
                if pipe:
                    try:
                        pipe.close()
                    except (OSError, ValueError):
                        pass
            with self.lock:
                self.state = "failed" if self.error else "stopped"
            self.ready.set()
            self.closed.set()

    def status(self):
        with self.lock:
            return dict(
                state=self.state,
                samples=self.window.samples,
                final_sequence=self.retained_sequence,
                records=sum(len(g) for g in self.window.groups),
                dropped_samples=self.retained_dropped,
                evicted_samples=self.window.evicted,
                error=self._health_error(),
                build=self.build,
                session_id=self.decoder.identity[0] if self.decoder.identity else None,
                elapsed_ms=max(0, self.decoder.elapsed_ms),
                limit_samples=MAX_SAMPLES,
                has_evidence=bool(
                    self.window.groups
                    or self._health_error()
                    or self.retained_dropped
                    or self.window.evicted
                ),
            )

    def snapshot(self):
        with self.lock:
            return snapshot_rows(
                self.window.groups,
                self.state,
                self.window.evicted,
                self.retained_dropped,
                self._health_error(),
                baseline_sha256=native.digest(self.decoder.registry),
                final_sequence=self.retained_sequence,
            )

    def _health_error(self):
        stale = self.state == "running" and time.monotonic() - self.last_received > 5
        return self.error or (
            "Waiting for collection; no sample received for over 5 seconds." if stale else None
        )

    def stop(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write(b"stop\n")
                self.process.stdin.flush()
            except (OSError, ValueError):
                pass
        if not self.closed.wait(4):
            with self.lock:
                self.error = (
                    "Collection did not stop in time. The retained evidence may be incomplete."
                )
            try:
                self.process.kill()
            except OSError:
                pass
            self.closed.wait(4)
        self.reader.join(timeout=1)
        return self.status()

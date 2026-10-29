"""Owned synthetic stream worker. Reads one recipe after the supervisor's gate."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import engine
import native_integrity as native
import native_stream as stream
from check_approval_contract import fixture
from check_retention import accounting_case, count_case, import_case, FixedFixtureClock

MAX_INPUT = 256 * 1024
TARGETS = {"native_stream.py", "native_integrity.py", "integrity_manifest.py", "engine.py"}


def digest(value):
    return hashlib.sha256(engine.canonical(value).encode()).hexdigest()


def encode(value):
    return engine.canonical(value).encode()


def model_input(recipe):
    capture = fixture(recipe["ranges"], recipe["bytes"])
    shift = recipe["shift"]
    mapping = {}
    for row in capture["ranges"]:
        old = row["range_name"]
        row.update(range_name=recipe["prefix"] + old, range_rva=row["range_rva"] + shift)
        mapping[old] = row
    manifest = capture["integrity_manifest"]
    manifest["ranges"] = copy.deepcopy(capture["ranges"])
    for row in manifest["executable_ranges"] + manifest["exclusions"]:
        row["range_rva"] += shift
    for row in capture["observations"]:
        row.update(mapping[row["range_name"]], pid=recipe["pid"],
                   process_started=str(recipe["creation"]), build=recipe["build"],
                   session_id=recipe["prefix"] + "session")
    registry = native.approve(capture, dict(schema=native.BASELINE_SCHEMA, entries=[]),
                               "Synthetic stream-model fixture")
    ready = dict(schema=stream.STREAM_SCHEMA, type="ready", build=recipe["build"],
                 ranges=capture["ranges"], integrity_manifest=manifest,
                 interval_ms=500, duration_ms=600000)
    slots, samples, expected = [], [], []
    elapsed = 0
    base = capture["observations"][:recipe["ranges"]]
    for index, gap in enumerate(recipe["gaps"]):
        slots.extend([False] * gap)
        slots.append(True)
        elapsed += recipe["ticks"][index]
        observations = copy.deepcopy(base)
        for ordinal, row in enumerate(observations):
            row.pop("scenario")
            row["phase"] = "live"
            mode = (index + ordinal + recipe["mode_offset"]) % 4 if recipe["mixed"] else 0
            if mode == 1:
                row["observed_hex"] = "ff" * row["range_size"]
            elif mode == 2:
                row.update(memory_status="failed", observed_hex=None)
            elif mode == 3:
                row["page_protection"] = 64
            expected.append(("No finding", "Review", "Unknown", "Review")[mode])
        samples.append(dict(schema=stream.STREAM_SCHEMA, type="sample", sequence=len(slots),
                            dropped_samples=slots.count(False), elapsed_ms=elapsed,
                            observations=observations))
    slots.extend([False] * recipe["tail_loss"])
    end = dict(schema=stream.STREAM_SCHEMA, type="end", sequence=len(slots),
               dropped_samples=slots.count(False), reason="stopped")
    return registry, ready, samples, end, slots, expected


class FakeProcess:
    def __init__(self, raw):
        self.stdout, self.stdin = io.BytesIO(raw), io.BytesIO()
    def wait(self, timeout=None):
        return 0
    def poll(self):
        return 0
    def kill(self):
        raise AssertionError("Completed fake pipe should not require process killing")


def reader(registry, raw):
    assert len(raw) <= MAX_INPUT
    session = object.__new__(stream.NativeSession)
    session.decoder = stream.StreamDecoder(registry)
    session.lock = threading.Lock()
    session.window = stream.SampleWindow()
    session.retained_sequence = session.retained_dropped = 0
    session.error = None
    session.state = "running"
    session.last_received = session.started = time.monotonic()
    session.closed, session.ready = threading.Event(), threading.Event()
    session.process = FakeProcess(raw)
    stream.NativeSession._read(session)
    assert session.closed.is_set() and session.ready.is_set()
    return session


def lines(frames):
    raw = b"".join(encode(frame) + b"\n" for frame in frames)
    assert len(raw) <= MAX_INPUT
    return raw


def replay(rows, folder, save=False):
    results = []
    for fmt in ("json", "jsonl"):
        raw = encode(rows) if fmt == "json" else lines(rows)
        assert len(raw) <= MAX_INPUT
        data = engine.parse_bytes(raw, "synthetic." + fmt)
        config = native.default_policy(data)
        result = engine.analyze(data, None, config)
        results.append(result)
        if save and fmt == "jsonl":
            path = folder / "round-trip.surgecase"
            engine.save_case(path, data, None, config, result)
            restored = engine.open_case(path)
            assert restored[0].manifest() == data.manifest() and restored[0].text == data.text
            assert restored[1] is None and restored[2] == config and restored[3] == result
            path.unlink()
    assert results[0]["records"] == results[1]["records"]
    assert results[0]["summary"] == results[1]["summary"]
    return results[0]


def mutation(name, ready, samples, end):
    # Every failure after the prefix must leave that prefix's evidence intact.
    first = copy.deepcopy(samples[0])
    first.update(sequence=1, dropped_samples=0, elapsed_ms=500)
    bad = copy.deepcopy(first)
    bad.update(sequence=2, elapsed_ms=1000)
    prefix = [ready, first]
    if name == "sample_before_ready": return [], first
    if name == "end_before_ready": return [], end
    if name == "duplicate_ready": return prefix, ready
    if name == "unknown_type": bad["type"] = "unknown"
    elif name == "duplicate_sequence": bad["sequence"] = 1
    elif name == "reversed_sequence": bad["sequence"] = 0
    elif name == "unexplained_gap": bad["sequence"] = 3
    elif name == "loss_rollback":
        first.update(sequence=3, dropped_samples=2)
        bad.update(sequence=4, dropped_samples=1)
    elif name == "joint_rollback":
        first.update(sequence=3, dropped_samples=2)
        bad.update(sequence=2, dropped_samples=0)
    elif name in ("negative_time", "backward_time", "boolean_time", "nonfinite_time"):
        bad["elapsed_ms"] = {"negative_time": -1, "backward_time": 499,
                             "boolean_time": True, "nonfinite_time": float("inf")}[name]
    elif name == "boolean_sequence": bad["sequence"] = True
    elif name == "negative_drop": bad["dropped_samples"] = -1
    elif name == "missing_range": bad["observations"].pop()
    elif name == "duplicate_range": bad["observations"][1] = copy.deepcopy(bad["observations"][0])
    elif name.startswith("identity_"):
        field = name.removeprefix("identity_")
        values = dict(session_id="other", pid=99, module_sha256="b"*64,
                      process_started="999", build="v2" if ready["build"] == "v1" else "v1")
        bad["observations"][-1][field] = values[field]
    elif name.startswith("invalid_"):
        field = name.removeprefix("invalid_")
        bad["observations"][-1][field] = dict(pid=False, process_started="-1", build="v3")[field]
    elif name == "end_wrong_loss":
        bad = dict(end, sequence=2, dropped_samples=0)
    elif name == "duplicate_end":
        good_end = dict(end, sequence=1, dropped_samples=0)
        return prefix + [good_end], good_end
    elif name == "sample_after_end":
        return prefix + [dict(end, sequence=1, dropped_samples=0)], bad
    elif name == "scenario_in_live": bad["observations"][0]["scenario"] = "clean"
    return prefix, bad


def ordinary(recipe, folder):
    registry, ready, samples, end, slots, expected = model_input(recipe)
    kind = recipe["kind"]
    if kind == "positive":
        decoder, window = stream.StreamDecoder(registry), stream.SampleWindow()
        decoder.accept(ready)
        frozen = None
        for index, frame in enumerate(samples):
            group = decoder.accept(frame)
            window.append(group)
            delivered = [i+1 for i, value in enumerate(slots[:frame["sequence"]]) if value]
            assert [g[0]["stream_sequence"] for g in window.groups] == delivered
            assert window.evicted == 0 and window.samples == len(delivered)
            if frozen is None:
                frozen = stream.snapshot_rows(window.groups, dropped=frame["dropped_samples"],
                                              final_sequence=frame["sequence"])
                fingerprint = digest(frozen)
        decoder.accept(end)
        assert decoder.ended and decoder.sequence == len(slots)
        assert decoder.dropped_samples == slots.count(False)
        assert frozen is None or digest(frozen) == fingerprint
        session = reader(registry, lines([ready, *samples, end]))
        assert session.state == "stopped" and session.error is None
        rows = session.snapshot()
        if not rows:
            return dict(outcome="accepted_empty", slots=slots, rows=0)
        result = replay(rows, folder, save=True)
        expected += ["Unknown"] if False in slots else []
        assert [r["status"] for r in result["records"]] == expected
        return dict(outcome="accepted", slots=slots, expected=expected,
                    rows=len(rows), snapshot_sha256=digest(rows), summary=result["summary"])
    if kind == "replay":
        session = reader(registry, lines([ready, *samples, end]))
        rows = session.snapshot()
        assert rows[-1].get("stream_health")
        name = recipe["variant"]
        if name == "missing_health": rows.pop()
        elif name == "wrong_health_session": rows[-1]["session_id"] = "different"
        elif name == "wrong_health_loss": rows[-1]["stream_dropped_samples"] += 1
        elif name == "wrong_health_eviction": rows[-1]["stream_evicted_samples"] += 1
        elif name == "wrong_final_sequence": rows[0]["stream_final_sequence"] += 1
        elif name == "poisoned_health_verdict": rows[-1]["memory_matches"] = True
        else: raise AssertionError(name)
        reasons = []
        for fmt in ("json", "jsonl"):
            raw = encode(rows) if fmt == "json" else lines(rows)
            try:
                data = engine.parse_bytes(raw, "invalid." + fmt)
                native.default_policy(data)
            except ValueError as exc:
                reasons.append(str(exc))
            else: raise AssertionError("Malformed replay accepted: " + name)
        return dict(outcome="rejected_replay", reasons=reasons)
    if kind == "framing":
        name = recipe["variant"]
        first = copy.deepcopy(samples[0]); first.update(sequence=1, dropped_samples=0, elapsed_ms=0)
        ending = dict(end, sequence=1, dropped_samples=0)
        prefix = lines([ready, first])
        if name.startswith("line_"):
            edge = {"line_minus": -1, "line_exact": 0, "line_plus": 1}[name]
            content = encode(ready)
            padded = content + b" " * (stream.MAX_LINE + edge - len(content) - 1) + b"\n"
            raw = padded + lines([first, ending])
            expected_good = edge <= 0
        elif name == "valid_utf8":
            raw = lines([dict(ready, note="\u00e9\U0001f680"), first, ending]); expected_good = True
        else:
            bad = {"missing_newline": encode(ending), "invalid_utf8": b'\xff\n',
                   "truncated_utf8": b'{"note":"\xc3\n', "truncated_json": b'{\n',
                   "duplicate_json_key": b'{"schema":"x","schema":"y"}\n',
                   "missing_end": b""}[name]
            raw = prefix + bad; expected_good = False
        session = reader(registry, raw)
        assert (session.state == "stopped") is expected_good
        assert (session.error is None) is expected_good
        rows = session.snapshot()
        if not expected_good:
            assert rows[-1]["stream_health"] is True
        if name != "line_plus":
            assert len(session.window.groups) == 1
            assert session.retained_sequence == 1
        result = replay(rows, folder)
        assert result["summary"]["Unknown"] == (int(not expected_good) +
            sum(r["memory_status"] != "complete" for r in rows if not r.get("stream_health")))
        return dict(outcome="accepted_framing" if expected_good else "rejected_framing",
                    input_bytes=len(raw), retained=len(session.window.groups), summary=result["summary"])
    prefix, bad = mutation(recipe["variant"], ready, samples, end)
    decoder = stream.StreamDecoder(registry)
    for frame in prefix: decoder.accept(frame)
    try: decoder.accept(bad)
    except ValueError as exc: reason = str(exc)
    else: raise AssertionError("Malformed live transition accepted: " + recipe["variant"])
    raw = b"".join(json.dumps(f, separators=(",", ":")).encode() + b"\n" for f in [*prefix, bad])
    session = reader(registry, raw)
    assert session.state == "failed" and session.error
    expected_retained = int(len(prefix) >= 2)
    assert len(session.window.groups) == expected_retained
    rows = session.snapshot()
    assert rows[-1]["stream_health"] and len(rows) == expected_retained * recipe["ranges"] + 1
    result = replay(rows, folder)
    assert result["summary"]["Unknown"] >= 1
    return dict(outcome="rejected_live", reason=reason, retained=expected_retained,
                snapshot_sha256=digest(rows), summary=result["summary"])


def execute(recipe, folder):
    kind = recipe["kind"]
    if kind == "timeout_probe":
        time.sleep(6); raise AssertionError("Deadline control was not stopped")
    if kind == "memory_probe":
        try: buffer = bytearray(1024 * 1024 * 1024)
        except MemoryError: return dict(outcome="allocation_refused")
        else:
            del buffer
            raise AssertionError("1 GiB allocation passed the 1 GiB private-memory job limit")
    if kind == "safe_probe":
        buffer = bytearray(16 * 1024 * 1024)
        assert len(buffer) == 16 * 1024 * 1024
        return dict(outcome="safe_allocation_passed")
    if kind == "boundary":
        name = recipe["variant"]
        if name.startswith("count_"):
            _, count, samples = name.split("_")
            fingerprint, metrics = count_case(int(count), int(samples), folder, "retention")
            path = folder / "retention.surgecase"
            metrics["case_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            path.unlink()
        elif name.startswith("import_"): fingerprint, metrics = import_case(name)
        else: fingerprint, metrics = accounting_case(name)
        return dict(outcome="boundary_passed", input_sha256=fingerprint, metrics=metrics)
    return ordinary(recipe, folder)


def main():
    request = json.loads(sys.stdin.readline())
    recipe, folder = request["recipe"], Path(request["folder"])
    hits, arcs, functions, previous = {}, {}, {}, {}
    target_paths = {str(ROOT / name): name for name in TARGETS}
    def trace(frame, event, arg):
        key = target_paths.get(frame.f_code.co_filename)
        if key is not None:
            functions.setdefault(key, set()).add(frame.f_code.co_name)
            if event == "line":
                line = frame.f_lineno
                hits.setdefault(key, set()).add(line)
                prior = previous.get(id(frame))
                if prior is not None: arcs.setdefault(key, set()).add((prior, line))
                previous[id(frame)] = line
            elif event == "return": previous.pop(id(frame), None)
            return trace
        return None
    with (patch.object(native, "datetime", FixedFixtureClock),
          patch.object(stream, "datetime", FixedFixtureClock),
          patch.object(engine, "datetime", FixedFixtureClock)):
        if recipe["kind"] not in ("boundary", "memory_probe", "safe_probe", "timeout_probe"):
            sys.settrace(trace)
        try: result = execute(recipe, folder)
        finally: sys.settrace(None)
    output = dict(status="passed", recipe_sha256=digest(recipe), result=result,
                  result_sha256=digest(result),
                  coverage={name: dict(lines=sorted(hits.get(name, [])),
                                       arcs=sorted(arcs.get(name, [])),
                                       functions=sorted(functions.get(name, [])))
                            for name in sorted(TARGETS) if name in hits})
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__": main()

"""Fixed synthetic retention boundaries; no process collection or image loading."""

import hashlib
import json
from pathlib import Path
import sys
import traceback
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import engine
import native_integrity as native
import native_stream as stream
from scripts.retention_contract import CASE_IDS, LIMITS, validate_evidence
from test_native_replay_contract import sample
from test_native_window import many_ranges

BUDGET = 8_372_224


def encode(value):
    # Independent serialization for the accounting oracle; do not use the
    # window's stored sizes or its eviction loop to choose expected groups.
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def cost(group):
    return sum(len(encode(row)) + 513 for row in group)


def suffix(history):
    selected, total = [], 0
    for group, size in reversed(history):
        if len(selected) == 500 or total + size > BUDGET:
            break
        selected.append((group, size))
        total += size
    return list(reversed(selected)), total


def verify_window(window, history):
    expected, total = suffix(history)
    assert list(window.groups) == [g for g, _ in expected]
    assert list(window.sizes) == [s for _, s in expected]
    assert window.encoded_bytes == total
    assert window.samples == len(history)
    assert window.evicted == len(history) - len(expected)
    assert total <= BUDGET and len(expected) <= 500


def state(window):
    return dict(groups=list(window.groups), sizes=list(window.sizes),
                accounted_bytes=window.encoded_bytes, samples=window.samples,
                evicted=window.evicted)


class FixedFixtureClock(datetime):
    @staticmethod
    def now(tz):
        assert tz == timezone.utc
        return datetime(2026, 10, 23, tzinfo=timezone.utc)


def snapshot(window, sequence):
    # Only the synthetic health row's clock is fixed; observations, identities,
    # counters and conclusions are checked without normalization.
    with patch.object(stream, "datetime", FixedFixtureClock):
        return stream.snapshot_rows(window.groups, evicted=window.evicted,
                                    final_sequence=sequence)


def count_case(ranges, samples, folder, identity):
    # Synthetic approval provenance is also clocked before generation, rather
    # than dropping its timestamp or baseline fingerprint from comparisons.
    with patch.object(native, "datetime", FixedFixtureClock):
        decoder, observations = many_ranges(ranges)
    window, history, inputs = stream.SampleWindow(), [], hashlib.sha256()
    frozen = None
    for sequence in range(1, samples + 1):
        frame = sample(observations, sequence, (sequence - 1) * 500)
        inputs.update(encode(frame) + b"\n")
        group = decoder.accept(frame)
        history.append((group, cost(group)))
        window.append(group)
        verify_window(window, history)
        assert all(len(g) == ranges for g in window.groups)
        assert [g[0]["stream_sequence"] for g in window.groups] == list(
            range(window.evicted + 1, sequence + 1))
        if sequence == 498:
            frozen = snapshot(window, sequence)
            frozen_hash = digest(frozen)
    assert frozen is not None and digest(frozen) == frozen_hash
    rows = snapshot(window, samples)
    exports = {"json": encode(rows), "jsonl": b"".join(encode(r) + b"\n" for r in rows)}
    results, data = {}, None
    for fmt, raw in exports.items():
        assert len(raw) <= 8_388_608 and len(raw) < 16_777_216
        data = engine.parse_bytes(raw, "retention." + fmt)
        policy = native.default_policy(data)
        results[fmt] = engine.analyze(data, None, policy)
        summary = results[fmt]["summary"]
        assert summary["No finding"] == len(window.groups) * ranges
        assert summary["Unknown"] == int(window.evicted > 0)
        assert summary["Review"] == 0
    assert results["json"]["records"] == results["jsonl"]["records"]
    assert results["json"]["summary"] == results["jsonl"]["summary"]
    assert len(rows) == ranges * len(window.groups) + int(window.evicted > 0)
    if window.evicted:
        assert rows[-1]["stream_health"] is True
        assert rows[-1]["stream_evicted_samples"] == window.evicted
    case = folder / (identity + ".surgecase")
    # A case's creation time is fixture metadata too. Fix it before writing so
    # isoformat's optional fractional seconds cannot vary the measured size.
    with patch.object(engine, "datetime", FixedFixtureClock):
        engine.save_case(case, data, None, policy, results["jsonl"])
    reopened = engine.open_case(case)
    assert reopened[0].manifest() == data.manifest()
    assert reopened[3] == results["jsonl"]
    metrics = dict(samples=samples, ranges=ranges, retained=len(window.groups),
                   evicted=window.evicted, accounted_bytes=window.encoded_bytes,
                   json_bytes=len(exports["json"]), jsonl_bytes=len(exports["jsonl"]),
                   case_bytes=case.stat().st_size, case_replay="passed",
                   snapshot_stable="passed", replay="passed",
                   conclusions_sha256=digest(results["jsonl"]),
                   snapshot_sha256=digest(rows))
    if ranges == 2:
        assert len(window.groups) == min(samples, 500)
    return inputs.hexdigest(), metrics


def padded_group(size, marker=0, multibyte=False):
    row = dict(marker=marker, padding="")
    needed = size - cost([row])
    assert needed >= 0 and size <= BUDGET + 1
    row["padding"] = ("\u00e9" * (needed // 2) + "x" * (needed % 2)
                      if multibyte else "x" * needed)
    assert cost([row]) == size
    return [row]


def accounting_case(identity):
    delta = {"minus": -1, "exact": 0, "plus": 1}
    window, history, inputs = stream.SampleWindow(), [], hashlib.sha256()

    def append(group):
        inputs.update(encode(group) + b"\n")
        window.append(group)
        history.append((group, cost(group)))
        verify_window(window, history)

    if identity.startswith("single_"):
        append(padded_group(1024))
        group = padded_group(BUDGET + delta[identity.split("_")[-1]], 1)
        if identity.endswith("plus"):
            before = digest(state(window))
            inputs.update(encode(group) + b"\n")
            try:
                window.append(group)
            except ValueError as exc:
                assert "retained evidence size limit" in str(exc)
            else:
                raise AssertionError("Oversized incoming group accepted")
            assert digest(state(window)) == before
        else:
            append(group)
            assert window.evicted == 1
    elif identity.startswith("aggregate_"):
        append(padded_group(4096))
        append(padded_group(BUDGET - 4096 + delta[identity.split("_")[-1]], 1))
        assert window.evicted == int(identity.endswith("plus"))
    elif identity == "multiple_evictions":
        for i in range(4):
            append(padded_group(2048, i))
        append(padded_group(BUDGET - 4096, 4))
        assert window.evicted == 2 and len(window.groups) == 3
        assert window.encoded_bytes == BUDGET
    elif identity == "utf8":
        append(padded_group(4096, multibyte=True))
        append(padded_group(BUDGET - 4096, 1, multibyte=True))
        assert window.encoded_bytes == BUDGET and window.evicted == 0
        append(padded_group(1024, 2, multibyte=True))
        assert window.evicted == 1
    elif identity == "empty":
        append(padded_group(1024))
        before = digest(state(window))
        inputs.update(b"[]\n")
        try:
            window.append([])
        except ValueError as exc:
            assert "retained evidence size limit" in str(exc)
        else:
            raise AssertionError("Empty group accepted")
        assert digest(state(window)) == before
    else:
        raise AssertionError(identity)
    return inputs.hexdigest(), dict(samples=window.samples, retained=len(window.groups),
                                    evicted=window.evicted, accounted_bytes=window.encoded_bytes,
                                    state_sha256=digest(state(window)))


def import_case(identity):
    _, fmt, label = identity.split("_")
    length = 16_777_216 + {"minus": -1, "exact": 0, "plus": 1}[label]
    seed = b'[{"sample":1}]' if fmt == "json" else b'{"sample":1}\n'
    raw = seed + b" " * (length - len(seed))
    assert len(raw) == length <= 16_777_217
    if label == "plus":
        try:
            engine.parse_bytes(raw, "boundary." + fmt)
        except engine.ImportFailure as exc:
            assert "no larger than 16 MiB" in str(exc)
        else:
            raise AssertionError("Oversized import accepted")
        outcome = "rejected_at_byte_guard"
    else:
        data = engine.parse_bytes(raw, "boundary." + fmt)
        assert data.rows == ({"sample": 1},)
        outcome = "accepted"
    return hashlib.sha256(raw).hexdigest(), dict(bytes=length, outcome=outcome)


def finalize_report(report):
    # Do not label a preserved failed attempt repeatable before its independent
    # evidence contract accepts every comparison.
    candidate = dict(report, status="passed", repeatability="passed")
    validate_evidence(candidate)
    report.update(status="passed", repeatability="passed")


def run():
    assert (stream.MAX_SAMPLES, stream.MAX_WINDOW_BYTES, stream.HEALTH_RESERVE_BYTES,
            stream.SNAPSHOT_ROW_RESERVE_BYTES, engine.MAX_BYTES) == (
                500, 8_388_608, 16_384, 512, 16_777_216)
    folder = ROOT / "verification/qualification" / ("retention-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    report = dict(schema="surge-retention-v1", status="incomplete",
                  original_fuzzing_campaign="incomplete", repeatability="incomplete",
                  evaluations=0, limits=LIMITS,
                  runs=[dict(id=name, repeat=repeat, status="not_run")
                        for repeat in (1, 2) for name in sorted(CASE_IDS)])

    def save():
        path = folder / "report.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    save()
    print("Retention evidence: " + str(folder), flush=True)
    try:
        for row in report["runs"]:
            row["status"] = "running"
            save()
            name = row["id"]
            if name.startswith("count_"):
                _, ranges, samples = name.split("_")
                fingerprint, metrics = count_case(int(ranges), int(samples), folder,
                                                  f"{name}-{row['repeat']}")
            elif name.startswith("import_"):
                fingerprint, metrics = import_case(name)
            else:
                fingerprint, metrics = accounting_case(name)
            row.update(status="passed", input_sha256=fingerprint,
                       result_sha256=digest(metrics), metrics=metrics)
            report["evaluations"] += 1
            save()
            print(f"{name}: repeat={row['repeat']} passed", flush=True)
        finalize_report(report)
    except Exception as exc:
        if row["status"] == "running":
            row.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        traceback.print_exc()
        raise
    finally:
        save()
        print("SURGE_RETENTION_JSON=" + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    run()

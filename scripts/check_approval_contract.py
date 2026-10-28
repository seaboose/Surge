"""Fixed owned-data approval/verdict oracle; not the original fuzzing campaign."""

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine
import native_integrity as native
from test_native_manifest_security import versioned_capture

STATES = (
    "approved_clean", "unapproved_clean", "approved_changed", "unapproved_changed",
    "approved_unavailable", "unapproved_unavailable", "approved_protection",
    "unapproved_protection", "stale_module", "stale_manifest", "legacy_registry",
    "legacy_capture", "mixed",
)
SCENARIOS = tuple((count, size, state) for count in (2, 3, 16)
                  for size in (1, 64) for state in STATES)
MAX_INPUT = 1024 * 1024
MAX_CASE = 8 * 1024 * 1024
FROZEN_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)
SOURCES = ("scripts/check_approval_contract.py", "scripts/run_approval_contract.py",
           "docs/approval-contract-acceptance.md",
           "engine.py", "native_integrity.py", "integrity_manifest.py",
           "test_native_manifest_security.py")

# This table is an external contract, independent of conversion/analysis code.
# Fields: approval, byte match, protection match, verdict, has gaps.
TRUTH = {
    (True, "clean"): (True, True, True, "No finding", False),
    (False, "clean"): (False, None, True, "Review", True),
    (True, "changed"): (True, False, True, "Review", False),
    (False, "changed"): (False, None, True, "Review", True),
    (True, "unavailable"): (True, None, None, "Unknown", True),
    (False, "unavailable"): (False, None, None, "Review", True),
    (True, "protection"): (True, True, False, "Review", False),
    (False, "protection"): (False, None, False, "Review", True),
}


def digest(value):
    return hashlib.sha256(engine.canonical(value).encode("utf-8")).hexdigest()


def fixture(count, size):
    capture = versioned_capture()
    ranges = []
    for index in range(count):
        raw = bytes([index + 1]) * size
        ranges.append(dict(range_name=f"Owned{index}", range_rva=4096 + index * 128,
                           range_size=size, reference_hex=raw.hex(),
                           reference_sha256=hashlib.sha256(raw).hexdigest()))
    capture["ranges"] = ranges
    capture["integrity_manifest"].update(
        ranges=copy.deepcopy(ranges), executable_bytes=count * 128,
        checked_bytes=count * size, excluded_bytes=count * (128 - size),
        executable_ranges=[dict(range_rva=4096, range_size=count * 128)],
        exclusions=[dict(range_rva=r["range_rva"] + size, range_size=128 - size,
                         reason="not_declared") for r in ranges],
    )
    base = capture["observations"][0]
    capture["observations"] = [dict(base, **r, observed_hex=r["reference_hex"], phase=p)
                               for p in native.PHASES for r in ranges]
    return capture


def prepare(count, size, state):
    capture = fixture(count, size)
    empty = dict(schema=native.BASELINE_SCHEMA, entries=[])
    approval_capture = copy.deepcopy(capture)
    if state == "legacy_registry":
        del approval_capture["integrity_manifest"]
    registry = native.approve(approval_capture, empty, "Synthetic contract fixture")
    approved = not (state.startswith("unapproved_") or state in {
        "stale_module", "stale_manifest", "legacy_registry", "legacy_capture"})
    if state.startswith("unapproved_"):
        registry = empty
    if state == "stale_module":
        capture["integrity_manifest"]["module_sha256"] = "b" * 64
        for row in capture["observations"]:
            row["module_sha256"] = "b" * 64
    elif state == "stale_manifest":
        # Same excluded byte set, different explicit declaration/approval identity.
        original = capture["integrity_manifest"]["exclusions"].pop(0)
        first = dict(original, range_size=1)
        second = dict(original, range_rva=original["range_rva"] + 1,
                      range_size=original["range_size"] - 1)
        capture["integrity_manifest"]["exclusions"][:0] = [first, second]
    elif state == "legacy_capture":
        del capture["integrity_manifest"]
    modes = []
    for index, row in enumerate(capture["observations"]):
        mode = ("clean", "changed", "unavailable", "protection")[index % count % 4] \
            if state == "mixed" else state.split("_", 1)[1] \
            if state.startswith(("approved_", "unapproved_")) else "clean"
        modes.append(mode)
        if mode == "changed":
            row["observed_hex"] = "ff" * size
        elif mode == "unavailable":
            row.update(memory_status="failed", observed_hex=None)
        elif mode == "protection":
            row["page_protection"] = 64
    return capture, registry, [TRUTH[approved, mode] for mode in modes], modes


def encoded(rows, fmt, alternate=False):
    if alternate:
        rows = [dict(reversed(tuple(row.items()))) for row in rows]
    raw = (json.dumps(rows, ensure_ascii=False, indent=1) if fmt == "json" and alternate
           else engine.canonical(rows) if fmt == "json"
           else "\n".join(json.dumps(r, ensure_ascii=False) if alternate
                           else engine.canonical(r) for r in rows) + "\n").encode("utf-8")
    assert len(raw) <= MAX_INPUT, ("input budget", len(raw))
    return raw


def analyze(raw, fmt):
    data = engine.parse_bytes(raw, "synthetic." + fmt)
    config = native.default_policy(data)
    return data, config, engine.analyze(data, None, config)


def must_reject(action):
    try:
        action()
    except ValueError as exc:
        return str(exc)
    raise AssertionError("Invalid synthetic comparison was accepted")


def check(count, size, state, folder, label):
    capture, registry, expected, modes = prepare(count, size, state)
    before = copy.deepcopy((capture, registry))
    rows = native.convert(capture, registry)
    assert len(rows) == len(expected)
    for row, (approved, memory, protection, verdict, gaps) in zip(rows, expected):
        assert row["baseline_approved"] is approved
        assert row["memory_matches"] is memory
        assert row["protection_matches"] is protection
        assert (row["expected_sha256"] is not None) is approved
        assert (row["observed_sha256"] is not None) is (row["memory_status"] == "complete")
    clean = all(mode == "clean" for mode in modes)
    if clean:
        fresh = native.approve(capture, dict(schema=native.BASELINE_SCHEMA, entries=[]),
                               "Synthetic new approval")
        assert all(r["baseline_approved"] is True for r in native.convert(capture, fresh))
        approval_outcome = "accepted_clean_capture"
    else:
        must_reject(lambda: native.approve(capture, dict(schema=native.BASELINE_SCHEMA,
                                                        entries=[]), "Must refuse"))
        approval_outcome = "rejected_nonclean_capture"
    assert (capture, registry) == before
    results, input_hashes, input_sizes, reject_reasons = [], {}, {}, {}
    for fmt in ("json", "jsonl"):
        raw = encoded(rows, fmt)
        data, config, result = analyze(raw, fmt)
        assert len(result["records"]) == len(expected)
        for record, row_expectation in zip(result["records"], expected):
            assert record["status"] == row_expectation[3]
            assert bool(record["gaps"]) is row_expectation[4]
        for status in ("No finding", "Review", "Unknown"):
            assert result["summary"][status] == sum(e[3] == status for e in expected)
        alternative, _, alternative_result = analyze(encoded(rows, fmt, True), fmt)
        assert alternative.rows == data.rows
        assert alternative_result["records"] == result["records"]
        assert alternative_result["summary"] == result["summary"]
        poisoned = copy.deepcopy(rows)
        poisoned[0]["memory_matches"] = not rows[0]["memory_matches"]
        reject_reasons[fmt] = must_reject(lambda: analyze(encoded(poisoned, fmt), fmt))
        input_hashes[fmt] = hashlib.sha256(raw).hexdigest()
        input_sizes[fmt] = len(raw)
        results.append(result)
        if fmt == "jsonl":
            path = folder / (label + ".case.json")
            engine.save_case(path, data, None, config, result)
            case_bytes = path.read_bytes()
            assert len(case_bytes) <= MAX_CASE
            restored, reference, restored_config, restored_result = engine.open_case(path)
            assert restored.manifest() == data.manifest()
            assert restored.text == data.text and reference is None
            assert restored_config == config and restored_result == result
            case_hash = hashlib.sha256(case_bytes).hexdigest()
            path.unlink()
    assert results[0]["records"] == results[1]["records"]
    assert results[0]["summary"] == results[1]["summary"]
    assert (capture, registry) == before
    metrics = dict(ranges=count, range_bytes=size, state=state, rows=len(rows),
                   expected=[list(e) for e in expected], summary=results[0]["summary"],
                   input_sizes=input_sizes, input_hashes=input_hashes,
                   approval=approval_outcome, poisoned_rejections=reject_reasons,
                   case_bytes=len(case_bytes), case_sha256=case_hash,
                   case_replay="passed", representation_changes="passed")
    return digest(dict(capture=capture, registry=registry, expected=expected)), metrics


def run():
    started = time.monotonic()
    folder = ROOT / "verification/qualification" / ("approval-contract-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in SOURCES:
        raw = (ROOT / name).read_bytes()
        destination = folder / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    report = dict(schema="surge-approval-contract-v1", status="incomplete",
                  original_fuzzing_campaign="incomplete", held_back_phase=False,
                  source_sha256=hashes, evaluations=0, repeatability="incomplete",
                  limits=dict(max_input_bytes=MAX_INPUT, max_case_bytes=MAX_CASE,
                              outer_seconds=300, output_bytes=10 * 1024 * 1024),
                  runs=[dict(id=f"{c}-{s}-{state}", repeat=r, status="not_run")
                        for r in (1, 2) for c, s, state in SCENARIOS])

    def save():
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    save()
    print("Approval contract evidence: " + str(folder), flush=True)
    active = None
    try:
        with (patch.object(native, "datetime", wraps=datetime) as native_clock,
              patch.object(engine, "datetime", wraps=datetime) as case_clock):
            native_clock.now.return_value = FROZEN_TIME
            case_clock.now.return_value = FROZEN_TIME
            for active in report["runs"]:
                active["status"] = "running"
                save()
                tick = time.monotonic()
                count, size, state = active["id"].split("-", 2)
                fingerprint, metrics = check(int(count), int(size), state, folder,
                                             active["id"] + "-" + str(active["repeat"]))
                active.update(status="passed", input_sha256=fingerprint, metrics=metrics,
                              result_sha256=digest(metrics), seconds=round(time.monotonic()-tick, 6))
                report["evaluations"] += 1
                save()
                print(f"{active['id']}: repeat={active['repeat']} passed", flush=True)
        for first, second in zip(report["runs"][:78], report["runs"][78:]):
            assert (first["input_sha256"], first["result_sha256"]) == \
                (second["input_sha256"], second["result_sha256"]), first["id"]
        assert report["evaluations"] == 156
        for name, fingerprint in hashes.items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == fingerprint
        report.update(status="passed", repeatability="passed")
    except Exception as exc:
        if active and active["status"] == "running":
            active.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        traceback.print_exc()
        raise
    finally:
        report["seconds"] = round(time.monotonic() - started, 6)
        save()
        manifest = [dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size,
                         sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in sorted(folder.rglob("*")) if p.is_file()]
        (folder / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                     encoding="utf-8")
        print("SURGE_APPROVAL_CONTRACT_STATUS=" + report["status"], flush=True)


if __name__ == "__main__":
    run()

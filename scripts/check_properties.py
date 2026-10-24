"""Bounded synthetic contract checks. No subprocess or native binary access."""

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HYPOTHESIS_STORAGE_DIRECTORY"] = str(ROOT / "verification/qualification/property-cache")

import hypothesis
from hypothesis import given, seed, settings, strategies as st, Phase
import integrity_manifest
import native_stream as stream
from test_native_manifest_security import versioned_capture
from test_native_window import many_ranges
from test_native_replay_contract import sample, analyze

VERSION = "6.170.8"
SEEDS = (20261023, 17)
EXAMPLES = 64
NAMES = ("manifest_partition", "stream_ordering", "replay_consistency")


def rejected(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("Invalid synthetic evidence was accepted")


def occupancy(manifest):
    """Independent bounded byte-set oracle, not the production interval walk."""

    def bytes_in(parts):
        return Counter(
            b for p in parts for b in range(p["range_rva"], p["range_rva"] + p["range_size"])
        )

    checked = bytes_in(manifest["ranges"])
    excluded = bytes_in(manifest["exclusions"])
    executable = bytes_in(manifest["executable_ranges"])
    return (
        all(n == 1 for n in (checked + excluded).values())
        and checked + excluded == executable
        and sum(checked.values()) == manifest["checked_bytes"]
        and sum(excluded.values()) == manifest["excluded_bytes"]
        and sum(executable.values()) == manifest["executable_bytes"]
    )


def manifest_partition(layout):
    manifest = copy.deepcopy(versioned_capture()["integrity_manifest"])
    ranges, exclusions = [], []
    cursor = 4096
    for index, (size, gap) in enumerate(layout):
        raw = bytes([index + 1]) * size
        ranges.append(
            dict(
                range_name=f"Owned{index}",
                range_rva=cursor,
                range_size=size,
                reference_hex=raw.hex(),
                reference_sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
        exclusions.append(dict(range_rva=cursor + size, range_size=gap, reason="not_declared"))
        cursor += size + gap
    manifest.update(
        ranges=ranges,
        exclusions=exclusions,
        executable_ranges=[dict(range_rva=4096, range_size=cursor - 4096)],
        executable_bytes=cursor - 4096,
        checked_bytes=sum(s for s, g in layout),
        excluded_bytes=sum(g for s, g in layout),
    )
    assert occupancy(manifest)
    before = copy.deepcopy(manifest)
    assert integrity_manifest.validate(manifest) == before
    assert manifest == before
    for mutation in ("hole", "overlap", "total", "boolean", "version"):
        bad = copy.deepcopy(manifest)
        if mutation == "hole":
            bad["exclusions"].pop()
            bad["excluded_bytes"] = sum(p["range_size"] for p in bad["exclusions"])
            assert not occupancy(bad)
        elif mutation == "overlap":
            bad["exclusions"][0]["range_rva"] -= 1
            assert not occupancy(bad)
        elif mutation == "total":
            bad["checked_bytes"] += 1
            assert not occupancy(bad)
        elif mutation == "boolean":
            bad["module_size"] = True
        else:
            bad["descriptor_version"] = 2
        rejected(lambda: integrity_manifest.validate(bad))


def history(count, gaps, ticks, mode="clean"):
    decoder, observations = many_ranges(count)
    if mode == "changed":
        for row in observations:
            row["observed_hex"] = "00" * row["range_size"]
    elif mode == "unavailable":
        for row in observations:
            row.update(memory_status="not_loaded", observed_hex=None)
    # Delivered slots are True, missing slots False. Derive counters by counting
    # this external history rather than reusing the decoder's gap equation.
    slots, groups = [], []
    elapsed = 0
    for gap in gaps:
        slots.extend([False] * gap)
        slots.append(True)
        elapsed += ticks
        groups.append(decoder.accept(sample(observations, len(slots), elapsed, slots.count(False))))
    return decoder, observations, groups, len(slots), slots.count(False), elapsed


def stream_ordering(value):
    count, gaps, ticks = value
    decoder, observations, groups, final, dropped, elapsed = history(count, gaps, ticks)
    assert len(groups) == len(gaps) and all(len(g) == count for g in groups)
    assert (decoder.sequence, decoder.dropped_samples) == (final, dropped)
    for seq, loss, clock in (
        (final, dropped, elapsed),
        (final - 1, dropped, elapsed),
        (final + 2, dropped, elapsed + ticks),
        (final + 1, dropped - 1, elapsed + ticks),
        (final + 1, dropped, elapsed - 1),
    ):
        fresh = copy.deepcopy(decoder)
        rejected(lambda: fresh.accept(sample(observations, seq, clock, loss)))


def replay_consistency(value):
    count, gaps, ticks = value
    for mode, expected in (
        ("clean", "No finding"),
        ("changed", "Review"),
        ("unavailable", "Unknown"),
    ):
        decoder, obs, groups, final, dropped, elapsed = history(count, gaps, ticks, mode)
        rows = stream.snapshot_rows(groups, dropped=dropped, final_sequence=final)
        original = copy.deepcopy(rows)
        results = [analyze(rows, jsonl) for jsonl in (False, True)]
        assert results[0]["summary"] == results[1]["summary"]
        assert results[0]["records"] == results[1]["records"]
        counts = {"No finding": 0, "Review": 0, "Unknown": int(dropped > 0)}
        counts[expected] += count * len(gaps)
        for key, value in counts.items():
            assert results[0]["summary"][key] == value, (mode, counts, results[0]["summary"])
        assert rows == original
        changed = copy.deepcopy(rows)
        changed[1]["process_started"] = "999"
        reversed_rows = stream.snapshot_rows(
            list(reversed(groups)), dropped=dropped, final_sequence=final
        )
        for bad in (changed, reversed_rows):
            for jsonl in (False, True):
                rejected(lambda: analyze(bad, jsonl))


def run():
    assert hypothesis.__version__ == VERSION, "Pinned Hypothesis version required"
    layout = st.lists(st.tuples(st.integers(1, 64), st.integers(1, 8)), min_size=2, max_size=16)
    histories = st.tuples(
        st.integers(2, 16), st.lists(st.integers(0, 3), min_size=2, max_size=8), st.integers(1, 500)
    )
    runs = []
    for repeat in (1, 2):
        for number in SEEDS:
            for name, strategy in zip(NAMES, (layout, histories, histories)):
                count, fingerprint = 0, hashlib.sha256()
                check = globals()[name]

                def body(value):
                    nonlocal count
                    check(value)
                    count += 1
                    fingerprint.update((json.dumps(value, separators=(",", ":")) + "\n").encode())

                test = seed(number)(
                    settings(
                        max_examples=EXAMPLES,
                        database=None,
                        deadline=2000,
                        phases=(Phase.generate, Phase.shrink),
                        print_blob=True,
                    )(given(strategy)(body))
                )
                test()
                assert count >= EXAMPLES, (name, count)
                runs.append(
                    dict(
                        property=name,
                        seed=number,
                        repeat=repeat,
                        evaluations=count,
                        input_sha256=fingerprint.hexdigest(),
                    )
                )
                print(f"{name}: seed={number} repeat={repeat} evaluations={count}", flush=True)
    for a, b in zip(runs[:6], runs[6:]):
        assert (a["evaluations"], a["input_sha256"]) == (b["evaluations"], b["input_sha256"])
    result = dict(
        schema="surge-properties-v1",
        status="passed",
        hypothesis_version=VERSION,
        seeds=list(SEEDS),
        examples_per_property=EXAMPLES,
        runs=runs,
        evaluations=sum(r["evaluations"] for r in runs),
        repeatability="passed",
        original_fuzzing_campaign="incomplete",
    )
    print("SURGE_PROPERTIES_JSON=" + json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    run()

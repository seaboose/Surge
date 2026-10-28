"""Complete native windows must remain importable as range counts increase."""

import copy
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import engine
import native_integrity as native
import native_stream as stream
from test_native_manifest_security import versioned_capture


def many_ranges(count):
    capture = versioned_capture()
    seed = capture["ranges"][0]
    ranges = [
        dict(seed, range_name=f"OwnedRange{i}", range_rva=4096 + 128 * i) for i in range(count)
    ]
    manifest = capture["integrity_manifest"]
    manifest.update(
        ranges=ranges,
        executable_ranges=[dict(range_rva=4096, range_size=4096)],
        executable_bytes=4096,
        checked_bytes=4 * count,
        excluded_bytes=4096 - 4 * count,
        exclusions=[
            dict(
                range_rva=spec["range_rva"] + 4,
                range_size=124 if i < count - 1 else 4096 - 128 * i - 4,
                reason="not_declared",
            )
            for i, spec in enumerate(ranges)
        ],
    )
    base = capture["observations"][0]
    capture["ranges"] = ranges
    capture["observations"] = [
        dict(base, **spec, phase=phase) for phase in native.PHASES for spec in ranges
    ]
    registry = native.approve(
        capture, dict(schema=native.BASELINE_SCHEMA, entries=[]), "Reviewed window fixture"
    )
    decoder = stream.StreamDecoder(registry)
    decoder.accept(
        dict(
            schema=stream.STREAM_SCHEMA,
            type="ready",
            build="v1",
            ranges=ranges,
            integrity_manifest=manifest,
            interval_ms=500,
            duration_ms=600000,
        )
    )
    observations = [dict(base, **spec, phase="live") for spec in ranges]
    for row in observations:
        row.pop("scenario")
    return decoder, observations


class NativeWindowTests(unittest.TestCase):
    def collect(self, count, samples=500):
        decoder, observations = many_ranges(count)
        window = stream.SampleWindow()
        for sequence in range(1, samples + 1):
            window.append(
                decoder.accept(
                    dict(
                        schema=stream.STREAM_SCHEMA,
                        type="sample",
                        sequence=sequence,
                        elapsed_ms=(sequence - 1) * 500,
                        dropped_samples=0,
                        observations=observations,
                    )
                )
            )
        rows = stream.snapshot_rows(
            window.groups, evicted=window.evicted, final_sequence=decoder.sequence
        )
        raw = ("\n".join(engine.canonical(row) for row in rows) + "\n").encode()
        self.assertLessEqual(len(raw), stream.MAX_WINDOW_BYTES)
        self.assertLess(len(raw), engine.MAX_BYTES)
        data = engine.parse_bytes(raw, "window.jsonl")
        result = engine.analyze(data, None, native.default_policy(data))
        return window, rows, result

    def test_default_two_ranges_keep_all_500_samples(self):
        window, rows, result = self.collect(2)
        self.assertEqual(window.samples, 500)
        self.assertEqual(len(window.groups), 500)
        self.assertEqual(window.evicted, 0)
        self.assertEqual(len(rows), 1000)
        self.assertEqual(result["summary"]["No finding"], 1000)
        self.assertEqual(result["summary"]["Unknown"], 0)

    def test_sixteen_ranges_evict_complete_samples_and_replay_with_unknown_health(self):
        window, rows, result = self.collect(16)
        self.assertEqual(window.samples, 500)
        self.assertGreater(window.evicted, 0)
        self.assertEqual(window.evicted + len(window.groups), 500)
        self.assertTrue(all(len(group) == 16 for group in window.groups))
        self.assertEqual(rows[0]["stream_sequence"], window.evicted + 1)
        self.assertEqual(rows[-1]["stream_evicted_samples"], window.evicted)
        self.assertTrue(rows[-1]["stream_health"])
        self.assertEqual(result["summary"]["Unknown"], 1)
        self.assertEqual(result["summary"]["Review"], 0)

    def test_sample_count_limit_still_applies_to_small_samples(self):
        window = stream.SampleWindow()
        with patch.object(stream, "MAX_SAMPLES", 3):
            for i in range(5):
                window.append([{"sample": i}])
        self.assertEqual([group[0]["sample"] for group in window.groups], [2, 3, 4])
        self.assertEqual(window.samples, 5)
        self.assertEqual(window.evicted, 2)

    def test_oversized_group_is_refused_without_destroying_retained_samples(self):
        window = stream.SampleWindow()
        window.append([{"sample": 1}])
        before = copy.deepcopy(list(window.groups))
        with patch.object(stream, "MAX_WINDOW_BYTES", stream.HEALTH_RESERVE_BYTES + 16):
            with self.assertRaisesRegex(ValueError, "retained evidence size limit"):
                window.append([{"sample": 2}])
        self.assertEqual(list(window.groups), before)
        self.assertEqual(window.samples, 1)
        self.assertEqual(window.evicted, 0)

    @unittest.skipUnless(
        os.name == "nt"
        and (Path(__file__).parent / "native/build/surge_owned_app.exe").is_file(),
        "Build the owned Windows app first",
    )
    def test_session_size_failure_remains_unknown_and_closes_child(self):
        with patch.object(stream, "MAX_WINDOW_BYTES", stream.HEALTH_RESERVE_BYTES + 16):
            session = stream.NativeSession(
                "v1", dict(schema=native.BASELINE_SCHEMA, entries=[])
            )
            self.addCleanup(session.stop)
            self.assertTrue(session.closed.wait(5))
        status = session.status()
        self.assertEqual(status["state"], "failed")
        self.assertIn("retained evidence size limit", status["error"])
        self.assertIsNotNone(session.process.poll())
        rows = session.snapshot()
        data = engine.parse_bytes(engine.canonical(rows).encode(), "failed.json")
        result = engine.analyze(data, None, native.default_policy(data))
        self.assertEqual(result["summary"]["Unknown"], 1)

    @unittest.skipUnless(
        os.name == "nt"
        and (Path(__file__).parent / "native/build/surge_owned_app.exe").is_file(),
        "Build the owned Windows app first",
    )
    def test_later_size_failure_keeps_prior_window_replayable(self):
        session = stream.NativeSession("v1", dict(schema=native.BASELINE_SCHEMA, entries=[]))
        self.addCleanup(session.stop)
        deadline = time.monotonic() + 5
        while session.status()["samples"] == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertGreater(session.status()["samples"], 0)
        with patch.object(stream, "MAX_WINDOW_BYTES", stream.HEALTH_RESERVE_BYTES + 16):
            self.assertTrue(session.closed.wait(5))
        self.assertEqual(session.status()["state"], "failed")
        rows = session.snapshot()
        self.assertGreater(len(rows), 1)
        self.assertEqual(rows[-2]["stream_final_sequence"], rows[-2]["stream_sequence"])
        data = engine.parse_bytes(engine.canonical(rows).encode(), "partial.json")
        result = engine.analyze(data, None, native.default_policy(data))
        self.assertEqual(result["summary"]["Unknown"], 1)


if __name__ == "__main__":
    unittest.main()

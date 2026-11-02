"""Protocol regressions: omissions, process changes, and loss must remain visible."""

import copy
import unittest

import engine
import native_integrity as native
import native_stream as stream
from test_native_integrity import capture


class StreamTests(unittest.TestCase):
    def setUp(self):
        base = capture()["observations"][0]
        base.pop("scenario")
        base.update(phase="live", process_started="134370000000000000")
        self.ranges = [
            dict(
                range_name=name,
                range_rva=rva,
                range_size=base["range_size"],
                reference_hex=base["reference_hex"],
                reference_sha256=base["reference_sha256"],
            )
            for name, rva in (("LabCodeProbe", 4096), ("LabCodeSecondary", 8192))
        ]
        self.ready = dict(
            schema=stream.STREAM_SCHEMA,
            type="ready",
            build="v1",
            ranges=self.ranges,
            interval_ms=500,
            duration_ms=600000,
        )
        self.sample = dict(
            schema=stream.STREAM_SCHEMA,
            type="sample",
            sequence=1,
            elapsed_ms=0,
            dropped_samples=0,
            observations=[dict(base, **spec) for spec in self.ranges],
        )
        self.registry = dict(schema=native.BASELINE_SCHEMA, entries=[])

    def decoder(self):
        decoder = stream.StreamDecoder(self.registry)
        decoder.accept(self.ready)
        return decoder

    def analyze(self, rows):
        data = engine.parse_bytes(engine.canonical(rows).encode(), "stream.json")
        return engine.analyze(data, None, native.default_policy(data))

    def test_missing_or_duplicate_sample_and_invalid_ending_rejected(self):
        for frame in (dict(self.sample, sequence=2), dict(self.sample, sequence=True)):
            with self.assertRaises(ValueError):
                self.decoder().accept(frame)
        decoder = self.decoder()
        decoder.accept(self.sample)
        with self.assertRaises(ValueError):
            decoder.accept(self.sample)
        with self.assertRaises(ValueError):
            decoder.accept(
                dict(
                    schema=stream.STREAM_SCHEMA,
                    type="end",
                    sequence=2,
                    dropped_samples=0,
                    reason="stopped",
                )
            )

    def test_transport_gap_and_trailing_drops_are_accounted_for(self):
        decoder = self.decoder()
        groups = [decoder.accept(self.sample)]
        groups.append(
            decoder.accept(dict(self.sample, sequence=4, elapsed_ms=1500, dropped_samples=2))
        )
        decoder.accept(
            dict(
                schema=stream.STREAM_SCHEMA,
                type="end",
                sequence=5,
                dropped_samples=3,
                reason="stopped",
            )
        )
        rows = stream.snapshot_rows(groups, dropped=3, final_sequence=5)
        result = self.analyze(rows)
        self.assertEqual(result["summary"]["Unknown"], 1)
        self.assertEqual(rows[-1]["stream_dropped_samples"], 3)
        with self.assertRaises(ValueError):
            self.analyze(rows[:-1])

    def test_partial_ranges_wrong_session_and_scenario_labels_rejected(self):
        invalid = []
        one = copy.deepcopy(self.sample)
        one["observations"].pop()
        invalid.append(one)
        for key, value in (
            ("session_id", "other"),
            ("scenario", "changed"),
            ("captured_at", "2026-10-21T12:00:00"),
        ):
            changed = copy.deepcopy(self.sample)
            changed["observations"][1][key] = value
            invalid.append(changed)
        for frame in invalid:
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                self.decoder().accept(frame)

    def test_restart_requires_new_decoder_and_time_cannot_reverse(self):
        decoder = self.decoder()
        decoder.accept(dict(self.sample, elapsed_ms=500))
        with self.assertRaises(ValueError):
            decoder.accept(dict(self.sample, sequence=2, elapsed_ms=100))
        changed = copy.deepcopy(self.sample)
        changed.update(sequence=2, elapsed_ms=600)
        for raw in changed["observations"]:
            raw["session_id"] = "new-process"
        with self.assertRaises(ValueError):
            decoder.accept(changed)

    def test_retained_window_declares_eviction_and_preserves_unknown(self):
        decoder = self.decoder()
        decoder.accept(self.sample)
        groups = [decoder.accept(dict(self.sample, sequence=2, elapsed_ms=500))]
        rows = stream.snapshot_rows(groups, evicted=1)
        self.assertEqual(self.analyze(rows)["summary"]["Unknown"], 1)
        changed = copy.deepcopy(rows)
        for row in changed:
            row["stream_evicted_samples"] = 0
        with self.assertRaises(ValueError):
            self.analyze(changed)

    def test_removed_tail_sample_detected_by_snapshot_ending(self):
        decoder = self.decoder()
        groups = [
            decoder.accept(self.sample),
            decoder.accept(dict(self.sample, sequence=2, elapsed_ms=500)),
        ]
        rows = stream.snapshot_rows(groups)
        with self.assertRaises(ValueError):
            self.analyze(rows[:2])
        for row in rows:
            for key in (
                "stream_capture_state",
                "stream_final_sequence",
                "stream_final_dropped",
            ):
                row.pop(key)
        with self.assertRaises(ValueError):
            self.analyze(rows)

    def test_failed_before_first_sample_is_unknown(self):
        rows = stream.snapshot_rows([], state="failed", error="Producer disconnected")
        self.assertEqual(self.analyze(rows)["summary"]["Unknown"], 1)

    def test_terminal_frame_closes_decoder(self):
        decoder = self.decoder()
        decoder.accept(
            dict(
                schema=stream.STREAM_SCHEMA,
                type="end",
                sequence=0,
                dropped_samples=0,
                reason="stopped",
            )
        )
        with self.assertRaises(ValueError):
            decoder.accept(self.sample)


if __name__ == "__main__":
    unittest.main()

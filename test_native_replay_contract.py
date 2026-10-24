"""Replay must enforce the same narrow identity/history contract as live input.

All observations and approvals are synthetic; these tests launch no process.
They establish internal consistency, not authenticity of local evidence.
"""

import copy
import json
import unittest
from unittest.mock import patch

import engine
import native_integrity as native
import native_stream as stream
from test_native_integrity import capture as legacy_capture
from test_native_manifest_security import versioned_capture
from test_native_window import many_ranges


def sample(observations, sequence=1, elapsed=0, dropped=0):
    return dict(
        schema=stream.STREAM_SCHEMA,
        type="sample",
        sequence=sequence,
        elapsed_ms=elapsed,
        dropped_samples=dropped,
        observations=observations,
    )


def analyze(rows, jsonl=False):
    encoded = (
        "\n".join(engine.canonical(row) for row in rows) + "\n"
        if jsonl
        else engine.canonical(rows)
    )
    data = engine.parse_bytes(encoded.encode(), "replay.jsonl" if jsonl else "replay.json")
    return engine.analyze(data, None, native.default_policy(data))


class NativeReplayContractTests(unittest.TestCase):
    def test_identical_replay_manifests_are_validated_once_per_layer_per_call(self):
        rows = stream.snapshot_rows(self.groups(8))
        with patch.object(native, "validate_manifest", wraps=native.validate_manifest) as validate:
            native.validate_coverage(rows)
            self.assertEqual(validate.call_count, 2)
            native.validate_coverage(rows)
            self.assertEqual(validate.call_count, 4)

    def test_repeated_manifest_reuse_keeps_row_context_and_fingerprints_checked(self):
        rows = stream.snapshot_rows(self.groups(2))
        for field, value in (
            ("module_size", True), ("module_size", 1),
            ("module_sha256", "0" * 64),
            ("range_manifest_sha256", "0" * 64),
            ("integrity_manifest_sha256", "0" * 64),
            ("range_manifest", "[]"), ("integrity_manifest", "{}"),
        ):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(rows)
                changed[-1][field] = value
                with self.assertRaises(ValueError):
                    native.validate_coverage(changed)

    def test_changed_range_manifest_revalidates_unchanged_declaration(self):
        rows = stream.snapshot_rows(self.groups(2))
        manifest = json.loads(rows[-1]["range_manifest"])
        manifest[-1]["range_rva"] += 1024
        rows[-1]["range_manifest"] = engine.canonical(manifest)
        rows[-1]["range_manifest_sha256"] = native.digest(manifest)
        with self.assertRaises(ValueError):
            native.validate_coverage(rows)

    def groups(self, count=2):
        decoder, observations = many_ranges(2)
        groups = [
            decoder.accept(sample(observations, n, (n - 1) * 500)) for n in range(1, count + 1)
        ]
        return groups

    def assert_import_rejected(self, rows):
        for jsonl in (False, True):
            with self.subTest(encoding="jsonl" if jsonl else "json"):
                with self.assertRaises(ValueError):
                    analyze(rows, jsonl)

    def test_approved_versioned_control_replays_without_findings_or_gaps(self):
        for jsonl in (False, True):
            result = analyze(stream.snapshot_rows(self.groups()), jsonl)
            self.assertEqual(result["summary"]["No finding"], 4)
            self.assertEqual(result["summary"]["Unknown"], 0)
            self.assertTrue(all(not row["gaps"] for row in result["records"]))

    def test_joint_sequence_and_drop_rollback_rejected_on_replay(self):
        groups = self.groups()
        for group, sequence, dropped in ((groups[0], 3, 2), (groups[1], 2, 0)):
            for row in group:
                row.update(
                    stream_sequence=sequence,
                    stream_dropped_samples=dropped,
                    event_id=f"{sequence}:{row['range_name']}",
                )
        self.assert_import_rejected(stream.snapshot_rows(groups, final_sequence=2))

    def test_joint_sequence_and_drop_rollback_rejected_live(self):
        decoder, observations = many_ranges(2)
        decoder.accept(sample(observations, sequence=3, dropped=2))
        with self.assertRaises(ValueError):
            decoder.accept(sample(observations, sequence=2, elapsed=500, dropped=0))

    def test_valid_transport_loss_keeps_unknown_health(self):
        decoder, observations = many_ranges(2)
        groups = [decoder.accept(sample(observations, sequence=3, dropped=2))]
        groups.append(decoder.accept(sample(observations, sequence=5, elapsed=500, dropped=3)))
        rows = stream.snapshot_rows(groups, dropped=3, final_sequence=5)
        result = analyze(rows)
        self.assertEqual(result["summary"]["No finding"], 4)
        self.assertEqual(result["summary"]["Unknown"], 1)
        self.assert_import_rejected(rows[:-1])

    def test_sibling_creation_and_build_conflicts_rejected_on_replay(self):
        for field, value in (("process_started", "999"), ("build", "v2")):
            with self.subTest(field=field):
                rows = stream.snapshot_rows(self.groups(1))
                rows[1][field] = value
                self.assert_import_rejected(rows)

    def test_cross_sample_creation_and_build_conflicts_rejected_on_replay(self):
        for field, value in (("process_started", "999"), ("build", "v2")):
            with self.subTest(field=field):
                groups = self.groups()
                for row in groups[1]:
                    row[field] = value
                self.assert_import_rejected(stream.snapshot_rows(groups))

    def test_sibling_and_cross_sample_identity_conflicts_rejected_live(self):
        for field, value in (("process_started", "999"), ("build", "v2")):
            for siblings in (True, False):
                with self.subTest(field=field, siblings=siblings):
                    decoder, observations = many_ranges(2)
                    decoder.accept(sample(observations))
                    changed = copy.deepcopy(observations)
                    for row in changed[1:] if siblings else changed:
                        row[field] = value
                    with self.assertRaises(ValueError):
                        decoder.accept(sample(changed, sequence=2, elapsed=500))

    def test_invalid_pid_rejected_on_live_and_replay(self):
        for value in (None, False, 0, -1, 0x100000000, 1.0, "1"):
            with self.subTest(value=value):
                decoder, observations = many_ranges(2)
                rows = stream.snapshot_rows(self.groups(1))
                for row in observations + rows:
                    row["pid"] = value
                with self.assertRaises(ValueError):
                    decoder.accept(sample(observations))
                self.assert_import_rejected(rows)

    def test_invalid_creation_rejected_on_live_and_replay(self):
        for value in (None, False, "", "not-a-filetime", "-1", "1.0", "1" * 21):
            with self.subTest(value=value):
                decoder, observations = many_ranges(2)
                rows = stream.snapshot_rows(self.groups(1))
                for row in observations + rows:
                    row["process_started"] = value
                with self.assertRaises(ValueError):
                    decoder.accept(sample(observations))
                self.assert_import_rejected(rows)

    def test_unsupported_build_rejected_on_live_and_replay(self):
        for value in (None, False, "", "v3"):
            with self.subTest(value=value):
                decoder, observations = many_ranges(2)
                rows = stream.snapshot_rows(self.groups(1))
                for row in observations + rows:
                    row["build"] = value
                with self.assertRaises(ValueError):
                    decoder.accept(sample(observations))
                self.assert_import_rejected(rows)

    def test_live_identity_endpoints_and_opaque_session_remain_valid(self):
        for pid, creation in ((1, "0"), (0xFFFFFFFF, "9" * 20), (1, 1)):
            with self.subTest(pid=pid, creation=creation):
                decoder, observations = many_ranges(2)
                for row in observations:
                    row.update(pid=pid, process_started=creation, session_id="opaque-session")
                rows = stream.snapshot_rows([decoder.accept(sample(observations))])
                self.assertEqual(analyze(rows)["summary"]["No finding"], 2)

    def test_legacy_one_shot_does_not_acquire_live_identity_requirements(self):
        for creation in (None, "2026-01-01T00:00:00Z"):
            capture = legacy_capture()
            for row in capture["observations"]:
                if creation is not None:
                    row["process_started"] = creation
                row.pop("build")
            registry = native.approve(
                capture, dict(schema=native.BASELINE_SCHEMA, entries=[]), "Legacy fixture"
            )
            self.assertEqual(
                analyze(native.convert(capture, registry))["summary"]["No finding"], 3
            )

    def test_legacy_live_without_integrity_manifest_remains_readable(self):
        decoder, observations = many_ranges(2)
        legacy = stream.StreamDecoder(dict(schema=native.BASELINE_SCHEMA, entries=[]))
        legacy.accept(
            dict(
                schema=stream.STREAM_SCHEMA,
                type="ready",
                build="v1",
                ranges=decoder.ranges,
                interval_ms=500,
                duration_ms=600000,
            )
        )
        rows = stream.snapshot_rows([legacy.accept(sample(observations))])
        self.assertTrue(all("integrity_manifest" not in row for row in rows))
        self.assertEqual(analyze(rows)["summary"]["Review"], 2)

    def test_unreadable_precedence_preserves_collection_gaps(self):
        capture = versioned_capture()
        empty = dict(schema=native.BASELINE_SCHEMA, entries=[])
        approved = native.approve(capture, empty, "Approved synthetic fixture")
        capture["observations"][2].update(memory_status="failed", observed_hex=None)
        for registry, status in ((approved, "Unknown"), (empty, "Review")):
            with self.subTest(status=status):
                converted = native.convert(capture, registry)
                result = analyze(converted)
                row = result["records"][2]
                self.assertEqual(row["status"], status)
                self.assertTrue(row["gaps"])
                self.assertIsNone(converted[2]["memory_matches"])
                self.assertIsNone(converted[2]["observed_sha256"])
                self.assertIsNone(converted[2]["protection_matches"])

    def test_staleness_is_current_health_not_durable_pause_history(self):
        session = stream.NativeSession.__new__(stream.NativeSession)
        session.state, session.error, session.last_received = "running", None, 100.0
        with patch.object(stream.time, "monotonic", return_value=106.5):
            self.assertIn("no sample received", session._health_error())
            session.last_received = 106.5
            self.assertIsNone(session._health_error())
        decoder, observations = many_ranges(2)
        groups = [decoder.accept(sample(observations))]
        groups.append(decoder.accept(sample(observations, sequence=2, elapsed=6500)))
        rows = stream.snapshot_rows(groups)
        self.assertEqual(rows[2]["stream_elapsed_ms"], 6500)
        self.assertEqual(analyze(rows)["summary"]["No finding"], 4)
        self.assertFalse(any(row.get("stream_health") for row in rows))


if __name__ == "__main__":
    unittest.main()

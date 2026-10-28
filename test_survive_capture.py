"""Recorder boundaries, evidence preservation and unchanged detector integration."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

import survive_capture as capture


SID = "c" * 32


def row(t, event="sample", **extra):
    value = dict(schema="survive-v3", session_id=SID, seq=0, elapsed_s=t,
                 event=event, x_cm=0, y_cm=0, z_cm=90, movement_mode="walking",
                 related_id="", detail="", a=0, b=0, c=0, d=0,
                 source_x_cm=0, source_y_cm=0, velocity_x_cm_s=0, velocity_y_cm_s=0,
                 server_tick=int(t * 60 + .0001), delta_s=1 / 60, monotonic_s=t,
                 profile_id="survive-lucian-practice-v1", path_radius_cm=41,
                 hit_radius_cm=65, visual_radius_cm=50, threat_x_cm=0, threat_y_cm=0,
                 nearest_clearance_cm=0, clearance_valid=False, baseline_threat="unknown")
    value.update(extra)
    return value


def lines(*rows):
    return [(json.dumps(dict(r, seq=i), allow_nan=False) + "\n").encode() for i, r in enumerate(rows)]


def full():
    return b"".join(lines(row(0, "run_start", detail="fixed_seed", a=1337, b=.5, c=60, d=3),
                          row(0), row(1 / 30, x_cm=335 / 30), row(60, x_cm=335 / 30),
                          row(60, "run_end", detail="completed", movement_mode="ended", x_cm=335 / 30)))


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.base = Path(self.temp.name)
        self.manager = capture.CaptureManager(self.base / "sources", self.base / "recordings", poll_seconds=.01)
        self.source = self.manager.source_root / (SID + ".jsonl")

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def wait(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self.manager.status()
            if predicate(value):
                return value
            time.sleep(.01)
        self.fail("Recorder did not reach expected state: " + str(self.manager.status()["capture"]))

    def finish(self):
        self.wait(lambda r: r["capture"]["state"] in {"complete", "failed", "stopped"})
        return self.manager.stop()

    def test_split_lines_preserve_bytes_and_stop_does_not_forge_terminal(self):
        pieces = lines(row(0, "run_start", detail="fixed_seed"), row(.03))
        self.manager.start("next")
        self.source.write_bytes(pieces[0] + pieces[1][:40])
        state = self.wait(lambda s: s["capture"]["records"] == 1)
        self.assertEqual(state["capture"]["health"]["pending_bytes"], 40)
        self.assertEqual(state["view"]["analysis"]["state"], "pending")
        stopped = self.manager.stop()
        rid = stopped["capture"]["recording_id"]
        raw = (self.manager.recording_root / rid / "source.jsonl").read_bytes()
        self.assertEqual(raw, pieces[0] + pieces[1][:40])
        self.assertNotIn(b'"run_end"', raw)
        self.assertEqual(stopped["capture"]["analysis_state"], "unavailable")
        self.assertEqual(self.manager.open(rid)["capture"]["completion"], None)

    def test_partial_append_later_completes_and_reopen_reproduces(self):
        raw = full()
        self.source.write_bytes(raw[:100])
        self.manager.start(SID)
        self.wait(lambda s: s["capture"]["bytes"] == 100)
        with self.source.open("ab") as target:
            target.write(raw[100:])
        state = self.finish()
        self.assertEqual(state["capture"]["state"], "complete", state["capture"])
        self.assertEqual(state["capture"]["source_sha256"], hashlib.sha256(raw).hexdigest())
        rid = state["capture"]["recording_id"]
        reopened = self.manager.open(rid)
        self.assertEqual(reopened["view"]["constraints"], state["view"]["constraints"])
        self.assertEqual(reopened["view"]["analysis"], state["view"]["analysis"])
        self.assertEqual(self.source.read_bytes(), raw)

    def test_next_waits_for_new_source_and_never_rolls_into_restart(self):
        self.source.write_bytes(full())
        self.manager.start("next")
        time.sleep(.04)
        self.assertEqual(self.manager.status()["capture"]["state"], "waiting")
        second = "d" * 32
        raw = full().replace(SID.encode(), second.encode())
        (self.manager.source_root / (second + ".jsonl")).write_bytes(raw)
        state = self.finish()
        self.assertEqual(state["capture"]["session_id"], second)
        (self.manager.source_root / ("e" * 32 + ".jsonl")).write_bytes(full().replace(SID.encode(), b"e" * 32))
        self.assertEqual(self.manager.status()["capture"]["session_id"], second)

    def test_ambiguous_next_source_is_rejected(self):
        self.manager.start("next")
        with self.manager.active.lock:
            self.source.write_bytes(full())
            (self.manager.source_root / ("d" * 32 + ".jsonl")).write_bytes(full().replace(SID.encode(), b"d" * 32))
        state = self.finish()
        self.assertEqual(state["capture"]["state"], "failed")
        self.assertIn("More than one", state["capture"]["health"]["error"])
        self.assertEqual(state["capture"]["records"], 0)

    def test_recording_write_failure_is_not_retried_as_a_source_lock(self):
        class FailedWriter:
            def __init__(self, stream):
                self.stream, self.writes = stream, 0
            def write(self, value):
                self.writes += 1
                raise PermissionError("injected output write failure")
            def flush(self):
                return self.stream.flush()
            def fileno(self):
                return self.stream.fileno()
            def close(self):
                return self.stream.close()
        self.manager.start("next")
        with self.manager.active.lock:
            failed = FailedWriter(self.manager.active.raw_stream)
            self.manager.active.raw_stream = failed
            self.source.write_bytes(full())
        state = self.finish()
        self.assertEqual(state["capture"]["state"], "failed")
        self.assertEqual(failed.writes, 1)
        self.assertTrue(failed.stream.closed)
        self.assertEqual(state["capture"]["health"]["parse_errors"], 0)
        self.assertIn("output write failure", state["capture"]["health"]["error"])
        self.assertEqual(self.manager.open(state["capture"]["recording_id"])["capture"]["state"], "failed")

    def test_initialization_failure_closes_open_output(self):
        opened = []
        original = Path.open
        def controlled(path, *args, **kwargs):
            if path.name == "receipts.jsonl":
                raise PermissionError("injected second output failure")
            stream = original(path, *args, **kwargs)
            if path.name == "source.jsonl":
                opened.append(stream)
            return stream
        with mock.patch.object(Path, "open", controlled):
            with self.assertRaises(PermissionError):
                self.manager.start("next")
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)
        self.assertFalse(list(self.manager.recording_root.glob("*/manifest.json")))
        attempts = self.manager.sessions()
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["review_status"], "Unknown")
        self.assertEqual(attempts[0]["retained_bytes"], 0)

    def test_terminal_results_are_published_only_after_manifest_is_durable(self):
        observed = []
        original = capture._Session._save_manifest
        def saving(session):
            observed.append((self.manager.status(), (session.directory / "manifest.json").exists()))
            original(session)
        with mock.patch.object(capture._Session, "_save_manifest", saving):
            self.manager.start("next")
            self.source.write_bytes(full())
            final = self.finish()
        during, existed = observed[0]
        self.assertFalse(existed)
        self.assertTrue(during["capture"]["finalizing"])
        self.assertFalse(during["capture"]["finalized"])
        self.assertEqual(during["capture"]["state"], "recording")
        self.assertEqual(during["view"]["analysis"], {"state": "pending", "counts": None})
        self.assertFalse(during["view"]["constraints"])
        self.assertTrue(final["capture"]["finalized"])
        self.assertFalse(final["capture"]["finalizing"])
        self.assertEqual(final["capture"]["state"], "complete")
        self.assertTrue((self.manager.active.directory / "manifest.json").is_file())

    def test_missing_and_corrupt_manifests_remain_visible_with_retained_bytes(self):
        raw = full()
        self.source.write_bytes(raw)
        self.manager.start(SID)
        rid = self.finish()["capture"]["recording_id"]
        directory = self.manager.recording_root / rid
        (directory / "manifest.json").unlink()
        for corrupt in (None, b"{broken"):
            if corrupt is not None:
                (directory / "manifest.json").write_bytes(corrupt)
            attempt = self.manager.sessions()[0]
            self.assertEqual(attempt["recording_id"], rid)
            self.assertEqual(attempt["review_status"], "Unknown")
            self.assertEqual(attempt["retained_bytes"], len(raw))
            self.assertFalse(attempt["verified"])
            with self.assertRaisesRegex(ValueError, str(len(raw)) + " source bytes remain retained"):
                self.manager.open(rid)
            report = self.manager.verified_summaries()
            self.assertEqual(report["rejected"][0]["recording_id"], rid)
            self.assertEqual(report["rejected"][0]["bytes"], len(raw))
            self.assertFalse(report["recordings"])
            self.assertEqual((directory / "source.jsonl").read_bytes(), raw)

    def test_incremental_verified_summaries_bound_reanalysis_and_recheck_cache(self):
        self.source.write_bytes(full())
        ids = []
        for _ in range(6):
            self.manager.start(SID)
            ids.append(self.finish()["capture"]["recording_id"])
        reviewer = capture.CaptureManager(self.manager.source_root, self.manager.recording_root, poll_seconds=.01)
        try:
            with mock.patch.object(capture, "_analysis", wraps=capture._analysis) as analysis:
                first = reviewer.verified_summaries()
                self.assertEqual(analysis.call_count, 4)
                self.assertEqual(len(first["recordings"]), 4)
                self.assertEqual(len(first["pending"]), 2)
                self.assertIsNone(reviewer._opened)
                analysis.reset_mock()
                second = reviewer.verified_summaries()
                self.assertEqual(analysis.call_count, 2)
                self.assertEqual(len(second["recordings"]), 6)
                self.assertFalse(second["pending"])
                analysis.reset_mock()
                reviewer.start("next")
                selected = reviewer.status()["capture"]["recording_id"]
                third = reviewer.verified_summaries()
                self.assertEqual(analysis.call_count, 0)
                self.assertEqual(third["pending"], [selected])
                self.assertEqual(reviewer.status()["capture"]["state"], "waiting")
                self.assertIsNone(reviewer._opened)
                for cached in reviewer._verified.values():
                    self.assertEqual(set(cached), {"hashes", "analysis_identity", "summary"})
                    self.assertNotIn("samples", cached["summary"]["view"])
                saved = reviewer.recording_root / ids[0] / "source.jsonl"
                saved.write_bytes(saved.read_bytes() + b" ")
                fourth = reviewer.verified_summaries()
                self.assertEqual(analysis.call_count, 0)
                self.assertEqual(len(fourth["recordings"]), 5)
                self.assertEqual(fourth["rejected"][0]["recording_id"], ids[0])
                reviewer.verified_summaries()
                self.assertEqual(analysis.call_count, 0)
                with mock.patch.object(capture, "_analysis_identity", return_value={"changed": "identity"}):
                    changed = reviewer.verified_summaries(0)
                self.assertFalse(changed["recordings"])
                self.assertEqual(len(changed["rejected"]), 5)
            for invalid in (-1, 5, True, 1.5):
                with self.assertRaises(ValueError):
                    reviewer.verified_summaries(invalid)
        finally:
            reviewer.close()

    def test_unterminated_line_and_wait_timeout_remain_incomplete(self):
        self.source.write_bytes(b"x" * (capture.MAX_LINE + 1))
        self.manager.start(SID)
        state = self.finish()
        self.assertEqual(state["capture"]["state"], "failed")
        self.assertIsNone(state["capture"]["completion"])
        limited = capture.CaptureManager(self.base / "wait", self.base / "waitout", poll_seconds=.01, max_seconds=.03)
        try:
            limited.start("next")
            limited.active.thread.join(3)
            result = limited.stop()
            self.assertEqual(result["capture"]["stop_reason"], "recording_time_limit")
            self.assertIsNone(result["view"]["analysis"]["counts"])
        finally:
            limited.close()

    def test_sequence_loss_is_failed_and_visible(self):
        raw = b"".join(lines(row(0, "run_start"), row(.03))).replace(b'"seq": 1', b'"seq": 3')
        self.source.write_bytes(raw)
        self.manager.start(SID)
        state = self.finish()
        self.assertEqual(state["capture"]["state"], "failed")
        self.assertEqual(state["capture"]["health"]["sequence_gaps"], 2)
        self.assertFalse(state["view"]["constraints"])
        self.assertEqual(self.manager.open(state["capture"]["recording_id"])["capture"]["state"], "failed")

    def test_rewriting_accepted_bytes_fails(self):
        raw = b"".join(lines(row(0, "run_start"), row(.03)))
        self.source.write_bytes(raw)
        self.manager.start(SID)
        self.wait(lambda s: s["capture"]["records"] == 2)
        self.source.write_bytes(raw.replace(b'"x_cm": 0', b'"x_cm": 1', 1))
        state = self.finish()
        self.assertEqual(state["capture"]["state"], "failed")
        saved = self.manager.recording_root / state["capture"]["recording_id"] / "source.jsonl"
        self.assertEqual(saved.read_bytes(), raw)

    def test_profile_labels_and_duplicate_fields_rejected(self):
        raws = [full().replace(b'"profile_id": "survive-lucian-practice-v1"', b'"profile_id": "survive-lucian-reference-v1"'),
                full().replace(b'"event": "sample"', b'"event": "sample", "condition": "human"', 1),
                full().replace(b'"seq": 0', b'"seq": 0, "seq": 0', 1)]
        for raw in raws:
            self.source.write_bytes(raw)
            self.manager.start(SID)
            state = self.finish()
            self.assertEqual(state["capture"]["state"], "failed")
            self.assertFalse(state["view"]["constraints"])

    def test_limits_and_ids(self):
        for source_id in ("../escape", "c" * 32 + ".jsonl", "C:/private", None, []):
            with self.assertRaises((ValueError, TypeError)):
                self.manager.start(source_id)
        for recording_id in ("../escape", "f" * 31, "f" * 32 + "/file"):
            with self.assertRaises(ValueError):
                self.manager.open(recording_id)
        small = capture.CaptureManager(self.base / "small", self.base / "smallout", poll_seconds=.01, max_bytes=128)
        try:
            (small.source_root / (SID + ".jsonl")).write_bytes(full())
            small.start(SID)
            small.active.thread.join(3)
            self.assertEqual(small.stop()["capture"]["state"], "failed")
            self.assertLessEqual((small.active.directory / "source.jsonl").stat().st_size, 128)
        finally:
            small.close()

    def test_tampering_and_untrusted_manifest_paths_fail(self):
        self.source.write_bytes(full())
        self.manager.start(SID)
        state = self.finish()
        directory = self.manager.recording_root / state["capture"]["recording_id"]
        raw = (directory / "source.jsonl").read_bytes()
        (directory / "source.jsonl").write_bytes(raw + b" ")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.manager.open(state["capture"]["recording_id"])
        (directory / "source.jsonl").write_bytes(raw)
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["files_sha256"]["../escape"] = "0" * 64
        (directory / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "Unexpected recording files"):
            self.manager.open(state["capture"]["recording_id"])

    def test_reopen_does_not_interrupt_active_recording_and_imports_are_private(self):
        before = {name: sys.modules.get(name) for name in ("prepare", "prepare_v2", "prepare_v3", "audit_v3")}
        self.source.write_bytes(full())
        self.manager.start(SID)
        first = self.finish()["capture"]["recording_id"]
        self.manager.start("next")
        current = self.manager.status()["capture"]["recording_id"]
        self.manager.open(first)
        self.assertEqual(self.manager.status()["capture"]["recording_id"], current)
        self.assertEqual(self.manager.status()["capture"]["state"], "waiting")
        self.assertEqual(before, {name: sys.modules.get(name) for name in before})

    def test_exact_raw_selection_from_active_and_saved_after_page_limit(self):
        raw = b"".join(lines(row(0, "run_start"), *[row(i / 30) for i in range(300)],
                             row(60, "run_end", detail="completed", movement_mode="ended")))
        self.source.write_bytes(raw)
        self.manager.start(SID)
        state = self.finish()
        rid = state["capture"]["recording_id"]
        expected = json.loads(raw.splitlines()[280])
        self.assertEqual(self.manager.record(rid, 280)["record"], expected)
        self.manager.start("next")
        self.manager.open(rid)
        self.assertEqual(self.manager.record(rid, 280)["record"], expected)
        self.assertEqual(len(self.manager.open(rid)["records"]), 256)
        for seq in (-1, True, 10000, 900):
            with self.assertRaises(ValueError):
                self.manager.record(rid, seq)
        directory = self.manager.recording_root / rid
        (directory / "source.jsonl").write_bytes(raw + b" ")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.manager.record(rid, 280)

    def test_all_nine_original_pilot_streams_remain_byte_identical(self):
        report_path = capture.LAB / "telemetry/local/opportunity-v2-reanalysis-20261026T115100Z-b6a76d5c/report.json"
        if not report_path.is_file():
            self.skipTest("Local nine-run evidence is not included in a source checkout")
        report = json.loads(report_path.read_text())
        profile, _, policy = capture._profile("survive-lucian-practice-v1")
        checked = 0
        for trial in report["trials"]:
            # Locate by the exact retained source hash, not an assumed case label.
            source_hash = trial.get("raw_sha256")
            if source_hash is None:
                continue
            candidates = capture.LAB.glob("telemetry/local/development-pilot-review-20261026T112755Z-88b998ed/**/source.jsonl")
            source = next((p for p in candidates if hashlib.sha256(p.read_bytes()).hexdigest() == source_hash), None)
            self.assertIsNotNone(source)
            analysis, derived = capture._analysis(source.read_bytes(), profile, policy)
            self.assertEqual(derived, source.with_name("surge.jsonl").read_bytes())
            self.assertEqual(hashlib.sha256(derived).hexdigest(), trial["current_derived_sha256"])
            self.assertEqual(analysis["counts"], trial["verdict_counts"])
            self.assertTrue(analysis["constraints"])
            checked += 1
        self.assertEqual(checked, 9)


if __name__ == "__main__":
    unittest.main()

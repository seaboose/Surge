"""Pinned evidence, immutable revisions, export safety and failure recovery."""
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from survive_capture import CaptureManager
import survive_investigations as investigation

SID = "e" * 32


def capture_bytes():
    def row(seq, elapsed, event="sample", **extra):
        value = dict(schema="survive-v3", session_id=SID, seq=seq, elapsed_s=elapsed,
                     event=event, x_cm=0, y_cm=0, z_cm=90, movement_mode="walking",
                     related_id="", detail="", a=0, b=0, c=0, d=0,
                     source_x_cm=0, source_y_cm=0, velocity_x_cm_s=0, velocity_y_cm_s=0,
                     server_tick=int(elapsed * 60 + .0001), delta_s=1 / 60, monotonic_s=elapsed,
                     profile_id="survive-lucian-practice-v1", path_radius_cm=41,
                     hit_radius_cm=65, visual_radius_cm=50, threat_x_cm=0, threat_y_cm=0,
                     nearest_clearance_cm=0, clearance_valid=False, baseline_threat="unknown")
        value.update(extra)
        return value
    rows = [row(0, 0, "run_start", detail="fixed_seed", a=1337, b=.5, c=60, d=3), row(1, 0),
            row(2, 1 / 30, x_cm=335 / 30), row(3, 60, x_cm=335 / 30),
            row(4, 60, "run_end", detail="completed", movement_mode="ended", x_cm=335 / 30)]
    return b"".join(investigation._encoded(value) for value in rows)


class HTMLAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attributes = []
        self.in_json = False
        self.json_text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)
        if tag == "pre" and dict(attrs).get("id") == "surge-investigation-json":
            self.in_json = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_json = False

    def handle_data(self, value):
        if self.in_json:
            self.json_text.append(value)


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.base = Path(self.temp.name)
        self.capture = CaptureManager(self.base / "sources", self.base / "recordings", poll_seconds=.01)
        self.source = self.capture.source_root / (SID + ".jsonl")
        self.source.write_bytes(capture_bytes())
        self.capture.start(SID)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            state = self.capture.status()
            if state["capture"]["state"] in {"complete", "failed", "stopped"}:
                break
            time.sleep(.01)
        self.capture.stop()
        self.assertEqual(state["capture"]["state"], "complete", state)
        self.rid = state["capture"]["recording_id"]
        self.manager = investigation.InvestigationManager(self.capture, self.base / "Investigations")
        self.doc = self.manager.create("Movement investigation", "Analyst")["document"]
        self.iid = self.doc["investigation_id"]

    def tearDown(self):
        self.capture.close()
        self.temp.cleanup()

    def attach(self, seq=2, constraint="2:walking_displacement", revision=1):
        return self.manager.attach(self.iid, revision, self.rid, seq, constraint, "Analyst", "Attach measured interval")

    def save(self, expected=1, **override):
        args = dict(investigation_id=self.iid, expected_revision=expected, title="Movement investigation",
                    author="Reviewer", change_reason="Document observation", status="draft",
                    sections={name: "" for name in investigation.SECTIONS})
        args.update(override)
        return self.manager.save(**args)

    def test_evidence_revision_navigation_and_detector_bytes_stay_unchanged(self):
        folder = self.capture.recording_root / self.rid
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        first_revision = (self.manager.root / self.iid / "0001.json").read_bytes()
        attached = self.attach()
        card = attached["document"]["evidence"][0]
        self.assertEqual(card["raw_record"], self.capture.record(self.rid, 2)["record"])
        self.assertEqual(card["interval_start_record"]["seq"], 1)
        self.assertEqual(attached["verification"]["counts"]["verified"], 1)
        sections = dict(attached["document"]["sections"], conclusion="Allowance was respected in [E1].")
        saved = self.save(expected=2, sections=sections, status="reviewed")
        self.assertTrue(saved["verification"]["review_valid"])
        self.assertEqual(self.manager.resolve(self.iid, "E1", 3)["constraint_id"], "2:walking_displacement")
        historical = self.manager.open(self.iid, 2)
        self.assertEqual(historical["latest_revision"], 3)
        self.assertEqual(historical["document"]["status"], "draft")
        self.assertEqual(historical["document"]["sections"]["conclusion"], "")
        self.assertEqual(first_revision, (self.manager.root / self.iid / "0001.json").read_bytes())
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertEqual(self.source.read_bytes(), capture_bytes())

    def test_stale_save_and_bad_reference_preserve_draft_and_revision(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "another window"):
            self.save(expected=1)
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            self.save(expected=2, sections={name: "[E99]" for name in investigation.SECTIONS})
        self.assertEqual(self.manager.open(self.iid)["document"]["revision"], 2)

    def test_history_byte_bound_preserves_published_revisions(self):
        path = self.manager.root / self.iid / "0001.json"
        original = path.read_bytes()
        with mock.patch.object(investigation, "MAX_HISTORY_BYTES", len(original) + 1):
            with self.assertRaisesRegex(ValueError, "history bound"):
                self.save()
        self.assertEqual(original, path.read_bytes())
        self.assertFalse((path.parent / "0002.json").exists())
        with mock.patch.object(investigation, "MAX_HISTORY_BYTES", len(original) - 1):
            with self.assertRaisesRegex(ValueError, "history bound"):
                self.manager.open(self.iid)

    def test_resolution_returns_the_verified_snapshot_without_second_client_open(self):
        card = self.attach()["document"]["evidence"][0]
        with mock.patch.object(self.capture, "record", side_effect=AssertionError("Must use the bound source snapshot")):
            resolved = self.manager.resolve(self.iid, "E1", 2)
        self.assertEqual(resolved["raw_record"], card["raw_record"])
        self.assertEqual(resolved["constraint"], card["constraint"])
        self.assertEqual(resolved["replay"]["capture"]["source_sha256"], card["capture"]["source_sha256"])
        self.assertEqual(next(row for row in resolved["replay"]["records"] if row["seq"] == 2), card["raw_record"])

    def test_concurrent_writers_publish_exactly_one_revision(self):
        peer = investigation.InvestigationManager(self.capture, self.manager.root)
        barrier = threading.Barrier(2)
        publisher = investigation._publish
        def synchronize(*args):
            barrier.wait(timeout=5)
            return publisher(*args)
        def write(manager, title):
            try:
                return manager.save(self.iid, 1, title, "Author", "Concurrent edit", "draft", {key: "" for key in investigation.SECTIONS})["document"]["title"]
            except ValueError as exc:
                return str(exc)
        with mock.patch.object(investigation, "_publish", side_effect=synchronize):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(write, manager, title) for manager, title in ((self.manager, "A"), (peer, "B"))]
                results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sum(value in {"A", "B"} for value in results), 1, results)
        self.assertEqual(len(self.manager.open(self.iid)["document"]["history"]), 2)

    def test_failed_atomic_publication_preserves_previous_revision(self):
        original = (self.manager.root / self.iid / "0001.json").read_bytes()
        with mock.patch.object(investigation.os, "link", side_effect=OSError("fixture link unsupported")):
            with self.assertRaisesRegex(ValueError, "safely publish"):
                self.save()
        self.assertEqual(original, (self.manager.root / self.iid / "0001.json").read_bytes())
        self.assertFalse((self.manager.root / self.iid / "0002.json").exists())
        self.assertFalse(list((self.manager.root / self.iid).glob(".pending-*")))

    def test_changed_source_retains_snapshot_blocks_navigation_and_review(self):
        original = self.attach()["document"]["evidence"][0]
        path = self.capture.recording_root / self.rid / "source.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        opened = self.manager.open(self.iid)
        self.assertEqual(opened["verification"]["items"][0]["state"], "changed")
        self.assertEqual(opened["document"]["evidence"][0], original)
        with self.assertRaisesRegex(ValueError, "navigation is unavailable"):
            self.manager.resolve(self.iid, "E1")
        with self.assertRaisesRegex(ValueError, "Resolve missing"):
            self.save(expected=2, status="reviewed", sections=dict(self.doc["sections"], conclusion="Checked [E1]"))
        exported = self.manager.export(self.iid, 2)
        self.assertIn("CHANGED", exported["html"])
        self.assertEqual(json.loads(exported["json"])["document"]["evidence"][0], original)

    def test_missing_source_has_explicit_warning_not_clean_evidence(self):
        self.attach()
        (self.capture.recording_root / self.rid / "source.jsonl").unlink()
        opened = self.manager.open(self.iid)
        self.assertEqual(opened["verification"]["items"][0]["state"], "missing")
        self.assertFalse(opened["verification"]["review_valid"])
        self.assertIn("MISSING", self.manager.export(self.iid)["html"])

    def test_revision_tampering_and_truncation_are_visible(self):
        self.save()
        first = self.manager.root / self.iid / "0001.json"
        value = json.loads(first.read_text())
        value["title"] = "Tampered first revision"
        first.write_bytes(investigation._encoded(value))
        with self.assertRaisesRegex(ValueError, "chain changed"):
            self.manager.open(self.iid)
        listed = self.manager.list()
        self.assertFalse(listed["investigations"][0]["history_verified"])
        first.write_bytes(b'{"schema":')
        with self.assertRaisesRegex(ValueError, "unreadable or truncated"):
            self.manager.open(self.iid)
        (self.manager.root / self.iid / "0002.json").write_bytes(b'{"schema":')
        self.assertEqual(self.manager.list()["unavailable"][0]["investigation_id"], self.iid)

    def test_export_escapes_active_content_and_structured_snapshot_is_exact(self):
        self.attach()
        text = '<script>alert(1)</script><img src="https://invalid.example/leak" onerror="bad()"> & [E1]'
        saved = self.save(expected=2, title=text[:120], sections=dict(self.doc["sections"], observations=text))
        self.save(expected=3, title="Later title")
        output = self.manager.export(self.iid, 3)
        parser = HTMLAudit()
        parser.feed(output["html"])
        self.assertNotIn("script", parser.tags)
        self.assertNotIn("img", parser.tags)
        self.assertFalse(any(key.lower().startswith("on") for key, value in parser.attributes))
        self.assertTrue(all(value.startswith("#E") for key, value in parser.attributes if key == "href"))
        embedded = json.loads("".join(parser.json_text))
        self.assertEqual(embedded, json.loads(output["json"]))
        self.assertEqual(embedded["document"]["sections"], saved["document"]["sections"])
        self.assertEqual(max(item["revision"] for item in embedded["document"]["history"]), 3)
        self.assertNotIn(str(self.base), output["html"])
        self.assertIn("default-src &#x27;none&#x27;", output["html"].replace("'", "&#x27;"))

    def test_export_rounds_summary_but_preserves_exact_measurements(self):
        attached = self.attach()
        original = attached["document"]["evidence"][0]
        revision_path = self.manager.root / self.iid / "0002.json"
        saved_bytes = revision_path.read_bytes()
        output = self.manager.export(self.iid, 2)
        self.assertIn("0.033 s · sequence 2", output["html"])
        self.assertIn("Observed 11.167 / allowed 16.167 cm", output["html"])
        self.assertIn("rounded to 3 decimal places", output["html"])
        self.assertEqual(json.loads(output["json"])["document"]["evidence"][0], original)
        self.assertEqual(original["constraint"]["observed"], 335 / 30)
        self.assertEqual(original["time_s"], 1 / 30)
        self.assertEqual(saved_bytes, revision_path.read_bytes())
        self.assertEqual(investigation._display_number(None), "Unavailable")
        self.assertEqual(investigation._display_number("not measured"), "Unavailable")

    def test_attachment_forces_draft_and_reviewed_status_can_become_stale(self):
        self.attach()
        self.save(expected=2, status="reviewed", sections=dict(self.doc["sections"], conclusion="Checked [E1]"))
        attached = self.attach(seq=1, constraint=None, revision=3)
        self.assertEqual(attached["document"]["status"], "draft")
        self.assertEqual(self.manager.open(self.iid, 3)["document"]["status"], "reviewed")
        (self.capture.recording_root / self.rid / "policy.json").write_text("{}")
        historic = self.manager.open(self.iid, 3)
        self.assertEqual(historic["document"]["status"], "reviewed")
        self.assertFalse(historic["verification"]["review_valid"])

    def test_distinct_source_verified_once_per_operation(self):
        self.attach()
        self.attach(seq=1, constraint=None, revision=2)
        with mock.patch.object(self.capture, "open", wraps=self.capture.open) as opened:
            result = self.manager.open(self.iid)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(result["verification"]["counts"]["verified"], 2)

    def test_strict_boundaries_and_constraint_mismatch(self):
        for identifier in ("../outside", "A" * 32, None, 1):
            with self.assertRaises(ValueError):
                self.manager.open(identifier)
        for seq in (True, -1, 10000):
            with self.assertRaises(ValueError):
                self.attach(seq=seq, constraint=None)
        with self.assertRaisesRegex(ValueError, "does not belong"):
            self.attach(seq=1)
        with self.assertRaises(ValueError):
            self.save(title=" " * 3)
        with self.assertRaises(ValueError):
            self.save(sections={key: "x" * 4001 for key in investigation.SECTIONS})
        with self.assertRaisesRegex(ValueError, "need evidence"):
            self.save(status="reviewed", sections=dict(self.doc["sections"], conclusion="Unsupported clean assertion"))
        self.assertEqual(self.manager.open(self.iid)["document"]["revision"], 1)

    def test_duplicate_evidence_and_unsafe_root_are_rejected(self):
        self.attach()
        with self.assertRaisesRegex(ValueError, "already attached"):
            self.attach(revision=2)
        fake = self.base / "not-a-directory"
        fake.write_text("fixture")
        with self.assertRaises(ValueError):
            investigation.InvestigationManager(self.capture, fake / "Investigations")


if __name__ == "__main__":
    unittest.main()

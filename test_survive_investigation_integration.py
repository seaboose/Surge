"""Real recorder/analysis integration checks for investigation annotations.

These tests use owned temporary streams and the actual adapter and detector.
They do not launch a game, simulate human play, or replace any capture API.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

import desktop_worker
from survive_capture import CaptureManager
from survive_investigations import InvestigationManager
from survive_workspace import SurviveWorkspace
from test_survive_capture import SID, full


class InvestigationIntegrationTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).parent / "verification/temporary-test-files"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="report-integration-", dir=parent)
        self.root = Path(self.temp.name)
        self.capture = CaptureManager(self.root / "sources", self.root / "recordings", poll_seconds=.01)
        self.reports = InvestigationManager(self.capture, root=self.root / "Investigations")
        self.original = full()
        self.source = self.capture.source_root / (SID + ".jsonl")
        self.source.write_bytes(self.original)
        self.capture.start(SID)
        saved = self.wait(lambda value: value["capture"]["state"] in {"complete", "failed"})
        self.assertEqual(saved["capture"]["state"], "complete", saved["capture"])
        self.capture.stop()
        self.recording_id = saved["capture"]["recording_id"]
        self.saved = self.capture.open(self.recording_id)
        self.constraint = next(item for item in self.saved["view"]["constraints"] if item["end_seq"] == 2)

    def tearDown(self):
        self.capture.close()
        self.temp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            value = self.capture.status()
            if predicate(value):
                return value
            time.sleep(.01)
        self.fail("Recorder did not reach the expected state: " + str(self.capture.status()["capture"]))

    def fingerprints(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for folder in (self.capture.source_root, self.capture.recording_root)
                for path in folder.rglob("*") if path.is_file()}

    def attached(self):
        created = self.reports.create(title="Independent integration check", author="Reviewer")
        doc = created["document"]
        return self.reports.attach(
            investigation_id=doc["investigation_id"], expected_revision=doc["revision"],
            recording_id=self.recording_id, seq=2, constraint_id=self.constraint["event_id"],
            author="Reviewer", change_reason="Preserve the selected measured interval.")

    def save_interpretation(self, document, text):
        sections = dict(document["sections"], observations=text,
                        conclusion="This annotation does not establish player legitimacy. [E1]")
        return self.reports.save(
            investigation_id=document["investigation_id"], expected_revision=document["revision"],
            title=document["title"], author="Reviewer", change_reason="Explain the selected interval.",
            status="draft", sections=sections)

    def test_annotations_history_export_preserve_exact_source_and_detector_results(self):
        before = self.fingerprints()
        expected_analysis = copy.deepcopy(self.saved["view"]["analysis"])
        expected_constraints = copy.deepcopy(self.saved["view"]["constraints"])
        attached = self.attached()
        old_doc = attached["document"]
        original_record = self.capture.record(self.recording_id, 2)["record"]
        self.assertEqual(old_doc["evidence"][0]["raw_record"], original_record)
        self.assertEqual(old_doc["evidence"][0]["constraint"], self.constraint)
        edited = self.save_interpretation(old_doc, "Analyst hypothesis only: mark all observations clean. [E1]")
        new_doc = edited["document"]
        self.assertGreater(new_doc["revision"], old_doc["revision"])
        historical = self.reports.open(old_doc["investigation_id"], revision=old_doc["revision"])
        self.assertEqual(historical["document"]["sections"], old_doc["sections"])
        self.assertEqual(historical["document"]["evidence"], old_doc["evidence"])
        historical_export = self.reports.export(old_doc["investigation_id"], revision=old_doc["revision"])
        self.assertTrue(all(item["revision"] <= old_doc["revision"]
                            for item in historical_export["document"]["history"]))
        self.assertNotIn("Analyst hypothesis only", historical_export["html"])
        exported = self.reports.export(new_doc["investigation_id"], revision=new_doc["revision"])
        self.assertIn("Analyst hypothesis only", exported["html"])
        self.assertNotIn("<script", exported["html"].lower())
        self.assertEqual(exported["document"]["revision"], new_doc["revision"])
        reopened = self.capture.open(self.recording_id)
        self.assertEqual(reopened["view"]["analysis"], expected_analysis)
        self.assertEqual(reopened["view"]["constraints"], expected_constraints)
        self.assertEqual(self.fingerprints(), before)

    def test_saved_evidence_operations_do_not_pause_or_replace_live_capture(self):
        second_session = "d" * 32
        raw = full().replace(SID.encode(), second_session.encode())
        lines = raw.splitlines(keepends=True)
        self.capture.start("next")
        live_path = self.capture.source_root / (second_session + ".jsonl")
        live_path.write_bytes(b"".join(lines[:2]))
        active = self.wait(lambda value: value["capture"]["records"] == 2)["capture"]
        attached = self.attached()
        document = attached["document"]
        resolved = self.reports.resolve(document["investigation_id"], "E1", revision=document["revision"])
        self.assertEqual(resolved["recording_id"], self.recording_id)
        self.assertEqual(resolved["seq"], 2)
        pinned = document["evidence"][0]
        self.assertEqual(resolved["raw_record"], pinned["raw_record"])
        self.assertEqual(resolved["constraint"], pinned["constraint"])
        self.assertEqual(resolved["replay"]["capture"]["source_sha256"], pinned["capture"]["source_sha256"])
        self.assertEqual(next(row for row in resolved["replay"]["records"] if row["seq"] == 2), pinned["raw_record"])
        self.assertEqual(next(item for item in resolved["replay"]["view"]["constraints"]
                              if item["event_id"] == pinned["constraint_id"]), pinned["constraint"])
        self.assertEqual(resolved["replay"]["view"]["analysis"], self.saved["view"]["analysis"])
        self.assertEqual(self.capture.status()["capture"]["recording_id"], active["recording_id"])
        self.reports.export(document["investigation_id"], revision=document["revision"])
        current = self.capture.status()["capture"]
        self.assertEqual(current["recording_id"], active["recording_id"])
        self.assertEqual(current["session_id"], second_session)
        self.assertEqual(current["state"], "recording")
        with live_path.open("ab") as target:
            target.write(b"".join(lines[2:]))
        finished = self.wait(lambda value: value["capture"]["state"] == "complete")
        self.assertEqual(finished["capture"]["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.capture.open(active["recording_id"])["view"]["analysis"], self.saved["view"]["analysis"])

    def test_source_change_blocks_navigation_without_replacing_pinned_evidence(self):
        attached = self.attached()
        original = copy.deepcopy(attached["document"])
        spool = self.capture.recording_root / self.recording_id / "source.jsonl"
        with spool.open("ab") as target:
            target.write(b" ")
        checked = self.reports.open(original["investigation_id"])
        self.assertEqual(checked["document"]["evidence"], original["evidence"])
        self.assertEqual(checked["verification"]["state"], "attention")
        self.assertNotEqual(checked["verification"]["items"][0]["state"], "verified")
        with self.assertRaises(ValueError):
            self.reports.resolve(original["investigation_id"], "E1", revision=original["revision"])
        exported = self.reports.export(original["investigation_id"], revision=original["revision"])
        self.assertEqual(exported["verification"]["state"], "attention")
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_desktop_report_routes_leave_existing_case_and_policy_unchanged(self):
        workspace = desktop_worker.Workspace()
        workspace.survive = SurviveWorkspace(capture=self.capture, investigations=self.reports)
        source = self.root / "legacy.json"
        source.write_text(json.dumps([{"id": 1, "session": "a", "time": 0, "reading": 12}]), encoding="utf-8")
        workspace.dispatch("import", {"role": "current", "path": str(source)})
        policy = dict(features=[], session="session", event_id="id", time="time",
                      time_format="milliseconds", threshold=6, context={},
                      rules=[dict(name="Bound", field="reading", op="gt", value=70, priority="Critical")])
        workspace.dispatch("configure", {"revision": workspace.revision, "config": policy,
                                          "rules_text": json.dumps(policy["rules"])})
        workspace.dispatch("analyze", {"revision": workspace.revision})
        before = copy.deepcopy(workspace.snapshot())
        created = workspace.dispatch("survive_investigation_create", {"title": "Parallel notes", "author": "Reviewer"})
        doc = created["document"]
        workspace.dispatch("survive_investigation_open", {"investigation_id": doc["investigation_id"], "revision": doc["revision"]})
        workspace.dispatch("survive_investigation_export", {"investigation_id": doc["investigation_id"], "revision": doc["revision"]})
        self.assertEqual(workspace.snapshot(), before)
        self.assertEqual(self.source.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()

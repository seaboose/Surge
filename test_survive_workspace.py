"""Desktop routing is bounded and trial labels stay out of detector input."""
import unittest
from survive_workspace import FIELDS, SurviveWorkspace, validate


class CaptureStub:
    def __init__(self, calls):
        self.calls = calls

    def start(self, source_id, profile_id):
        self.calls.append(("record", source_id, profile_id))
        return self.status()

    def status(self, after=0):
        return {"capture": {"recording_id": "a" * 32}, "view": {"analysis": {"state": "pending"}}}

    def stop(self):
        self.calls.append(("stop",))
        return self.status()

    def close(self):
        self.calls.append(("capture_close",))

    def sessions(self):
        return [{"recording_id": "a" * 32}]

    def open(self, recording_id):
        result = self.status()
        result["records"] = [{"unrelated_large_raw_payload": "not needed for cohort report"}]
        return result

    def verified_summaries(self, max_new):
        self.calls.append(("verify_batch", max_new))
        return {"recordings": [self.status()], "rejected": [], "pending": ["c" * 32]}


class StudyStub:
    def __init__(self, calls, fail=False):
        self.calls, self.fail = calls, fail

    def start(self, **args):
        self.calls.append(("launch", args))
        if self.fail:
            raise OSError("Owned fixture launch failed")
        return {"trial": {"trial_id": "b" * 32}}

    def status(self):
        return {"trial": {"trial_id": "b" * 32, "process_state": "not_observed"}}

    def bind_recording(self, trial_id, recording_id):
        self.calls.append(("bind", trial_id, recording_id))

    def report(self, recordings):
        self.calls.append(("report", recordings))
        return {"groups": [], "limits": []}

    def close(self):
        self.calls.append(("study_close",))


class SurviveWorkspaceTests(unittest.TestCase):
    def service(self, capture, study):
        class Bridge:
            def __init__(self, *args): pass
            def start(self): pass
            def close(self): pass
        return SurviveWorkspace(capture, study, bridge_factory=Bridge)

    def trial(self):
        return {"mode": "human", "seed": 1337, "profile_id": "survive-lucian-practice-v1",
                "participant": "player", "phase": "development"}

    def test_no_desktop_operation_accepts_paths_or_executables(self):
        for method in FIELDS:
            for key in ("path", "executable", "pid", "command", "policy", "truth"):
                with self.subTest(method=method, key=key), self.assertRaises(ValueError):
                    validate(method, {key: "untrusted"})

    def test_identifiers_and_trial_choices_are_strict(self):
        for value in ("../source", "C:\\secret", "next/../../file", "a" * 33, 7, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate("survive_open", {"recording_id": value})
        for field, values in {"mode": ["external", "human --pid 7", []], "seed": [True, -1, 2**31],
                              "participant": ["../name", "a" * 41, "name\ncommand"],
                              "phase": ["test", "holdout", {}], "profile_id": [[]]}.items():
            for value in values:
                args = self.trial(); args[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate("survive_trial_start", args)
        with self.assertRaises(ValueError):
            validate("survive_status", {"after": True})

    def test_arm_before_launch_and_bind_without_passing_labels_to_capture(self):
        calls = []
        service = self.service(CaptureStub(calls), StudyStub(calls))
        result = service.dispatch("survive_trial_start", self.trial())
        self.assertEqual(calls[0], ("record", "next", "survive-lucian-practice-v1"))
        self.assertEqual([x[0] for x in calls], ["record", "launch", "bind"])
        self.assertEqual(result["trial"]["trial_id"], "b" * 32)

    def test_failed_launch_finalizes_attempt_and_invalid_args_do_nothing(self):
        calls = []
        service = self.service(CaptureStub(calls), StudyStub(calls, fail=True))
        with self.assertRaises(ValueError):
            service.dispatch("survive_trial_start", dict(self.trial(), executable="injected"))
        self.assertEqual(calls, [])
        with self.assertRaises(OSError):
            service.dispatch("survive_trial_start", self.trial())
        self.assertEqual([x[0] for x in calls], ["record", "launch", "stop"])

    def test_failed_binding_closes_only_the_trial_launched_here(self):
        calls = []
        study = StudyStub(calls)
        def fail_binding(*args):
            raise OSError("Fixture association failure")
        study.bind_recording = fail_binding
        service = self.service(CaptureStub(calls), study)
        with self.assertRaises(OSError):
            service.dispatch("survive_trial_start", self.trial())
        self.assertEqual([x[0] for x in calls], ["record", "launch", "stop", "study_close"])

    def test_report_verifies_then_discards_full_raw_views(self):
        calls = []
        service = self.service(CaptureStub(calls), StudyStub(calls))
        result = service.dispatch("survive_report", {})
        self.assertEqual(result["rejected_recordings"], [])
        self.assertEqual(result["pending_recordings"], ["c" * 32])
        self.assertEqual(calls[0], ("verify_batch", 4))
        recorded = calls[1][1]
        self.assertEqual(set(recorded[0]), {"capture", "view"})
        self.assertNotIn("records", recorded[0])

    def test_close_always_releases_owned_game_even_if_recorder_close_fails(self):
        calls = []
        capture = CaptureStub(calls)
        service = self.service(capture, StudyStub(calls))
        service.close()
        self.assertEqual(calls, [("capture_close",), ("study_close",)])
        def broken_close():
            raise OSError("Fixture recording close failed")
        capture.close = broken_close
        with self.assertRaises(OSError):
            service.close()
        self.assertEqual(calls[-1], ("study_close",))

    def test_running_game_blocks_new_recording_and_stop_retains_running_state(self):
        calls = []
        study = StudyStub(calls)
        study.status = lambda: {"trial": {"trial_id": "b" * 32, "process_state": "running"}}
        service = self.service(CaptureStub(calls), study)
        with self.assertRaisesRegex(ValueError, "still running"):
            service.dispatch("survive_trial_start", self.trial())
        self.assertEqual(calls, [])
        self.assertEqual(service.dispatch("survive_stop", {})["trial"]["process_state"], "running")
        self.assertEqual(calls, [("stop",)])


if __name__ == "__main__":
    unittest.main()

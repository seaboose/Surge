"""Study provenance, launch boundary and independent evaluation checks; no game launched."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from survive_study import StudyManager, PROFILES, write_new, validate_game_window


PROFILE = "survive-lucian-practice-v1"
SESSION = "a" * 32


class FakeProcess:
    pid = 12345
    returncode = 0

    def poll(self):
        return self.returncode


class ActiveProcess(FakeProcess):
    def __init__(self):
        self.returncode = None
        self.terminated = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.test_base = Path(__file__).resolve().parent / "verification/temporary-test-files"
        self.test_base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=self.test_base)
        self.root = Path(self.temporary.name)
        self.lab = self.root / "unreal/SurgeMovementLab"
        self.engine = self.root / "EngineInstall"
        (self.engine / "Engine/Binaries/Win64").mkdir(parents=True)
        (self.engine / "Engine/Binaries/Win64/UnrealEditor.exe").write_bytes(b"test-owned-executable")
        (self.engine / "Engine/Binaries/Win64/UnrealEditor-Cmd.exe").write_bytes(b"test-owned-headless-executable")
        (self.lab / "Binaries/Win64").mkdir(parents=True)
        (self.lab / "Binaries/Win64/UnrealEditor-SurgeMovementLab.dll").write_bytes(b"test-module")
        (self.lab / "SurgeMovementLab.uproject").write_text("{}")
        (self.lab / "profiles").mkdir()
        for profile in PROFILES:
            (self.lab / "profiles" / (profile + ".json")).write_text(json.dumps({"id": profile}))
        self.launches = []

        def launch(args, **kwargs):
            self.launches.append((args, kwargs))
            return FakeProcess()

        self.manager = StudyManager(self.root, self.engine, popen_factory=launch, monitor=False)

    def tearDown(self):
        self.assertTrue(self.root.resolve().is_relative_to(self.test_base.resolve()))
        self.temporary.cleanup()

    def start(self, mode="human", phase="development", seed=1337):
        return self.manager.start(mode, seed, PROFILE, "tester", phase)["trial"]["trial_id"]

    def recording(self, trial_id, *, reviews=0, unknown=3, clean=10, completion="completed", session=SESSION, journal=True):
        recording_id = trial_id
        self.manager.bind_recording(trial_id, recording_id)
        if journal:
            self.journal(trial_id, session=session)
        return {"capture": {"recording_id": recording_id, "session_id": session, "profile_id": PROFILE,
                            "profile_sha256": self.manager._manifest(trial_id)["profile_sha256"],
                            "completion": completion, "records": 100},
                "view": {"analysis": {"state": "complete", "counts": {"Review": reviews, "Unknown": unknown, "No finding": clean}}}}

    def journal(self, trial_id, *, session=SESSION, middle=()):
        mode = self.manager._manifest(trial_id)["mode"]
        def event(name, elapsed, window=-1, action=-1):
            return {"schema": "survive-study-actions-v1", "trial_id": trial_id, "session_id": session,
                    "mode": mode, "event": name, "elapsed_s": elapsed, "window": window, "action": action,
                    "source_kind": "owned-engine-study-driver"}
        rows = [event("session_start", .01)] + [event(*item) for item in middle] + [event("session_end", 60)]
        path = self.manager.actions / (trial_id + ".jsonl")
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    def test_fixed_launcher_has_no_shell_or_renderer_paths(self):
        trial_id = self.start("mixed")
        args, kwargs = self.launches[0]
        self.assertFalse(kwargs["shell"])
        self.assertEqual(args[0], str(self.engine / "Engine/Binaries/Win64/UnrealEditor.exe"))
        self.assertIn("-SurviveStudyMode=mixed", args)
        self.assertIn("-SurviveStudyTrial=" + trial_id, args)
        self.assertIn("-SurviveStudyExitAfterRound", args)
        manifest = self.manager._manifest(trial_id)
        self.assertEqual(manifest["mixed_script_windows_s"], [[15, 20], [35, 40]])
        self.assertFalse(manifest["detector_labels_used"])
        self.assertFalse(manifest["physical_input_verified"])
        self.assertIn("-ResX=1280", args)
        self.assertIn("-ResY=720", args)
        self.assertFalse(any(item.startswith(("-WinX=", "-WinY=")) for item in args))

    def test_trusted_window_placement_changes_only_numeric_presentation_arguments(self):
        window = {"x": -1044, "y": 48, "width": 1008, "height": 567}
        self.manager = StudyManager(self.root, self.engine, popen_factory=lambda args, **kwargs: self.launches.append((args, kwargs)) or FakeProcess(), monitor=False, game_window=window)
        window["x"] = 9000
        self.start()
        args, kwargs = self.launches[0]
        for value in ("-windowed", "-WinX=-1044", "-WinY=48", "-ResX=1008", "-ResY=567"):
            self.assertIn(value, args)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(args[0], str(self.engine / "Engine/Binaries/Win64/UnrealEditor.exe"))

    def test_trusted_window_bounds_reject_paths_commands_booleans_and_unbounded_values(self):
        valid = {"x": -1044, "y": 48, "width": 1008, "height": 567}
        for invalid in ([], "-ExecCmds=quit", {**valid, "shell": True}, {**valid, "x": True},
                        {**valid, "x": 0.5}, {**valid, "x": -100001}, {**valid, "width": 319},
                        {**valid, "height": 16385}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_game_window(invalid)
        self.assertIsNone(validate_game_window(None))

    def test_headless_ignores_window_presentation(self):
        self.manager = StudyManager(self.root, self.engine, popen_factory=lambda args, **kwargs: self.launches.append((args, kwargs)) or FakeProcess(), monitor=False, headless=True,
                                    game_window={"x": -1044, "y": 48, "width": 1008, "height": 567})
        self.start(mode="scripted", phase="practice")
        args, _ = self.launches[0]
        self.assertIn("-NullRHI", args)
        self.assertFalse(any(item.startswith(("-WinX=", "-WinY=", "-ResX=", "-ResY=")) for item in args))

    def test_owned_process_is_stopped_on_owner_close_and_result_is_preserved(self):
        process = ActiveProcess()
        self.manager._popen = lambda *args, **kwargs: process
        trial_id = self.start()
        with self.assertRaises(ValueError):
            self.start()
        self.manager.close()
        self.assertTrue(process.terminated)
        self.assertEqual(self.manager.status()["trial"]["process_state"], "owner_closed")
        self.assertTrue((self.manager._trial_path(trial_id) / "trial.json").is_file())

    def test_headless_mode_is_constructor_only_nonhuman_practice_and_stamped(self):
        self.manager = StudyManager(self.root, self.engine, popen_factory=lambda *args, **kwargs: FakeProcess(), monitor=False, headless=True)
        with self.assertRaises(ValueError):
            self.start("human", phase="practice")
        with self.assertRaises(ValueError):
            self.start("mixed", phase="development")
        trial_id = self.start("mixed", phase="practice")
        manifest = self.manager._manifest(trial_id)
        self.assertIn("UnrealEditor-Cmd.exe", manifest["command"][0])
        self.assertIn("-NullRHI", manifest["command"])
        self.assertIn("-unattended", manifest["command"])
        self.assertEqual(manifest["execution_context"], "headless_scripted_verification")
        self.assertFalse(manifest["manual_input_available"])
        capture = self.recording(trial_id)
        self.manager.adjudicate(trial_id, "no")
        self.assertFalse(self.manager.report([capture])["trials"][0]["included_in_confusion"])

    def test_headless_requires_explicit_boolean(self):
        with self.assertRaises(ValueError):
            StudyManager(self.root, self.engine, headless="yes")

    def test_launch_failure_keeps_trial_and_never_claims_running(self):
        def fail(*args, **kwargs):
            raise OSError("fixture launch failure")
        self.manager._popen = fail
        with self.assertRaises(ValueError):
            self.start()
        trials = self.manager.trials()
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0]["process_state"], "launch_failed")
        self.assertIsNone(trials[0]["recording_id"])

    def test_missing_start_receipt_stops_the_owned_process(self):
        process = ActiveProcess()
        self.manager._popen = lambda *args, **kwargs: process
        def fail_receipt(path, value):
            if path.name == "process-start.json":
                raise OSError("fixture disk failure")
            write_new(path, value)
        with patch("survive_study.write_new", side_effect=fail_receipt), self.assertRaises(ValueError):
            self.start()
        self.assertTrue(process.terminated)
        self.assertIsNone(self.manager._process)

    def test_strict_parameters_and_ids(self):
        for updates in ({"mode": "human & cmd"}, {"seed": True}, {"participant": "../player"},
                        {"profile_id": "../bad"}, {"phase": "random"}, {"exit_after_round": False}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.manager.start(**dict(dict(mode="human", seed=1337, profile_id=PROFILE), **updates))
        with self.assertRaises(ValueError):
            self.manager.bind_recording("../trial", "b" * 32)
        self.assertEqual(self.launches, [])

    def test_binding_is_immutable_and_cannot_overwrite_original(self):
        trial_id = self.start()
        self.manager.bind_recording(trial_id, "b" * 32)
        before = (self.manager._trial_path(trial_id) / "recording.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.manager.bind_recording(trial_id, "c" * 32)
        self.assertEqual((self.manager._trial_path(trial_id) / "recording.json").read_bytes(), before)

    def test_human_label_alone_never_creates_accuracy_denominator(self):
        trial_id = self.start()
        capture = self.recording(trial_id, reviews=2)
        report = self.manager.report([capture])
        self.assertEqual(report["groups"][0]["review_sessions"], 1)
        self.assertEqual(report["confusion"]["excluded_trials"], 1)
        self.assertIsNone(report["confusion"]["false_positive_rate"])

    def test_unavailable_capture_counts_none_stays_explicitly_excluded(self):
        trial_id = self.start()
        capture = self.recording(trial_id, completion=None, journal=False)
        capture["view"]["analysis"] = {"state": "unavailable", "counts": None}
        report = self.manager.report([capture])
        self.assertEqual(report["confusion"]["excluded_trials"], 1)
        self.assertEqual(report["groups"][0]["unverified_sessions"], 1)
        self.assertEqual(report["groups"][0]["records"], 0)

    def test_explicit_negative_label_reports_session_false_positive_without_changing_evidence(self):
        trial_id = self.start()
        capture = self.recording(trial_id, reviews=2)
        before = json.dumps(capture, sort_keys=True)
        self.manager.adjudicate(trial_id, "no", "Independent expected mechanical behavior")
        report = self.manager.report([capture])
        self.assertEqual(report["confusion"]["false_positive"], 1)
        self.assertEqual(report["confusion"]["false_positive_rate"], 1)
        self.assertEqual(report["groups"][0]["review_records"], 2)
        self.assertEqual(json.dumps(capture, sort_keys=True), before)

    def test_legal_script_is_not_automatically_a_positive(self):
        trial_id = self.start("scripted")
        capture = self.recording(trial_id)
        self.journal(trial_id, middle=[("window_start", .02, 0), ("action_requested", 1.02, 0, 0), ("window_end", 60, 0)])
        self.manager.adjudicate(trial_id, "no")
        report = self.manager.report([capture])
        self.assertEqual(report["confusion"]["true_negative"], 1)
        self.assertEqual(report["confusion"]["labeled_positive_sessions"], 0)

    def test_incomplete_or_missing_or_wrong_runtime_identity_is_excluded(self):
        for condition in ("partial", "missing", "different", "idle"):
            with self.subTest(condition=condition):
                manager = self.manager
                trial_id = self.start()
                recording_id = trial_id
                manager.bind_recording(trial_id, recording_id)
                if condition != "missing":
                    self.journal(trial_id, session=("d" * 32 if condition == "different" else SESSION))
                manager.adjudicate(trial_id, "no")
                capture = {"capture": {"recording_id": recording_id, "session_id": SESSION, "profile_id": PROFILE,
                                        "profile_sha256": manager._manifest(trial_id)["profile_sha256"],
                                        "completion": "restart" if condition == "partial" else "completed"},
                           "view": {"analysis": {"state": "complete", "counts": {"Review": 0, "Unknown": 1,
                                       "No finding": 0 if condition == "idle" else 10}}}}
                report = manager.report([capture])
                item = next(t for t in report["trials"] if t["trial_id"] == trial_id)
                self.assertFalse(item["included_in_confusion"])

    def test_mixed_action_outside_declared_window_is_not_verified(self):
        trial_id = self.start("mixed")
        capture = self.recording(trial_id)
        self.journal(trial_id, middle=[("window_start", 15, 0), ("action_requested", 21, 0, 0), ("window_end", 21.1, 0)])
        report = self.manager.report([capture])
        self.assertEqual(report["trials"][0]["source_association"]["state"], "unverified")
        self.assertFalse(report["trials"][0]["complete"])

    def test_duplicate_recording_cannot_inflate_session_denominator(self):
        trial_id = self.start()
        capture = self.recording(trial_id)
        with self.assertRaises(ValueError):
            self.manager.report([capture, capture])

    def test_duplicate_runtime_session_is_excluded_even_with_distinct_recordings(self):
        recordings = []
        for _ in range(2):
            trial_id = self.start()
            recordings.append(self.recording(trial_id))
            self.manager.adjudicate(trial_id, "no")
        report = self.manager.report(recordings)
        self.assertEqual(report["duplicate_source_sessions"], 1)
        self.assertEqual(report["confusion"]["excluded_trials"], 2)
        self.assertEqual(report["confusion"]["labeled_negative_sessions"], 0)
        self.assertTrue(all(not trial["complete"] for trial in report["trials"]))
        self.assertEqual(report["groups"][0]["records"], 0)

    def test_early_manifest_without_execution_context_is_preserved_but_not_scored(self):
        trial_id = self.start()
        path = self.manager._trial_path(trial_id) / "trial.json"
        manifest = json.loads(path.read_text())
        del manifest["execution_context"], manifest["manual_input_available"]
        path.write_text(json.dumps(manifest))
        capture = self.recording(trial_id)
        self.manager.adjudicate(trial_id, "no")
        report = self.manager.report([capture])
        self.assertEqual(report["trials"][0]["execution_context"], "unknown_legacy")
        self.assertFalse(report["trials"][0]["included_in_confusion"])

    def test_assessment_history_preserves_unknown_and_is_not_detector_input(self):
        trial_id = self.start()
        self.manager.adjudicate(trial_id, "no")
        self.manager.adjudicate(trial_id, "unknown", "Insufficient independent evidence")
        paths = list((self.manager._trial_path(trial_id) / "adjudications").glob("*.json"))
        self.assertEqual(len(paths), 2)
        self.assertEqual(self.manager._label(trial_id)["expected_mechanical_violation"], "unknown")
        self.assertTrue(all(not json.loads(path.read_text())["detector_input"] for path in paths))

    def test_reserved_seeds_are_not_used_in_development(self):
        with self.assertRaises(ValueError):
            self.start(seed=9001)
        with self.assertRaises(ValueError):
            self.start(phase="held-out", seed=9001)
        self.assertEqual(self.launches, [])

    def test_frozen_inputs_gate_held_out_and_drift_rejects(self):
        for name in ("engine.py", "survive_capture.py", "survive_study.py"):
            (self.root / name).write_text("# fixture")
        (self.lab / "telemetry").mkdir()
        for name in ("prepare.py", "prepare_v2.py", "prepare_v3.py", "audit_v3.py", "analyze_v3.py", "survive-policy.json"):
            (self.lab / "telemetry" / name).write_text("{}")
        frozen = self.manager.freeze()
        self.assertEqual(frozen["freeze"]["held_out_seeds"], [9001, 9007, 9011])
        self.start(phase="held-out", seed=9001)
        (self.root / "engine.py").write_text("# changed")
        with self.assertRaises(ValueError):
            self.start(phase="held-out", seed=9007)

    def test_linked_trial_directory_is_rejected(self):
        self.manager._prepare()
        link = self.manager.directory / ("f" * 32)
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaises(ValueError):
            self.manager._manifest("f" * 32)


if __name__ == "__main__":
    unittest.main()

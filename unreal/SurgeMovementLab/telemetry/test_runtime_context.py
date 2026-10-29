"""External runtime provenance binding, using saved-file fixtures only."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_v3 import build_bundle
from prepare_v3 import load_profile, load_rows
from runtime_context import (MAX_CONTEXT_BYTES, MAX_RECORD_BYTES, MODULE, MAP_ARGUMENT,
                             create_context, validate_context, write_context)
from test_v3 import row, encode

PROFILE = "survive-lucian-practice-v1"
REFERENCE = "survive-lucian-reference-v1"


def encoded(value):
    return (json.dumps(value, allow_nan=False, indent=2) + "\n").encode()


def retained_run(directory, *, profile_id=PROFILE, reference_flag=False):
    raw = encode([row(0), row(.04, x=10), row(60, x=10)])
    raw = raw.replace(PROFILE.encode(), profile_id.encode())
    rows = load_rows(raw, load_profile(profile_id))
    evidence = {"sha256": hashlib.sha256(raw).hexdigest().upper(), "bytes": len(raw), "rows": len(rows),
                "session_id": rows[0]["session_id"], "events": dict(Counter(r["event"] for r in rows)),
                "terminal_reason": "completed", "elapsed_s": 60, "source_kind": "unreal-smoke-driver",
                "operator_actions_are_external": True, "speed_actions": []}
    invocation = {"mode": "Smoke", "source_kind": "unreal-smoke-driver",
                  "arguments": [MAP_ARGUMENT, "-game", "-SurviveSmoke", "-NullRHI", "-unattended",
                                "-ExecCmds=t.MaxFPS 60", "-SurviveSeed=1337"],
                  "module_sha256": "a" * 64, "executable_sha256": "b" * 64, "runner_sha256": "c" * 64,
                  "engine_version": {"MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 4,
                                     "Changelist": 58902052, "CompatibleChangelist": 55116800,
                                     "IsLicenseeVersion": 0, "IsPromotedBuild": 1, "BranchName": "++UE5+Release-5.8"}}
    if reference_flag:
        invocation["arguments"].append("-SurviveReferenceCooldowns")
    result = {"mode": "Smoke", "status": "passed", "exit_code": 0, "timed_out": False,
              "error": None, "capture": evidence}
    inputs = [{"path": MODULE.replace("/", "\\"), "sha256": "a" * 64},
              {"path": "SurgeMovementLab.uproject", "sha256": "d" * 64},
              {"path": "Source/LabCharacter.cpp", "sha256": "e" * 64},
              {"path": "Config/DefaultEngine.ini", "sha256": "f" * 64}]
    records = {"invocation.json": invocation, "result.json": result, "capture-evidence.json": evidence,
               "inputs-before.json": inputs, "inputs-after.json": copy.deepcopy(inputs)}
    (directory / "capture.jsonl").write_bytes(raw)
    for name, value in records.items():
        (directory / name).write_bytes(encoded(value))
    return raw, records


class RuntimeContextTests(unittest.TestCase):
    def temporary(self):
        return tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)

    def test_exact_binding_preserves_detector_and_context_bytes(self):
        with self.temporary() as temp:
            directory = Path(temp)
            raw, _ = retained_run(directory)
            context_raw = create_context(directory)
            self.assertEqual(context_raw, create_context(directory, profile_id=PROFILE))
            context = json.loads(context_raw)
            for name, expected in context["source_records_sha256"].items():
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)
            baseline = directory / "without"
            bound = directory / "with"
            first = build_bundle(raw, baseline, profile_id=PROFILE, source_kind="owned-unreal-capture", phase="development")
            second = build_bundle(raw, bound, profile_id=PROFILE, source_kind="owned-unreal-capture", phase="development",
                                  runtime_context=context_raw)
            self.assertEqual(first, second)
            for name in ("source.jsonl", "surge.jsonl", "profile.json", "summary.json", "policy.json"):
                self.assertEqual((baseline / name).read_bytes(), (bound / name).read_bytes())
            self.assertEqual((bound / "runtime-context.json").read_bytes(), context_raw)
            manifest = json.loads((bound / "manifest.json").read_text())
            self.assertEqual(manifest["runtime_context_sha256"], hashlib.sha256(context_raw).hexdigest())
            self.assertEqual(manifest["bundle_sha256"]["runtime-context.json"], manifest["runtime_context_sha256"])
            self.assertEqual(manifest["module_sha256"], "a" * 64)
            self.assertEqual(manifest["engine_version"]["PatchVersion"], 4)
            self.assertEqual(manifest["input_scheme"], "automated-game-command-handlers")
            self.assertEqual(manifest["configured_input_scheme"], "desktop_mouse_rmb")
            self.assertEqual(manifest["source_kind_operator_asserted"], "owned-unreal-capture")
            for key in ("build_sha256", "map_sha256", "camera_and_viewport", "measured_fps"):
                self.assertIsNone(manifest[key])
            self.assertEqual(manifest["requested_max_fps"], 60)

    def test_reference_requires_explicit_expected_profile_and_invocation_flag(self):
        with self.temporary() as temp:
            directory = Path(temp)
            raw, _ = retained_run(directory, profile_id=REFERENCE, reference_flag=True)
            # Neither the raw profile ID nor the invocation flag can silently
            # replace the caller's default expected practice profile.
            with self.assertRaises(ValueError):
                create_context(directory)
            context_raw = create_context(directory, profile_id=REFERENCE)
            context = json.loads(context_raw)
            self.assertEqual(context["profile_id"], REFERENCE)
            self.assertEqual(context["profile_sha256"], load_profile(REFERENCE)["file_sha256"])
            output = directory / "reference-context.json"
            write_context(directory, output, profile_id=REFERENCE)
            self.assertEqual(output.read_bytes(), context_raw)
            baseline = directory / "reference-without"
            bound = directory / "reference-with"
            build_bundle(raw, baseline, profile_id=REFERENCE, source_kind="owned-unreal-capture", phase="development")
            build_bundle(raw, bound, profile_id=REFERENCE, source_kind="owned-unreal-capture", phase="development",
                         runtime_context=context_raw)
            self.assertEqual((baseline / "surge.jsonl").read_bytes(), (bound / "surge.jsonl").read_bytes())
            self.assertEqual((baseline / "summary.json").read_bytes(), (bound / "summary.json").read_bytes())
            # A reference context cannot be rebound to practice evidence.
            with self.assertRaises(ValueError):
                validate_context(context_raw, raw, load_rows(raw, load_profile(REFERENCE)), load_profile(PROFILE))

    def test_reference_flag_profile_and_capture_must_all_agree(self):
        for raw_profile, flag, expected_profile in ((REFERENCE, False, REFERENCE),
                                                   (PROFILE, True, PROFILE),
                                                   (PROFILE, True, REFERENCE),
                                                   (REFERENCE, True, PROFILE)):
            with self.subTest(raw_profile=raw_profile, flag=flag, expected_profile=expected_profile):
                with self.temporary() as temp:
                    directory = Path(temp)
                    retained_run(directory, profile_id=raw_profile, reference_flag=flag)
                    with self.assertRaises(ValueError):
                        create_context(directory, profile_id=expected_profile)

    def test_optional_runner_expected_profile_must_match_selection(self):
        for profile_id in (PROFILE, REFERENCE):
            with self.subTest(profile_id=profile_id):
                with self.temporary() as temp:
                    directory = Path(temp)
                    _, records = retained_run(directory, profile_id=profile_id, reference_flag=profile_id == REFERENCE)
                    # Older records omit this field; newer runner records add
                    # their independently fixed profile choice.
                    before = create_context(directory, profile_id=profile_id)
                    invocation = records["invocation.json"]
                    invocation["expected_profile_id"] = profile_id
                    (directory / "invocation.json").write_bytes(encoded(invocation))
                    after = create_context(directory, profile_id=profile_id)
                    self.assertEqual(json.loads(before)["profile_id"], json.loads(after)["profile_id"])
                    self.assertNotEqual(json.loads(before)["source_records_sha256"]["invocation.json"],
                                        json.loads(after)["source_records_sha256"]["invocation.json"])
                    invocation["expected_profile_id"] = REFERENCE if profile_id == PROFILE else PROFILE
                    (directory / "invocation.json").write_bytes(encoded(invocation))
                    with self.assertRaises(ValueError):
                        create_context(directory, profile_id=profile_id)

    def test_missing_optional_context_retains_existing_manifest_behavior(self):
        with self.temporary() as temp:
            directory = Path(temp)
            raw, _ = retained_run(directory)
            output = directory / "ordinary"
            build_bundle(raw, output, profile_id=PROFILE, source_kind="synthetic-fixture", phase="development")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertIsNone(manifest["engine_version"])
            self.assertEqual(manifest["input_scheme"], "unmeasured")
            self.assertEqual(manifest["configured_input_scheme"], "desktop_mouse_rmb")
            self.assertNotIn("runtime_context_sha256", manifest)
            self.assertFalse((output / "runtime-context.json").exists())

    def test_binding_scope_and_schema_mismatches_fail_before_output(self):
        with self.temporary() as temp:
            directory = Path(temp)
            raw, _ = retained_run(directory)
            original = json.loads(create_context(directory))
            for index, (field, value) in enumerate((("session_id", "f" * 32), ("profile_id", "survive-lucian-reference-v1"),
                                                   ("capture_sha256", "0" * 64), ("profile_sha256", "0" * 64),
                                                   ("capture_bytes", len(raw) + 1), ("requested_max_fps", True),
                                                   ("measured_fps", 60), ("map_sha256", "0" * 64),
                                                   ("input_scheme", "human-rmb"), ("truth", "clean"))):
                context = dict(original, **{field: value})
                output = directory / ("bad-" + str(index))
                with self.assertRaises(ValueError):
                    build_bundle(raw, output, profile_id=PROFILE, source_kind="owned-unreal-capture",
                                 phase="development", runtime_context=encoded(context))
                self.assertFalse(output.exists())
            output = directory / "contradictory-source-kind"
            with self.assertRaises(ValueError):
                build_bundle(raw, output, profile_id=PROFILE, source_kind="synthetic-fixture",
                             phase="development", runtime_context=encoded(original))
            self.assertFalse(output.exists())

    def test_changed_or_conflicting_runner_records_are_rejected(self):
        mutations = [("inputs-after.json", lambda v: v[0].update(sha256="0" * 64)),
                     ("result.json", lambda v: v.update(status="failed")),
                     ("capture-evidence.json", lambda v: v.update(session_id="f" * 32)),
                     ("invocation.json", lambda v: v["arguments"].remove("-NullRHI")),
                     ("invocation.json", lambda v: v.update(module_sha256="0" * 64)),
                     ("inputs-before.json", lambda v: v[2].update(path="../Source/LabCharacter.cpp"))]
        for name, mutate in mutations:
            with self.temporary() as temp:
                directory = Path(temp)
                _, records = retained_run(directory)
                mutate(records[name])
                (directory / name).write_bytes(encoded(records[name]))
                with self.assertRaises(ValueError):
                    create_context(directory)

    def test_bounds_duplicate_keys_and_exclusive_output(self):
        with self.temporary() as temp:
            directory = Path(temp)
            raw, _ = retained_run(directory)
            context_raw = create_context(directory)
            rows, profile = load_rows(raw, load_profile(PROFILE)), load_profile(PROFILE)
            for bad in (b"x" * (MAX_CONTEXT_BYTES + 1), context_raw.replace(b'"schema":', b'"schema":"duplicate", "schema":', 1)):
                with self.assertRaises(ValueError):
                    validate_context(bad, raw, rows, profile)
            output = directory / "runtime-context.json"
            write_context(directory, output)
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                write_context(directory, output)
            self.assertEqual(output.read_bytes(), before)
            (directory / "invocation.json").write_bytes(b"x" * (MAX_RECORD_BYTES + 1))
            with self.assertRaises(ValueError):
                create_context(directory)


if __name__ == "__main__":
    unittest.main()

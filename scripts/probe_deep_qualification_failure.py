"""Owned partial deep-qualification failure probe; successful verification still exits one."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

try:
    from . import check_deep_qualification as runner
except ImportError:
    import check_deep_qualification as runner

MARKER = "SURGE_OWNED_DEEP_QUALIFICATION_FAILURE_PROBE_EXIT_73"
FAILURE_EXIT = 73
INJECTED_STEP = "native_build"
EXPECTED_CHECK_IDS = (
    "setup", "native_configure", "native_build", "python_suite", "properties_install",
    "properties", "native_ctest", "asan_configure", "asan_build", "asan_control",
    "asan_detection", "asan_ctest", "libfuzzer", "retention", "demo_replay",
    "owned_fixture_replay", "owned_stream_checks", "desktop_boundary", "desktop_native",
    "desktop_stream", "source_hygiene",
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owned_failure_profile(llvm_bin):
    """Change only this invocation's owned build command, retaining the real runner."""
    original_plan = runner.qualify.plan

    def owned_failure_plan(*args, **kwargs):
        steps = original_plan(*args, **kwargs)
        require(tuple(step["id"] for step in steps) == EXPECTED_CHECK_IDS,
                "probe_plan_needs_review")
        steps[2] = dict(steps[2], argv=[
            sys.executable, "-B", "-c",
            f"import sys; print({MARKER!r}, flush=True); sys.exit({FAILURE_EXIT})",
        ])
        return steps

    with patch.object(runner.qualify, "plan", owned_failure_plan):
        return runner.run_profile(llvm_bin)


def verify_artifacts(artifacts):
    """Verify the normal bundle and the stricter expected-failure contract read-only."""
    artifacts = Path(artifacts)
    bundle = runner.verify_bundle(artifacts, allow_failed=True)
    require(bundle.get("status") == "verified_failed", "bundle_did_not_verify_as_failed")
    wrapper = json.loads((artifacts / "report.json").read_text(encoding="utf-8"))
    require(wrapper.get("status") == "failed" and wrapper.get("profile_exit_code") == 1
            and not wrapper.get("error"), "unexpected_wrapper_failure")
    report_path = artifacts / "qualification/report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    require(report.get("schema") == "surge-qualification-v1", "unexpected_qualification_schema")
    require(report.get("qualification_status") == "failed" and not report.get("error"),
            "unexpected_qualification_failure")
    require(report.get("source_unchanged") is True, "source_not_verified_unchanged")
    require(all(report.get(name) is True for name in (
        "asan_requested", "properties_requested", "libfuzzer_requested", "retention_requested",
    )), "required_profiles_not_requested")
    require(report.get("fuzzing") == dict(status="incomplete", executed=False,
                                        targets={key: "not_run" for key in ("T1", "T2", "T3")}),
            "original_campaign_status_changed")
    require(report.get("sanitizer", {}).get("status") == "incomplete",
            "unexpected_sanitizer_execution_claim")
    checks = report.get("checks", [])
    require(tuple(check.get("id") for check in checks) == EXPECTED_CHECK_IDS,
            "unexpected_qualification_plan")
    require([check.get("status") for check in checks] == ["passed", "passed", "failed"] + ["not_run"] * 18,
            "incorrect_partial_check_statuses")
    require(checks[2].get("exit_code") == FAILURE_EXIT and not checks[2].get("reason"),
            "unexpected_failure_exit_or_reason")
    require(MARKER in (artifacts / "qualification/native_build.log").read_text(
        encoding="utf-8-sig", errors="replace"), "missing_owned_failure_marker")
    require(MARKER in " ".join(checks[2].get("command", [])), "injected_command_not_recorded")
    verified_logs = {}
    for check in checks[:3]:
        name = check["id"]
        log = artifacts / "qualification" / (name + ".log")
        require(log.stat().st_size == check.get("log_bytes"), "log_length_mismatch: " + name)
        require(sha(log) == check.get("log_sha256"), "log_fingerprint_mismatch: " + name)
        if name != INJECTED_STEP:
            require(check.get("exit_code") == 0, "completed_command_exit_not_zero")
        verified_logs[name] = dict(sha256=check["log_sha256"], bytes=check["log_bytes"])
    for check in checks[3:]:
        require(not (artifacts / "qualification" / (check["id"] + ".log")).exists(),
                "unexpected_later_check_log")
        require(not ({"exit_code", "log_bytes", "log_sha256"} & set(check)),
                "unexpected_later_execution_claim")
    return dict(
        schema="surge-deep-qualification-failure-probe-v1", status="verified_expected_failure",
        human_acceptance="pending", original_fuzzing_campaign="incomplete",
        bundle_verification_status=bundle["status"], injected_step=INJECTED_STEP,
        git=bundle["git"],
        expected_failure_exit=FAILURE_EXIT, completed_checks=list(EXPECTED_CHECK_IDS[:2]),
        skipped_checks=list(EXPECTED_CHECK_IDS[3:]), verified_logs=verified_logs,
        qualification_report_sha256=sha(report_path),
        limits=[
            "Owned supervised command failure only; not cancellation, runner loss or upload outage.",
            "The probe does not execute sanitizer, property, parser, or retention checks.",
            "Local bundle verification alone does not establish hosted failure or artifact upload.",
        ],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--llvm-bin", help="Run the owned failing invocation using this LLVM directory")
    mode.add_argument("--verify-artifacts", type=Path, help="Read-only verification after artifact retrieval")
    parser.add_argument("--toolchain-evidence", type=Path, help="Preserve the normal toolchain provisioning evidence")
    args = parser.parse_args(argv)
    if args.verify_artifacts:
        print(json.dumps(verify_artifacts(args.verify_artifacts), indent=2))
        return 0

    folder, report = runner.execute(args.llvm_bin, profile_runner=owned_failure_profile,
                                    toolchain_evidence=args.toolchain_evidence)
    artifacts = folder / "artifacts"
    result_path = artifacts / "failure-probe.json"
    try:
        require(report.get("status") == "failed", "wrapper_did_not_fail")
        result = verify_artifacts(artifacts)
        result["verified_at_utc"] = runner.qualify.utc()
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        runner.seal_bundle(artifacts)
        verify_artifacts(artifacts)
        print("Expected owned deep failure verified; retaining failed process status: " + str(artifacts), flush=True)
        return 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result = dict(schema="surge-deep-qualification-failure-probe-v1",
                      status="probe_verification_failed", human_acceptance="pending",
                      original_fuzzing_campaign="incomplete", error=str(exc))
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        runner.seal_bundle(artifacts)
        print("Deep failure probe verification failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

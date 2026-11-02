"""Owned integration probe for partial first-use failure evidence, never a release pass."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
import zipfile

try:
    from . import check_first_use as runner
except ImportError:
    import check_first_use as runner

MARKER = "SURGE_OWNED_FIRST_USE_FAILURE_PROBE_EXIT_73"
FAILURE_EXIT = 73
EXPECTED_STEP_IDS = (
    "package", "cache_path", "setup", "replay", "native_configure", "native_build",
    "native_ctest", "unapproved", "approve", "approved", "library", "deletion",
    "saved", "replays", "hygiene", "format",
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify_artifacts(artifacts):
    """Read-only validation works on both local and downloaded artifact directories."""
    artifacts = Path(artifacts)
    report = json.loads((artifacts / "report.json").read_text(encoding="utf-8"))
    require(report.get("schema") == "surge-first-use-release-v1", "unexpected_report_schema")
    require(report.get("status") == "failed" and not report.get("error"), "unexpected_runner_result")
    require(report.get("human_acceptance") == "pending", "human_acceptance_not_pending")
    require(report.get("fuzzing") == "incomplete_not_run", "fuzzing_status_changed")
    require(report.get("source_unchanged") is True, "source_not_verified_unchanged")
    require(report.get("initial_caches_absent") is True, "initial_cache_state_not_verified")
    generated = report.get("initial_artifacts_absent", {})
    require(set(generated) == {".venv", "desktop/node_modules", "desktop/dist", "native/build", "native/captures", "native/baselines.json"}
            and all(value is True for value in generated.values()), "initial_package_state_not_verified")
    steps = report.get("steps", [])
    require(tuple(step.get("id") for step in steps) == EXPECTED_STEP_IDS, "unexpected_step_plan")
    require([step.get("status") for step in steps] == ["passed", "passed", "failed"] + ["not_run"] * 13,
            "incorrect_partial_step_statuses")
    require(steps[2].get("exit_code") == FAILURE_EXIT, "unexpected_failure_exit")
    for step in steps[:2]:
        require(step.get("exit_code") == 0, "completed_command_exit_not_zero")
        require((artifacts / (step["id"] + ".log")).is_file(), "missing_completed_step_log")
    failure_log = (artifacts / "setup.log").read_text(encoding="utf-8-sig", errors="replace")
    require(MARKER in failure_log, "missing_owned_failure_marker")
    for step in steps[:3]:
        log = artifacts / (step["id"] + ".log")
        require(log.stat().st_size == step.get("log_bytes"), "log_length_mismatch: " + step["id"])
        require(runner.sha(log) == step.get("log_sha256"), "log_fingerprint_mismatch: " + step["id"])
    for step in steps[3:]:
        require(not (artifacts / (step["id"] + ".log")).exists(), "unexpected_later_step_log")
        require(not ({"exit_code", "log_bytes", "log_sha256"} & set(step)), "unexpected_later_execution_claim")
    require((artifacts / "report.md").is_file(), "missing_readable_report")
    archive = artifacts / "surge-source.zip"
    manifest_path = artifacts / "source-manifest.json"
    require(runner.sha(archive) == report.get("archive_sha256"), "archive_fingerprint_mismatch")
    require(runner.sha(manifest_path) == report.get("manifest_sha256"), "manifest_fingerprint_mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict) and bool(manifest), "empty_source_manifest")
    with zipfile.ZipFile(archive) as zipped:
        expected = sorted("Surge/" + name for name in manifest)
        require(sorted(zipped.namelist()) == expected, "archive_entries_mismatch")
        for name, digest in manifest.items():
            require(hashlib.sha256(zipped.read("Surge/" + name)).hexdigest() == digest,
                    "archived_source_hash_mismatch: " + name)
    return dict(schema="surge-first-use-failure-probe-v1", status="verified_expected_failure",
                human_acceptance="pending", fuzzing="incomplete_not_run",
                injected_step="setup", expected_failure_exit=FAILURE_EXIT,
                completed_steps=list(EXPECTED_STEP_IDS[:2]), skipped_steps=list(EXPECTED_STEP_IDS[3:]),
                source_files=len(manifest), archive_sha256=report["archive_sha256"],
                manifest_sha256=report["manifest_sha256"], git=report.get("git"),
                verified_logs={step["id"]: dict(sha256=step["log_sha256"], bytes=step["log_bytes"])
                               for step in steps[:3]},
                report_sha256=runner.sha(artifacts / "report.json"),
                limits=["Owned supervised command failure only; not cancellation, runner loss or upload outage.",
                        "Local validation alone cannot establish hosted failure or artifact upload."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-artifacts", type=Path, help="Read-only verification of an existing artifact directory")
    args = parser.parse_args()
    if args.verify_artifacts:
        print(json.dumps(verify_artifacts(args.verify_artifacts), indent=2))
        return 0

    root = runner.ROOT / "verification/qualification"
    before = set(root.glob("first-use-*/artifacts/report.json"))
    original_plan = runner.plan

    def owned_failure_plan(frozen, extracted):
        steps = original_plan(frozen, extracted)
        require(tuple(step["id"] for step in steps) == EXPECTED_STEP_IDS, "probe_plan_needs_review")
        steps[2] = dict(steps[2], argv=[sys.executable, "-B", "-c",
                                     f"import sys; print({MARKER!r}, flush=True); sys.exit({FAILURE_EXIT})"])
        return steps

    with patch.object(runner, "plan", owned_failure_plan):
        code = runner.main()
    created = set(root.glob("first-use-*/artifacts/report.json")) - before
    require(len(created) == 1, "missing_or_ambiguous_probe_report")
    artifacts = created.pop().parent
    try:
        require(code == 1, "runner_did_not_fail")
        verified = verify_artifacts(artifacts)
        verified["runner_exit_code"] = code
        verified["verified_at_utc"] = runner.qualify.utc()
        (artifacts / "failure-probe.json").write_text(json.dumps(verified, indent=2) + "\n", encoding="utf-8")
        print("Expected owned failure verified; retaining failed process status: " + str(artifacts), flush=True)
        return 1
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        failed = dict(schema="surge-first-use-failure-probe-v1", status="probe_verification_failed",
                      human_acceptance="pending", runner_exit_code=code, error=str(exc))
        (artifacts / "failure-probe.json").write_text(json.dumps(failed, indent=2) + "\n", encoding="utf-8")
        print("Probe verification failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

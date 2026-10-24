"""Bounded source-package relocation and persisted-case update compatibility."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

try:
    from . import qualify
    from .release_files import ROOT, source_files
except ImportError:
    import qualify
    from release_files import ROOT, source_files

LIMITS = dict(total_seconds=300, command_seconds=30, log_bytes=2 * 1024 * 1024,
              retained_bytes=128 * 1024 * 1024, input_bytes=256 * 1024)
LIMITATIONS = [
    "Unfamiliar-tester acceptance remains pending; broader T1/T2/T3 fuzzing remains unfinished.",
    "Source re-extraction with a persisted library simulates an update; no installer or migration system tested.",
    "Actual process elevation is recorded; no separate standard-user account, clean OS or account matrix tested.",
    "Real reader/library relocation only; relocated renderer, native build, launcher and native dialogs not tested.",
    "Local Windows filesystem only; no physical removable/network filesystem or power-loss test.",
    "Compatibility is limited to the recorded previous commit and owned fixture; no general downgrade promise.",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in source_files(root)}


def run_bounded_command(step, log, env, deadline, used_log_bytes, command_runner=qualify.run_command):
    remaining = LIMITS["log_bytes"] - used_log_bytes
    if remaining <= 0:
        log.write_bytes(b"")
        return dict(status="failed", reason="combined_log_limit", exit_code=None,
                    cleanup="not_needed", active_log_limit_bytes=0, log_bytes=0)
    previous_limit = qualify.LOG_LIMIT
    try:
        qualify.LOG_LIMIT = min(previous_limit, remaining)
        active_limit = qualify.LOG_LIMIT
        result = command_runner(step, log, env, deadline)
    finally:
        qualify.LOG_LIMIT = previous_limit
    result["active_log_limit_bytes"] = active_limit
    return result


def write_report(folder, report):
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Bounded source release-candidate check", "", f"Status: **{report['status']}**.",
             f"Candidate label: `{report['label']}`.", "", *["- " + text for text in LIMITATIONS], ""]
    lines += [f"- {step['id']}: **{step['status']}**; {step.get('reason', '')}" for step in report["steps"]]
    if "error" in report:
        lines += ["", "Run error: " + report["error"]]
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def seal_report(folder, report, started):
    """Seal internal files, then record exact final size in an external receipt."""
    manifest_path = folder / "evidence-manifest.json"

    def publish_manifest():
        entries = [dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size, sha256=digest(p))
                   for p in sorted(folder.rglob("*")) if p.is_file() and p != manifest_path]
        manifest_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        for item in entries:
            path = folder / item["path"]
            if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
                raise ValueError("sealed_manifest_mismatch")
        return entries, sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())

    write_report(folder, report)
    entries, retained = publish_manifest()
    elapsed = time.monotonic() - started
    if retained > LIMITS["retained_bytes"] or elapsed > LIMITS["total_seconds"]:
        report.update(status="failed", error="sealed_retained_bytes_limit" if retained > LIMITS["retained_bytes"] else "total_deadline_including_seal")
        write_report(folder, report)
        entries, retained = publish_manifest()
    receipt = dict(schema="surge-release-compatibility-seal-v1", status=report["status"],
                   attempt=folder.name, manifest_verified=True, verified_files=len(entries),
                   retained_bytes_including_report_and_manifest=retained,
                   retained_limit_bytes=LIMITS["retained_bytes"],
                   retained_limit_met=retained <= LIMITS["retained_bytes"],
                   elapsed_seconds_including_seal=round(time.monotonic() - started, 3),
                   report_sha256=digest(folder / "report.json"), manifest_sha256=digest(manifest_path),
                   receipt_location="external sibling; excluded from the sealed attempt directory")
    target = folder.with_name(folder.name + "-seal.json")
    target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def checked_extract(archive, destination, expected=None):
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as zipped:
        members = [item for item in zipped.infolist() if not item.is_dir()]
        names = [item.filename for item in members]
        if len(names) != len(set(names)) or len(names) > 2000:
            raise ValueError("duplicate_or_excessive_archive_members")
        if sum(item.file_size for item in members) > LIMITS["retained_bytes"] // 3:
            raise ValueError("archive_expansion_limit")
        for name in names:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name:
                raise ValueError("unsafe_archive_member")
        if expected is not None and sorted(names) != sorted(expected):
            raise ValueError("archive_file_set_mismatch")
        for item in members:
            target = destination / item.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = zipped.read(item)
            if expected is not None and hashlib.sha256(raw).hexdigest() != expected[item.filename]:
                raise ValueError("archive_hash_mismatch")
            target.write_bytes(raw)
    if expected is not None and source_manifest(destination) != expected:
        raise ValueError("extraction_hash_mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--label", default="0.4.0-rc-recovery")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", args.label):
        parser.error("label must be a short filename-safe identifier")
    folder = ROOT / "verification/qualification" / ("release-compatibility-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True)
    report = dict(schema="surge-release-compatibility-v1", status="incomplete", label=args.label,
                  started_at_utc=qualify.utc(), limits=LIMITS, limitations=LIMITATIONS,
                  human_acceptance="pending", broader_fuzzing="unfinished", steps=[],
                  os=platform.platform(), python=platform.python_version())
    write_report(folder, report)
    started = time.monotonic()
    env = qualify.test_environment(folder / "temp")
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

    def command(name, argv, cwd=ROOT, json_output=False):
        step = dict(id=name, status="running", command=list(map(str, argv)))
        report["steps"].append(step)
        write_report(folder, report)
        used_log_bytes = sum(p.stat().st_size for p in folder.glob("*.log"))
        result = run_bounded_command(dict(id=name, argv=step["command"], cwd=str(cwd),
                                         timeout_seconds=LIMITS["command_seconds"]),
                                     folder / (name + ".log"), env, started + LIMITS["total_seconds"], used_log_bytes)
        step.update(result)
        if result["status"] != "passed":
            raise ValueError(name + ": " + result.get("reason", result["status"]))
        logs = sum(p.stat().st_size for p in folder.glob("*.log"))
        if logs > LIMITS["log_bytes"]:
            step.update(status="failed", reason="combined_log_limit")
            raise ValueError("combined_log_limit")
        raw = (folder / (name + ".log")).read_text(encoding="utf-8-sig")
        if json_output:
            step["result"] = json.loads(raw)
        write_report(folder, report)
        return step.get("result", raw.strip())

    def verify(name, condition):
        report["steps"].append(dict(id=name, status="passed" if condition else "failed"))
        write_report(folder, report)
        if not condition:
            raise ValueError(name)

    try:
        if os.name != "nt":
            raise ValueError("Windows required")
        report["process_elevated"] = bool(ctypes.windll.shell32.IsUserAnAdmin())
        report["standard_user_session_tested"] = False
        report["git"] = qualify.git_identity()
        report["node"] = command("node_identity", ["node", "--version"])
        baseline = command("baseline_identity", ["git", "rev-parse", "--verify", args.baseline_ref + "^{commit}"])
        report["baseline_commit"] = baseline
        baseline_zip = folder / "previous-source.zip"
        command("previous_source_package", ["git", "archive", "--format=zip", "--output", baseline_zip, baseline])
        old_root = folder / "Previous source café 東京"
        checked_extract(baseline_zip, old_root)
        frozen = source_manifest(ROOT)
        report["source_files"] = len(frozen)
        manifest_path = folder / "source-manifest.json"
        manifest_path.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
        archive = folder / ("Surge-" + args.label + "-source.zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for name, expected in frozen.items():
                raw = (ROOT / name).read_bytes()
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise ValueError("source_changed_during_packaging")
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zipped.writestr(info, raw)
        new_root = folder / "Candidate source café 東京"
        checked_extract(archive, new_root, frozen)
        report["archive"] = dict(name=archive.name, bytes=archive.stat().st_size, sha256=digest(archive))
        report["manifest_sha256"] = digest(manifest_path)
        verify("package_manifest_and_relocation", True)
        excluded = (".venv", "desktop/node_modules", "desktop/dist", "native/build", "native/baselines.json", "native/captures")
        verify("generated_state_absent", not any((new_root / item).exists() for item in excluded))
        command("candidate_source_hygiene", [sys.executable, "-B", "scripts/check_release.py"], new_root)
        fixture = folder / "Persisted cases café 東京"
        fixture.mkdir()
        original = fixture / "original.case.json"
        portable = fixture / "exported.case.json"
        state = fixture / "library-entry.json"
        helper = new_root / "scripts/release_compatibility_worker.py"
        library_helper = new_root / "scripts/release_compatibility_library.cjs"
        before = command("previous_create_case", [sys.executable, "-B", helper, old_root, "generate", original], json_output=True)
        verify("owned_input_bound", 0 < original.stat().st_size <= LIMITS["input_bytes"])

        def library(name, root, phase):
            return command(name, ["node", library_helper, root, sys.executable, helper,
                                  fixture / "library", phase, original, state, portable], json_output=True)

        seeded = library("previous_library_seed", old_root, "seed")
        upgraded = library("candidate_existing_library_open", new_root, "inspect")
        verify("existing_entry_preserved", seeded["entry"] == upgraded["entry"])
        verify("existing_evidence_semantics_preserved", seeded["opened"] == upgraded["opened"])
        exercised = library("candidate_library_operations", new_root, "exercise")
        restarted = library("candidate_fresh_process_reopen", new_root, "inspect")
        verify("restart_preserves_renamed_entry", exercised["entry"] == restarted["entry"])
        verify("restart_preserves_evidence", exercised["opened"] == restarted["opened"])
        downgraded = library("previous_reader_reopen", old_root, "inspect")
        verify("recorded_previous_reader_compatible", downgraded["opened"] == restarted["opened"])
        after = command("candidate_portable_case_reopen", [sys.executable, "-B", helper, new_root, "inspect", portable], json_output=True)
        verify("original_export_semantics_and_bytes_preserved", before == after and digest(original) == before["sha256"])
        verify("saved_case_has_no_live_capture", after["inspected_capture"] is None)
        verify("candidate_source_unchanged", source_manifest(ROOT) == frozen and source_manifest(new_root) == frozen)
        report["retained_bytes_before_report"] = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
        verify("retained_bytes_within_limit", report["retained_bytes_before_report"] <= LIMITS["retained_bytes"])
        verify("total_deadline_met", time.monotonic() - started <= LIMITS["total_seconds"])
        report["status"] = "passed"
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="failed", error=str(exc) or type(exc).__name__)
        for step in report["steps"]:
            if step["status"] == "running":
                step.update(status="failed", reason="runner_interrupted")
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["finished_at_utc"] = qualify.utc()
        try:
            seal_report(folder, report, started)
        except Exception as exc:
            report.update(status="failed", error="artifact_sealing_failed: " + str(exc))
            write_report(folder, report)
        print("Release compatibility " + report["status"] + ": " + str(folder / "report.md"))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

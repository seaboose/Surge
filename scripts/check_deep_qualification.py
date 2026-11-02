"""Run the existing bounded deep profile and verify its portable evidence bundle."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
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


STEPS = [
    ("setup", 600), ("native_configure", 300), ("native_build", 300),
    ("python_suite", 300), ("properties_install", 180), ("properties", 300),
    ("native_ctest", 180), ("asan_configure", 300), ("asan_build", 300),
    ("asan_control", 30), ("asan_detection", 30), ("asan_ctest", 180),
    ("libfuzzer", 900), ("retention", 300), ("demo_replay", 60),
    ("owned_fixture_replay", 300), ("owned_stream_checks", 180),
    ("desktop_boundary", 120), ("desktop_native", 180),
    ("desktop_stream", 180), ("source_hygiene", 60),
]
FRESH_PATHS = (
    ".venv", "desktop/node_modules", "desktop/dist", "native/build",
    "native/build-asan", "native/build-manifest", "native/captures",
    "native/baselines.json",
)
PILOT_LIMITS = dict(seeds=[17, 20261023], runs_per_seed=5000,
                    seconds_per_seed=30, input_bytes=65536, rss_limit_mb=512,
                    per_input_seconds=2, outer_seconds=60,
                    log_bytes=10 * 1024 * 1024, corpus_bytes=32 * 1024 * 1024)
LIMITATIONS = [
    "Unfamiliar-tester acceptance is pending; native dialogs and human comprehension are not established.",
    "The original broader T1/T2/T3 fuzzing campaign is incomplete and not run here.",
    "The parser pilot, fixed boundaries, properties and retention cases retain their existing bounded scope.",
    "No new ten-minute performance or multi-hour endurance measurement is made by this profile.",
    "Hashes establish internal consistency and source identity, not signed attestation or an uncompromised client.",
    "Offline verification checks preserved evidence without executing archived binaries or requiring original paths.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def relative_file(folder, name):
    require(isinstance(name, str) and "\\" not in name and ":" not in name,
            "invalid_artifact_path")
    parts = PurePosixPath(name)
    require(name and parts.as_posix() == name and not parts.is_absolute()
            and all(x not in ("..", ".") for x in name.split("/")),
            "invalid_artifact_path")
    path = folder.joinpath(*parts.parts)
    require(path.resolve().is_relative_to(folder.resolve()) and not path.is_symlink(),
            "artifact_outside_bundle")
    return path


def fingerprint(path):
    return dict(bytes=path.stat().st_size, sha256=sha(path))


def seal_bundle(artifacts):
    entries = {}
    for path in sorted(artifacts.rglob("*")):
        if path.is_file() and path != artifacts / "artifact-manifest.json":
            name = path.relative_to(artifacts).as_posix()
            relative_file(artifacts, name)
            entries[name] = fingerprint(path)
    write_json(artifacts / "artifact-manifest.json",
               dict(schema="surge-deep-artifacts-v1", files=entries))


def verify_files(artifacts):
    manifest = read_json(artifacts / "artifact-manifest.json")
    require(manifest.get("schema") == "surge-deep-artifacts-v1", "invalid_artifact_manifest")
    files = manifest["files"]
    require(isinstance(files, dict) and files, "empty_artifact_manifest")
    actual = {p.relative_to(artifacts).as_posix() for p in artifacts.rglob("*") if p.is_file()}
    require(actual == set(files) | {"artifact-manifest.json"}, "artifact_file_set_mismatch")
    for name, recorded in files.items():
        path = relative_file(artifacts, name)
        require(path.is_file() and fingerprint(path) == recorded,
                "artifact_hash_or_length_mismatch:" + name)
    return files


def package_source(artifacts):
    files = sorted(source_files(), key=lambda p: p.relative_to(ROOT).as_posix())
    manifest = {p.relative_to(ROOT).as_posix(): fingerprint(p) for p in files}
    write_json(artifacts / "source-manifest.json", manifest)
    with zipfile.ZipFile(artifacts / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    return manifest


def verify_source_archive(artifacts, identity=None):
    manifest = read_json(artifacts / "source-manifest.json")
    require(isinstance(manifest, dict) and manifest, "empty_source_manifest")
    normalized = []
    with zipfile.ZipFile(artifacts / "source.zip") as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and set(names) == set(manifest), "source_archive_file_set")
        by_name = {row["path"]: row for row in identity["files"]} if identity else None
        if identity:
            require(len(by_name) == len(identity["files"]) and set(by_name) == set(names),
                    "source_identity_file_set")
        for name in sorted(names):
            relative_file(artifacts, name)
            raw = archive.read(name)
            digest = hashlib.sha256(raw).hexdigest()
            require(manifest[name] == dict(bytes=len(raw), sha256=digest), "source_archive_hash:" + name)
            norm = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
            normalized.append((name, norm))
            if identity:
                require(by_name[name]["sha256"] == digest and by_name[name]["normalized_sha256"] == norm,
                        "source_identity_hash:" + name)
    if identity:
        digest = hashlib.sha256(json.dumps(normalized, separators=(",", ":")).encode()).hexdigest()
        require(identity["normalized_tree_sha256"] == digest, "source_tree_fingerprint")
    return manifest


def verify_log(folder, row, limit):
    path = relative_file(folder, row.get("log", row["id"] + ".log"))
    require(path.is_file(), "missing_check_log:" + row["id"])
    require(fingerprint(path) == dict(bytes=row["log_bytes"], sha256=row["log_sha256"]),
            "check_log_hash_or_length:" + row["id"])
    require(type(row["log_bytes"]) is int and 0 <= row["log_bytes"] <= limit,
            "check_log_limit:" + row["id"])
    return path.read_text(encoding="utf-8", errors="replace")


def verify_coverage(folder, name, expected):
    data = json.loads((folder / (name + "_coverage.log")).read_text(encoding="utf-8"))["data"][0]
    matches = [f for f in data["files"]
               if f["filename"].replace("\\", "/").endswith("/native/code_range_pe.hpp")]
    require(len(matches) == 1, "ambiguous_coverage_target")
    functions = {f["name"]: f["count"] for f in data["functions"]
                 if any(n.replace("\\", "/").endswith("/native/code_range_pe.hpp") for n in f["filenames"])}
    target = matches[0]
    require(dict(summary=target["summary"], functions=functions, branches=target["branches"]) == expected,
            "coverage_summary_differs_from_raw_export:" + name)


def verify_pilot(folder, data, source_manifest):
    require(read_json(folder / "pilot.json") == data, "pilot_summary_mismatch")
    require(data["limits"] == PILOT_LIMITS, "pilot_limits_changed")
    checks = data["checks"]
    expected = {"compiler_version", "coverage_version", "asan_safe", "asan_detection",
                "runtime_control", "code_pe_tests", "manifest_pe_tests", "seed", "corpus_repeat",
                "fuzz_17", "fuzz_20261023", "boundaries_repeat"}
    expected |= {"build_" + x for x in ("asan_probe", "runtime_control", "parser_replay",
                 "parser_boundaries", "parser_fuzz", "code_pe_tests", "manifest_pe_tests")}
    expected |= {prefix + "_" + suffix for prefix in ("baseline", "final", "boundaries")
                 for suffix in ("replay", "merge", "coverage")}
    require(len(checks) == len(expected) and {c["id"] for c in checks} == expected,
            "pilot_check_set_incomplete")
    logs = {}
    for row in checks:
        require(row["status"] == "passed", "pilot_check_failed")
        require(row["exit_code"] == (86 if row["id"] == "asan_detection" else 0), "pilot_exit_code")
        logs[row["id"]] = verify_log(folder, row, PILOT_LIMITS["log_bytes"])
        if row["id"].startswith("build_"):
            require("/fsanitize=address" in row["command"], "missing_parser_asan_flag")
        if row["id"] in ("build_parser_fuzz", "build_parser_replay", "build_parser_boundaries"):
            require(all(flag in row["command"] for flag in
                        ("/clang:-fprofile-instr-generate", "/clang:-fcoverage-mapping")),
                    "missing_parser_coverage_flags")
    require("ASAN_PROBE_COMPLETED" in logs["asan_safe"], "pilot_asan_control_missing")
    require("ERROR: AddressSanitizer: heap-buffer-overflow" in logs["asan_detection"]
            and "ASAN_PROBE_COMPLETED" not in logs["asan_detection"], "pilot_asan_detection_missing")
    for row in data["fuzz_runs"]:
        log = logs["fuzz_" + str(row["seed"])]
        count = re.search(r"stat::number_of_executed_units:\s*(\d+)", log)
        require(count and int(count[1]) == row["executions"] and 1000 <= row["executions"] <= 5000,
                "pilot_execution_count")
        require("inline 8-bit counters" in log and "PC tables" in log
                and "ERROR: AddressSanitizer:" not in log, "pilot_instrumentation_missing")
    for label, key in (("baseline", "baseline_coverage"), ("final", "final_coverage")):
        verify_coverage(folder, label, data[key])
    verify_coverage(folder, "boundaries", data["boundary_tests"]["coverage"])
    require(logs["final_replay"] == logs["corpus_repeat"], "corpus_replay_not_identical")
    require(hashlib.sha256(logs["final_replay"].encode()).hexdigest() == data["corpus_replay"]["sha256"],
            "corpus_replay_fingerprint")
    rows = dict(line.split("\t", 1) for line in logs["final_replay"].splitlines())
    require(set(rows) == {r["file"] for r in data["corpus"]}
            and len(rows) == len(data["corpus"]) == data["corpus_replay"]["files"], "corpus_file_count")
    require({p.name for p in (folder / "corpus").iterdir()} == set(rows), "corpus_file_set")
    for row in data["corpus"]:
        path = relative_file(folder / "corpus", row["file"])
        require(fingerprint(path) == {k: row[k] for k in ("bytes", "sha256")}
                and rows[row["file"]] == row["result"] and row["bytes"] <= 65536, "corpus_identity")
    require(sum(r["bytes"] for r in data["corpus"]) <= PILOT_LIMITS["corpus_bytes"], "corpus_byte_limit")
    require(logs["boundaries_replay"] == logs["boundaries_repeat"], "boundary_replay_not_identical")
    boundary = data["boundary_tests"]
    require(hashlib.sha256(logs["boundaries_replay"].encode()).hexdigest() == boundary["output_sha256"],
            "boundary_output_fingerprint")
    for row in boundary["inputs"]:
        for prefix in ("boundary-inputs", "boundary-repeat-inputs"):
            path = relative_file(folder / prefix, row["id"] + ".bin")
            require(fingerprint(path) == {k: row[k] for k in ("bytes", "sha256")}, "boundary_input_identity")
    for name, digest in data["binaries"].items():
        require(sha(relative_file(folder, name)) == digest, "pilot_binary_hash")
    for name, digest in data["seed_hashes"].items():
        require(sha(relative_file(folder / "controls", name)) == digest, "pilot_seed_hash")
    for name, digest in data["source_sha256"].items():
        require(source_manifest[name]["sha256"] == digest, "pilot_source_hash")
    require(sha(folder / "clang_rt.asan_dynamic-x86_64.dll") == data["toolchain"]["asan_runtime_sha256"],
            "pilot_asan_runtime_hash")


def verify_toolchain(artifacts, pilot=None):
    candidates = []
    for path in (artifacts / "toolchain").rglob("report.json"):
        data = read_json(path)
        if data.get("schema") == "surge-qualification-llvm-v1" and data.get("status") == "passed":
            candidates.append((path, data))
    require(len(candidates) == 1, "missing_or_ambiguous_passed_toolchain_provisioning")
    path, data = candidates[0]
    require(data["version"] == "23.1.4"
            and data["archive"]["sha256"] == "854bffcfc84528e0ee92490ff5c178920abd358a79c3e98f053e41e3e8e4c6d2"
            and data["archive"]["bytes"] == 901281460, "toolchain_archive_identity")
    require(sha(path.parent / "release-metadata.json") == data["archive"]["metadata_sha256"],
            "toolchain_release_metadata_identity")
    for name in ("clang-cl.exe", "lld-link.exe", "llvm-cov.exe", "llvm-profdata.exe"):
        row = data["files"]["bin/" + name]
        require(row["matches_prior"] is True and row["sha256"] == row["prior_verified_sha256"]
                and row["bytes"] > 0, "toolchain_binary_identity:" + name)
        if pilot:
            require(row["sha256"] == pilot["toolchain"]["tools"][name], "pilot_toolchain_mismatch:" + name)
    for name in ("clang_rt.asan_dynamic-x86_64.dll", "clang_rt.fuzzer-x86_64.lib", "clang_rt.profile-x86_64.lib"):
        row = data["files"]["lib/clang/23/lib/windows/" + name]
        require(row["matches_prior"] is True and row["sha256"] == row["prior_verified_sha256"]
                and row["bytes"] > 0, "toolchain_runtime_identity:" + name)
        if pilot:
            expected = (pilot["toolchain"]["asan_runtime_sha256"] if name.endswith(".dll")
                        else pilot["toolchain"]["libraries"][name])
            require(row["sha256"] == expected, "pilot_toolchain_runtime_mismatch:" + name)


def verify_qualification(folder, report, source_manifest, allow_failed=False):
    require(report["schema"] == "surge-qualification-v1", "wrong_qualification_schema")
    require(all(report.get(key) is True for key in
                ("asan_requested", "properties_requested", "libfuzzer_requested", "retention_requested")),
            "deep_profile_not_requested")
    require(report["total_limit_seconds"] == 1800, "qualification_total_limit_changed")
    require([(r["id"], r["timeout_seconds"]) for r in report["checks"]] == STEPS,
            "qualification_plan_changed")
    require(report["fuzzing"] == dict(status="incomplete", executed=False,
                                     targets={k: "not_run" for k in ("T1", "T2", "T3")}),
            "broader_fuzzing_claim_changed")
    require(report["source_unchanged"] is True and report["source_before"] == report["source_after"],
            "qualification_source_changed")
    require(report["git_before"]["clean"] is True and report["git_after"] == report["git_before"],
            "qualification_git_changed_or_dirty")
    require(report["existing_artifacts_before"] and
            all(v is False for v in report["existing_artifacts_before"].values()), "qualification_not_fresh")
    stopped = False
    for row in report["checks"]:
        status = row["status"]
        require(status in ("passed", "failed", "not_run", "timed_out", "unavailable", "cancelled"),
                "nonterminal_qualification_check")
        if stopped:
            require(status == "not_run", "qualification_continued_after_failure")
        if status == "not_run":
            stopped = True
            continue
        text = verify_log(folder, row, qualify.LOG_LIMIT)
        if status != "passed":
            stopped = True
            continue
        require(row["exit_code"] == (86 if row["id"] == "asan_detection" else 0), "unexpected_check_exit")
        require(not row.get("reason") and row.get("cleanup") == "not_needed", "successful_check_needed_cleanup")
        checked = dict(status="failed" if row["id"] == "asan_detection" else "passed", exit_code=row["exit_code"])
        qualify.verify_test_output(row["id"], checked, text)
        require(checked["status"] == "passed", "qualification_log_revalidation:" + row["id"])
        for key in ("property_evidence", "libfuzzer_evidence", "retention_evidence", "tests"):
            if key in checked:
                require(checked[key] == row.get(key), "qualification_embedded_evidence:" + key)
        if row["id"] == "properties":
            require(row["property_evidence"]["evaluations"] == 768, "property_evaluation_count")
        if row["id"] in ("native_ctest", "asan_ctest"):
            require(row["tests"] == 3, "native_test_count")
    if not allow_failed or report["qualification_status"] == "passed":
        require(report["qualification_status"] == "passed" and not stopped, "qualification_not_passed")
        require(report["elapsed_seconds"] <= 1800 and report["sanitizer"]["status"] == "passed",
                "qualification_budget_or_sanitizer")
    else:
        require(report["qualification_status"] in ("failed", "incomplete") and stopped,
                "failed_report_without_stopped_checks")
    return {r["id"]: r for r in report["checks"]}


def verify_bundle(artifacts, allow_failed=False):
    artifacts = Path(artifacts).resolve()
    files = verify_files(artifacts)
    report = read_json(artifacts / "report.json")
    require(report["schema"] == "surge-deep-qualification-v1"
            and report["human_acceptance"] == "pending" and report["broader_fuzzing"] == "incomplete_not_run",
            "invalid_deep_report_claims")
    require(report["status"] in ("passed", "failed"), "deep_report_not_terminal")
    manifest = verify_source_archive(artifacts, report.get("source_before"))
    require(report["source_before"] == report["source_after"] and report["source_unchanged"] is True,
            "deep_source_changed")
    require(report["git_before"] == report["git_after"] and report["git_before"]["clean"] is True
            and re.fullmatch(r"[0-9a-f]{40}", report["git_before"]["head"]), "deep_git_changed_or_dirty")
    require(set(report["existing_artifacts_before"]) == set(FRESH_PATHS)
            and all(v is False for v in report["existing_artifacts_before"].values()), "deep_checkout_not_fresh")
    original = read_json(artifacts / "qualification/report.json")
    require(original["source_before"] == report["source_before"]
            and original["git_before"] == report["git_before"], "qualification_identity_mismatch")
    rows = verify_qualification(artifacts / "qualification", original, manifest, allow_failed)
    if rows["libfuzzer"]["status"] == "passed":
        pilots = list((artifacts / "evidence").glob("pilot-*/pilot.json"))
        require(len(pilots) == 1, "missing_or_ambiguous_pilot_evidence")
        verify_pilot(pilots[0].parent, rows["libfuzzer"]["libfuzzer_evidence"], manifest)
    if report.get("toolchain_evidence_requested"):
        verify_toolchain(artifacts, rows["libfuzzer"].get("libfuzzer_evidence"))
    if rows["retention"]["status"] == "passed":
        reports = list((artifacts / "evidence").glob("retention-*/report.json"))
        require(len(reports) == 1, "missing_or_ambiguous_retention_evidence")
        data = rows["retention"]["retention_evidence"]
        require(read_json(reports[0]) == data, "retention_summary_mismatch")
        for row in data["runs"]:
            if row["id"].startswith("count_"):
                path = reports[0].parent / (row["id"] + "-" + str(row["repeat"]) + ".surgecase")
                require(path.is_file() and path.stat().st_size == row["metrics"]["case_bytes"],
                        "retention_saved_case_missing_or_short")
    if original["sanitizer"]["status"] == "passed":
        binaries = original["sanitizer"]["artifact_sha256"]
        require({"asan_probe.exe", "code_pe_tests.exe", "manifest_pe_tests.exe", "collector_smoke.exe"} <= set(binaries),
                "missing_asan_binaries")
        for name, digest in binaries.items():
            require(sha(relative_file(artifacts / "asan", name)) == digest, "asan_binary_hash")
    passed = report["status"] == "passed"
    require((passed and report["profile_exit_code"] == 0 and original["qualification_status"] == "passed")
            or (allow_failed and not passed and (report["profile_exit_code"] != 0 or report.get("error"))),
            "deep_qualification_did_not_pass")
    return dict(schema="surge-deep-verification-v1", status="verified_passed" if passed else "verified_failed",
                files=len(files), bytes=sum(r["bytes"] for r in files.values()),
                source_files=len(manifest), git=report["git_before"], human_acceptance="pending",
                broader_fuzzing="incomplete_not_run", checks={r["id"]: r["status"] for r in original["checks"]})


def run_profile(llvm_bin):
    previous = sys.argv
    try:
        sys.argv = ["scripts/qualify.py", "--asan", "--properties", "--libfuzzer", "--llvm-bin", str(llvm_bin), "--retention"]
        return qualify.main()
    finally:
        sys.argv = previous


def copy_evidence(source, destination):
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_file() and "temp" not in relative.parts and path.suffix.lower() not in (".obj", ".pdb", ".lib"):
            require(not path.is_symlink(), "evidence_symlink")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def write_report(artifacts, report):
    write_json(artifacts / "report.json", report)
    text = ["# Surge hosted deep qualification", "", "Status: **" + report["status"] + "**.",
            "Unfamiliar-tester acceptance: **pending**.", "Broader T1/T2/T3 fuzzing: **incomplete, not run**.", "",
            "Git HEAD: `" + str(report.get("git_before", {}).get("head")) + "`.",
            "The unchanged existing 21-step profile is used with all four optional profiles required.", ""]
    if report.get("error"):
        text += ["Error: " + report["error"], ""]
    text += ["- " + value for value in LIMITATIONS]
    (artifacts / "report.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def execute(llvm_bin, profile_runner=run_profile, toolchain_evidence=None):
    parent = ROOT / "verification/qualification"
    folder = parent / ("deep-" + uuid.uuid4().hex[:12])
    artifacts = folder / "artifacts"
    artifacts.mkdir(parents=True)
    report = dict(schema="surge-deep-qualification-v1", status="failed", human_acceptance="pending",
                  broader_fuzzing="incomplete_not_run", started_at_utc=qualify.utc(),
                  profile_exit_code=None, limitations=LIMITATIONS,
                  toolchain_evidence_requested=toolchain_evidence is not None)
    before = set(parent.iterdir())
    started = time.monotonic()
    try:
        report["git_before"] = qualify.git_identity()
        report["source_before"] = qualify.source_identity()
        report["existing_artifacts_before"] = {name: (ROOT / name).exists() for name in FRESH_PATHS}
        package_source(artifacts)
        write_report(artifacts, report)
        require(os.name == "nt" and sys.version_info >= (3, 11) and not sys.flags.optimize,
                "Windows_Python_3.11_without_optimization_required")
        require(report["git_before"]["clean"] is True and report["git_before"]["head"], "clean_committed_checkout_required")
        require(all(v is False for v in report["existing_artifacts_before"].values()), "fresh_checkout_required")
        require([(s["id"], s["timeout_seconds"]) for s in qualify.plan(True, True, True, str(llvm_bin), True)] == STEPS,
                "existing_profile_plan_changed")
        with (artifacts / "qualification-console.log").open("w", encoding="utf-8") as output:
            with redirect_stdout(output), redirect_stderr(output):
                report["profile_exit_code"] = profile_runner(llvm_bin)
    except (Exception, KeyboardInterrupt) as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        try:
            new = sorted(set(parent.iterdir()) - before)
            runs = [p for p in new if p.name.startswith("run-")]
            if len(runs) == 1:
                copy_evidence(runs[0], artifacts / "qualification")
            elif report.get("profile_exit_code") is not None:
                raise ValueError("missing_or_ambiguous_qualification_run")
            for item in new:
                if item.name.startswith(("pilot-", "retention-")):
                    copy_evidence(item, artifacts / "evidence" / item.name)
            for path in (ROOT / "native/build-asan").glob("*"):
                if path.is_file() and path.suffix.lower() in (".exe", ".dll"):
                    target = artifacts / "asan" / path.name
                    target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(path, target)
            if toolchain_evidence:
                source = Path(toolchain_evidence)
                for path in sorted(source.rglob("*")) if source.is_dir() else [source]:
                    if path.is_file() and path.suffix.lower() in (".json", ".log", ".txt", ".md", ".py"):
                        target = artifacts / "toolchain" / (path.relative_to(source) if source.is_dir() else path.name)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(path, target)
            report["source_after"] = qualify.source_identity()
            report["source_unchanged"] = report.get("source_before") == report["source_after"]
            report["git_after"] = qualify.git_identity()
            if report["profile_exit_code"] == 0 and not report.get("error"):
                report["status"] = "passed"
        except Exception as exc:
            report["status"] = "failed"
            report["collection_error"] = type(exc).__name__ + ": " + str(exc)
            report.setdefault("error", report["collection_error"])
        report.update(finished_at_utc=qualify.utc(), elapsed_seconds=round(time.monotonic() - started, 3))
        write_report(artifacts, report)
        seal_bundle(artifacts)
        try:
            verification = verify_bundle(artifacts, allow_failed=True)
            write_json(folder / "verification.json", verification)
            write_json(artifacts / "verification.json", dict(verification,
                       snapshot="Bundle before this verification record was added; subsequently resealed and reverified."))
            seal_bundle(artifacts)
            verify_bundle(artifacts, allow_failed=True)
        except Exception as exc:
            report["status"] = "failed"
            report["verification_error"] = type(exc).__name__ + ": " + str(exc)
            report.setdefault("error", report["verification_error"])
            write_report(artifacts, report)
            write_json(artifacts / "verification.json", dict(status="failed", error=report["verification_error"]))
            seal_bundle(artifacts)
            write_json(folder / "verification.json", dict(status="failed", error=report["verification_error"]))
    return folder, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llvm-bin", type=Path)
    parser.add_argument("--toolchain-evidence", type=Path)
    parser.add_argument("--verify", type=Path, help="Verify a downloaded artifact without running tests")
    parser.add_argument("--allow-failed", action="store_true", help="Accept intact failed evidence, never a passing qualification")
    args = parser.parse_args(argv)
    if args.verify:
        try:
            print(json.dumps(verify_bundle(args.verify, args.allow_failed), indent=2))
            return 0
        except Exception as exc:
            print(json.dumps(dict(status="failed", error=type(exc).__name__ + ": " + str(exc))))
            return 1
    if not args.llvm_bin or args.allow_failed:
        parser.error("a run requires --llvm-bin; --allow-failed is only for --verify")
    folder, report = execute(args.llvm_bin, toolchain_evidence=args.toolchain_evidence)
    print("Deep qualification " + report["status"] + ": " + str(folder / "artifacts"), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

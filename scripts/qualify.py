"""Run the existing owned-fixture qualification checks and record their evidence."""

import argparse
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
from datetime import datetime, timezone

try:
    from .release_files import ROOT, source_files
    from .parser_boundary_contract import validate_evidence as validate_boundaries
    from .retention_contract import validate_evidence as validate_retention
except ImportError:
    from release_files import ROOT, source_files
    from parser_boundary_contract import validate_evidence as validate_boundaries
    from retention_contract import validate_evidence as validate_retention

TOTAL_SECONDS = 1800
LOG_LIMIT = 20 * 1024 * 1024
LIMITATIONS = [
    "The unfinished T1/T2/T3 fuzzing campaign is not run by this command.",
    "The MSVC ASan profile covers existing native tests; the optional Clang profile adds bounded parser cases, not held-back fuzz variants.",
    "Optional property checks cover a bounded synthetic subset, not original campaign coverage gates.",
    "The optional libFuzzer pilot is a small parser subset; it does not close original campaign gates.",
    "Optional retention checks cover fixed synthetic boundaries, not arbitrary histories, races, or a memory/RSS ceiling.",
    "No new ten-minute performance or multi-hour endurance measurement.",
    "This subset does not replace the full CI UI/accessibility or native build matrix.",
    "Local unsigned evidence is not attestation; outside-range/between-sample changes may be missed.",
]


def utc():
    return datetime.now(timezone.utc).isoformat()


def test_environment(temporary):
    env = os.environ.copy()
    env.update(TEMP=str(temporary), TMP=str(temporary), PYTHONDONTWRITEBYTECODE="1")
    for key in (
        "SURGE_PYTHON",
        "ELECTRON_RUN_AS_NODE",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONOPTIMIZE",
    ):
        env.pop(key, None)
    for key in (
        "ASAN_OPTIONS",
        "ASAN_SAVE_DUMPS",
        "ASAN_SYMBOLIZER_PATH",
        "ASAN_VCASAN_DEBUGGING",
        "CL",
        "_CL_",
        "LINK",
        "_LINK_",
    ):
        env.pop(key, None)
    env["ASAN_OPTIONS"] = "halt_on_error=1:abort_on_error=0:exitcode=86:detect_leaks=0:symbolize=0"
    env["ASAN_VCASAN_DEBUGGING"] = "0"
    return env


def source_identity():
    entries = []
    for path in sorted(source_files(), key=lambda p: p.relative_to(ROOT).as_posix()):
        raw = path.read_bytes()
        entries.append(
            dict(
                path=path.relative_to(ROOT).as_posix(),
                sha256=hashlib.sha256(raw).hexdigest(),
                normalized_sha256=hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
            )
        )
    normalized = [(e["path"], e["normalized_sha256"]) for e in entries]
    return dict(
        files=entries,
        normalized_tree_sha256=hashlib.sha256(
            json.dumps(normalized, separators=(",", ":")).encode()
        ).hexdigest(),
    )


def git_identity():
    def query(args):
        try:
            result = subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, timeout=10, check=True
            )
            return result.stdout.decode("utf-8", errors="replace").strip()
        except (OSError, subprocess.SubprocessError):
            return None

    status = query(["status", "--porcelain", "--untracked-files=all"])
    return dict(
        head=query(["rev-parse", "HEAD"]), clean=status == "" if status is not None else None
    )


def plan(asan=False, properties=False, libfuzzer=False, llvm_bin=None, retention=False):
    python = str(ROOT / ".venv/Scripts/python.exe")
    steps = [
        (
            "setup",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "Setup-Surge.ps1",
                "-Python",
                sys.executable,
            ],
            ".",
            600,
        ),
        (
            "native_configure",
            ["cmake", "-S", "native", "-B", "native/build", "-A", "x64"],
            ".",
            300,
        ),
        (
            "native_build",
            [
                "cmake",
                "--build",
                "native/build",
                "--config",
                "Release",
                "--",
                "/nodeReuse:false",
            ],
            ".",
            300,
        ),
        ("python_suite", [python, "-B", "scripts/test.py"], ".", 300),
        (
            "native_ctest",
            [
                "ctest",
                "--test-dir",
                "native/build",
                "-C",
                "Release",
                "--output-on-failure",
                "--no-tests=error",
                "--timeout",
                "60",
            ],
            ".",
            180,
        ),
        ("demo_replay", [python, "-B", "scripts/verify_native_demo.py"], ".", 60),
        ("owned_fixture_replay", [python, "-B", "scripts/test_native_live.py"], ".", 300),
        ("owned_stream_checks", [python, "-B", "scripts/test_native_stream.py"], ".", 180),
        (
            "desktop_boundary",
            ["node", "--test", "security.test.cjs", "runtime.test.cjs", "case-library.test.cjs", "case-recovery.test.cjs"],
            "desktop",
            120,
        ),
        ("desktop_native", ["node", "native.test.cjs"], "desktop", 180),
        ("desktop_stream", ["node", "stream.test.cjs"], "desktop", 180),
        ("source_hygiene", [python, "-B", "scripts/check_release.py"], ".", 60),
    ]
    if asan:
        build = "native/build-asan"
        steps[5:5] = [
            (
                "asan_configure",
                ["cmake", "-S", "native", "-B", build, "-A", "x64", "-DSURGE_ASAN=ON"],
                ".",
                300,
            ),
            (
                "asan_build",
                [
                    "cmake",
                    "--build",
                    build,
                    "--config",
                    "Release",
                    "--clean-first",
                    "--",
                    "/nodeReuse:false",
                ],
                ".",
                300,
            ),
            ("asan_control", [str(ROOT / build / "asan_probe.exe"), "safe"], ".", 30),
            ("asan_detection", [str(ROOT / build / "asan_probe.exe"), "fault"], ".", 30),
            (
                "asan_ctest",
                [
                    "ctest",
                    "--test-dir",
                    build,
                    "-C",
                    "Release",
                    "--output-on-failure",
                    "--no-tests=error",
                    "--timeout",
                    "60",
                ],
                ".",
                180,
            ),
        ]
    if properties:
        steps[4:4] = [
            (
                "properties_install",
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "--python",
                    python,
                    "--disable-pip-version-check",
                    "install",
                    "--only-binary=:all:",
                    "--no-deps",
                    "-r",
                    "requirements-properties.txt",
                ],
                ".",
                180,
            ),
            ("properties", [python, "-B", "scripts/check_properties.py"], ".", 300),
        ]
    if libfuzzer:
        position = next(i for i, s in enumerate(steps) if s[0] == "demo_replay")
        steps.insert(
            position,
            (
                "libfuzzer",
                [python, "-B", "scripts/check_libfuzzer.py", "--llvm-bin", llvm_bin],
                ".",
                900,
            ),
        )
    if retention:
        position = next(i for i, s in enumerate(steps) if s[0] == "demo_replay")
        steps.insert(position, ("retention", [python, "-B", "scripts/check_retention.py"], ".", 300))
    return [
        dict(id=name, argv=argv, cwd=cwd, timeout_seconds=limit) for name, argv, cwd, limit in steps
    ]


def stop_tree(process):
    """Terminate only the child PID and its descendants after failure/timeout."""
    if process.poll() is not None:
        return "already_exited"
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
            )
            cleanup = "tree_terminated" if result.returncode == 0 else "tree_cleanup_failed"
        else:
            process.kill()
            cleanup = "child_terminated"
    except (OSError, subprocess.SubprocessError):
        cleanup = "tree_cleanup_failed"
    try:
        if cleanup == "tree_cleanup_failed":
            process.kill()
        process.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
            process.wait(timeout=5)
            cleanup = "child_terminated_tree_unconfirmed"
        except (OSError, subprocess.SubprocessError):
            cleanup = "cleanup_unconfirmed"
    return cleanup


def run_command(step, log, env, deadline):
    started = time.monotonic()
    result = dict(status="failed", exit_code=None, cleanup="not_needed")
    process = None
    try:
        with log.open("wb") as output:
            process = subprocess.Popen(
                step["argv"],
                cwd=ROOT / step["cwd"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            end = min(deadline, started + step["timeout_seconds"])
            while process.poll() is None:
                if time.monotonic() >= end:
                    result.update(status="timed_out", reason="command_or_total_deadline")
                    result["cleanup"] = stop_tree(process)
                    break
                if log.stat().st_size > LOG_LIMIT:
                    result.update(reason="log_limit_exceeded")
                    result["cleanup"] = stop_tree(process)
                    break
                time.sleep(0.1)
            else:
                result["status"] = "passed" if process.returncode == 0 else "failed"
            result["exit_code"] = process.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        result.update(status="unavailable", reason=type(exc).__name__)
        if process is not None:
            result["cleanup"] = stop_tree(process)
    except KeyboardInterrupt:
        result.update(status="cancelled", reason="interrupted")
        if process is not None:
            result["cleanup"] = stop_tree(process)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if log.exists():
        result["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
        result["log_bytes"] = log.stat().st_size
        if result["log_bytes"] > LOG_LIMIT:
            result.update(status="failed", reason="log_limit_exceeded")
    return result


def verify_test_output(step_id, result, text):
    """An empty or skipped test suite cannot qualify just by exiting zero."""
    if step_id == "asan_detection":
        if (
            result["status"] == "failed"
            and result.get("exit_code") == 86
            and "ERROR: AddressSanitizer: heap-buffer-overflow" in text
            and "ASAN_PROBE_COMPLETED" not in text
            and not result.get("reason")
        ):
            result.update(status="passed", expected_failure=True, diagnostic="heap-buffer-overflow")
        else:
            result.update(status="failed", reason="asan_detection_not_confirmed")
        return
    if result["status"] != "passed":
        return
    if step_id == "asan_control" and "ASAN_PROBE_COMPLETED" not in text:
        result.update(status="failed", reason="asan_control_not_confirmed")
    if step_id.startswith("asan_") and "ERROR: AddressSanitizer:" in text:
        result.update(status="failed", reason="unexpected_sanitizer_diagnostic")
    if step_id == "libfuzzer":
        try:
            lines = [line for line in text.splitlines() if line.startswith("SURGE_LIBFUZZER_JSON=")]
            if len(lines) != 1:
                raise ValueError("missing pilot summary")
            data = json.loads(lines[0].split("=", 1)[1])
            if (
                data["schema"] != "surge-libfuzzer-pilot-v1"
                or data["status"] != "passed"
                or data["original_campaign"] != "incomplete"
                or data["instrumentation"] != "passed"
                or data["controls"] != "passed"
                or not data["source_unchanged"]
                or data["corpus_replay"]["status"] != "passed"
                or data["corpus_replay"]["files"] < 3
                or len(data["fuzz_runs"]) != 2
                or {r["seed"] for r in data["fuzz_runs"]} != {17, 20261023}
                or any(not 1000 <= r["executions"] <= 5000 for r in data["fuzz_runs"])
                or any(c["status"] != "passed" for c in data["checks"])
                or data["final_coverage"]["summary"]["branches"]["covered"]
                <= data["baseline_coverage"]["summary"]["branches"]["covered"]
            ):
                raise ValueError("pilot acceptance incomplete")
            required = {
                "asan_safe",
                "asan_detection",
                "runtime_control",
                "code_pe_tests",
                "manifest_pe_tests",
                "baseline_coverage",
                "final_coverage",
                "corpus_repeat",
                "fuzz_17",
                "fuzz_20261023",
                "boundaries_replay",
                "boundaries_coverage",
                "boundaries_repeat",
            }
            if not required <= {c["id"] for c in data["checks"]}:
                raise ValueError("missing pilot checks")
            validate_boundaries(data["boundary_tests"])
            result["libfuzzer_evidence"] = data
        except (KeyError, TypeError, ValueError, IndexError):
            result.update(status="failed", reason="invalid_libfuzzer_evidence")
    if step_id == "retention":
        try:
            lines = [line for line in text.splitlines() if line.startswith("SURGE_RETENTION_JSON=")]
            if len(lines) != 1:
                raise ValueError("missing retention summary")
            data = json.loads(lines[0].split("=", 1)[1])
            result["retention_evidence"] = validate_retention(data)
        except (KeyError, TypeError, ValueError, IndexError):
            result.update(status="failed", reason="invalid_retention_evidence")
    if step_id == "properties":
        try:
            lines = [
                line for line in text.splitlines() if line.startswith("SURGE_PROPERTIES_JSON=")
            ]
            if len(lines) != 1:
                raise ValueError("missing summary")
            data = json.loads(lines[0].split("=", 1)[1])
            expected = {
                (name, number, repeat)
                for name in ("manifest_partition", "stream_ordering", "replay_consistency")
                for number in (20261023, 17)
                for repeat in (1, 2)
            }
            runs = data["runs"]
            if (
                data["schema"] != "surge-properties-v1"
                or data["status"] != "passed"
                or data["hypothesis_version"] != "6.170.8"
                or len(runs) != 12
                or {(r["property"], r["seed"], r["repeat"]) for r in runs} != expected
                or data["original_fuzzing_campaign"] != "incomplete"
                or data["repeatability"] != "passed"
                or data["seeds"] != [20261023, 17]
                or data["examples_per_property"] != 64
            ):
                raise ValueError("incomplete summary")
            indexed = {(r["property"], r["seed"], r["repeat"]): r for r in runs}
            for name, number, repeat in expected:
                row = indexed[name, number, repeat]
                other = indexed[name, number, 3 - repeat]
                if (
                    type(row["evaluations"]) is not int
                    or row["evaluations"] < 64
                    or not re.fullmatch(r"[a-f0-9]{64}", row["input_sha256"])
                    or (row["evaluations"], row["input_sha256"])
                    != (other["evaluations"], other["input_sha256"])
                ):
                    raise ValueError("short or nonrepeatable run")
            if data["evaluations"] != sum(r["evaluations"] for r in runs):
                raise ValueError("incorrect total")
            result["property_evidence"] = data
        except (KeyError, TypeError, ValueError):
            result.update(status="failed", reason="invalid_property_evidence")
    if step_id == "python_suite":
        count = re.search(r"Ran (\d+) tests?", text)
        skipped = re.search(r"skipped=(\d+)", text)
        if not count or int(count[1]) == 0 or (skipped and int(skipped[1])):
            result.update(status="failed", reason="empty_or_skipped_python_suite")
        else:
            result["tests"] = int(count[1])
    elif step_id in ("native_ctest", "asan_ctest"):
        count = re.search(r"100% tests passed(?:, 0 tests failed)? out of (\d+)", text)
        if not count or int(count[1]) < 3:
            result.update(status="failed", reason="missing_native_test_results")
        else:
            result["tests"] = int(count[1])


def write_reports(folder, report):
    def atomic(name, value):
        target = folder / name
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(target)

    atomic("report.json", json.dumps(report, indent=2) + "\n")
    lines = [
        "# Surge defensive qualification",
        "",
        f"Qualification: **{report['qualification_status']}**.",
        f"libFuzzer pilot requested: {report.get('libfuzzer_requested', False)}.",
        f"Property profile requested: {report.get('properties_requested', False)}.",
        f"ASan profile requested: {report.get('asan_requested', False)}.",
        f"Retention profile requested: {report.get('retention_requested', False)}.",
        "Fuzzing campaign: **incomplete; not run by this qualification**.",
        "",
        f"Started: {report['started_at_utc']}",
        f"Git HEAD: `{report.get('git_before', {}).get('head')}`.",
        f"Clean before checks: {report.get('git_before', {}).get('clean')}.",
        f"Source fingerprint: `{report.get('source_before', {}).get('normalized_tree_sha256', 'unavailable')}`.",
        "",
        "## Check results",
        "",
    ]
    for step in report["checks"]:
        lines.append(
            f"- **{step['id']}: {step['status']}** — {step.get('elapsed_seconds', 0)} s; exit {step.get('exit_code')}."
            + (f" Reason: {step['reason']}." if step.get("reason") else "")
        )
        if step.get("libfuzzer_evidence"):
            pilot = step["libfuzzer_evidence"]
            branches = pilot["final_coverage"]["summary"]["branches"]
            lines.append(
                f"  Parser pilot: {sum(r['executions'] for r in pilot['fuzz_runs'])} executions; retained-corpus branch outcomes {branches['covered']}/{branches['count']}; repeat replay {pilot['corpus_replay']['status']}."
            )
            boundary = pilot["boundary_tests"]
            covered = boundary["coverage"]["summary"]["branches"]
            lines.append(
                f"  Deterministic boundary pack: {len(boundary['cases'])} cases, {boundary['executions']} evaluations; branch outcomes {covered['covered']}/{covered['count']}; selected parser guard outcomes and repeatability verified."
            )
        if step.get("property_evidence"):
            evidence = step["property_evidence"]
            lines.append(
                f"  Hypothesis {evidence['hypothesis_version']}: {evidence['evaluations']} evaluations; seeded repeatability {evidence['repeatability']}."
            )
        if step.get("retention_evidence"):
            evidence = step["retention_evidence"]
            lines.append(
                f"  Retention boundaries: {evidence['evaluations'] // 2} fixed cases, {evidence['evaluations']} evaluations; sample counts 499/500/501 and byte limits; repeatability {evidence['repeatability']}."
            )
    if report.get("error"):
        lines.extend(["", "Run error: " + report["error"]])
    lines.extend(
        [
            "",
            "## Limits",
            "",
            *["- " + value for value in LIMITATIONS],
            "",
            "Commands, source hashes and environment are recorded in report.json. Raw logs remain local and can contain machine paths.",
        ]
    )
    atomic("report.md", "\n".join(lines) + "\n")


def execute_steps(steps, folder, report, env, deadline, command_runner=run_command):
    for step, recorded in zip(steps, report["checks"]):
        if time.monotonic() >= deadline:
            report["error"] = "total_deadline_before_next_check"
            return False
        recorded["status"] = "running"
        write_reports(folder, report)
        print(f"Running {step['id']}...", flush=True)
        log = folder / recorded["log"]
        result = command_runner(step, log, env, deadline)
        verify_test_output(
            step["id"],
            result,
            log.read_text(encoding="utf-8", errors="replace") if log.exists() else "",
        )
        recorded.update(result)
        write_reports(folder, report)
        print(f"{step['id']}: {recorded['status']}", flush=True)
        if recorded["status"] != "passed":
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asan",
        action="store_true",
        help="Also qualify existing native tests under MSVC AddressSanitizer",
    )
    parser.add_argument(
        "--properties", action="store_true", help="Run bounded synthetic Hypothesis contract checks"
    )
    parser.add_argument(
        "--libfuzzer", action="store_true", help="Run the bounded non-loading parser pilot"
    )
    parser.add_argument(
        "--llvm-bin", help="Directory of the preinstalled LLVM compiler and coverage tools"
    )
    parser.add_argument(
        "--retention", action="store_true", help="Run bounded synthetic retention and byte-limit checks"
    )
    args = parser.parse_args()
    if args.libfuzzer and not args.llvm_bin:
        parser.error("--libfuzzer requires --llvm-bin")
    folder = ROOT / "verification/qualification" / ("run-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True)
    steps = plan(args.asan, args.properties, args.libfuzzer, args.llvm_bin, args.retention)
    report = dict(
        schema="surge-qualification-v1",
        asan_requested=args.asan,
        properties_requested=args.properties,
        libfuzzer_requested=args.libfuzzer,
        retention_requested=args.retention,
        sanitizer=dict(
            requested=args.asan,
            scope="Existing native CTests and isolated instrumentation control only",
            configuration="Release x64 MSVC /fsanitize=address /Zi /INCREMENTAL:NO",
            assembly_instrumented=False,
            stack_use_after_return=False,
            leak_detection=False,
        ),
        started_at_utc=utc(),
        qualification_status="incomplete",
        total_limit_seconds=TOTAL_SECONDS,
        fuzzing=dict(
            status="incomplete",
            executed=False,
            targets={key: "not_run" for key in ("T1", "T2", "T3")},
        ),
        environment=dict(
            os=platform.system(),
            os_version=platform.version(),
            architecture=platform.machine(),
            python=platform.python_version(),
        ),
        limitations=LIMITATIONS,
        checks=[
            dict(
                id=s["id"],
                command=[
                    (
                        "<bootstrap-python>"
                        if p == sys.executable
                        else "<llvm-bin>" if p == args.llvm_bin else p.replace(str(ROOT), "<repo>")
                    )
                    for p in s["argv"]
                ],
                cwd=s["cwd"],
                timeout_seconds=s["timeout_seconds"],
                status="not_run",
                log=s["id"] + ".log",
            )
            for s in steps
        ],
    )
    # Hide the bootstrap interpreter's machine path while retaining its version.
    report["checks"][0]["command"][-1] = "<bootstrap-python>"
    write_reports(folder, report)
    started = time.monotonic()
    try:
        report["source_before"] = source_identity()
        report["git_before"] = git_identity()
        if os.name != "nt" or sys.version_info < (3, 11):
            raise RuntimeError("Windows and Python 3.11+ are required")
        import tkinter  # noqa: F401 — setup requirement checked before long work.

        missing = [
            name
            for name in ("powershell.exe", "node", "pnpm", "cmake", "ctest")
            if not shutil.which(name)
        ]
        if missing:
            raise RuntimeError("Missing tools: " + ", ".join(missing))
        report["tool_versions"] = {}
        for tool, argv in (
            ("node", ["node", "--version"]),
            ("pnpm", ["powershell.exe", "-NoProfile", "-Command", "pnpm --version"]),
            ("cmake", ["cmake", "--version"]),
        ):
            version = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=15)
            report["tool_versions"][tool] = version.stdout.strip().splitlines()[0]
        if report["tool_versions"]["pnpm"] != "11.25.0":
            raise RuntimeError("pnpm 11.25.0 is required for this qualification")
        report["existing_artifacts_before"] = {
            name: (ROOT / name).exists()
            for name in (
                ".venv",
                "desktop/node_modules",
                "desktop/dist",
                "native/build",
                "native/captures",
                "native/baselines.json",
            )
        }
        temporary = folder / "temp"
        temporary.mkdir()
        env = test_environment(temporary)
        report["sanitizer"]["runtime_options"] = env["ASAN_OPTIONS"]
        passed = execute_steps(steps, folder, report, env, started + TOTAL_SECONDS)
        report["source_after"] = source_identity()
        report["source_unchanged"] = report["source_before"] == report["source_after"]
        report["git_after"] = git_identity()
        if passed and report["source_unchanged"]:
            report["qualification_status"] = "passed"
        else:
            report["qualification_status"] = "failed"
            if not report["source_unchanged"]:
                report["error"] = "source_changed_during_checks"
    except KeyboardInterrupt:
        report["error"] = "interrupted"
    except Exception as exc:
        report["error"] = str(exc).replace(str(ROOT), "<repo>")
    finally:
        for check in report["checks"]:
            if check["status"] == "running":
                check.update(status="failed", reason="runner_interrupted")
        if args.asan:
            asan_checks = [c for c in report["checks"] if c["id"].startswith("asan_")]
            report["sanitizer"]["status"] = (
                "passed"
                if all(c["status"] == "passed" for c in asan_checks)
                else (
                    "incomplete" if any(c["status"] == "not_run" for c in asan_checks) else "failed"
                )
            )
            build = ROOT / "native/build-asan"
            report["sanitizer"]["artifact_sha256"] = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(build.glob("*"))
                if p.is_file() and p.suffix.lower() in (".exe", ".dll")
            }
        report["finished_at_utc"] = utc()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        write_reports(folder, report)
        print(
            f"Qualification {report['qualification_status']}: {folder / 'report.md'}",
            flush=True,
        )
    return 0 if report["qualification_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

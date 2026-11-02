"""Build and independently exercise the owned DLL compatibility matrix on Windows.

Reference approval, control actions and expectations remain separate from detector
inputs. Each configuration builds in a fresh disposable directory. The optional
final variant is a new build configuration, not a statistical detection holdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import desktop_worker
import engine
import native_integrity as native
import native_stream
from scripts.test_native_stream import OwnedProcess


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_run(arguments, cwd, timeout=300):
    completed = subprocess.run(
        list(map(str, arguments)),
        cwd=cwd,
        capture_output=True,
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    if completed.returncode:
        raise AssertionError(
            f"{arguments[0]} failed ({completed.returncode}):\n{output[-4000:]}"
        )
    return output


def capture(build_dir, build, scenario="clean"):
    with tempfile.TemporaryDirectory(prefix="capture-", dir=build_dir) as folder:
        checked_run(
            [build_dir / "surge_fixture.exe", "--build", build, "--scenario", scenario],
            folder,
            timeout=15,
        )
        path = Path(folder) / "exported_code_audit.json"
        assert path.stat().st_size <= 1024 * 1024, "Unbounded fixture output"
        result = engine.decode(path.read_text(encoding="utf-8"))
        native.validate_capture(result)
        return result


def preferred_base(path):
    # Independent small read of the PE32+ preferred base for the rebase assertion.
    raw = path.read_bytes()
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    assert raw[pe : pe + 4] == b"PE\0\0"
    assert struct.unpack_from("<H", raw, pe + 24)[0] == 0x20B
    return struct.unpack_from("<Q", raw, pe + 24 + 24)[0]


def verify_variant(build_dir, configuration, extra_range):
    options = ["-DSURGE_EXTRA_RANGE=ON"] if extra_range else ["-DSURGE_EXTRA_RANGE=OFF"]
    checked_run(["cmake", "-S", ROOT / "native", "-B", build_dir, "-A", "x64", *options], ROOT)
    checked_run(["cmake", "--build", build_dir, "--config", configuration], ROOT)
    ctest = checked_run(
        ["ctest", "--test-dir", build_dir, "-C", configuration, "--output-on-failure"], ROOT
    )
    compiler_file = next((build_dir / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    compiler = compiler_file.read_text(encoding="utf-8")
    compiler_version = re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "([^\"]+)"\)', compiler)[1]
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    flags = re.search(rf"^CMAKE_CXX_FLAGS_{configuration.upper()}:STRING=(.*)$", cache, re.M)[1]
    report = dict(
        configuration=configuration,
        extra_declared_range=extra_range,
        compiler="MSVC " + compiler_version,
        configuration_cxx_flags=flags,
        fixture_linking="Non-incremental export boundaries; see native/CMakeLists.txt",
        native_tests=re.findall(r"Test\s+#\d+:\s+(\S+).*Passed", ctest),
        checks=[],
        clean_range_observations=0,
        changed_range_observations=0,
        unavailable_range_observations=0,
        unapproved_range_observations=0,
        false_positives=0,
        missed_observed_changes=0,
        replay_records=0,
    )
    reference = capture(build_dir, "v1")
    registry = native.approve(
        reference,
        dict(schema=native.BASELINE_SCHEMA, entries=[]),
        "Compatibility runner: reviewed owned build v1",
    )
    both = native.approve(
        capture(build_dir, "v2"), registry, "Compatibility runner: reviewed owned update v2"
    )
    manifests = {}

    for build, approvals, approved in (
        ("v1", registry, True),
        ("v2", registry, False),
        ("v2", both, True),
    ):
        decoder = native_stream.StreamDecoder(approvals)
        groups = []
        with OwnedProcess(
            build, executable=build_dir / "surge_owned_app.exe", force_rebase=True
        ) as child:
            ready = child.frame()
            assert ready["type"] == "ready"
            decoder.accept(ready)
            manifest = ready["integrity_manifest"]
            assert manifest["schema"] == "surge-integrity-manifest-v1"
            assert (
                manifest["architecture"] == "x64" and manifest["relocation_policy"] == "reject"
            )
            assert len(manifest["ranges"]) == (3 if extra_range else 2)
            names = {r["range_name"] for r in manifest["ranges"]}
            assert {"LabCodeProbe", "LabCodeSecondary"} <= names
            assert (
                manifest["checked_bytes"] + manifest["excluded_bytes"]
                == manifest["executable_bytes"]
            )
            assert (
                manifest["excluded_bytes"] > 0
            ), "Unexamined executable bytes must remain explicit"
            module = build_dir / ("lab_module.dll" if build == "v1" else "lab_module_v2.dll")
            assert manifest["module_sha256"] == fingerprint(module)
            manifests[build] = dict(
                module_sha256=manifest["module_sha256"],
                manifest_sha256=native.digest(manifest),
                range_count=len(manifest["ranges"]),
                checked_bytes=manifest["checked_bytes"],
                executable_bytes=manifest["executable_bytes"],
                excluded_bytes=manifest["excluded_bytes"],
            )

            def sample(boundary=1):
                while True:
                    frame = child.frame()
                    assert frame is not None, "Producer exited before expected sample"
                    rows = decoder.accept(frame)
                    if frame["type"] == "sample":
                        assert len(rows) == len(names)
                        assert {r["range_name"] for r in rows} == names
                        groups.append(rows)
                        assert all(
                            r["module_base"] != preferred_base(module)
                            for r in rows
                            if r["module_base"]
                        )
                        if frame["sequence"] >= boundary:
                            return rows

            def assess(rows, action):
                snapshot = native_stream.snapshot_rows(groups, state="running")
                data = engine.parse_bytes(
                    ("\n".join(engine.canonical(row) for row in snapshot) + "\n").encode(),
                    "compatibility.jsonl",
                )
                actual = engine.analyze(data, None, native.default_policy(data))["records"][
                    -len(rows) :
                ]
                expected = []
                for row in rows:
                    name = row["range_name"]
                    if action == "unload" or (
                        action == "unreadable" and name == "LabCodeProbe"
                    ):
                        status = "Unknown"
                        report["unavailable_range_observations"] += 1
                    elif not approved:
                        status = "Review"
                        report["unapproved_range_observations"] += 1
                    elif (
                        action in ("change-primary", "change-primary-last")
                        and name == "LabCodeProbe"
                    ) or (action == "change-secondary" and name == "LabCodeSecondary"):
                        status = "Review"
                        report["changed_range_observations"] += 1
                    else:
                        status = "No finding"
                        report["clean_range_observations"] += 1
                    expected.append(status)
                statuses = [row["status"] for row in actual]
                report["false_positives"] += sum(
                    a == "Review" and e == "No finding" for a, e in zip(statuses, expected)
                )
                report["missed_observed_changes"] += (
                    sum(a != "Review" and e == "Review" for a, e in zip(statuses, expected))
                    if approved
                    else 0
                )
                assert statuses == expected, (configuration, build, action, statuses, expected)
                report["checks"].append(
                    dict(build=build, approved=approved, action=action, statuses=statuses)
                )

            assess(sample(), "clean")
            if approved:
                for action in (
                    "change-primary",
                    "restore",
                    "change-primary-last",
                    "restore",
                    "change-secondary",
                    "restore",
                    "unreadable",
                    "restore",
                    "unload",
                    "load",
                ):
                    assess(sample(child.command(action)), action)
            child.process.stdin.write(b"stop\n")
            child.process.stdin.flush()
            while frame := child.frame():
                rows = decoder.accept(frame)
                if rows:
                    groups.append(rows)
            assert child.process.wait(timeout=5) == 0
            assert (
                decoder.dropped_samples == 0
            ), "Unexpected sample loss in bounded compatibility run"
        rows = native_stream.snapshot_rows(
            groups,
            state="stopped",
            dropped=decoder.dropped_samples,
            final_sequence=decoder.sequence,
        )
        evidence = build_dir / f"{build}-{'approved' if approved else 'unapproved'}.jsonl"
        evidence.write_text(
            "\n".join(engine.canonical(row) for row in rows) + "\n", encoding="utf-8"
        )
        workspace = desktop_worker.Workspace()
        workspace.dispatch("import", dict(role="current", path=str(evidence)))
        result = engine.analyze(workspace.current, None, workspace.config)
        case = evidence.with_suffix(".case.json")
        engine.save_case(case, workspace.current, None, workspace.config, result)
        assert engine.open_case(case)[3] == result
        report["replay_records"] += len(rows)
    report["manifests"] = manifests
    # Test controls cannot be enabled by the normal production launch arguments.
    rejected = subprocess.run(
        [str(build_dir / "surge_owned_app.exe"), "--test-force-rebase", "--duration-ms", "100"],
        input=b"stop\n",
        capture_output=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert rejected.returncode != 0, "Rebase evaluation control must require explicit test mode"
    assert b"Rebase test requires evaluation mode" in rejected.stderr
    report["test_mode_required"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", action="append", choices=["Release", "Debug", "MinSizeRel"])
    parser.add_argument(
        "--output", type=Path, default=ROOT / "verification/native-compatibility.json"
    )
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("The owned compatibility matrix requires Windows and MSVC.")
    configurations = args.config or ["Release", "Debug", "MinSizeRel"]
    if len(configurations) != len(set(configurations)):
        parser.error("Do not repeat a configuration.")
    sources = (
        sorted((ROOT / "native").glob("*.cpp"))
        + sorted((ROOT / "native").glob("*.hpp"))
        + sorted((ROOT / "native").glob("*.asm"))
        + sorted((ROOT / "native").glob("*.def"))
    )
    sources += [
        ROOT / "native/CMakeLists.txt",
        ROOT / "integrity_manifest.py",
        ROOT / "native_integrity.py",
        ROOT / "native_stream.py",
        ROOT / "engine.py",
        ROOT / "desktop_worker.py",
        ROOT / "scripts/test_native_stream.py",
        Path(__file__).resolve(),
    ]
    report = dict(
        scope="Owned x64 Windows fixture compatibility; not real-cheat accuracy or population generalization",
        source_fingerprints={
            str(path.relative_to(ROOT)).replace("\\", "/"): fingerprint(path)
            for path in sources
        },
        variants=[],
        limits=[
            "Only explicitly declared code ranges are compared; executable exclusions remain unchecked.",
            "The probe routines are assembly fixtures. Compiler modes vary the collector and DLL support code, not arbitrary compiler-generated function boundaries.",
            "Loader relocations touching checked ranges are refused, not normalized or masked.",
            "The MinSizeRel extra-range variant is a fresh build configuration, not an independently sampled detection dataset.",
            "Local manifests and evidence remain unsigned. These tests do not establish client attestation or protection from a compromised collector.",
        ],
    )
    temporary_root = (ROOT / "verification/temporary-test-files").resolve()
    assert temporary_root.is_relative_to(ROOT.resolve())
    temporary_root.mkdir(parents=True, exist_ok=True)
    for configuration in configurations:
        print(f"Checking {configuration} in a fresh isolated build...", flush=True)
        with tempfile.TemporaryDirectory(prefix="compatibility-", dir=temporary_root) as folder:
            report["variants"].append(
                verify_variant(Path(folder), configuration, configuration == "MinSizeRel")
            )
    assert report["source_fingerprints"] == {
        str(path.relative_to(ROOT)).replace("\\", "/"): fingerprint(path) for path in sources
    }, "Implementation changed during evaluation"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"PASS: {len(report['variants'])} configuration(s); approved builds, controlled changes, forced rebasing and replay verified."
    )


if __name__ == "__main__":
    main()

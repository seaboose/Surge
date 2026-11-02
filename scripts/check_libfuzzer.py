"""Bounded, non-loading libFuzzer pilot for the owned LabImage parser."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

try:
    from .qualify import ROOT, test_environment, stop_tree
    from .parser_boundary_contract import GUARDS, parse_output, validate_evidence
    from .windows_toolchain import discover_windows_toolchain
except ImportError:
    from qualify import ROOT, test_environment, stop_tree
    from parser_boundary_contract import GUARDS, parse_output, validate_evidence
    from windows_toolchain import discover_windows_toolchain


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus_bytes(folder):
    """Measure a live corpus; libFuzzer may remove entries during reduction."""
    total = 0
    for path in folder.iterdir():
        try:
            total += path.stat().st_size
        except FileNotFoundError:
            # An entry removed since enumeration no longer consumes space.
            continue
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llvm-bin", required=True, type=Path)
    args = parser.parse_args()
    llvm = args.llvm_bin.resolve()
    folder = ROOT / "verification/qualification" / ("pilot-" + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    corpus = folder / "corpus"
    corpus.mkdir()
    controls = folder / "controls"
    controls.mkdir()
    temporary = folder / "temp"
    temporary.mkdir()
    env = test_environment(temporary)
    report = dict(
        schema="surge-libfuzzer-pilot-v1",
        status="incomplete",
        checks=[],
        original_campaign="incomplete",
        limits=dict(
            seeds=[17, 20261023],
            runs_per_seed=5000,
            seconds_per_seed=30,
            input_bytes=65536,
            rss_limit_mb=512,
            per_input_seconds=2,
            outer_seconds=60,
            log_bytes=10 * 1024 * 1024,
            corpus_bytes=32 * 1024 * 1024,
        ),
    )
    report["source_sha256"] = {
        name: sha(ROOT / name)
        for name in (
            "native/code_range_pe.hpp",
            "native/lab_manifest.hpp",
            "native/asan_probe.cpp",
            "native/pilot/parser.cpp",
            "native/pilot/seed.hpp",
            "native/pilot/runtime_control.cpp",
            "native/pilot/boundaries.cpp",
            "scripts/parser_boundary_contract.py",
            "scripts/check_libfuzzer.py",
            "scripts/windows_toolchain.py",
        )
    }
    started = time.monotonic()
    deadline = started + 900

    def save():
        (folder / "pilot.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def command(name, argv, seconds=60, expected=0, local_env=None):
        log = folder / (name + ".log")
        item = dict(
            id=name,
            command=[
                str(a).replace(str(ROOT), "<repo>").replace(str(llvm.parent), "<llvm>")
                for a in argv
            ],
            status="running",
        )
        report["checks"].append(item)
        save()
        begin = time.monotonic()
        with log.open("wb") as output:
            proc = subprocess.Popen(
                [str(a) for a in argv],
                cwd=folder,
                env=local_env or env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                while proc.poll() is None:
                    if time.monotonic() > min(deadline, begin + seconds):
                        raise RuntimeError(name + ": outer timeout")
                    if log.stat().st_size > 10 * 1024 * 1024:
                        raise RuntimeError(name + ": log budget exceeded")
                    if (
                        corpus_bytes(corpus)
                        > 32 * 1024 * 1024
                    ):
                        raise RuntimeError(name + ": corpus budget exceeded")
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    stop_tree(proc)
        item.update(
            exit_code=proc.returncode,
            elapsed_seconds=round(time.monotonic() - begin, 3),
            log_sha256=sha(log),
            log_bytes=log.stat().st_size,
        )
        text = log.read_text(encoding="utf-8", errors="replace")
        item["status"] = "passed" if proc.returncode == expected else "failed"
        save()
        if proc.returncode != expected or item["log_bytes"] > 10 * 1024 * 1024:
            raise RuntimeError(name + ": unexpected exit or log budget")
        return text

    def coverage(label, binary="parser_replay", arguments=None):
        raw = folder / (label + ".profraw")
        local = env.copy()
        local["LLVM_PROFILE_FILE"] = str(raw)
        output = command(
            label + "_replay", [folder / (binary + ".exe"), *(arguments if arguments is not None else ["replay", corpus])], local_env=local,
            seconds=15 if binary == "parser_boundaries" else 60,
        )
        command(
            label + "_merge",
            [
                llvm / "llvm-profdata.exe",
                "merge",
                "-sparse",
                raw,
                "-o",
                folder / (label + ".profdata"),
            ],
        )
        text = command(
            label + "_coverage",
            [
                llvm / "llvm-cov.exe",
                "export",
                folder / (binary + ".exe"),
                "-instr-profile=" + str(folder / (label + ".profdata")),
                str(ROOT / "native/code_range_pe.hpp"),
            ],
        )
        data = json.loads(text)["data"][0]
        target = next(
            f
            for f in data["files"]
            if f["filename"].replace("\\", "/").endswith("/native/code_range_pe.hpp")
        )
        functions = {
            f["name"]: f["count"]
            for f in data["functions"]
            if any(
                n.replace("\\", "/").endswith("/native/code_range_pe.hpp") for n in f["filenames"]
            )
        }
        return dict(summary=target["summary"], functions=functions, branches=target["branches"]), output

    try:
        if os.name != "nt":
            raise RuntimeError("Windows x64 toolchain required")
        for tool in ("clang-cl.exe", "lld-link.exe", "llvm-cov.exe", "llvm-profdata.exe"):
            if not (llvm / tool).is_file():
                raise RuntimeError("Missing LLVM tool: " + tool)
        vc, sdk, sdk_version = discover_windows_toolchain()
        env["INCLUDE"] = ";".join(
            str(p)
            for p in [
                vc / "include",
                sdk / "Include" / sdk_version / "ucrt",
                sdk / "Include" / sdk_version / "shared",
                sdk / "Include" / sdk_version / "um",
            ]
        )
        env["LIB"] = ";".join(
            str(p)
            for p in [
                vc / "lib/x64",
                sdk / "Lib" / sdk_version / "ucrt/x64",
                sdk / "Lib" / sdk_version / "um/x64",
            ]
        )
        env["PATH"] = str(llvm) + os.pathsep + env["PATH"]
        resource = max((llvm.parent / "lib/clang").iterdir(), key=lambda p: int(p.name))
        runtime = resource / "lib/windows/clang_rt.asan_dynamic-x86_64.dll"
        shutil.copyfile(runtime, folder / runtime.name)
        report["toolchain"] = dict(
            msvc=vc.name,
            sdk=sdk_version,
            stl_container_annotations=False,
            tools={
                tool: sha(llvm / tool)
                for tool in ("clang-cl.exe", "lld-link.exe", "llvm-cov.exe", "llvm-profdata.exe")
            },
            libraries={
                p.name: sha(p)
                for p in (resource / "lib/windows").glob("*.lib")
                if any(x in p.name for x in ("fuzzer", "asan", "profile"))
            },
            asan_runtime_sha256=sha(runtime),
        )
        report["toolchain"]["compiler_version"] = command(
            "compiler_version", [llvm / "clang-cl.exe", "--version"]
        ).splitlines()[0]
        report["toolchain"]["coverage_version"] = (
            command("coverage_version", [llvm / "llvm-cov.exe", "--version"])
            .splitlines()[1]
            .strip()
        )
        common = [
            llvm / "clang-cl.exe",
            "/nologo",
            "/std:c++17",
            "/EHsc",
            "/MT",
            "/D_DISABLE_STRING_ANNOTATION",
            "/D_DISABLE_VECTOR_ANNOTATION",
            "/O1",
            "/Zi",
            "/fsanitize=address",
            "-fuse-ld=lld",
        ]
        profile = ["/clang:-fprofile-instr-generate", "/clang:-fcoverage-mapping"]
        for name, source, extra in (
            ("asan_probe", ROOT / "native/asan_probe.cpp", []),
            (
                "runtime_control",
                ROOT / "native/pilot/runtime_control.cpp",
                profile + ["-fsanitize=fuzzer", "/DEXCEPTION_CONTROL"],
            ),
            ("parser_replay", ROOT / "native/pilot/parser.cpp", profile),
            ("parser_boundaries", ROOT / "native/pilot/boundaries.cpp", profile),
            (
                "parser_fuzz",
                ROOT / "native/pilot/parser.cpp",
                profile + ["/DSURGE_FUZZ", "-fsanitize=fuzzer"],
            ),
            ("code_pe_tests", ROOT / "native/code_pe_tests.cpp", []),
            ("manifest_pe_tests", ROOT / "native/manifest_pe_tests.cpp", []),
        ):
            command(
                "build_" + name,
                [
                    *common,
                    *extra,
                    source,
                    "/Fe" + str(folder / (name + ".exe")),
                    "/Fo" + str(folder / (name + ".obj")),
                    "/link",
                    "/INCREMENTAL:NO",
                    "/DEBUG",
                ],
                seconds=180,
            )
        safe = command("asan_safe", [folder / "asan_probe.exe", "safe"])
        assert "ASAN_PROBE_COMPLETED" in safe
        fault = command("asan_detection", [folder / "asan_probe.exe", "fault"], expected=86)
        assert (
            "ERROR: AddressSanitizer: heap-buffer-overflow" in fault
            and "ASAN_PROBE_COMPLETED" not in fault
        )
        report["instrumentation"] = "passed"
        command(
            "runtime_control",
            [folder / "runtime_control.exe", "-runs=16", "-seed=17", "-timeout=2", "-max_len=8"],
        )
        for name in ("code_pe_tests", "manifest_pe_tests"):
            command(name, [folder / (name + ".exe")])
        inputs = folder / "boundary-inputs"
        boundary_coverage, boundary_output = coverage("boundaries", "parser_boundaries", [inputs])
        rows = parse_output(boundary_output)
        local = env.copy()
        local["LLVM_PROFILE_FILE"] = str(folder / "boundaries-repeat.profraw")
        repeat_inputs = folder / "boundary-repeat-inputs"
        repeated = command("boundaries_repeat", [folder / "parser_boundaries.exe", repeat_inputs], seconds=15, local_env=local)
        assert repeated == boundary_output, "Boundary outcomes changed across repetitions"
        for path in inputs.glob("*.bin"):
            assert sha(path) == sha(repeat_inputs / path.name), "Boundary inputs changed"
        source_lines = (ROOT / "native/code_range_pe.hpp").read_text().splitlines()
        guards = {}
        for prefix in GUARDS:
            lines = [i for i, line in enumerate(source_lines, 1) if line.strip().startswith(prefix)]
            assert len(lines) == 1, prefix
            guards[prefix] = [b for b in boundary_coverage["branches"] if b[0] == lines[0]]
        report["boundary_tests"] = dict(
            status="passed", cases=rows, executions=2*len(rows), repeatability="passed",
            output_sha256=hashlib.sha256(boundary_output.encode()).hexdigest(),
            coverage=boundary_coverage, guards=guards,
            relocation_reader_executed=any("read@U_IMAGE_BASE_RELOCATION" in name and count > 0 for name, count in boundary_coverage["functions"].items()),
            inputs=[dict(id=p.stem, bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(inputs.glob("*.bin"))],
        )
        try:
            validate_evidence(report["boundary_tests"])
        except Exception:
            report["boundary_tests"]["status"] = "failed"
            raise
        save()
        command("seed", [folder / "parser_replay.exe", "seed", corpus])
        for p in corpus.iterdir():
            shutil.copyfile(p, controls / p.name)
        baseline, control_output = coverage("baseline")
        expected = (
            "OK|16384|S:4096:512|R:LabCodeProbe:4096:"
            + ("90" * 9)
            + "|R:LabCodeSecondary:4128:"
            + ("90" * 6)
        )
        control_rows = dict(line.split("\t", 1) for line in control_output.splitlines())
        assert control_rows["valid.bin"] == expected
        assert control_rows["short.bin"].startswith("REFUSED|") and control_rows[
            "descriptor.bin"
        ].startswith("REFUSED|")
        report["controls"] = "passed"
        report["baseline_coverage"] = baseline
        report["seed_hashes"] = {p.name: sha(p) for p in controls.iterdir()}
        report["fuzz_runs"] = []
        for number in (17, 20261023):
            local = env.copy()
            local["LLVM_PROFILE_FILE"] = str(folder / ("fuzz-" + str(number) + ".profraw"))
            text = command(
                "fuzz_" + str(number),
                [
                    folder / "parser_fuzz.exe",
                    corpus,
                    "-seed=" + str(number),
                    "-runs=5000",
                    "-max_total_time=30",
                    "-max_len=65536",
                    "-timeout=2",
                    "-rss_limit_mb=512",
                    "-print_final_stats=1",
                    "-artifact_prefix=" + str(folder) + "\\",
                ],
                local_env=local,
            )
            count = re.search(r"stat::number_of_executed_units:\s*(\d+)", text)
            peak = re.search(r"stat::peak_rss_mb:\s*(\d+)", text)
            assert count and 1000 <= int(count[1]) <= 5000
            assert "inline 8-bit counters" in text and "PC tables" in text
            assert "ERROR: AddressSanitizer:" not in text
            if peak:
                assert int(peak[1]) <= 512
            report["fuzz_runs"].append(
                dict(
                    seed=number,
                    executions=int(count[1]),
                    peak_rss_mb=int(peak[1]) if peak else None,
                    progress=re.findall(r"#\d+\s+(?:INITED|NEW|REDUCE|DONE).*", text),
                )
            )
        final, output1 = coverage("final")
        report["final_coverage"] = final
        assert final["summary"]["branches"]["covered"] > baseline["summary"]["branches"]["covered"]
        for family in (
            "??0LabImage",
            "executable_ranges",
            "exported",
            "declarations",
            "offset",
            "declared_ranges",
            "probe",
        ):
            assert any(
                family in name and count > 0 for name, count in final["functions"].items()
            ), family
        local = env.copy()
        local["LLVM_PROFILE_FILE"] = str(folder / "repeat.profraw")
        output2 = command(
            "corpus_repeat", [folder / "parser_replay.exe", "replay", corpus], local_env=local
        )
        assert output1 == output2
        rows = dict(line.split("\t", 1) for line in output1.splitlines())
        report["corpus"] = [
            dict(file=p.name, sha256=sha(p), bytes=p.stat().st_size, result=rows[p.name])
            for p in sorted(corpus.iterdir())
            if p.is_file()
        ]
        assert all(p["bytes"] <= 65536 for p in report["corpus"])
        assert sum(p["bytes"] for p in report["corpus"]) <= 32 * 1024 * 1024
        report["classification_counts"] = dict(
            Counter("accepted" if row.startswith("OK|") else row for row in rows.values())
        )
        report["corpus_replay"] = dict(
            status="passed", sha256=hashlib.sha256(output1.encode()).hexdigest(), files=len(rows)
        )
        report["binaries"] = {p.name: sha(p) for p in folder.glob("*.exe")}
        report["source_unchanged"] = all(
            sha(ROOT / name) == digest for name, digest in report["source_sha256"].items()
        )
        assert report["source_unchanged"]
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = (str(exc) or type(exc).__name__).replace(str(ROOT), "<repo>")
        report["status"] = "failed"
        for item in report["checks"]:
            if item["status"] == "running":
                item["status"] = "failed"
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        save()
        print("SURGE_LIBFUZZER_JSON=" + json.dumps(report, sort_keys=True), flush=True)
        print("Local pilot evidence: " + str(folder / "pilot.json"), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Build a bounded, self-contained Windows x64 candidate from existing Surge code."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile

try:
    from . import qualify
    from .release_files import ROOT, source_files
except ImportError:
    import qualify
    from release_files import ROOT, source_files

LIMITS = dict(total_seconds=1200, command_seconds=600, download_seconds=180,
              log_bytes=10 * 1024 * 1024, archive_bytes=256 * 1024 * 1024,
              expanded_bytes=768 * 1024 * 1024, files=10000, input_bytes=256 * 1024)
BACKEND = ("chart", "comparison", "desktop_worker", "engine", "evaluation", "evidence_labels",
           "import_errors", "integrity_manifest", "investigation", "mapping_checks", "native_integrity",
           "native_stream", "record_search", "workflow")
DESKTOP = ("main.cjs", "preload.cjs", "runtime.cjs", "boundary.cjs", "case-library.cjs", "startup.cjs")
GUIDES = ("windows-package.md", "windows-package-tester.md", "windows-package-session-record.md")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def package_filename(version, commit, dirty):
    label = commit[:7] + ("-dirty" if dirty else "")
    return f"Surge-{version}-{label}-windows-x64.zip"


def inventory(root):
    return [dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
            for p in sorted(root.rglob("*")) if p.is_file()]


def extract_checked(archive, destination, deadline):
    """No traversal, links, duplicate/case-colliding files or unchecked expansion."""
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as source:
        entries = [item for item in source.infolist() if not item.is_dir()]
        names = [item.filename for item in entries]
        if len(entries) > LIMITS["files"] or len({name.casefold() for name in names}) != len(names):
            raise ValueError("runtime_archive_file_count_or_collision")
        if sum(item.file_size for item in entries) > LIMITS["expanded_bytes"]:
            raise ValueError("runtime_archive_expansion_limit")
        for item in entries:
            name = item.filename
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith("/") or ".." in parts or "\\" in name or ":" in name
                    or any(part.endswith((".", " ")) for part in parts)
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("unsafe_runtime_archive_path")
            if time.monotonic() >= deadline:
                raise TimeoutError("total_deadline")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(item) as incoming, target.open("xb") as output:
                shutil.copyfileobj(incoming, output, length=1024 * 1024)
            if target.stat().st_size != item.file_size:
                raise ValueError("runtime_archive_length_mismatch")


def dependency(lock, cache, deadline):
    """The lock is reviewed source; an existing cache is still hashed before use."""
    target = cache / lock["filename"]
    cache.mkdir(parents=True, exist_ok=True)
    cached = target.exists()
    started = time.monotonic()
    final_url = lock["url"]
    if not cached:
        partial = target.with_name(target.name + ".partial-" + uuid.uuid4().hex[:8])
        end = min(deadline, started + LIMITS["download_seconds"])
        with urllib.request.urlopen(lock["url"], timeout=min(30, max(1, end - started))) as response:
            final_url = response.url
            with partial.open("xb") as output:
                while True:
                    if time.monotonic() >= end:
                        raise TimeoutError("runtime_download_deadline")
                    raw = response.read(1024 * 1024)
                    if not raw:
                        break
                    output.write(raw)
                    if output.tell() > LIMITS["archive_bytes"]:
                        raise ValueError("runtime_download_size_limit")
        if sha(partial) != lock["sha256"]:
            raise ValueError("runtime_download_hash_mismatch: " + str(partial))
        partial.rename(target)
    if target.stat().st_size > LIMITS["archive_bytes"] or sha(target) != lock["sha256"]:
        raise ValueError("runtime_cache_hash_mismatch: " + str(target))
    if time.monotonic() > min(deadline, started + LIMITS["download_seconds"]):
        raise TimeoutError("runtime_download_deadline")
    return target, dict(**lock, bytes=target.stat().st_size, cache_used=cached,
                        downloaded_from=final_url, elapsed_seconds=round(time.monotonic() - started, 3))


def run_builder(args):
    started = time.monotonic()
    deadline = started + LIMITS["total_seconds"]
    folder = args.output_root.resolve() / ("windows-package-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    payload = folder / "payload"
    work = folder / "work"
    work.mkdir()
    report = dict(schema="surge-windows-package-build-v1", status="incomplete", steps=[],
                  started_at_utc=datetime.now(timezone.utc).isoformat(), limits=LIMITS,
                  os=platform.platform(), bootstrap_python=platform.python_version(),
                  native_parser_tests_run=False, ordinary_sample_check=True,
                  human_acceptance="pending", broader_fuzzing="unfinished")
    logs_used = 0

    def command(name, argv, cwd=ROOT, timeout=None):
        nonlocal logs_used
        argv = [str(value) for value in argv]
        remaining = LIMITS["log_bytes"] - logs_used
        if remaining <= 0 or time.monotonic() >= deadline:
            raise ValueError("build_log_or_time_budget_exhausted")
        log = folder / (name + ".log")
        step = dict(id=name, argv=argv, cwd=str(cwd), timeout_seconds=timeout or LIMITS["command_seconds"])
        previous = qualify.LOG_LIMIT
        try:
            qualify.LOG_LIMIT = remaining
            result = qualify.run_command(step, log, os.environ.copy(), deadline)
        finally:
            qualify.LOG_LIMIT = previous
        logs_used += result.get("log_bytes", 0)
        report["steps"].append(dict(id=name, command=argv, active_log_limit_bytes=remaining, **result))
        if result["status"] != "passed":
            raise ValueError(name + ": " + result["status"])
        return log.read_text(encoding="utf-8", errors="replace").strip()

    def check(name, condition):
        report["steps"].append(dict(id=name, status="passed" if condition else "failed"))
        if not condition:
            raise ValueError(name)

    try:
        check("windows_x64", sys.platform == "win32" and platform.machine().lower() in ("amd64", "x86_64"))
        commit = command("source_commit", ["git", "rev-parse", "HEAD"], timeout=30)
        status = command("source_status", ["git", "status", "--porcelain=v1"], timeout=30)
        check("clean_source_or_explicit_development_attempt", not status or args.allow_dirty)
        source = {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files()}
        report["source"] = dict(commit=commit, dirty=bool(status), files=source)
        write_json(folder / "source-manifest.json", report["source"])
        lock = json.loads((ROOT / "scripts/windows-package-lock.json").read_text())
        package = json.loads((ROOT / "desktop/package.json").read_text())
        check("stable_package_identity", package["name"] == "surge-desktop" and not package.get("productName"))
        check("electron_version_locked", package["devDependencies"]["electron"] == lock["electron"]["version"])
        official_checksums = json.loads((ROOT / "desktop/node_modules/electron/checksums.json").read_text())
        check("electron_official_npm_checksum", official_checksums[lock["electron"]["filename"]] == lock["electron"]["sha256"])
        archives = {}
        report["runtimes"] = {}
        for name in ("electron", "python"):
            # An independently supervised child enforces the overall download
            # deadline even if a network read stalls between chunk checks.
            download_report = folder / (name + "-download.json")
            command("download_" + name, [sys.executable, "-B", Path(__file__).resolve(),
                                        "--fetch-runtime", name, "--cache", args.cache.resolve(),
                                        "--download-report", download_report], timeout=LIMITS["download_seconds"])
            report["runtimes"][name] = json.loads(download_report.read_text())
            archives[name] = args.cache.resolve() / lock[name]["filename"]
            check(name + "_download_hash", sha(archives[name]) == lock[name]["sha256"])
        extract_checked(archives["electron"], payload, deadline)
        (payload / "electron.exe").rename(payload / "Surge.exe")
        if (payload / "electron_wer.dll").exists():
            (payload / "electron_wer.dll").rename(payload / "Surge_wer.dll")
        # Keep upstream support files and all locales; only the Electron demo is omitted.
        default_app = payload / "resources/default_app.asar"
        if default_app.exists():
            default_app.unlink()
        extract_checked(archives["python"], payload / "resources/python", deadline)
        py = payload / "resources/python/python.exe"
        python_version = command("bundled_python_identity", [py, "-I", "-B", "-c", "import platform; print(platform.python_version())"], timeout=30)
        check("bundled_python_version", python_version == lock["python"]["version"])
        app = payload / "resources/app"
        desktop = app / "desktop"
        (desktop / "dist").mkdir(parents=True)
        write_json(app / "package.json", dict(name="surge-desktop", version=package["version"], main="desktop/main.cjs",
                                               description=package["description"]))
        identity = dict(schema="surge-windows-package-identity-v1", version=package["version"], platform="win32-x64",
                        source_commit=commit, source_dirty=bool(status), electron_version=lock["electron"]["version"],
                        python_version=lock["python"]["version"], sample_build="v2")
        write_json(app / "package-identity.json", identity)
        for name in BACKEND:
            shutil.copy2(ROOT / (name + ".py"), app / (name + ".py"))
        for name in DESKTOP:
            shutil.copy2(ROOT / "desktop" / name, desktop / name)
        # Freeze renderer/native inputs for this attempt; never use stale build output.
        for relative in source:
            if relative.startswith(("desktop/src/", "native/")):
                target = work / "source" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
        script = "const e=require('esbuild'),p=require('node:path');e.buildSync({entryPoints:[process.argv[1]],outfile:process.argv[2],nodePaths:[p.join(process.cwd(),'node_modules')],bundle:true,minify:true,sourcemap:false,define:{'process.env.NODE_ENV':'\"production\"'},legalComments:'eof'});"
        command("renderer_build", ["node", "-e", script, work / "source/desktop/src/main.jsx", desktop / "dist/app.js"], ROOT / "desktop")
        for name in ("index.html", "style.css"):
            shutil.copy2(work / "source/desktop/src" / name, desktop / "dist" / name)
        command("node_identity", ["node", "--version"], timeout=30)
        command("cmake_identity", ["cmake", "--version"], timeout=30)
        native_build = work / "native-build"
        command("native_configure", ["cmake", "-S", work / "source/native", "-B", native_build, "-A", "x64", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded"])
        command("native_build", ["cmake", "--build", native_build, "--config", "Release", "--target", "surge_owned_app", "surge_fixture", "--", "/nodeReuse:false"])
        cache_text = (native_build / "CMakeCache.txt").read_text()
        linker = re.search(r"^CMAKE_LINKER:FILEPATH=(.+)$", cache_text, re.M).group(1)
        dumpbin = Path(linker).with_name("dumpbin.exe")
        dependencies = {}
        for name in ("surge_owned_app.exe", "lab_module_v2.dll"):
            dependencies[name] = command("dependencies_" + name.replace(".", "_"), [dumpbin, "/dependents", native_build / name], timeout=30)
            check("static_runtime_" + name.replace(".", "_"), not re.search(r"(?i)(?:MSVCP|VCRUNTIME)\d", dependencies[name]))
            target = app / "native/build" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(native_build / name, target)
        # Existing clean-capture approval path, in a new owned root. No developer registry read.
        approval = work / "approval"
        (approval / "scripts").mkdir(parents=True)
        (approval / "native/build").mkdir(parents=True)
        for name in BACKEND:
            shutil.copy2(app / (name + ".py"), approval / (name + ".py"))
        shutil.copy2(ROOT / "scripts/native_capture.py", approval / "scripts/native_capture.py")
        for name in ("surge_fixture.exe", "lab_module_v2.dll"):
            shutil.copy2(native_build / name, approval / "native/build" / name)
        baseline = app / "native/baselines.json"
        command("approve_exact_v2", [py, "-I", "-B", approval / "scripts/native_capture.py", "approve", "--build", "v2", "--baselines", baseline,
                                    "--reason", "Reviewed owned v2 source; exact static-runtime Windows package build only."], timeout=30)
        registry = json.loads(baseline.read_text())
        module_hash = sha(app / "native/build/lab_module_v2.dll")
        check("approval_exact_module_only", len(registry["entries"]) == 2 and all(entry["module_sha256"] == module_hash and entry.get("integrity_manifest_sha256") for entry in registry["entries"]))
        report["sample"] = dict(build="v2", dll_sha256=module_hash, baseline_sha256=sha(baseline), entries=len(registry["entries"]),
                                range_names=[entry["range_name"] for entry in registry["entries"]], runtime="MultiThreaded", approval_generated_at_build=True)
        # Validate the existing ordinary capture/reader path using the packaged backend.
        probe = "import sys,json;sys.path.insert(0,sys.argv[1]);import desktop_worker,native_stream;w=desktop_worker.Workspace();s=native_stream.NativeSession('v2');s.ready.wait(5);import time;time.sleep(1.2);status=s.stop();rows=s.snapshot();assert status['state']=='stopped' and s.process.poll()==0,status;assert len(rows)>=4 and all(r.get('baseline_approved') is True and r.get('memory_matches') is True and r.get('protection_matches') is True for r in rows),rows;print(json.dumps({'backend':desktop_worker.__file__,'python':sys.executable,'samples':status['samples'],'observations':len(rows),'sample_exit_code':s.process.returncode}));w.close()"
        command("ordinary_packaged_sample", [py, "-I", "-B", "-c", probe, app], timeout=30)
        # Existing backend cases, copied unchanged; imports resolve to shipped code.
        backend_tests = work / "backend-checks"
        (backend_tests / "verification/temporary-test-files").mkdir(parents=True)
        for name in ("test_desktop_worker.py", "test_evaluation.py"):
            shutil.copy2(ROOT / name, backend_tests / name)
        backend_probe = (
            "import sys,json,pathlib,unittest;sys.path.insert(0,sys.argv[1]);sys.path.append(sys.argv[2]);"
            "names=json.loads(sys.argv[3]);mods=[__import__(n) for n in names];"
            "assert all(pathlib.Path(m.__file__).resolve().parent==pathlib.Path(sys.argv[1]).resolve() for m in mods);"
            "suite=unittest.defaultTestLoader.loadTestsFromNames(['test_desktop_worker','test_evaluation']);"
            "result=unittest.TextTestRunner(verbosity=2).run(suite);"
            "print('SURGE_BUNDLED_BACKEND='+json.dumps({'python':sys.executable,'modules':{m.__name__:m.__file__ for m in mods},'tests':result.testsRun,'skipped':len(result.skipped),'passed':result.wasSuccessful()}));"
            "sys.exit(0 if result.wasSuccessful() and result.testsRun==25 and not result.skipped else 1)"
        )
        command("existing_backend_on_bundled_python", [py, "-I", "-B", "-c", backend_probe, app, backend_tests, json.dumps(BACKEND)], timeout=120)
        licenses = payload / "licenses"
        licenses.mkdir()
        shutil.copy2(ROOT / "LICENSE", licenses / "Surge-MIT.txt")
        shutil.copy2(payload / "LICENSE", licenses / "Electron-LICENSE.txt")
        # Python ships its full license and bundled-library acknowledgements unchanged.
        python_license = payload / "resources/python/LICENSE.txt"
        check("python_license_present", python_license.is_file() and python_license.stat().st_size > 1000)
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
        for name in ("react", "react-dom", "scheduler"):
            module = ROOT / "desktop/node_modules" / name
            if name == "scheduler":
                module = ROOT / "desktop/node_modules/.pnpm" / (name + "@" + lock["renderer"][name]) / "node_modules" / name
            meta = json.loads((module / "package.json").read_text())
            check("locked_" + name, meta["version"] == lock["renderer"][name])
            shutil.copy2(module / "LICENSE", licenses / (name + "-LICENSE.txt"))
        (payload / "THIRD-PARTY-NOTICES.txt").write_text(
            "Surge application: MIT; see licenses/Surge-MIT.txt.\n"
            "Electron: licenses/Electron-LICENSE.txt. Chromium/Node and bundled components: LICENSES.chromium.html.\n"
            "React, ReactDOM and Scheduler: licenses/*-LICENSE.txt; renderer retains bundled legal comments.\n"
            "CPython and its bundled libraries/runtime files: resources/python/LICENSE.txt (also licenses/Python-LICENSE.txt).\n"
            "Owned native sample: Surge MIT source, built with the Microsoft C++ static runtime; Windows OS DLLs are not bundled.\n"
            "Build tools (esbuild, CMake, MSVC, pnpm) and developer dependencies are not shipped.\n"
            "Runtime upstream URLs and hashes: resources/app/runtime-provenance.json. This candidate is not publisher-signed.\n", encoding="utf-8")
        write_json(app / "runtime-provenance.json", lock)
        for name in GUIDES:
            destination = payload / "docs" / name
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(ROOT / "docs" / name, destination)
        for item in sorted((ROOT / "demos/native").iterdir()):
            if item.is_file() and (item.name in ("README.md", "expected.json") or item.name.endswith(".case.json")):
                destination = payload / "demos/native" / item.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)
        (payload / "OPEN-SURGE.txt").write_text("Extract this whole folder, then open Surge.exe. No setup or developer tools are needed.\nRead docs/windows-package.md for instructions and limits. Cases stay in your Windows profile when replacing this folder.\n", encoding="utf-8")
        check("source_unchanged", source == {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files()})
        files = inventory(payload)
        check("payload_bounds", len(files) <= LIMITS["files"] and sum(item["bytes"] for item in files) <= LIMITS["expanded_bytes"])
        forbidden = [item["path"] for item in files if any(part in (".git", ".venv", "node_modules", "__pycache__") for part in PurePosixPath(item["path"]).parts)
                     or item["path"].endswith((".log", ".pdb")) or item["path"].endswith(("surge_fixture.exe", "lab_module.dll"))]
        check("no_developer_or_internal_test_payload", not forbidden)
        archive = folder / package_filename(package["version"], commit, bool(status))
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
            for item in files:
                if time.monotonic() >= deadline:
                    raise TimeoutError("total_deadline")
                output.write(payload / item["path"], item["path"])
        check("zip_size_bound", archive.stat().st_size <= LIMITS["archive_bytes"])
        with zipfile.ZipFile(archive) as zipped:
            check("zip_crc_and_file_set", zipped.testzip() is None and sorted(zipped.namelist()) == sorted(item["path"] for item in files))
            for item in files:
                raw = zipped.read(item["path"])
                if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                    raise ValueError("zip_readback_hash_mismatch")
        check("zip_all_bytes_verified", True)
        manifest = dict(schema="surge-windows-package-v1", version=package["version"], platform="win32-x64", source=report["source"],
                        runtimes=report["runtimes"], sample=report["sample"], files=files, limits=LIMITS,
                        archive=dict(name=archive.name, bytes=archive.stat().st_size, sha256=sha(archive)))
        write_json(folder / "package-manifest.json", manifest)
        report.update(status="passed", package=str(archive), manifest=str(folder / "package-manifest.json"),
                      manifest_sha256=sha(folder / "package-manifest.json"), archive=manifest["archive"], files=len(files),
                      expanded_bytes=sum(item["bytes"] for item in files), app_identity=identity)
    except Exception as error:
        report.update(status="failed", error=str(error), error_type=type(error).__name__)
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["log_bytes"] = logs_used
        if report["elapsed_seconds"] > LIMITS["total_seconds"]:
            report.update(status="failed", error="total_deadline_including_verification")
        write_json(folder / "report.json", report)
        print("Windows package " + report["status"] + ": " + str(folder / "report.json"))
    return 0 if report["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "verification/qualification")
    parser.add_argument("--cache", type=Path, default=ROOT / "verification/qualification/windows-package-cache")
    parser.add_argument("--allow-dirty", action="store_true", help="Development attempt only; final release requires clean committed source.")
    parser.add_argument("--fetch-runtime", choices=("electron", "python"), help=argparse.SUPPRESS)
    parser.add_argument("--download-report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.fetch_runtime:
        if args.download_report is None:
            parser.error("--fetch-runtime requires --download-report")
        lock = json.loads((ROOT / "scripts/windows-package-lock.json").read_text())
        _, result = dependency(lock[args.fetch_runtime], args.cache.resolve(), time.monotonic() + LIMITS["download_seconds"])
        write_json(args.download_report, result)
        return 0
    return run_builder(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""Prepare and run an offline Windows guest qualification kit, separate from Product.

A hosted self-check never counts as clean-machine acceptance. Guest qualification
requires a VM-shaped machine, no observed installed developer dependencies, and
an explicit fresh-guest provenance note, followed by the existing real journeys.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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

# Embedded Python deliberately omits the script directory from its import path.
# Resolve only this reviewed tooling directory, never the caller's working folder.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from . import check_windows_package as consumer
except ImportError:
    import check_windows_package as consumer

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "surge-clean-windows-qualification-v1"
VM_MODELS = ("virtual machine", "vmware virtual platform", "virtualbox", "standard pc", "kvm", "qemu", "parallels")
HARNESS = (
    "scripts/check_clean_machine.py", "scripts/check_clean_machine.ps1",
    "scripts/check_windows_package.py", "scripts/check_survive_package.py",
    "scripts/check_launcher.py", "scripts/release_files.py",
    "scripts/verify_windows_consumer.py", "scripts/windows_owned_processes.py",
    "scripts/survive_package.py", "desktop/packaged.test.cjs",
    "desktop/survive-packaged.test.cjs",
    "demos/native/approved-update.case.json", "demos/native/expected.json",
)
MAX_KIT_FILES = 4000
MAX_TOOL_BYTES = 96 * 1024**2
TOTAL_SECONDS = 2400


def isolated_script_command(python, script, *arguments):
    """Run reviewed sibling tools under embedded Python's isolated import policy."""
    runner = ("import runpy,sys;from pathlib import Path;"
              "p=Path(sys.argv[1]).resolve(strict=True);"
              "sys.path.insert(0,str(p.parent));sys.argv=sys.argv[1:];"
              "runpy.run_path(str(p),run_name='__main__')")
    return [str(python), "-I", "-B", "-c", runner, str(Path(script).resolve(strict=True)), *arguments]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path, limit=16 * 1024**2):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError("JSON exceeds reviewed bound")
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def environment_probe():
    if os.name != "nt":
        raise RuntimeError("Windows is required")
    command = r"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$os = Get-CimInstance Win32_OperatingSystem
$machine = Get-CimInstance Win32_ComputerSystem
$tools = @('python.exe','python3.exe','node.exe','pnpm.cmd','UnrealEditor.exe','UnrealEditor-Cmd.exe','cl.exe')
$commands = @($tools | ForEach-Object { Get-Command $_ -ErrorAction SilentlyContinue } | Select-Object Name,Source)
$keys = @('HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*')
$installed = @($keys | ForEach-Object { Get-ItemProperty $_ -ErrorAction SilentlyContinue } | Where-Object { $_.DisplayName -match '^(Python [0-9]|Node\.js|Unreal Engine|Microsoft Visual Studio|Build Tools for Visual Studio)' } | Select-Object DisplayName,DisplayVersion)
$storeTools = @(Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'PythonSoftwareFoundation|Nodejs|UnrealEngine|VisualStudioCode' } | Select-Object Name,Version)
$engineRoots = @()
foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
 if ($base) { $engineRoots += @(Get-ChildItem -LiteralPath (Join-Path $base 'Epic Games') -Directory -ErrorAction SilentlyContinue | Where-Object Name -Like 'UE_*' | Select-Object -ExpandProperty Name) }
}
$registeredEngines = @(Get-ItemProperty 'HKCU:\Software\Epic Games\Unreal Engine\Builds' -ErrorAction SilentlyContinue | ForEach-Object { $_.PSObject.Properties | Where-Object Name -NotLike 'PS*' } | Select-Object -ExpandProperty Name)
$gpus = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion)
[ordered]@{os=@{caption=$os.Caption;version=$os.Version;build=$os.BuildNumber;architecture=$os.OSArchitecture};machine=@{manufacturer=$machine.Manufacturer;model=$machine.Model;hypervisor_present=$machine.HypervisorPresent};graphics=$gpus;path_commands=$commands;installed_developer_products=$installed;installed_store_developer_products=$storeTools;known_engine_roots=$engineRoots;registered_engines=$registeredEngines;windows_sandbox_available=[bool](Get-Command WindowsSandbox.exe -ErrorAction SilentlyContinue);hyperv_management_available=[bool](Get-Command Get-VM -ErrorAction SilentlyContinue)} | ConvertTo-Json -Depth 6 -Compress
"""
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, timeout=25, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if len(result.stdout) > 128 * 1024:
        raise ValueError("Machine inventory exceeds reviewed bound")
    return json.loads(result.stdout.decode("utf-8-sig"))


def guest_preconditions(probe, provenance):
    """Return every reason qualification cannot be called a clean Windows VM run."""
    issues = []
    model = str(probe.get("machine", {}).get("model", "")).casefold()
    if not any(name in model for name in VM_MODELS):
        issues.append("Machine model does not identify a supported Windows VM; host isolation is not a clean guest")
    if not str(probe.get("os", {}).get("architecture", "")).startswith("64"):
        issues.append("Windows x64 is required")
    # Windows App Execution Aliases are recorded, but do not imply an installed interpreter.
    commands = [x for x in probe.get("path_commands", [])
                if "\\microsoft\\windowsapps\\" not in str(x.get("Source", "")).casefold()]
    if commands or probe.get("installed_developer_products") or probe.get("installed_store_developer_products") or probe.get("known_engine_roots") or probe.get("registered_engines"):
        issues.append("Developer runtimes/tools or Unreal installations were observed")
    if not isinstance(provenance, dict) or set(provenance) != {"provisioning", "image", "created_utc"}:
        issues.append("Fresh guest provenance requires provisioning, image and created_utc")
    elif provenance.get("provisioning") not in {"fresh-vm", "fresh-sandbox"} or any(not isinstance(v, str) or not 1 <= len(v) <= 256 for v in provenance.values()):
        issues.append("Invalid fresh guest provenance")
    else:
        try:
            stamp = datetime.fromisoformat(provenance["created_utc"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("Timezone required")
        except ValueError:
            issues.append("Fresh guest creation timestamp must be timezone-qualified ISO 8601")
    return issues


def tooling_inventory(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise ValueError("Qualification tooling cannot contain symlinks")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    if len(result) > MAX_KIT_FILES or sum(x["bytes"] for x in result.values()) > MAX_TOOL_BYTES:
        raise ValueError("Qualification tooling exceeds file/byte bounds")
    return result


def observe_game_modules(application, observed, began):
    """Read only owned Shipping processes; never inspect other games or apps."""
    from windows_owned_processes import processes_owned_by
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    windows = powershell.parents[3]
    for process in processes_owned_by(application):
        if Path(process["ExecutablePath"]).name != "SurgeMovementLab-Win64-Shipping.exe":
            continue
        pid = process["ProcessId"]
        state = observed.setdefault(pid, {"pid": pid, "first_seen_s": time.monotonic() - began,
                                          "application": str(application), "snapshots": []})
        age = time.monotonic() - began - state["first_seen_s"]
        due = 5 if not state["snapshots"] else 35
        if len(state["snapshots"]) >= 2 or age < due:
            continue
        token = consumer.token_identity(pid)
        if token.get("token_elevated") is not False:
            raise ValueError("Owned game was not running with a non-elevated token")
        command = ("$ErrorActionPreference='Stop'; $OutputEncoding=[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding $false; "
                   "$owned=Get-Process -Id " + str(pid) + "; @{modules=@($owned.Modules | ForEach-Object {$_.FileName});"
                   "tcp=@(Get-NetTCPConnection -ErrorAction Stop | Where-Object OwningProcess -EQ " + str(pid) + " | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State);"
                   "udp=@(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object OwningProcess -EQ " + str(pid) + " | Select-Object LocalAddress,LocalPort)} | ConvertTo-Json -Depth 4 -Compress")
        result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        value = json.loads(result.stdout.decode("utf-8-sig"))
        modules = value["modules"]
        if not isinstance(modules, list) or not 1 <= len(modules) <= 512:
            raise ValueError("Unexpected owned game module inventory")
        outside = [name for name in modules if not Path(name).resolve().is_relative_to(application)
                   and not Path(name).resolve().is_relative_to(windows)]
        if outside or value["tcp"] or value["udp"]:
            raise ValueError("Owned game used an external module or network endpoint: " + repr(outside))
        state["snapshots"].append({"observed_after_start_s": round(age, 3), "token": token, **value})


def run_consumer(command, *, name, kit, output, env, remaining):
    began, observed = time.monotonic(), {}
    with (output / (name + ".log")).open("xb") as stream:
        process = subprocess.Popen(command, cwd=kit / "tools", env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            while process.poll() is None:
                if time.monotonic() - began > remaining:
                    raise TimeoutError("Clean qualification exceeded total deadline")
                if name == "gameplay-to-report":
                    for application in output.glob("s/consumer-*/application"):
                        observe_game_modules(application, observed, began)
                time.sleep(1)
            if name == "gameplay-to-report":
                write_new(output / "owned-game-modules.json", list(observed.values()))
                if process.returncode == 0 and (len(observed) != 3 or any(len(value["snapshots"]) != 2 for value in observed.values())):
                    raise ValueError("Expected two module/network observations for all three owned game rounds")
            return process.returncode
        finally:
            if process.poll() is None:
                # Closing the child consumer also closes its existing kernel job,
                # which owns the application/game children. No name-based kills.
                process.kill()
                process.wait(timeout=10)


def prepare(archive, manifest_path, output_root, playwright):
    archive, manifest_path = archive.resolve(strict=True), manifest_path.resolve(strict=True)
    manifest = read_json(manifest_path)
    verified = consumer.verify_package(archive, manifest)
    if verified["package_kind"] != "surge-survive":
        raise ValueError("Combined Survive package required")
    playwright = playwright.resolve(strict=True)
    info = read_json(playwright / "package.json", 64 * 1024)
    version = info["version"]
    expected = read_json(ROOT / "desktop/package.json")["devDependencies"]["playwright"]
    if version != expected or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Qualification Playwright must match the locked development version")
    # pnpm's sibling dependency directory, or a conventional flat node_modules.
    core = playwright.parent / "playwright-core"
    if not core.is_dir() or read_json(core / "package.json")["version"] != version:
        raise ValueError("Matching playwright-core dependency is unavailable")
    folder = output_root.resolve() / ("clean-windows-kit-" + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    inputs, tools = folder / "inputs", folder / "tools"
    inputs.mkdir()
    tools.mkdir()
    for name in HARNESS:
        target = tools / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    for source, name in ((playwright, "playwright"), (core.resolve(strict=True), "playwright-core")):
        if not (source / "LICENSE").is_file():
            raise ValueError("Qualification tool licence is missing")
        # These are pre-existing, locked local packages. Copy their resolved bytes;
        # do not ship node_modules junctions, browser downloads or the developer tree.
        shutil.copytree(source, tools / "desktop/node_modules" / name)
    shutil.copyfile(archive, inputs / "product.zip")
    shutil.copyfile(manifest_path, inputs / "package-manifest.json")
    shutil.copyfile(ROOT / "scripts/check_clean_machine.ps1", folder / "Start-Qualification.ps1")
    write_new(folder / "kit-manifest.json", {
        "schema": "surge-clean-windows-kit-v1", "product_sha256": digest(inputs / "product.zip"),
        "package_manifest_sha256": digest(inputs / "package-manifest.json"),
        "bootstrap_sha256": digest(folder / "Start-Qualification.ps1"),
        "tool_files": tooling_inventory(tools), "playwright": version,
        "status": "prepared-not-qualified", "no_download_or_install_required": True,
    })
    (folder / "README.txt").write_text(
        "OFFLINE WINDOWS GUEST QUALIFICATION KIT\n\n"
        "This is developer validation tooling, not the Product distribution.\n"
        "Copy the entire folder into a freshly provisioned Windows x64 VM.\n"
        "No Unreal, Python, Node, package-manager or compiler installation is needed.\n"
        "The product's bundled Python and Electron supervise the tests; Playwright\n"
        "tooling is isolated here and is never copied into Product. No downloads occur.\n\n"
        "Create guest-provenance.json with exactly provisioning (fresh-vm or\n"
        "fresh-sandbox), image (Windows image/version), and created_utc (ISO8601 UTC).\n"
        "Run Start-Qualification.ps1 -Provenance <absolute-guest-provenance.json>.\n"
        "Use an ordinary non-elevated PowerShell session, sufficient graphics support,\n"
        "at least 12 GiB free disk space, and a short local output path. The default\n"
        "is a new folder under Public Documents/SQ. No existing profiles are used.\n"
        "Do not bypass Windows security prompts or change execution/security policy.\n"
        "If local policy blocks the script, use your organization's approved runner.\n\n"
        "A host with developer tools or a non-VM model is blocked as clean acceptance.\n"
        "-HostedSelfCheck validates the harness only; its report can never claim clean\n"
        "acceptance. Freshness provenance is an operator assertion, not attestation.\n"
        "Keep the entire output receipt folder with the original ZIP and its manifest.\n",
        encoding="utf-8")
    return {"status": "prepared-not-qualified", "folder": str(folder), "tool_files": len(tooling_inventory(tools)), "product_sha256": digest(archive)}


def run_guest(kit, bootstrap, output, provenance_path=None, hosted=False):
    kit, bootstrap, output = kit.resolve(strict=True), bootstrap.resolve(strict=True), output.resolve(strict=True)
    if not output.is_relative_to(output.parent) or output == kit or output.is_relative_to(kit):
        raise ValueError("Qualification output must be separate from the immutable kit")
    receipt = output / "clean-machine-report.json"
    if receipt.exists():
        raise ValueError("Qualification receipt already exists")
    began = time.monotonic()
    report = {"schema": SCHEMA, "status": "failed", "clean_machine_qualified": False,
              "mode": "hosted-self-check" if hosted else "clean-windows-guest",
              "created_utc": datetime.now(timezone.utc).isoformat(), "steps": [],
              "limits": ["Operator-declared fresh provisioning is not cryptographic attestation",
                         "Absence checks cover PATH, installed-product registration and known engine roots, not an exhaustive disk scan",
                         "Automated practice controls are not human or unfamiliar-user acceptance"]}
    try:
        spec = read_json(kit / "kit-manifest.json")
        if spec.get("schema") != "surge-clean-windows-kit-v1":
            raise ValueError("Unexpected kit manifest")
        if (digest(kit / "inputs/product.zip") != spec["product_sha256"]
                or digest(kit / "inputs/package-manifest.json") != spec["package_manifest_sha256"]
                or digest(kit / "Start-Qualification.ps1") != spec["bootstrap_sha256"]
                or tooling_inventory(kit / "tools") != spec["tool_files"]):
            raise ValueError("Qualification kit bytes changed")
        report["product_sha256"] = spec["product_sha256"]
        report["tooling_manifest_sha256"] = digest(kit / "kit-manifest.json")
        report["environment"] = environment_probe()
        provenance = read_json(provenance_path, 4096) if provenance_path else None
        report["provisioning"] = provenance
        issues = guest_preconditions(report["environment"], provenance)
        report["clean_precondition_issues"] = issues
        if issues and not hosted:
            report["status"] = "blocked"
            return report
        manifest = read_json(kit / "inputs/package-manifest.json")
        consumer.verify_payload(bootstrap, manifest)
        expected_python = bootstrap / "resources/python/python.exe"
        if Path(sys.executable).resolve() != expected_python.resolve(strict=True):
            raise ValueError("Qualification must use the product's bundled Python")
        report["python_executable"] = str(Path(sys.executable))
        env = dict(os.environ)
        env["ELECTRON_RUN_AS_NODE"] = "1"
        env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
        for key in ("NODE_PATH", "NODE_OPTIONS", "PYTHONPATH", "PYTHONHOME"):
            env.pop(key, None)
        electron = bootstrap / "Surge.exe"
        # Electron's Node mode runs only the supervisor. Existing consumer harnesses
        # pass a separate restricted environment without this flag to the real app.
        probe = subprocess.run([str(electron), "-e", "const p=require('./desktop/node_modules/playwright');if(!p._electron)process.exit(1);console.log(JSON.stringify({node:process.versions.node,electron:process.versions.electron}))"],
                               cwd=kit / "tools", env=env, capture_output=True, timeout=20,
                               check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        report["supervisor_runtime"] = json.loads(probe.stdout.decode("utf-8-sig"))
        for name, command, relative in (
            ("gameplay-to-report", isolated_script_command(expected_python, kit / "tools/scripts/check_survive_package.py", "--archive", str(kit / "inputs/product.zip"), "--manifest", str(kit / "inputs/package-manifest.json"), "--node", str(electron), "--output-root", str(output / "s")), "s/consumer-*/report.json"),
            ("original-import-native", isolated_script_command(expected_python, kit / "tools/scripts/check_windows_package.py", "--package", str(kit / "inputs/product.zip"), "--manifest", str(kit / "inputs/package-manifest.json"), "--node", str(electron), "--output-root", str(output / "n")), "n/windows-consumer-*/artifacts/report.json"),
        ):
            remaining = TOTAL_SECONDS - (time.monotonic() - began)
            exit_code = run_consumer(command, name=name, kit=kit, output=output, env=env, remaining=remaining)
            reports = list(output.glob(relative))
            if exit_code != 0 or len(reports) != 1 or read_json(reports[0])["status"] != "passed":
                raise ValueError(name + " did not pass; inspect retained consumer receipt")
            identities = list(reports[0].parent.rglob("actual-processes.json"))
            if len(identities) != (2 if name == "gameplay-to-report" else 3):
                raise ValueError("Expected observed process identities for every application launch")
            for identity_path in identities:
                identity = read_json(identity_path)
                if any(identity.get(kind, {}).get("token_elevated") is not False for kind in ("main", "worker")):
                    raise ValueError("Application/backend did not use non-elevated tokens")
            report["steps"].append({"name": name, "status": "passed", "receipt": str(reports[0].relative_to(output)), "sha256": digest(reports[0])})
        consumer.verify_payload(bootstrap, manifest)
        if tooling_inventory(kit / "tools") != spec["tool_files"]:
            raise ValueError("Qualification tooling changed during acceptance")
        report.update(status="hosted-passed" if hosted else "passed", clean_machine_qualified=not hosted)
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - began, 3)
        write_new(receipt, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe")
    probe.add_argument("--output", type=Path, required=True)
    prepare_cmd = commands.add_parser("prepare")
    prepare_cmd.add_argument("--archive", type=Path, required=True)
    prepare_cmd.add_argument("--manifest", type=Path, required=True)
    prepare_cmd.add_argument("--output-root", type=Path, required=True)
    prepare_cmd.add_argument("--playwright", type=Path, default=ROOT / "desktop/node_modules/playwright")
    guest = commands.add_parser("guest")
    guest.add_argument("--kit", type=Path, required=True)
    guest.add_argument("--bootstrap", type=Path, required=True)
    guest.add_argument("--output", type=Path, required=True)
    guest.add_argument("--provenance", type=Path)
    guest.add_argument("--hosted-self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "probe":
        result = environment_probe()
        write_new(args.output, result)
    elif args.command == "prepare":
        result = prepare(args.archive, args.manifest, args.output_root, args.playwright)
    else:
        result = run_guest(args.kit, args.bootstrap, args.output, args.provenance, args.hosted_self_check)
    print(json.dumps(result))
    return 0 if args.command != "guest" or result["status"] in {"passed", "hosted-passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

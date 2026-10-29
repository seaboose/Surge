"""Locate installed x64 C++ headers/libraries without assuming a VS edition."""

import os
from pathlib import Path
import re
import subprocess


def newest_complete(folder, required):
    versions = sorted(
        (p for p in folder.iterdir() if p.is_dir() and re.fullmatch(r"\d+(?:\.\d+)*", p.name)),
        key=lambda p: tuple(map(int, p.name.split("."))),
        reverse=True,
    ) if folder.is_dir() else []
    for version in versions:
        if all((version / item).is_file() for item in required):
            return version
    raise RuntimeError("No complete x64 toolchain in " + str(folder))


def discover_windows_toolchain(program_files_x86=None, run=subprocess.run):
    base = Path(program_files_x86 or os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    locator = base / "Microsoft Visual Studio/Installer/vswhere.exe"
    if locator.is_file():
        result = run(
            [str(locator), "-latest", "-products", "*", "-requires",
             "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(paths) != 1 or not Path(paths[0]).is_absolute():
            raise RuntimeError("vswhere did not identify one installed C++ toolchain")
        installation = Path(paths[0])
    else:
        # Preserve compatibility with the original documented local installation.
        installation = base / "Microsoft Visual Studio/2022/BuildTools"
    vc = newest_complete(installation / "VC/Tools/MSVC", ("include/vector", "lib/x64/libcmt.lib"))
    sdk = base / "Windows Kits/10"
    sdk_versions = sorted(
        (p for p in (sdk / "Lib").iterdir() if p.is_dir() and re.fullmatch(r"\d+(?:\.\d+)*", p.name)),
        key=lambda p: tuple(map(int, p.name.split("."))), reverse=True,
    ) if (sdk / "Lib").is_dir() else []
    for version in sdk_versions:
        required = [version / "ucrt/x64/ucrt.lib", version / "um/x64/kernel32.lib",
                    sdk / "Include" / version.name / "ucrt/stdio.h",
                    sdk / "Include" / version.name / "shared/sdkddkver.h",
                    sdk / "Include" / version.name / "um/Windows.h"]
        if all(path.is_file() for path in required):
            return vc, sdk, version.name
    raise RuntimeError("No complete x64 Windows SDK")

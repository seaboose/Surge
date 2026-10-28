"""Save a verified integration+Unreal source recovery archive without Git changes."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "unreal/SurgeMovementLab"


def main():
    spec = importlib.util.spec_from_file_location("survive_archive_inputs", LAB / "scripts/save_source_archive.py")
    lab_archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab_archive)
    selected = set(lab_archive.selected_files())
    selected.update(ROOT.glob("*.py"))
    selected.update((ROOT / "desktop").glob("*.cjs"))
    selected.update(path for path in (ROOT / "desktop/src").rglob("*") if path.is_file())
    selected.update(ROOT / name for name in (
        "README.md", "Start-Surge.cmd", "Start-Surge.ps1", ".gitignore",
        "desktop/package.json", "desktop/pnpm-lock.yaml",
        "docs/survive-study.md", "docs/survive-implementation-review.md",
        "docs/survive-investigations.md",
        "docs/survive-workflow.md",
        "docs/code-map.md", "docs/runtime-release-scope.md",
        "docs/standalone-demo.md",
        "scripts/code_inventory.py",
        "scripts/check_survive_package.py", "scripts/survive_package.py",
        "scripts/check_windows_package.py", "scripts/windows_owned_processes.py",
        "scripts/windows-package-lock.json",
        "scripts/survive_study.py", "scripts/check_survive_live.py",
        "scripts/check_survive_regression.py", "scripts/save_survive_workspace.py",
        "scripts/release_files.py", "scripts/build_windows_package.py",
    ))
    if len(selected) > 2000:
        raise ValueError("Unexpected archive inventory")
    files = {}
    for path in sorted(selected):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Source archive cannot follow links or missing inputs: " + str(path))
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    if sum(map(len, files.values())) > 32 * 1024 * 1024:
        raise ValueError("Source archive exceeds reviewed size")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "verification" / ("survive-source-checkpoint-" + stamp + "-" + uuid.uuid4().hex[:8])
    output.mkdir(exist_ok=False)
    archive = output / "Surge-Survive-source.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as target:
        for name, raw in files.items():
            target.writestr(name, raw)
    with zipfile.ZipFile(archive) as saved:
        if saved.testzip() is not None or set(saved.namelist()) != set(files):
            raise ValueError("Source archive inventory/CRC failed")
        for name, raw in files.items():
            if saved.read(name) != raw or (ROOT / name).read_bytes() != raw:
                raise ValueError("Source changed while saving: " + name)
    manifest = {
        "schema": "surge-survive-source-checkpoint-v1", "created_utc": stamp,
        "archive": archive.name, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        "files": len(files), "verified_exact_bytes_and_crc": True,
        "scope": "Integration and Unreal source recovery only. No compiled game, engine, installed dependencies, personal recordings or previous backups. Existing runtime evidence remains in its original folders.",
    }
    with (output / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    print(json.dumps({"archive": str(archive), "files": len(files), "sha256": manifest["archive_sha256"]}))


if __name__ == "__main__":
    main()

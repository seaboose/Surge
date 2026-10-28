"""Create and verify a new source-only recovery ZIP; never overwrite earlier saves."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def selected_files():
    paths = set()
    for name in ("Source", "Config", "portable", "scripts", "third_party"):
        paths.update(p for p in (ROOT / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for directory, suffixes in (("telemetry", {".py", ".html", ".json"}),
                                ("profiles", {".json"})):
        paths.update(p for p in (ROOT / directory).iterdir() if p.is_file() and p.suffix in suffixes)
    paths.update(p for p in (ROOT / "docs").rglob("*")
                 if p.is_file() and p.suffix in {".md", ".json", ".py", ".cjs", ".html"})
    paths.update(p for p in ROOT.iterdir() if p.is_file() and
                 (p.suffix in {".cmd", ".uproject"} or p.name in {"README.md", "CONTINUE-HERE.md", ".gitignore"}))
    checkpoints = sorted((ROOT / "checkpoints").glob("*.json"))
    if checkpoints:
        paths.add(checkpoints[-1])
    selected = sorted(paths)
    if not selected or len(selected) > 2000:
        raise ValueError("Unexpected source file count")
    for path in selected:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Source archive cannot follow external links")
    return selected


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    files = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in selected_files()}
    if sum(map(len, files.values())) > 32 * 1024 * 1024:
        raise ValueError("Source snapshot exceeds32MiB; review selection")
    now = datetime.now(timezone.utc)
    output = ROOT / "Saved" / "Verification" / ("source-checkpoint-" + now.strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "Survive-source.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as target:
        for name, raw in files.items():
            target.writestr(name, raw)
    with zipfile.ZipFile(archive) as saved:
        if saved.testzip() is not None or set(saved.namelist()) != set(files):
            raise ValueError("Archive inventory/CRC verification failed")
        for name, raw in files.items():
            if saved.read(name) != raw:
                raise ValueError("Archive bytes differ from snapshot: " + name)
    after = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in selected_files()}
    hashes = {name: sha(raw) for name, raw in files.items()}
    if after != hashes:
        raise ValueError("Sources changed during save; incomplete archive retained without manifest")
    manifest = {"schema": "survive-source-archive-v1", "created_utc": now.isoformat(),
                "archive": archive.name, "archive_sha256": sha(archive.read_bytes()),
                "files": len(files), "source_bytes": sum(map(len, files.values())),
                "files_sha256": hashes, "reopened_exact_bytes_and_crc_verified": True,
                "limits": "Source only. Excludes engine/toolchains, Binaries, Intermediate, runtime captures/reports and downloaded calibration media. Existing local runtime evidence remains in Saved/Verification and telemetry/local."}
    with (output / "manifest.json").open("x", encoding="utf-8") as target:
        json.dump(manifest, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps({"directory": str(output), "files": len(files), "archive_sha256": manifest["archive_sha256"],
                      "reopened_exact_bytes_and_crc_verified": True}))


if __name__ == "__main__":
    main()

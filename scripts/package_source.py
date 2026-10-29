"""Create a source zip and manifest with published evidence, excluding local captures."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from release_files import ROOT, source_files
import check_release  # Refuse packaging when the source checks fail.

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output-root", type=Path, default=ROOT / "dist")
args = parser.parse_args()
destination = args.output_root.resolve()
destination.mkdir(parents=True, exist_ok=True)
manifest = {}
archive = destination / "surge-source.zip"
if archive.exists() or (destination / "source-manifest.json").exists():
    raise SystemExit("Source package already exists; choose a new --output-root.")
with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as output:
    for path in source_files():
        relative = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        manifest[relative] = hashlib.sha256(raw).hexdigest()
        output.writestr("Surge/" + relative, raw)
with zipfile.ZipFile(archive) as saved:
    if saved.testzip() is not None or len(saved.namelist()) != len(manifest):
        raise ValueError("Source package CRC/inventory verification failed")
    for name, expected in manifest.items():
        if (hashlib.sha256(saved.read("Surge/" + name)).hexdigest() != expected
                or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected):
            raise ValueError("Source changed during packaging: " + name)
(destination / "source-manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)
print(f"Packaged {len(manifest)} source files in {archive.name}.")

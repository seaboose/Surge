"""Create a source zip and a SHA-256 manifest; never include local evidence."""

import hashlib
import json
import zipfile
from release_files import ROOT, source_files
import check_release  # Refuse packaging when the source checks fail.

destination = ROOT / "dist"
destination.mkdir(exist_ok=True)
manifest = {}
archive = destination / "surge-source.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
    for path in source_files():
        relative = path.relative_to(ROOT).as_posix()
        raw = path.read_bytes()
        manifest[relative] = hashlib.sha256(raw).hexdigest()
        output.writestr("Surge/" + relative, raw)
(destination / "source-manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)
print(f"Packaged {len(manifest)} source files in {archive.name}.")

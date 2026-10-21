"""List source-package files without local environments, evidence, or test output."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "rt-iot2022",
    "temporary-test-files",
    "electron",
}


def source_files(root=ROOT):
    for folder, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in EXCLUDED)
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(root)
            if (
                path.suffix in {".pyc", ".log", ".zip"}
                or name.startswith(".env")
                or name == ".surge-ui.json"
            ):
                continue
            if relative.parts[0] == "verification" and path.suffix != ".py":
                continue
            if name.endswith(".case.json") and relative.parts[:2] != ("tests", "fixtures"):
                continue
            yield path

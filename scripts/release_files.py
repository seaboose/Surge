"""List source-package files, including the published evaluation archive only."""

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
    "build",
    "build-manifest",
    "build-asan",
    "captures",
    "work",
}


def source_files(root=ROOT):
    for folder, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in EXCLUDED)
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(root)
            if relative.parts[:2] == ("verification", "qualification"):
                continue
            if (
                (
                    path.suffix in {".pyc", ".log", ".zip"}
                    and relative.as_posix() != "evidence/surge-evaluation-evidence.zip"
                )
                or name.startswith(".env")
                or name == ".surge-ui.json"
                or relative.as_posix() == "native/baselines.json"
            ):
                continue
            if relative.parts[0] == "verification" and path.suffix != ".py":
                continue
            if name.endswith(".case.json") and relative.parts[:2] not in (
                ("tests", "fixtures"),
                ("demos", "native"),
            ):
                continue
            yield path

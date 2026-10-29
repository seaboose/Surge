"""List source-package files, including the published evaluation archive only."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".git",
    ".codex",
    ".agents",
    ".aws",
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
    "output",
    "_Recovery",
    "verification",
}


def source_files(root=ROOT):
    for folder, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in EXCLUDED)
        relative_folder = Path(folder).relative_to(root).parts
        if relative_folder == ("unreal", "SurgeMovementLab"):
            directories[:] = [name for name in directories if name not in {
                "Saved", "Binaries", "Intermediate", "DerivedDataCache", ".vs", "checkpoints"
            }]
        if relative_folder == ("unreal", "SurgeMovementLab", "telemetry"):
            directories[:] = [name for name in directories if name != "local"]
        if relative_folder == ("unreal", "SurgeMovementLab", "profiles"):
            directories[:] = [name for name in directories if name != "evidence"]
        for name in sorted(files):
            path = Path(folder) / name
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                continue
            relative = path.relative_to(root)
            if relative.parts[:2] == ("verification", "qualification"):
                continue
            if (
                (
                    path.suffix in {".pyc", ".log", ".zip"}
                    and relative.as_posix() != "evidence/surge-evaluation-evidence.zip"
                )
                or name.startswith(".env")
                or name.startswith("RECOVERY-")
                or name == ".git"  # Linked worktrees store metadata in a file.
                or name == "AGENTS.md"  # Local authoring instructions are not product source.
                or name == ".surge-ui.json"
                or relative.as_posix() == "native/baselines.json"
            ):
                continue
            # Local video-inspection helpers contain machine-specific paths;
            # calibration reports and reproducible analysis stay in the source kit.
            if (relative.parts[:4] == ("unreal", "SurgeMovementLab", "docs", "calibration")
                    and name.startswith("inspect-") and path.suffix == ".cjs"):
                continue
            if relative.parts[0] == "verification" and path.suffix != ".py":
                continue
            if name.endswith(".case.json") and relative.parts[:2] not in (
                ("tests", "fixtures"),
                ("demos", "native"),
            ):
                continue
            yield path

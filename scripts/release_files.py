"""Publish only reviewed files; work in both Git checkouts and source exports."""

from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "scripts/source-files.txt"


def reviewed_file(root, name):
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or relative.as_posix() != name
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or any(character in name for character in "\\:\x00")):
        raise ValueError(f"Invalid source-package path: {name!r}")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError(f"Source-package links are not allowed: {name}")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Reviewed source file is missing or outside the root: {name}")
    return path


def source_files(root=ROOT):
    requested_root = Path(root)
    root = requested_root.resolve()
    manifest = reviewed_file(root, MANIFEST)
    if manifest.stat().st_size > 512 * 1024:
        raise ValueError("Source-package manifest exceeds its size limit")
    names = [line.strip() for line in manifest.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(names) != len({name.casefold() for name in names}):
        raise ValueError("Duplicate source-package path")
    if MANIFEST not in names:
        raise ValueError("Source-package manifest must include itself")
    # Validate canonical paths before writing, but preserve the caller's root
    # spelling so relative_to(root) also works with Windows short-path aliases.
    names.sort()
    for name in names:
        reviewed_file(root, name)
    return iter([requested_root / name for name in names])

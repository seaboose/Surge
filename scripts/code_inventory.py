"""Bounded inventory of maintained first-party source, not installed dependencies.

Counts physical text lines, including comments and blanks. It never opens captures,
recovery material, generated output or dependency trees. The JSON is a learning and
release-scope aid, not proof that a packaged application works.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
# Capability observations below are an audit of these exact builder bytes, not
# an inference that remains valid after future packaging edits.
REVIEWED_BUILDER_SHA256 = "2cdc819db30b0c57cc0ce53a41aec9a499198871741a5b3368eceaa9392358ad"
REVIEWED_HELPER_SHA256 = "4d7ee0c01b2de16d5b61f6baf943d9bc6fee8f4bba526677fc16bbb2bc1a5c73"
MAX_FILES = 5000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TEXT_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 12
EXCLUDED_NAMES = frozenset({
    ".git", ".venv", ".codex", ".agents", ".aws", ".vs", "__pycache__",
    "node_modules", "dist", "build", "build-asan", "build-manifest", "work",
    "binaries", "intermediate", "deriveddatacache", "saved", "captures",
    "verification", "_recovery", "third_party", "rt-iot2022", "checkpoints", "output",
})
PRIVATE_PREFIXES = (
    ("unreal", "SurgeMovementLab", "telemetry", "local"),
    ("unreal", "SurgeMovementLab", "profiles", "evidence"),
)
CODE_SUFFIXES = frozenset({".py", ".js", ".jsx", ".mjs", ".cjs", ".cpp", ".h",
                           ".hpp", ".asm", ".cs", ".ps1", ".cmd", ".html", ".css"})
DOCUMENT_SUFFIXES = frozenset({".md", ".txt"})
CONFIG_SUFFIXES = frozenset({".json", ".ini", ".toml", ".yaml", ".yml", ".def",
                            ".uproject", ".csv", ".tsv"})
ADAPTERS = frozenset({"prepare.py", "prepare_v2.py", "prepare_v3.py", "audit_v3.py"})
NATIVE_RUNTIME = frozenset({"owned_app.cpp", "code_range_collector.cpp", "code_range_collector.hpp",
                            "code_range_pe.hpp", "lab_module.cpp", "lab_manifest.hpp", "lab_code_v2.asm"})
ALTERNATE_ROOT = frozenset({"app.py", "comparison_view.py", "Start-Surge-Legacy.cmd",
                            "Start-Surge-Legacy.ps1", "Start-Workbench.cmd", "Start-Workbench.ps1"})


def _regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("Inventory refuses linked or nonregular source files")
    return info


def package_allowlists(root):
    """Read literal package declarations without importing/executing the builder."""
    path = root / "scripts/build_windows_package.py"
    if _regular(path).st_size > MAX_FILE_BYTES:
        raise ValueError("Package declaration exceeds inventory bound")
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Package declaration exceeds inventory bound")
    tree = ast.parse(raw.decode("utf-8-sig"))
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"BACKEND", "DESKTOP"}:
                    value = ast.literal_eval(node.value)
                    if not isinstance(value, tuple) or not all(isinstance(x, str) for x in value):
                        raise ValueError("Package allowlists must remain literal string tuples")
                    result[target.id] = value
    if set(result) != {"BACKEND", "DESKTOP"}:
        raise ValueError("Current package allowlists were not found")
    return result


def classify(relative, allowlists):
    parts = relative.parts
    name = relative.name
    suffix = relative.suffix.lower()
    if suffix in DOCUMENT_SUFFIXES or name in {"LICENSE", "NOTICE"}:
        return "documentation"
    if suffix in CONFIG_SUFFIXES or name.startswith(".git"):
        return "configuration_and_assets"
    if suffix not in CODE_SUFFIXES and name != "CMakeLists.txt":
        return None
    if (name.startswith("test_") or ".test." in name or "_tests." in name
            or parts[0] == "tests" or name in {"SurviveAutomationTests.cpp", "survive_sim_checks.cpp",
                                               "collector_smoke.cpp", "parity.cjs", "evaluation.cjs"}):
        return "tests"
    if len(parts) == 1 and name in ALTERNATE_ROOT:
        return "alternate_interfaces"
    if len(parts) == 1 and name in {item + ".py" for item in allowlists["BACKEND"]}:
        return "backend_runtime_source"
    if parts[:2] == ("desktop", "src") or (parts[0] == "desktop" and name in allowlists["DESKTOP"]):
        return "desktop_runtime_source"
    if parts[:3] == ("unreal", "SurgeMovementLab", "Source"):
        return "development_tools" if suffix == ".cs" else "survive_game_runtime_source"
    if parts[:3] == ("unreal", "SurgeMovementLab", "telemetry") and name in ADAPTERS:
        return "survive_analysis_runtime_source"
    if parts[0] == "native" and name in NATIVE_RUNTIME:
        return "native_demo_runtime_source"
    if parts[0] in {"scripts", "benchmarks", "desktop", "native", "unreal"} or name in {
            "Start-Surge.cmd", "Start-Surge.ps1", "Setup-Surge.ps1"}:
        return "development_tools"
    return "other_first_party_code"


def inventory(root=ROOT):
    root = Path(root).resolve()
    allowlists = package_allowlists(root)
    files = []
    excluded = []
    total_bytes = 0
    seen = 0
    for folder, directories, names in os.walk(root, followlinks=False):
        relative_folder = Path(folder).relative_to(root)
        if len(relative_folder.parts) > MAX_DEPTH:
            raise ValueError("Inventory depth exceeds bound")
        kept = []
        for name in sorted(directories):
            relative = relative_folder / name
            path = root / relative
            info = path.lstat()
            # Telemetry tests create short-lived tempfile trees beside the adapters.
            telemetry_temp = (relative_folder.parts == ("unreal", "SurgeMovementLab", "telemetry")
                              and name.startswith("tmp"))
            if (name.casefold() in EXCLUDED_NAMES or name.startswith(".")
                    or telemetry_temp
                    or any(relative.parts[:len(prefix)] == prefix for prefix in PRIVATE_PREFIXES)
                    or path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400):
                excluded.append(relative.as_posix())
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            seen += 1
            if seen > MAX_FILES:
                raise ValueError("Inventory entry count exceeds bound")
            if (name.startswith(".env") or name.startswith("RECOVERY-") or name.endswith(".case.json")
                    or name == ".surge-ui.json"):
                continue
            relative = relative_folder / name
            category = classify(relative, allowlists)
            if category is None:
                continue
            path = root / relative
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                excluded.append(relative.as_posix())
                continue
            _regular(path)
            if info.st_size > MAX_FILE_BYTES:
                raise ValueError("Source file exceeds inventory bound: " + relative.as_posix())
            # Asset/document counts are useful, but source learning metrics never
            # include their data rows and do not need their contents.
            code = category not in {"documentation", "configuration_and_assets"}
            item = {"path": relative.as_posix(), "category": category, "bytes": info.st_size,
                    "physical_lines": None, "sha256": None}
            if code:
                total_bytes += info.st_size
                if total_bytes > MAX_TEXT_BYTES:
                    raise ValueError("Inventory source-byte bound exceeded")
                with path.open("rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise ValueError("Source changed while opening inventory input")
                    raw = stream.read(MAX_FILE_BYTES + 1)
                    after = os.fstat(stream.fileno())
                    if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError("Source changed while reading inventory input")
                if len(raw) > MAX_FILE_BYTES:
                    raise ValueError("Source grew beyond inventory bound")
                if len(raw) != opened.st_size:
                    raise ValueError("Source size changed during inventory")
                text = raw.decode("utf-8-sig")
                item.update(bytes=len(raw), physical_lines=len(text.splitlines()), sha256=hashlib.sha256(raw).hexdigest())
            files.append(item)
    categories = {}
    for category in sorted({f["category"] for f in files}):
        subset = [f for f in files if f["category"] == category]
        categories[category] = {"files": len(subset), "bytes": sum(f["bytes"] for f in subset),
                                "physical_lines": sum(f["physical_lines"] or 0 for f in subset)}
    runtime_names = [name for name in categories if name.endswith("runtime_source")]
    runtime = {key: sum(categories[name][key] for name in runtime_names)
               for key in ("files", "bytes", "physical_lines")}
    builder_sha = next(item["sha256"] for item in files if item["path"] == "scripts/build_windows_package.py")
    helper_sha = next((item["sha256"] for item in files if item["path"] == "scripts/survive_package.py"), None)
    reviewed_builder = builder_sha == REVIEWED_BUILDER_SHA256 and helper_sha == REVIEWED_HELPER_SHA256
    return {
        "schema": "surge-code-inventory-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Maintained first-party source selected by package declarations and documented path categories. Physical lines include blanks/comments. Generated, private and third-party trees were not traversed; this is not a total-workspace size or complete import-closure proof.",
        "limits": {"entries": MAX_FILES, "depth": MAX_DEPTH, "file_bytes": MAX_FILE_BYTES,
                   "source_bytes": MAX_TEXT_BYTES},
        "runtime_source_total": runtime, "categories": categories,
        "package_declarations": {key: list(value) for key, value in allowlists.items()},
        "release_capabilities": {
            "audit_date": "2026-10-26", "reviewed_builder_sha256": REVIEWED_BUILDER_SHA256,
            "reviewed_helper_sha256": REVIEWED_HELPER_SHA256, "current_helper_sha256": helper_sha,
            "current_builder_sha256": builder_sha, "reviewed_snapshot_matches": reviewed_builder,
            "scope": "Copy declarations describe both reviewed builder and helper bytes. If either hash differs, re-audit packaging. A declaration does not qualify a built package.",
            "surge_and_native_demo": {"declared_payload": True if reviewed_builder else None,
                "qualified_for_this_snapshot": False, "note": "Build/acceptance qualification is separate from this read-only inventory."},
            "full_survive_workflow": {"declared_payload": True if reviewed_builder else None,
                "package_mode": "Optional --survive-build; native-only packages do not include the game.",
                "qualified_for_this_snapshot": False,
                "reviewed_runtime_inputs": ["unreal/SurgeMovementLab/telemetry/" + name for name in sorted(ADAPTERS)] +
                    ["unreal/SurgeMovementLab/telemetry/survive-policy.json", "unreal/SurgeMovementLab/profiles/*.json"],
                "game_input": "A separately cooked standalone game with an explicitly verified bounded file manifest.",
                "qualification": "Use the matching extracted gameplay-to-report acceptance report for an exact ZIP/hash, not this inventory."},
        },
        "excluded_trees_not_traversed": sorted(excluded), "files": files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a new JSON report; existing files are never replaced")
    args = parser.parse_args()
    result = inventory()
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
        print(json.dumps({"output": str(args.output), "runtime_source_total": result["runtime_source_total"],
                          "categories": result["categories"]}))


if __name__ == "__main__":
    main()

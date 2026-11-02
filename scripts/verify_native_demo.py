"""Replay the public native demo without a compiler, network, or running collector."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine
import native_integrity


def verify(folder=ROOT / "demos/native"):
    expected = engine.decode((folder / "expected.json").read_text(encoding="utf-8"))
    if expected.get("schema") != "surge-native-demo-v1" or len(expected["cases"]) != 5:
        raise ValueError("Expected the five published demo cases.")
    seen = set()
    for spec in expected["cases"]:
        name = spec["file"]
        if not re.fullmatch(r"[a-z-]+\.case\.json", name) or name in seen:
            raise ValueError("Invalid or duplicate demo filename.")
        seen.add(name)
        raw = (folder / name).read_bytes()
        if len(raw) > 256 * 1024 or engine.sha(raw) != spec["sha256"]:
            raise ValueError(f"Demo file fingerprint differs: {name}")
        data, reference, config, result = engine.open_case(folder / name)
        if reference is not None or native_integrity.default_policy(data) != config:
            raise ValueError(f"Demo policy differs from native mapping: {name}")
        if [r["status"] for r in result["records"]] != spec["outcomes"]:
            raise ValueError(f"Recomputed outcomes differ: {name}")
        if [r["coverage_read_ranges"] for r in data.rows] != spec["readable_ranges"]:
            raise ValueError(f"Coverage differs: {name}")
        for row in data.rows:
            if (
                row["pid"] != 1
                or row["process_started"] != "1"
                or row["session_id"] != "demo-" + name.removesuffix(".case.json")
                or row["module_path"] not in ("lab_module.dll", "lab_module_v2.dll")
                or not row["captured_at"].startswith("2026-01-01T")
                or row["collection_ms"] != 0
                or "scenario" in row
            ):
                raise ValueError(f"Demo identity or timing was not sanitized: {name}")
        if re.search(r"(?i)(?:[a-z]:[/\\]|/users/|/home/)", raw.decode()):
            raise ValueError(f"Demo contains an absolute local path: {name}")
        print(
            f"{name}: "
            + ", ".join(
                f"{result['summary'][s]} {s}" for s in ("No finding", "Review", "Unknown")
            )
        )
    print(
        "PASS: five cases replay with expected outcomes and normalized identities. No local baseline was used or changed."
    )


if __name__ == "__main__":
    verify()

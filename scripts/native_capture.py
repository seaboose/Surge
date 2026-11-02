"""Explicit approval and capture for the fixed, owned Windows fixture only."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine
import native_integrity as native


def collect(build, scenario):
    executable = ROOT / "native/build/surge_fixture.exe"
    with tempfile.TemporaryDirectory(prefix="surge-native-") as folder:
        completed = subprocess.run(
            [str(executable), "--build", build, "--scenario", scenario],
            cwd=folder,
            capture_output=True,
            timeout=15,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if completed.returncode:
            raise ValueError(
                completed.stderr.decode("utf-8", errors="replace")[:1000].strip()
                or "Collector failed"
            )
        with (Path(folder) / "exported_code_audit.json").open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Collector output exceeds its bound.")
        capture = engine.decode(raw.decode("utf-8"))
        native.validate_capture(capture)
        return capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["approve", "capture"])
    parser.add_argument("--build", choices=["v1", "v2"], default="v1")
    parser.add_argument(
        "--scenario",
        choices=["clean", "memory-change", "secondary-change", "unreadable", "unloaded"],
        default="clean",
    )
    parser.add_argument("--baselines", type=Path, default=ROOT / "native/baselines.json")
    parser.add_argument("--reason")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "approve" and (not args.reason or args.scenario != "clean"):
        parser.error("Approval requires --reason and a clean scenario.")
    if args.action == "capture" and not args.output:
        parser.error("Capture requires --output; existing files are never replaced.")
    registry = {"schema": native.BASELINE_SCHEMA, "entries": []}
    if args.baselines.exists():
        if args.baselines.stat().st_size > 1024 * 1024:
            raise ValueError("Baseline registry is too large.")
        registry = engine.decode(args.baselines.read_text(encoding="utf-8"))
    native.validate_baselines(registry)
    try:
        capture = collect(args.build, args.scenario)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        if args.action == "approve":
            raise ValueError("Collection failed; no baseline was approved.") from error
        rows = [
            dict(
                schema=native.SCHEMA,
                event_id="collection-failed",
                session_id=f"failed-{os.getpid()}",
                captured_at=datetime.now(timezone.utc).isoformat(),
                pid=None,
                baseline_approved=None,
                memory_matches=None,
                protection_matches=None,
                memory_status="failed",
                collection_error=str(error)[:1000],
                baseline_sha256=native.digest(registry),
            )
        ]
    else:
        if args.action == "approve":
            registry = native.approve(capture, registry, args.reason)
            args.baselines.parent.mkdir(parents=True, exist_ok=True)
            # Keep an earlier registry until the complete replacement is ready.
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=args.baselines.parent, delete=False
            ) as stream:
                json.dump(registry, stream, indent=2)
                temp = Path(stream.name)
            try:
                os.replace(temp, args.baselines)
            finally:
                temp.unlink(missing_ok=True)
            print(f"Approved {args.build}; {len(registry['entries'])} baseline(s).")
            return
        rows = native.convert(capture, registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(engine.canonical(row) + "\n")
    print(f"Saved {len(rows)} observation(s). Import {args.output.name} into Surge, then Analyze.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

"""Bounded owned-fixture desktop latency, responsiveness and sampled memory check."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.test_native_stream import resources


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sources():
    names = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8"
    ).splitlines()
    names += [
        "scripts/measure_supported_limits.py",
        "desktop/performance-limits.cjs",
        "docs/supported-limits-performance.md",
    ]
    names += [
        p.relative_to(ROOT).as_posix() for p in (ROOT / "desktop/dist").rglob("*") if p.is_file()
    ]
    return {
        name: digest((ROOT / name).read_bytes())
        for name in sorted(set(names))
        if (ROOT / name).is_file()
        and (
            (ROOT / name).suffix in (".py", ".cjs", ".jsx", ".css")
            or name == "docs/supported-limits-performance.md"
            or name.startswith("desktop/dist/")
        )
    }


def main():
    folder = ROOT / "verification/qualification" / f"supported-limits-{uuid.uuid4().hex[:12]}"
    folder.mkdir(parents=True)
    (folder / "acceptance.md").write_bytes(
        (ROOT / "docs/supported-limits-performance.md").read_bytes()
    )
    report = {
        "schema": "surge-supported-limits-v1",
        "passed": False,
        "bounds": {"wall_seconds": 300, "memory_bytes": 1024**3, "expected_scenarios": 4},
        "environment": {
            "windows": platform.platform(),
            "python": platform.python_version(),
            "logical_processors": os.cpu_count(),
        },
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "sources": sources(),
        "samples": [],
        "measurement_errors": [],
        "unrun": [
            f"{kind}-{repeat}"
            for repeat in (1, 2)
            for kind in ("representative", "combined-limits")
        ],
    }
    with (folder / "source-state.patch").open("wb") as patch:
        subprocess.run(
            ["git", "diff", "--", "*.py", "*.cjs", "*.jsx", "*.css"],
            cwd=ROOT,
            stdout=patch,
            check=True,
        )
    for name in ("desktop/performance-limits.cjs", "scripts/measure_supported_limits.py"):
        (folder / Path(name).name).write_bytes((ROOT / name).read_bytes())
    report["environment"]["node"] = subprocess.check_output(
        ["node", "--version"], text=True
    ).strip()
    report["environment"]["cpu"] = platform.processor()
    lines = queue.Queue()
    start = time.monotonic()
    child = None
    try:
        with (
            (folder / "stdout.jsonl").open("w", encoding="utf-8") as stdout,
            (folder / "stderr.log").open("w", encoding="utf-8") as stderr,
        ):
            child = subprocess.Popen(
                ["node", str(ROOT / "desktop/performance-limits.cjs"), str(folder)],
                cwd=ROOT / "desktop",
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                env={**os.environ, "SURGE_PYTHON": sys.executable},
            )

            def read():
                for line in child.stdout:
                    lines.put(line)
                lines.put(None)

            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            ended = False
            while not ended:
                if time.monotonic() - start > 300:
                    raise TimeoutError("300-second campaign deadline exceeded")
                try:
                    line = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    ended = True
                    continue
                stdout.write(line)
                stdout.flush()
                event = json.loads(line)
                if event.get("type") != "resources":
                    continue
                event["sampled_time_ms"] = time.time() * 1000
                event["readings"] = []
                for process in event.pop("processes"):
                    try:
                        event["readings"].append(
                            dict(process, **resources(SimpleNamespace(pid=process["pid"])))
                        )
                    except OSError as error:
                        report["measurement_errors"].append(str(error))
                event["private_bytes"] = sum(p["private_bytes"] for p in event["readings"])
                report["samples"].append(event)
            report["exit_code"] = child.wait(timeout=10)
            reader.join(timeout=2)
            child.stdout.close()
        report["desktop"] = json.loads((folder / "desktop.json").read_text(encoding="utf-8"))
        report["unrun"] = [
            name
            for name in report["unrun"]
            if name not in {s["name"] for s in report["desktop"]["scenarios"]}
        ]
        assert report["exit_code"] == 0 and report["desktop"]["passed"], "Desktop campaign failed"
        assert report["samples"], "No memory measurements"
        report["peak_sampled_private_bytes"] = max(s["private_bytes"] for s in report["samples"])
        assert (
            report["peak_sampled_private_bytes"] < 1024**3
        ), "Sampled private memory exceeded 1 GiB"
        assert not report["measurement_errors"], "Resource readings failed"
        assert sources() == report["sources"], "Measured source changed during campaign"
        report["passed"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if child and child.poll() is None:
            killed = subprocess.run(
                ["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True, text=True
            )
            report["owned_tree_termination"] = {
                "returncode": killed.returncode,
                "stdout": killed.stdout,
                "stderr": killed.stderr,
            }
            child.wait(timeout=10)
        if (folder / "desktop.json").is_file():
            report["desktop"] = json.loads((folder / "desktop.json").read_text(encoding="utf-8"))
            report["unrun"] = [
                name
                for name in report["unrun"]
                if name not in {s["name"] for s in report["desktop"]["scenarios"]}
            ]
    finally:
        report["seconds"] = time.monotonic() - start
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        manifest = [
            {
                "path": p.relative_to(folder).as_posix(),
                "bytes": p.stat().st_size,
                "sha256": digest(p.read_bytes()),
            }
            for p in sorted(folder.rglob("*"))
            if p.is_file()
        ]
        (folder / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "folder": str(folder),
                    "passed": report["passed"],
                    "seconds": report["seconds"],
                    "error": report.get("error"),
                }
            )
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

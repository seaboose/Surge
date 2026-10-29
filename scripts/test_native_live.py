"""Reproducible owned-fixture checks; no game processes or benchmark holdouts."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import desktop_worker
import engine
import native_integrity as native
from native_capture import collect


def run(output):
    capture_root = output
    output = output / ("run-" + uuid.uuid4().hex[:12])
    output.mkdir(parents=True, exist_ok=True)
    registry = native.approve(
        collect("v1", "clean"),
        dict(schema=native.BASELINE_SCHEMA, entries=[]),
        "Reviewed owned fixture build v1",
    )
    checks = []

    def check(name, capture, expected):
        rows = native.convert(capture, registry)
        path = output / (name + ".jsonl")
        path.write_text("\n".join(engine.canonical(row) for row in rows) + "\n", encoding="utf-8")
        workspace = desktop_worker.Workspace()
        workspace.dispatch("import", dict(role="current", path=str(path)))
        result = engine.analyze(workspace.current, None, workspace.config)
        statuses = [row["status"] for row in result["records"]]
        assert statuses == expected, (name, statuses, expected)
        assert len({r["event_id"] for r in rows}) == 6
        sample = [r for r in rows if r["phase"] == "sample"]
        read = 0 if name.endswith("unloaded") else 1 if name.endswith("unreadable") else 2
        assert all(
            r["coverage_expected_ranges"] == 2 and r["coverage_read_ranges"] == read for r in sample
        )
        assert all(
            r["coverage_compared_ranges"] == (0 if name == "v2-unapproved" else read)
            for r in sample
        )
        case = output / (name + ".case.json")
        # Exercise the public case format and deterministic replay too.
        engine.save_case(case, workspace.current, None, workspace.config, result)
        assert engine.open_case(case)[3] == result
        checks.append(dict(name=name, statuses=statuses, coverage=native.coverage(sample)))

    clean = ["No finding"] * 6
    check("v1-clean", collect("v1", "clean"), clean)
    check("v2-unapproved", collect("v2", "clean"), ["Review"] * 6)
    registry = native.approve(
        collect("v2", "clean"), registry, "Reviewed legitimate fixture update v2"
    )
    for build in ("v1", "v2"):
        check(build + "-approved", collect(build, "clean"), clean)
        check(
            build + "-memory-change",
            collect(build, "memory-change"),
            ["No finding", "No finding", "Review", "No finding", "No finding", "No finding"],
        )
        check(
            build + "-secondary-change",
            collect(build, "secondary-change"),
            ["No finding", "No finding", "No finding", "Review", "No finding", "No finding"],
        )
        for scenario in ("unreadable", "unloaded"):
            check(
                build + "-" + scenario,
                collect(build, scenario),
                [
                    "No finding",
                    "No finding",
                    "Unknown",
                    "Unknown" if scenario == "unloaded" else "No finding",
                    "No finding",
                    "No finding",
                ],
            )
    for n in range(3):
        check(f"restart-{n}", collect("v2", "clean"), clean)
    (output / "baselines.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    report = dict(scope="Owned Windows fixture, not real-cheat effectiveness", checks=checks)
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (capture_root / "latest.json").write_text(json.dumps({"folder": output.name}), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run(Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT / "native/captures")

"""Compare source replacement and soak runs without counting test launchers."""

import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).parent / "electron"
LABELS = ("retention-before", "retention-after-1", "retention-after-2")
runs = {}
for label in LABELS:
    report = json.loads((ROOT / f"memory-{label}.json").read_text())
    assert report["soak"] and not report["forcedGC"]
    assert report["investigationMinutes"] == 5
    samples = [
        json.loads(line)
        for line in (Path(report["folder"]) / "samples.jsonl").read_text().splitlines()
    ]
    phases = {}
    for stage in report["summary"]:
        rows = []
        for sample in samples:
            if sample["phase"] != stage["name"]:
                continue
            processes = [
                p
                for p in sample["processes"]
                if p["name"].lower() == "electron.exe" or p["name"].lower().startswith("python")
            ]
            assert processes and all(not p.get("error") for p in processes)
            rows.append(sum(p["private"] for p in processes))
        assert len(rows) >= 3
        phases[stage["name"]] = dict(
            settledPrivate=median(rows[-5:]),
            peakPrivate=max(rows),
            visibleDom=stage["dom"],
            domCounters=stage["counters"],
            settledPythonPrivate=stage["settledPythonPrivate"],
            mainHeap=stage["mainHeap"],
            elapsedMs=stage["elapsedMs"],
        )
    runs[label] = dict(
        phases=phases,
        peakPrivate=max(p["peakPrivate"] for p in phases.values()),
        investigationSteps=report["investigationSteps"],
        rawReport=f"memory-{label}.json",
    )

diagnostic = json.loads((ROOT / "memory-retention-leak-check.json").read_text())
assert diagnostic["leakCheck"] and diagnostic["forcedGC"] and not diagnostic["soak"]
survivors = [s for s in diagnostic["summary"] if s["name"].startswith("retained-small-")]
assert len(survivors) == 9
floor, final = survivors[1], survivors[-1]
assert final["counters"]["nodes"] <= floor["counters"]["nodes"] + 100
assert final["counters"]["jsEventListeners"] <= floor["counters"]["jsEventListeners"] + 50
assert final["liveHeap"]["usedSize"] <= floor["liveHeap"]["usedSize"] + 2 * 1048576
comparisons = {}
for phase in runs[LABELS[0]]["phases"]:
    before = runs[LABELS[0]]["phases"][phase]["settledPrivate"]
    after = [runs[label]["phases"][phase]["settledPrivate"] for label in LABELS[1:]]
    comparisons[phase] = dict(
        before=before,
        after=after,
        afterMedian=median(after),
        reductionPercent=100 * (1 - median(after) / before),
    )
summary = dict(
    builds=json.loads((ROOT / "retention-builds.json").read_text(encoding="utf-8-sig")),
    workload=dict(records=10000, fields=64, replacements=8, continuousInvestigationMinutes=5),
    method="One baseline and two optimized fresh profiles. Same input and scripted actions. "
    "100 ms Windows PrivateUsage samples for isolated Electron and Python processes; "
    "test cmd/conhost launchers excluded from all runs. Median of final five phase samples "
    "after an 800 ms pause; final small-source idle is ten seconds. No forced collection or trimming.",
    units="Bytes; divide by 1,048,576 for MiB. Private commitment, not physical resident RAM.",
    limitations="Local synthetic workloads; brief peaks can be missed. The observed window cannot "
    "establish multi-hour or multi-day leak freedom. Collection timing varies between runs. "
    "Investigation step counts differ with responsiveness; each uses five active minutes.",
    comparisons=comparisons,
    runs=runs,
    retainedObjectDiagnostic=dict(
        report="memory-retention-leak-check.json",
        method="Separate final-build run, with forced renderer collection after each small workspace. "
        "Excluded from ordinary memory comparisons. Compares cycle 1 with cycle 8.",
        initialCounters=floor["counters"],
        finalCounters=final["counters"],
        initialJSHeap=floor["liveHeap"]["usedSize"],
        finalJSHeap=final["liveHeap"]["usedSize"],
        tolerance=dict(nodes=100, listeners=50, jsHeapBytes=2 * 1048576),
    ),
)
(ROOT / "retention-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
for phase in ("import", "compare", "small-replacement", "cycle-small-8", "long-small-idle"):
    value = comparisons[phase]
    print(
        f'{phase}: {value["before"]/1048576:.1f} -> '
        f'{value["afterMedian"]/1048576:.1f} MiB ({value["reductionPercent"]:.1f}% lower)'
    )
for label, run in runs.items():
    small = [
        v["settledPrivate"] / 1048576
        for k, v in run["phases"].items()
        if k.startswith("cycle-small")
    ]
    long = [
        v["settledPrivate"] / 1048576
        for k, v in run["phases"].items()
        if k.startswith("long-minute")
    ]
    print(
        label,
        "small",
        [round(v, 1) for v in small],
        "minutes",
        [round(v, 1) for v in long],
        "steps",
        run["investigationSteps"],
    )
    final = run["phases"]["long-small-idle"]
    print(
        "peak MiB",
        round(run["peakPrivate"] / 1048576, 1),
        "final DOM counters",
        final["domCounters"],
        "final JS heap",
        final["visibleDom"]["heap"],
    )
print("Separate retained-object diagnostic:", summary["retainedObjectDiagnostic"])

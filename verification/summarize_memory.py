"""Summarize paired local measurements; retain per-run ranges and raw samples."""

import json
from pathlib import Path
from statistics import median

root = Path(__file__).parent / "electron"
groups = {
    name: [json.loads((root / f"memory-{label}-{i}.json").read_text()) for i in (1, 2)]
    for name, label in (("before", "before"), ("after", "optimized"))
}


def stats(values):
    return dict(median=median(values), minimum=min(values), maximum=max(values))


phases = {}
for index, phase in enumerate(groups["before"][0]["summary"]):
    entry = {}
    for name, runs in groups.items():
        assert all(r["summary"][index]["name"] == phase["name"] for r in runs)
        entry[name] = {
            field: stats([r["summary"][index][field] for r in runs])
            for field in (
                "settledPrivate",
                "peakPrivate",
                "settledWorkingSet",
                "settledPythonPrivate",
                "elapsedMs",
            )
        }
    entry["settledReductionPercent"] = 100 * (
        1 - entry["after"]["settledPrivate"]["median"] / entry["before"]["settledPrivate"]["median"]
    )
    phases[phase["name"]] = entry

peak = {
    name: stats([max(s["peakPrivate"] for s in run["summary"]) for run in runs])
    for name, runs in groups.items()
}
report = dict(
    workload=dict(records=10000, fields=64, sourceBytes=groups["before"][0]["sourceBytes"]),
    method="Two fresh isolated profiles before and after. Full Electron descendant tree including Python. "
    "Windows GetProcessMemoryInfo, 100 ms sampling. Settled value is median of final five samples "
    "after an 800 ms pause. No forced garbage collection or working-set trimming.",
    units="Bytes; divide by 1,048,576 for MiB.",
    interpretation="PrivateUsage is private committed memory, not physical RAM residency. "
    "Working-set sums are also recorded, but may double-count shared pages. "
    "Sampled peaks are lower bounds; brief peaks may fall between samples. "
    "Two local runs establish an observed change, not statistical significance or a long-duration leak guarantee.",
    api_reference="https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex",
    phases=phases,
    peakPrivate=peak,
    peakReductionPercent=100 * (1 - peak["after"]["median"] / peak["before"]["median"]),
    source_reports={
        name: [str(Path(r["folder"]).name) for r in runs] for name, runs in groups.items()
    },
)
(root / "memory-summary.json").write_text(json.dumps(report, indent=2) + "\n")
for name in ("import", "investigate", "compare", "repeat-import", "small-replacement"):
    p = phases[name]
    print(
        f'{name}: {p["before"]["settledPrivate"]["median"]/1048576:.1f} -> '
        f'{p["after"]["settledPrivate"]["median"]/1048576:.1f} MiB; '
        f'{p["settledReductionPercent"]:.1f}% reduction'
    )
print(f'Peak: {peak["before"]["median"]/1048576:.1f} -> {peak["after"]["median"]/1048576:.1f} MiB')

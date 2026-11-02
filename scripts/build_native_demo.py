"""Regenerate public demo cases from the built, owned Windows application.

Expected outcomes come from the external controller's actions, not detection output.
Only the explicitly named demo directory is written; local approvals are never changed.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine
import native_integrity as native
import native_stream
from native_capture import collect
from scripts.test_native_stream import OwnedProcess

DESTINATION = ROOT / "demos/native"
DATE = "2026-01-01T00:00:00+00:00"
SPECS = (
    ("approved-update", "v2", None, True, ["No finding"] * 4),
    ("unapproved-update", "v2", None, False, ["Review"] * 4),
    (
        "changed-code",
        "v1",
        "change-primary",
        True,
        ["No finding", "No finding", "Review", "No finding"],
    ),
    (
        "unreadable",
        "v1",
        "unreadable",
        True,
        ["No finding", "No finding", "Unknown", "No finding"],
    ),
    ("outside-coverage", "v1", "change-outside", True, ["No finding"] * 4),
)


def collect_pair(build, action):
    with OwnedProcess(build, interval=500) as child:
        ready = child.frame()
        if ready["type"] != "ready":
            raise ValueError("Owned app did not declare its manifest.")
        first = child.frame()
        if first["type"] != "sample":
            raise ValueError("Owned app did not provide an initial sample.")
        boundary = child.command(action) if action else first["sequence"] + 1
        while True:
            second = child.frame()
            if second is None:
                raise ValueError("Owned app stopped before the controlled observation.")
            if second["type"] == "sample" and second["sequence"] >= boundary:
                break
        child.process.stdin.write(b"stop\n")
        child.process.stdin.flush()
        # Validate the ending even though only the selected pair is published.
        while frame := child.frame():
            if frame["type"] == "end":
                if frame["dropped_samples"]:
                    raise ValueError("Regenerate the demo without transport loss.")
                break
        else:
            raise ValueError("Owned app disconnected without an ending.")
        if child.process.wait(timeout=5):
            raise ValueError("Owned app failed to stop.")
        return ready, [first, second]


def main():
    registry = dict(schema=native.BASELINE_SCHEMA, entries=[])
    for build in ("v1", "v2"):
        registry = native.approve(
            collect(build, "clean"), registry, f"Reviewed owned demo build {build}"
        )
    for entry in registry["entries"]:
        entry["approved_at"] = DATE
    empty = dict(schema=native.BASELINE_SCHEMA, entries=[])
    manifest = dict(
        schema="surge-native-demo-v1",
        provenance="Derived from real controlled captures of Surge's own app. Paths, process identities, timestamps, timing and sequence positions are normalized for publication; code bytes, module fingerprints, permissions and verdict inputs are preserved.",
        cases=[],
    )
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, build, action, approved, expected in SPECS:
        ready, frames = collect_pair(build, action)
        source_hash = native.digest(dict(ready=ready, samples=frames))
        decoder = native_stream.StreamDecoder(registry if approved else empty)
        decoder.accept(ready)
        groups = []
        for index, frame in enumerate(frames):
            frame.update(sequence=index + 1, elapsed_ms=index * 500, dropped_samples=0)
            for raw in frame["observations"]:
                raw.update(
                    module_path="lab_module.dll" if build == "v1" else "lab_module_v2.dll",
                    module_base=268435456,
                    pid=1,
                    session_id=f"demo-{name}",
                    process_started="1",
                    captured_at=(
                        datetime(2026, 1, 1, tzinfo=timezone.utc)
                        + timedelta(milliseconds=index * 500)
                    ).isoformat(),
                    collection_ms=0,
                )
            groups.append(decoder.accept(frame))
        rows = native_stream.snapshot_rows(groups)
        data = engine.parse_bytes(
            ("\n".join(engine.canonical(r) for r in rows) + "\n").encode(), name + ".jsonl"
        )
        config = native.default_policy(data)
        result = engine.analyze(data, None, config)
        if [r["status"] for r in result["records"]] != expected:
            raise ValueError(f"Controlled outcomes did not match: {name}")
        document = engine.case_document(data, None, config, result)
        document["created_at"] = DATE
        raw = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()
        filename = name + ".case.json"
        (DESTINATION / filename).write_bytes(raw)
        manifest["cases"].append(
            dict(
                file=filename,
                sha256=engine.sha(raw),
                captured_source_sha256=source_hash,
                action=action or "unchanged owned build",
                approved=approved,
                outcomes=expected,
                readable_ranges=[2, 2, 1, 1] if name == "unreadable" else [2] * 4,
            )
        )
    (DESTINATION / "expected.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print("Generated five sanitized cases with separately declared expected outcomes.")


if __name__ == "__main__":
    main()

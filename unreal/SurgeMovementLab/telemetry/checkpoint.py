"""Save a durable source fingerprint/checkpoint without Git, hooks or remote writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"Binaries", "Intermediate", "DerivedDataCache", "Saved", ".vs", "__pycache__", "local", "checkpoints"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--note", required=True)
    args = parser.parse_args()
    snapshot = {}
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if set(relative.parts) & SKIP or not path.is_file() or path.is_symlink():
            continue
        if path.stat().st_size > 16 * 1024 * 1024:
            continue
        snapshot[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    now = datetime.now(timezone.utc)
    output = ROOT / "checkpoints"
    output.mkdir(exist_ok=True)
    record = {"schema": "survive-checkpoint-v1", "created_utc": now.isoformat(),
              "note": args.note, "files_sha256": snapshot,
              "limits": "Source fingerprint, not a build/playtest qualification or backup of external tools."}
    name = now.strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    with (output / name).open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"checkpoint": "checkpoints/" + name, "files": len(snapshot), "note": args.note}))


if __name__ == "__main__":
    main()

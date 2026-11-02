"""Verify retained package-consumer evidence without executing the package."""
import argparse
import json
from pathlib import Path
import sys

try:
    from .check_windows_package import verify_evidence
except ImportError:
    from check_windows_package import verify_evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-failure", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify_evidence(args.report, json.loads(args.manifest.read_text(encoding="utf-8")), args.expected_failure)
    except Exception as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

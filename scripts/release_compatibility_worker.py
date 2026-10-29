"""Real case-reader subprocess for the bounded, owned-fixture release check."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("method", choices=("generate", "inspect", "library_verify", "open"))
    parser.add_argument("case", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.root.resolve()))
    import desktop_worker as desktop
    import engine
    assert Path(desktop.__file__).resolve().parent == args.root.resolve()
    assert Path(engine.__file__).resolve().parent == args.root.resolve()
    if args.method == "generate":
        rows = [{"reading": n, "note": "Owned sample – café 東京"} for n in range(20)]
        current = engine.parse_bytes(engine.canonical(rows).encode("utf-8"), "owned.json")
        config = desktop.default_config()
        config["rules"] = [dict(name="Owned threshold", field="reading", op="gt", value=12, priority="Warning")]
        result = engine.analyze(current, None, config)
        engine.save_case(args.case, current, None, config, result)
    workspace = desktop.Workspace()
    if args.method == "library_verify":
        answer = workspace.dispatch("library_verify", {"path": str(args.case)})
    else:
        state = workspace.dispatch("open", {"path": str(args.case)})
        answer = dict(summary=state["summary"], current=workspace.current.text,
                      config=workspace.config, result=workspace.result,
                      inspected_capture=state["inspected_capture"],
                      bytes=args.case.stat().st_size,
                      sha256=hashlib.sha256(args.case.read_bytes()).hexdigest())
    print(json.dumps(answer, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()

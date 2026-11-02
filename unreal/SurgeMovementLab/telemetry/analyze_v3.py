"""Create a new, self-contained Survive evidence bundle without overwriting runs.

Source kind/phase are operator assertions in an external manifest, not detector
features. This tool does not collect from a running game or communicate online.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from audit_v3 import summarize
from prepare_v3 import derive_rows, load_profile, load_rows, PROFILE_IDS, PROFILE_ROOT
from prepare_v2 import MAX_BYTES


def encoded(value):
    return (json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build_bundle(raw, output, *, profile_id, source_kind, phase, repetition=1, include_replay=False,
                 runtime_context=None):
    if source_kind not in {"owned-unreal-capture", "synthetic-fixture"} or phase not in {"practice", "development", "held-out"}:
        raise ValueError("Explicit recognized source kind and phase required")
    if type(repetition) is not int or not 1 <= repetition <= 10000:
        raise ValueError("Repetition must be 1–10000")
    profile = load_profile(profile_id)
    profile_raw = (PROFILE_ROOT / (profile_id + ".json")).read_bytes()
    if digest(profile_raw) != profile["file_sha256"]:
        raise ValueError("Profile changed during analysis; retry after profile freeze")
    rows = load_rows(raw, profile)
    context = None
    if runtime_context is not None:
        if source_kind != "owned-unreal-capture":
            raise ValueError("Unreal smoke context contradicts synthetic-fixture source kind")
        from runtime_context import validate_context
        context = validate_context(runtime_context, raw, rows, profile)
    # Context is external provenance only. It is never passed to either the
    # movement derivation or geometry/quality summary below.
    records = derive_rows(rows, profile)
    summary = summarize(rows, profile)
    derived = ("\n".join(json.dumps(row, allow_nan=False, separators=(",", ":")) for row in records) + "\n").encode()
    if len(records) > 10000 or len(derived) > 16 * 1024 * 1024:
        raise ValueError("Derived evidence exceeds current Surge import limits")
    summary["constraint_counts"] = {
        "Review": sum(r["constraint_ratio"] is not None and r["constraint_ratio"] > 1 for r in records),
        "Unknown": sum(r["constraint_ratio"] is None for r in records),
        "No finding": sum(r["constraint_ratio"] is not None and r["constraint_ratio"] <= 1 for r in records),
    }
    source_dir = Path(__file__).resolve().parent
    adapter_files = ("prepare.py", "prepare_v2.py", "prepare_v3.py", "audit_v3.py", "analyze_v3.py")
    hashes = {name: digest((source_dir / name).read_bytes()) for name in adapter_files}
    manifest = {
        "schema": "survive-evidence-manifest-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "session_id": rows[0]["session_id"], "source_kind_operator_asserted": source_kind,
        "phase_operator_asserted": phase, "repetition": repetition, "profile_id": profile_id,
        "policy_sha256": profile["file_sha256"], "profile_sha256": profile["file_sha256"],
        "policy_sha256_meaning": "Reviewed movement-profile bytes; policy.json settings have a separate fingerprint.",
        "adapter_sha256": hashes,
        "source_sha256": digest(raw), "derived_sha256": digest(derived),
        "source_bytes": len(raw), "source_records": len(rows), "derived_records": len(records),
        "input_scheme": "unmeasured", "configured_input_scheme": "desktop_mouse_rmb", "run_seed": rows[0]["a"],
        "aimed_fraction": rows[0]["b"], "completion": rows[-1]["detail"],
        "ground_truth_used_by_detector": False, "authenticity": "not_attested",
        "engine_version": None, "build_sha256": None, "map_sha256": None,
        "camera_and_viewport": None,
        "missing_context": ["Actual input method is unmeasured; desktop RMB is the configured game control scheme.",
                            "Engine/build/map fingerprints and camera settings require an external runtime/build record.",
                            "Source kind and phase are operator assertions, not inferred authenticity."]}
    if context is not None:
        manifest.update({"runtime_context_sha256": digest(runtime_context),
                         "runtime_context_helper_sha256": digest((source_dir / "runtime_context.py").read_bytes()),
                         "engine_version": context["engine_version"], "module_sha256": context["module_sha256"],
                         "module_sha256_meaning": "Recorded UnrealEditor-SurgeMovementLab.dll only; not a whole-build hash.",
                         "input_scheme": context["input_scheme"], "runtime_driver": context["driver"],
                         "runtime_mode": context["mode"], "rendering": context["rendering"], "map": context["map"],
                         "requested_max_fps": context["requested_max_fps"], "measured_fps": None,
                         "missing_context": ["Whole-build/map fingerprints and camera/viewport settings remain unavailable.",
                                             "The60FPS cap was requested; no measured FPS is supplied by runtime context.",
                                             "Source kind/phase remain operator assertions; local context is not attestation."]})
    # Exclusive directory creation keeps earlier evidence intact. If a write is
    # interrupted, the partial directory remains clearly incomplete for recovery.
    output = Path(output)
    output.mkdir(parents=False, exist_ok=False)
    files = {"source.jsonl": raw, "surge.jsonl": derived,
             "profile.json": profile_raw,
             "summary.json": encoded(summary), "policy.json": (source_dir / "survive-policy.json").read_bytes()}
    if runtime_context is not None:
        files["runtime-context.json"] = runtime_context
    for name, content in files.items():
        with (output / name).open("xb") as target:
            target.write(content)
    manifest["bundle_sha256"] = {name: digest(content) for name, content in files.items()}
    manifest["analysis_settings_sha256"] = manifest["bundle_sha256"]["policy.json"]
    if include_replay:
        from render_replay import export_replay
        replay = export_replay(raw, output / "replay.html", profile_id=profile_id, source_kind=source_kind)
        if replay["profile_sha256"] != profile["file_sha256"]:
            raise ValueError("Profile changed during replay export; incomplete bundle retained without manifest")
        manifest["bundle_sha256"]["replay.html"] = digest((output / "replay.html").read_bytes())
        manifest["replay_exporter_sha256"] = {
            name: digest((source_dir / name).read_bytes()) for name in ("render_replay.py", "replay-template.html")}
        manifest["replay"] = replay
    # Write manifest last: its absence identifies an interrupted bundle creation.
    with (output / "manifest.json").open("xb") as target:
        target.write(encoded(manifest))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path, help="New evidence directory; its parent must exist")
    parser.add_argument("--profile", choices=sorted(PROFILE_IDS), default="survive-lucian-practice-v1")
    parser.add_argument("--source-kind", required=True, choices=("owned-unreal-capture", "synthetic-fixture"))
    parser.add_argument("--phase", required=True, choices=("practice", "development", "held-out"))
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--replay", action="store_true", help="Include a standalone offline replay and its fingerprints")
    parser.add_argument("--runtime-context", type=Path, help="Optional capture-bound external smoke-run context; never detector input")
    args = parser.parse_args()
    if not 1 <= args.repetition <= 10000:
        parser.error("Repetition must be 1–10000")
    with args.capture.open("rb") as source:
        raw = source.read(MAX_BYTES + 1)
    runtime_context = None
    if args.runtime_context is not None:
        from runtime_context import MAX_CONTEXT_BYTES, read_bounded
        runtime_context = read_bounded(args.runtime_context, MAX_CONTEXT_BYTES)
    summary = build_bundle(raw, args.output, profile_id=args.profile, source_kind=args.source_kind,
                           phase=args.phase, repetition=args.repetition, include_replay=args.replay,
                           runtime_context=runtime_context)
    print(json.dumps({"records": summary["records"], "completion": summary["completion"],
                      "constraints": summary["constraint_counts"], "audit_issues": len(summary["audit_issues"])}))


if __name__ == "__main__":
    main()

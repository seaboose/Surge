"""Bounded extracted Surge+Survive gameplay-to-report acceptance, with owned data.

Developer Python/Node supervise tests; the application uses its bundled runtimes.
The package is verified before extraction and checked for mutations afterwards.
No existing user profile, developer recording or third-party game is opened.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

try:
    from . import check_windows_package as consumer
except ImportError:
    import check_windows_package as consumer

ROOT = Path(__file__).resolve().parents[1]
TOTAL_SECONDS = 1200


def write_new(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "verification/survive-standalone-20261026")
    args = parser.parse_args(argv)
    if os.name != "nt":
        raise RuntimeError("Windows x64 package acceptance requires Windows.")
    archive, manifest_path, node = (value.resolve(strict=True) for value in (args.archive, args.manifest, args.node))
    if manifest_path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Package manifest exceeds acceptance input bound.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_kind") != "surge-survive":
        raise ValueError("Full Survive workflow requires a combined package manifest.")
    folder = args.output_root.resolve() / ("consumer-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    profile, temporary = folder / "user-profile", folder / "temporary"
    profile.mkdir()
    temporary.mkdir()
    started = time.monotonic()
    deadline = started + TOTAL_SECONDS
    report = {"schema": "surge-survive-package-acceptance-v1", "status": "incomplete",
              "started_utc": datetime.now(timezone.utc).isoformat(), "total_seconds_bound": TOTAL_SECONDS,
              "archive": str(archive), "archive_sha256": consumer.digest(archive),
              "manifest_sha256": consumer.digest(manifest_path), "steps": [],
              "human_baseline": False, "unfamiliar_user_acceptance": "deferred"}
    try:
        report["package"] = consumer.verify_package(archive, manifest)
        application = folder / "application"
        consumer.extract_verified(archive, application)
        report["steps"].append({"name": "verified extraction", "status": "passed"})
        app = application / "resources/app"
        descriptor = json.loads((app / "survive-runtime.json").read_text(encoding="utf-8"))
        game = app / descriptor["game_root"] / descriptor["game_executable"]
        if not game.resolve().is_relative_to(application) or not game.is_file():
            raise ValueError("Game executable is not inside the extracted package.")
        app_env = consumer.restricted_environment(temporary)
        # Explicitly poison developer overrides. The application receives neither
        # developer PATH entries nor a usable external Python/editor location.
        app_env.update(UE_ENGINE_ROOT=str(temporary / "unavailable-unreal"),
                       SURGE_SURVIVE_DATA=str(temporary / "untrusted-data-override"),
                       SURGE_GAME_EXECUTABLE=str(temporary / "untrusted-game-override"))
        report["environment"] = {"path": app_env["PATH"], "developer_overrides_invalid": True,
                                 "application_profile": str(profile),
                                 "scope": "Isolated profile and restricted process environment on a developer host, not a pristine Windows VM."}
        for mode in ("journey", "reopen"):
            output = folder / mode
            output.mkdir()
            if mode == "reopen":
                # Move only this checked, freshly extracted application. Data stays
                # outside it. This exercises relocation without copying live data.
                report["payload_before_relocation"] = consumer.verify_payload(application, manifest)
                replacement = folder / "replacement-application"
                if (application.resolve(strict=True).parent != folder.resolve(strict=True)
                        or application.resolve(strict=True) != application
                        or replacement.resolve().parent != folder.resolve(strict=True)
                        or replacement.exists()):
                    raise ValueError("Unexpected owned replacement location.")
                application.rename(replacement)
                application = replacement
                app = application / "resources/app"
                game = app / descriptor["game_root"] / descriptor["game_executable"]
            config = {"mode": mode, "application": str(application), "executable": str(application / "Surge.exe"),
                      "game_executable": str(game), "profile": str(profile), "app_env": app_env,
                      "output": str(output), "cwd": str(folder), "gate": str(output / "gate"),
                      "export_path": str(folder / "standalone-demonstration.html"),
                      "prior": str(folder / "journey/retained-session.json"),
                      "verification_python": sys.executable, "process_inspector": str(ROOT / "scripts/windows_owned_processes.py")}
            write_new(output / "config.json", config)
            command = [str(node), str(ROOT / "desktop/survive-packaged.test.cjs"), str(output / "config.json")]
            result = consumer.run_owned(command, output, os.environ.copy(), deadline, Path(config["gate"]), application)
            ui = json.loads((output / "results.json").read_text(encoding="utf-8"))
            if ui["status"] != "passed" or ui["renderer_errors"] or any(check["status"] != "passed" for check in ui["checks"]):
                raise ValueError("Packaged workflow did not pass every declared step.")
            report["steps"].append({"name": mode, "status": "passed", "supervision": result,
                                    "checks": len(ui["checks"]), "evidence": str((output / "results.json").relative_to(folder))})
        report["immutable_payload"] = consumer.verify_payload(application, manifest)
        report["archive_unchanged"] = consumer.digest(archive) == report["archive_sha256"]
        if not report["archive_unchanged"]:
            raise ValueError("Input archive changed during acceptance.")
        report["status"] = "passed"
        report["portable_report"] = str(folder / "standalone-demonstration.html")
        report["data_root"] = str(profile / "Survive")
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if report["elapsed_seconds"] > TOTAL_SECONDS:
            report.update(status="failed", error="Acceptance exceeded total deadline.")
        write_new(folder / "report.json", report)
        print(json.dumps({"status": report["status"], "report": str(folder / "report.json")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Local study helper: frozen plans, bounded owned-game trials and external labels."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from survive_study import StudyManager, MODES, PROFILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze")
    sub.add_parser("list")
    start = sub.add_parser("start")
    start.add_argument("--mode", choices=sorted(MODES), default="human")
    start.add_argument("--seed", type=int, default=1337)
    start.add_argument("--profile", choices=sorted(PROFILES), default="survive-lucian-practice-v1")
    start.add_argument("--participant", default="player")
    start.add_argument("--phase", choices=("practice", "development", "held-out"), default="development")
    label = sub.add_parser("label")
    label.add_argument("trial_id")
    label.add_argument("--expected-mechanical-violation", choices=("yes", "no", "unknown"), required=True)
    label.add_argument("--note", default="")
    args = parser.parse_args()
    manager = StudyManager()
    if args.command == "freeze":
        result = manager.freeze()
    elif args.command == "list":
        result = {"trials": manager.trials()}
    elif args.command == "label":
        result = manager.adjudicate(args.trial_id, args.expected_mechanical_violation, args.note)
    else:
        # Arm capture before launching; no closed-round marker is fabricated.
        from survive_capture import CaptureManager
        capture = CaptureManager()
        capture.start("next", args.profile)
        try:
            result = manager.start(args.mode, args.seed, args.profile, args.participant, args.phase)
            manager.bind_recording(result["trial"]["trial_id"], capture.status()["capture"]["recording_id"])
            print(json.dumps(result), flush=True)
            while manager._process.poll() is None:
                time.sleep(.25)
            result = {"trial": manager.status()["trial"], "recording": capture.stop()["capture"]}
        finally:
            try:
                capture.close()
            finally:
                manager.close()
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

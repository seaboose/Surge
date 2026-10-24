"""Windows-isolated stream model component with frozen held-back variants."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.retention_contract import CASE_IDS

MEMORY_LIMIT = 1024 * 1024 * 1024
LOG_LIMIT = 10 * 1024 * 1024
SOURCES = ("scripts/run_stream_model.py", "scripts/stream_model_worker.py",
           "docs/stream-model-acceptance.md", "scripts/check_approval_contract.py",
           "scripts/check_retention.py", "scripts/retention_contract.py",
           "test_native_manifest_security.py", "test_native_window.py",
           "test_native_replay_contract.py", "test_native_integrity.py",
           "native_stream.py", "native_integrity.py", "integrity_manifest.py", "engine.py")
NEGATIVE = ("sample_before_ready", "end_before_ready", "duplicate_ready", "unknown_type",
            "duplicate_sequence", "reversed_sequence", "unexplained_gap", "loss_rollback",
            "joint_rollback", "negative_time", "backward_time", "boolean_time", "nonfinite_time",
            "boolean_sequence", "negative_drop", "missing_range", "duplicate_range",
            "identity_session_id", "identity_pid", "identity_module_sha256",
            "identity_process_started", "identity_build", "invalid_pid",
            "invalid_process_started", "invalid_build", "end_wrong_loss", "duplicate_end",
            "sample_after_end", "scenario_in_live")
FRAMING = ("line_minus", "line_exact", "line_plus", "valid_utf8", "missing_newline",
           "invalid_utf8", "truncated_utf8", "truncated_json", "duplicate_json_key", "missing_end")
REPLAY = ("missing_health", "wrong_health_session", "wrong_health_loss", "wrong_health_eviction",
          "wrong_final_sequence", "poisoned_health_verdict")


class BASIC(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class IO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class EXTENDED(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def kernel():
    if os.name != "nt": raise RuntimeError("This component requires Windows job-object limits")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD, ctypes.c_void_p]
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    return api


def check_windows(ok):
    if not ok: raise ctypes.WinError(ctypes.get_last_error())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def fingerprint(value): return hashlib.sha256(canonical(value)).hexdigest()


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def one(recipe, folder):
    folder.mkdir(parents=True, exist_ok=False)
    request = dict(recipe=recipe, folder=str(folder))
    (folder / "request.json").write_bytes(canonical(request))
    timeout = 15 if recipe["kind"] == "boundary" else 5
    result = dict(status="failed", timeout_seconds=timeout, process_memory_limit=MEMORY_LIMIT,
                  recipe_sha256=fingerprint(recipe), timed_out=False)
    api, job, child = kernel(), None, None
    started = time.monotonic()
    try:
        job = api.CreateJobObjectW(None, None)
        check_windows(job)
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x100 | 0x2000
        info.ProcessMemoryLimit = MEMORY_LIMIT
        check_windows(api.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)))
        with (folder / "stdout.log").open("wb") as stdout, (folder / "stderr.log").open("wb") as stderr:
            child = subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts/stream_model_worker.py")],
                                     stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, cwd=ROOT,
                                     env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            # The worker blocks on stdin; its recipe is released only after the
            # kernel has assigned and confirmed the process memory limit.
            check_windows(api.AssignProcessToJobObject(job, wintypes.HANDLE(int(child._handle))))
            configured = EXTENDED()
            check_windows(api.QueryInformationJobObject(job, 9, ctypes.byref(configured),
                                                       ctypes.sizeof(configured), None))
            assert configured.ProcessMemoryLimit == MEMORY_LIMIT
            assert configured.BasicLimitInformation.LimitFlags & 0x100
            result["job_limit_verified"] = True
            child.stdin.write(canonical(request) + b"\n")
            child.stdin.close()
            try: child.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                child.kill(); child.wait(timeout=3)
        peak = EXTENDED()
        check_windows(api.QueryInformationJobObject(job, 9, ctypes.byref(peak), ctypes.sizeof(peak), None))
        result.update(exit_code=child.returncode, peak_private_bytes=peak.PeakProcessMemoryUsed,
                      seconds=round(time.monotonic() - started, 6))
        assert 0 < peak.PeakProcessMemoryUsed <= MEMORY_LIMIT
        if recipe["kind"] == "timeout_probe":
            assert result["timed_out"], "Owned deadline control was not killed"
            result["status"] = "expected_timeout"
        else:
            assert not result["timed_out"], "Owned case exceeded unchanged per-case deadline"
            assert child.returncode == 0, "Owned case failed; see retained stderr"
            output = (folder / "stdout.log").read_bytes()
            assert len(output) <= LOG_LIMIT
            payload = json.loads(output)
            assert payload["status"] == "passed" and payload["recipe_sha256"] == fingerprint(recipe)
            assert payload["result_sha256"] == fingerprint(payload["result"])
            result.update(status="passed", payload=payload)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if child and child.poll() is None:
            child.kill(); child.wait(timeout=3)
        if job: api.CloseHandle(job)
        result.setdefault("seconds", round(time.monotonic() - started, 6))
        (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def recipes(final=False):
    rng = random.Random(2026102303 if final else 17)
    def base(kind, index, count=2, samples=2):
        count = count if kind == "positive" else rng.choice((2, 3))
        sizes = (1, 7, 64) if not final else (2, 9, 63)
        return dict(kind=kind, ranges=count, bytes=rng.choice(sizes),
                    shift=rng.choice((0, 128)) if not final else rng.choice((512, 1024, 2048)),
                    prefix=("Dev" if not final else "Final") + str(index),
                    pid=rng.randint(1, 50000), creation=rng.randint(1, 1000000),
                    build="v2" if final else "v1", mixed=True, mode_offset=rng.randrange(4),
                    gaps=[rng.randrange(3 if not final else 5) for _ in range(samples)],
                    ticks=[rng.choice((0, 1, 500) if not final else (0, 19, 701)) for _ in range(samples)],
                    tail_loss=0 if not final else 1)
    cases = []
    for index, (count, samples) in enumerate(((2, 0), (2, 1), (2, 6), (3, 2), (3, 5), (16, 1))):
        row = base("positive", index, count, samples)
        if samples == 0: row["tail_loss"] = 0
        cases.append(dict(id=f"positive-{count}-{samples}", recipe=row))
    for kind, names in (("negative", NEGATIVE), ("framing", FRAMING), ("replay", REPLAY)):
        for index, name in enumerate(names):
            row = base(kind, index)
            row.update(variant=name)
            if kind == "replay": row["tail_loss"] = 1
            cases.append(dict(id=kind + "-" + name, recipe=row))
    return cases


def main(revalidation_of=None):
    folder = ROOT / "verification/qualification" / ("stream-model-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    hashes = source_hashes()
    for name in SOURCES:
        destination = folder / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / name).read_bytes())
    report = dict(schema="surge-stream-model-v1", status="incomplete", original_campaign="incomplete",
                  final_variant_status="known_variants_revalidation" if revalidation_of else "post_freeze_synthetic_variants",
                  revalidation_of=revalidation_of,
                  limits=dict(process_memory_bytes=MEMORY_LIMIT, ordinary_seconds=5, boundary_seconds=15,
                              ordinary_input_bytes=262144, development_seconds=900, final_seconds=600,
                              replay_seconds=900, total_seconds=5400, log_bytes=LOG_LIMIT),
                  source_sha256=hashes, controls=[], runs=[], phases=[])
    def save():
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    save(); print(str(folder), flush=True)
    started = None
    try:
        for kind in ("safe_probe", "memory_probe", "timeout_probe"):
            result = one(dict(kind=kind), folder / "preflight" / kind)
            report["controls"].append(dict(id=kind, result=result)); save()
            assert result["status"] == ("expected_timeout" if kind == "timeout_probe" else "passed")
        started = time.monotonic()
        def phase(name, cases, seconds):
            tick = time.monotonic()
            entries = [dict(phase=name, id=c["id"], recipe=c["recipe"], status="not_run") for c in cases]
            report["runs"].extend(entries); save()
            for entry in entries:
                assert time.monotonic()-started < 5400 and time.monotonic()-tick < seconds
                assert source_hashes() == hashes, "Frozen source changed during execution"
                result = one(entry["recipe"], folder / name / entry["id"])
                entry.update(status=result["status"], result=result); save()
                assert result["status"] == "passed", entry["id"]
                logs = sum(p.stat().st_size for p in folder.rglob("*.log"))
                assert logs <= LOG_LIMIT, "Component log budget exceeded"
                print(name + "/" + entry["id"] + " passed", flush=True)
            report["phases"].append(dict(name=name, cases=len(entries), seconds=round(time.monotonic()-tick, 6)))
            save()
            return entries
        development = recipes(False)
        phase("development", development, 900)
        boundaries = [dict(id=name, recipe=dict(kind="boundary", variant=name)) for name in CASE_IDS]
        phase("boundary-development", boundaries, 900 - report["phases"][0]["seconds"])
        freeze = dict(created_at=datetime.now(timezone.utc).isoformat(), source_sha256=hashes,
                      generator="recipes(final=True)", seed=2026102303, limits=report["limits"],
                      categories=dict(negative=NEGATIVE, framing=FRAMING, replay=REPLAY),
                      development_report_sha256=hashlib.sha256((folder / "report.json").read_bytes()).hexdigest())
        (folder / "final-freeze.json").write_text(json.dumps(freeze, indent=2) + "\n")
        final_cases = recipes(True)
        (folder / "final-recipes.json").write_text(json.dumps(final_cases, indent=2) + "\n")
        final = phase("final", final_cases, 600)
        first = phase("replay-1", final_cases, 900)
        second = phase("replay-2", final_cases, 900 - report["phases"][-1]["seconds"])
        phase("boundary-replay", boundaries, 900 - sum(p["seconds"] for p in report["phases"] if p["name"].startswith("replay")))
        for a, b, c in zip(final, first, second):
            assert a["recipe"] == b["recipe"] == c["recipe"]
            assert a["result"]["payload"]["result_sha256"] == b["result"]["payload"]["result_sha256"] == c["result"]["payload"]["result_sha256"]
        boundary_runs = [r for r in report["runs"] if r["recipe"]["kind"] == "boundary"]
        for a, b in zip(boundary_runs[:24], boundary_runs[24:]):
            assert a["result"]["payload"]["result_sha256"] == b["result"]["payload"]["result_sha256"]
        report.update(status="passed", final_repeatability="passed")
    except Exception as exc:
        report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        traceback.print_exc()
    finally:
        report["campaign_seconds"] = round(time.monotonic()-started, 6) if started else None
        save()
        manifest = [dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size,
                         sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in sorted(folder.rglob("*")) if p.is_file()]
        (folder / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps(dict(folder=str(folder), status=report["status"],
                              completed=sum(r["status"] == "passed" for r in report["runs"]),
                              error=report.get("error"))), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revalidation-of", help="Prior attempt ID whose already-seen variants are repeated")
    arguments = parser.parse_args()
    raise SystemExit(main(arguments.revalidation_of))

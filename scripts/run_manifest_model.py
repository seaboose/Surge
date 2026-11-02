"""Bounded isolated T2 component; freeze before distinct synthetic final recipes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import integrity_manifest
from isolated_owned_worker import run as isolated
from run_stream_model import one as stream_control

SOURCES = ("scripts/run_manifest_model.py", "scripts/manifest_model_worker.py",
           "scripts/isolated_owned_worker.py", "scripts/run_stream_model.py",
           "scripts/stream_model_worker.py", "scripts/check_approval_contract.py",
           "scripts/check_retention.py", "scripts/retention_contract.py",
           "docs/manifest-model-acceptance.md", "test_native_embedded_manifest_json.py",
           "test_native_manifest_security.py", "test_native_window.py",
           "test_native_replay_contract.py", "test_native_integrity.py",
           "native_integrity.py", "native_stream.py", "integrity_manifest.py", "engine.py")
MALFORMED = tuple(["missing:"+field for field in sorted(integrity_manifest.FIELDS)] +
    [f"dimension:{field}:{kind}" for field in ("module_size", "image_size", "checked_bytes", "excluded_bytes", "executable_bytes")
     for kind in ("boolean", "float", "negative", "huge", "missing")] +
    ["extra_key", "schema", "architecture", "descriptor_boolean", "descriptor_version", "relocation_policy",
     "module_hash_short", "module_hash_uppercase", "module_hash_badhex", "module_hash_nonstring",
     "range_boolean", "range_float", "range_zero", "range_huge", "duplicate_name", "name_empty", "name_digit",
     "name_long", "range_extra_key", "range_missing_key", "invalid_hex", "invalid_reference_hash", "range_65",
     "no_ranges", "one_range", "seventeen_ranges", "hole", "overlap", "outside", "duplicate_exclusion",
     "unknown_exclusion", "empty_executable", "overlap_executable", "wrong_checked_total",
     "wrong_executable_total", "wrong_excluded_total"])
ENCODED = ("duplicate_integrity_key", "duplicate_range_key", "nonfinite_embedded", "missing_manifest",
           "missing_digest", "wrong_digest", "poisoned_comparison", "poisoned_coverage", "mixed_schema",
           "truncated_embedded", "wrong_embedded_type")
META = ("clean", "module_changed", "split_excluded", "array_reorder", "legacy_registry", "legacy_capture", "name_64")


def hashes(): return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}


def recipes(final=False):
    rng = random.Random(2026102302 if final else 17)
    result = []
    def add(kind, variant, count=2, maximum=False):
        index = len(result)
        lengths = ([64 if index % 2 else 63 for _ in range(count)] if maximum else
                   [1+rng.randrange(3) for _ in range(count)]) if final else [64 if maximum else 1]*count
        if final and maximum: lengths[-1] = 64
        if final and not maximum: lengths[-1] = 1
        row = dict(kind=kind, variant=variant, ranges=count, lengths=lengths,
                   gaps=[rng.randint(2, 8 if not final else 11) for _ in range(count)],
                   prefix=("Dev" if not final else "Final")+str(index)+"R",
                   start=rng.choice((4096, 8192)) if not final else rng.choice((4608, 9216, 12288)),
                   layout=("single", "gapped")[(index+int(final)) % 2],
                   module=f"{rng.getrandbits(256):064x}", save_case=kind in ("truth", "metamorphic"))
        identity=f"{kind}-{variant}-{count}-{'max' if maximum else 'min'}".replace(":", "_")
        result.append(dict(id=identity, recipe=row))
    for count in (2, 3, 16):
        for maximum in (False, True):
            for approved in ("approved", "unapproved"):
                for mode in ("clean", "changed", "unavailable", "protection"):
                    add("truth", approved+"_"+mode, count, maximum)
        for name in META: add("metamorphic", name, count, maximum=count == 16)
    for name in MALFORMED: add("malformed", name, rng.choice((2, 3)))
    for name in ENCODED: add("encoded", name, rng.choice((2, 3)))
    for name in ("duplicate", "missing_reason", "wrong_manifest_digest", "extra_key"):
        add("approval_invalid", name)
    assert len(result) == len({r["id"] for r in result})
    return result


def main(revalidation_of=None, prior_attempts=()):
    folder = ROOT / "verification/qualification" / ("manifest-model-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    source = hashes()
    for name in SOURCES:
        destination=folder/"source"/name; destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT/name).read_bytes())
    used = dict(development=0.0, final=0.0, replay=0.0, total=0.0)
    prior_records = []
    for prior in prior_attempts:
        path = Path(prior) / "report.json"
        raw = path.read_bytes(); previous = json.loads(raw)
        assert previous["schema"] == "surge-manifest-model-v1"
        total = previous.get("campaign_seconds") or 0
        accounted = 0
        for item in previous["phases"]:
            group = "replay" if item["name"].startswith("replay") else item["name"]
            used[group] += item["seconds"]; accounted += item["seconds"]
        failed = next((r for r in previous["runs"] if r["status"] not in ("passed", "not_run")), None)
        if failed:
            group = "replay" if failed["phase"].startswith("replay") else failed["phase"]
            used[group] += max(0, total-accounted)
        used["total"] += total
        prior_records.append(dict(id=path.parent.name, sha256=hashlib.sha256(raw).hexdigest(),
                                  completed=sum(r["status"] == "passed" for r in previous["runs"])))
    report = dict(schema="surge-manifest-model-v1", status="incomplete", original_campaign="incomplete",
                  final_variant_status="known_variants_revalidation" if revalidation_of else "post_freeze_synthetic_variants",
                  revalidation_of=revalidation_of, prior_attempts=prior_records, prior_seconds=used,
                  limits=dict(ordinary_input_bytes=262144, process_memory_bytes=1073741824,
                              ordinary_seconds=5, development_cases=20000, development_seconds=600,
                              final_cases=10000, final_seconds=300, replay_seconds=900,
                              total_seconds=5400, log_bytes=10485760, corpus_bytes=33554432),
                  source_sha256=source, controls=[], runs=[], phases=[])
    def save(): (folder/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    save(); print(str(folder), flush=True)
    start=None
    try:
        for kind in ("safe_probe", "memory_probe", "timeout_probe"):
            control=stream_control(dict(kind=kind), folder/"preflight"/kind)
            report["controls"].append(dict(id=kind, result=control)); save()
            assert control["status"] == ("expected_timeout" if kind=="timeout_probe" else "passed")
        start=time.monotonic()
        def phase(name, cases, budget):
            tick=time.monotonic()
            rows=[dict(phase=name, id=c["id"], recipe=c["recipe"], status="not_run") for c in cases]
            report["runs"].extend(rows); save()
            for row in rows:
                assert time.monotonic()-start < 5400-used["total"] and time.monotonic()-tick < budget
                assert hashes()==source, "Frozen source changed"
                raw=isolated("scripts/manifest_model_worker.py", row["recipe"], folder/name/row["id"])
                compact={k:v for k,v in raw.items() if k != "payload"}
                if "payload" in raw:
                    compact["payload"]={k:v for k,v in raw["payload"].items() if k != "coverage"}
                row.update(status=raw["status"], result=compact); save()
                assert raw["status"] == "passed", row["id"]
                assert sum(p.stat().st_size for p in folder.rglob("*.log")) <= 10485760
                assert sum(p.stat().st_size for p in folder.rglob("request.json")) <= 33554432
                print(name+"/"+row["id"]+" passed", flush=True)
            report["phases"].append(dict(name=name, cases=len(rows), seconds=round(time.monotonic()-tick,6)))
            save(); return rows
        phase("development", recipes(False), 600-used["development"])
        freeze=dict(created_at=datetime.now(timezone.utc).isoformat(), source_sha256=source,
                    final_seed=2026102302, generator="recipes(final=True)", limits=report["limits"],
                    development_report_sha256=hashlib.sha256((folder/"report.json").read_bytes()).hexdigest())
        (folder/"final-freeze.json").write_text(json.dumps(freeze, indent=2)+"\n")
        final_recipes=recipes(True)
        (folder/"final-recipes.json").write_text(json.dumps(final_recipes, indent=2)+"\n")
        final=phase("final", final_recipes, 300-used["final"])
        first=phase("replay-1", final_recipes, 900-used["replay"])
        second=phase("replay-2", final_recipes, 900-used["replay"]-report["phases"][-1]["seconds"])
        for a,b,c in zip(final,first,second):
            assert a["recipe"]==b["recipe"]==c["recipe"]
            assert a["result"]["payload"]["result_sha256"]==b["result"]["payload"]["result_sha256"]==c["result"]["payload"]["result_sha256"]
        report.update(status="passed", final_repeatability="passed")
    except Exception as exc:
        report.update(status="failed", error=type(exc).__name__+": "+str(exc)); traceback.print_exc()
    finally:
        report["campaign_seconds"]=round(time.monotonic()-start,6) if start else None; save()
        manifest=[dict(path=p.relative_to(folder).as_posix(), bytes=p.stat().st_size,
                       sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                  for p in sorted(folder.rglob("*")) if p.is_file()]
        (folder/"evidence-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        print(json.dumps(dict(folder=str(folder), status=report["status"],
                              completed=sum(r["status"]=="passed" for r in report["runs"]),
                              error=report.get("error"))),flush=True)
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revalidation-of", help="Prior accepted attempt ID; these variants are now regression replay")
    parser.add_argument("--prior-attempt", action="append", default=[], type=Path,
                        help="Preserved earlier attempt whose consumed phase budgets must be deducted")
    arguments=parser.parse_args()
    raise SystemExit(main(arguments.revalidation_of, arguments.prior_attempt))

"""Independent small manifest/approval models on owned synthetic records."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import engine
import integrity_manifest as integrity
import native_integrity as native
import native_stream as stream
from check_approval_contract import fixture, TRUTH
from check_retention import FixedFixtureClock


def digest(value): return hashlib.sha256(engine.canonical(value).encode()).hexdigest()


def encoded(value):
    raw = engine.canonical(value).encode()
    assert len(raw) <= 262144
    return raw


def capture_for(recipe):
    capture = fixture(recipe["ranges"], 1)
    ranges, excluded, executable = [], [], []
    cursor = recipe["start"]
    first = cursor
    for index, (length, gap) in enumerate(zip(recipe["lengths"], recipe["gaps"])):
        raw = bytes([index + 1]) * length
        ranges.append(dict(range_name=recipe["prefix"] + str(index), range_rva=cursor,
                           range_size=length, reference_hex=raw.hex(),
                           reference_sha256=hashlib.sha256(raw).hexdigest()))
        excluded.append(dict(range_rva=cursor+length, range_size=gap, reason="not_declared"))
        if recipe["layout"] == "gapped":
            executable.append(dict(range_rva=cursor, range_size=length+gap))
            cursor += 97
        cursor += length + gap
    if recipe["layout"] == "single": executable = [dict(range_rva=first, range_size=cursor-first)]
    base = capture["observations"][0]
    capture["ranges"] = ranges
    capture["integrity_manifest"].update(
        module_sha256=recipe["module"], image_size=65536, ranges=copy.deepcopy(ranges),
        executable_ranges=executable, exclusions=excluded,
        executable_bytes=sum(s["range_size"] for s in executable),
        checked_bytes=sum(recipe["lengths"]), excluded_bytes=sum(recipe["gaps"]))
    capture["observations"] = [dict(base, **r, phase=p, observed_hex=r["reference_hex"],
                                    module_sha256=recipe["module"])
                               for p in native.PHASES for r in ranges]
    # Exercise the actual strict JSON decoder before object validation too.
    return engine.decode(encoded(capture).decode())


def occupancy(manifest):
    def counts(parts):
        return Counter(b for p in parts for b in range(p["range_rva"], p["range_rva"]+p["range_size"]))
    a, b, c = (counts(manifest[key]) for key in ("ranges", "exclusions", "executable_ranges"))
    return (all(n == 1 for n in (a+b).values()) and a+b == c and
            sum(a.values()) == manifest["checked_bytes"] and
            sum(b.values()) == manifest["excluded_bytes"] and
            sum(c.values()) == manifest["executable_bytes"])


def refuse(action):
    try: action()
    except ValueError as exc: return str(exc)
    raise AssertionError("Malformed synthetic evidence was accepted")


def rows_for(capture, registry):
    converted = native.convert(capture, registry)
    decoder = stream.StreamDecoder(registry)
    ready = dict(schema=stream.STREAM_SCHEMA, type="ready", build="v1",
                 ranges=capture["ranges"], interval_ms=500, duration_ms=600000)
    if "integrity_manifest" in capture: ready["integrity_manifest"] = capture["integrity_manifest"]
    decoder.accept(ready)
    observations = copy.deepcopy(capture["observations"][:len(capture["ranges"])])
    for row in observations: row.pop("scenario"); row["phase"] = "live"
    group = decoder.accept(dict(schema=stream.STREAM_SCHEMA, type="sample", sequence=1,
                                dropped_samples=0, elapsed_ms=0, observations=observations))
    return stream.snapshot_rows([group]), converted


def analyze(rows, fmt, alternate=False):
    source = [dict(reversed(tuple(r.items()))) for r in rows] if alternate else rows
    raw = (json.dumps(source, ensure_ascii=False, indent=1).encode() if fmt == "json" and alternate
           else encoded(source) if fmt == "json"
           else b"".join(encoded(r)+b"\n" for r in source))
    assert len(raw) <= 262144
    data = engine.parse_bytes(raw, "synthetic."+fmt)
    policy = native.default_policy(data)
    return data, policy, engine.analyze(data, None, policy), len(raw)


def mutate(value, name):
    if name.startswith("missing:"): value.pop(name.split(":", 1)[1]); return
    if name.startswith("dimension:"):
        _, key, kind = name.split(":")
        value[key] = dict(boolean=True, float=1.5, negative=-1, huge=2**64, missing=None)[kind]; return
    if name == "extra_key": value["unrecognized"] = True
    elif name == "schema": value["schema"] = "surge-integrity-manifest-v999"
    elif name == "architecture": value["architecture"] = "arm64"
    elif name == "descriptor_boolean": value["descriptor_version"] = True
    elif name == "descriptor_version": value["descriptor_version"] = 2
    elif name == "relocation_policy": value["relocation_policy"] = "mask"
    elif name.startswith("module_hash_"):
        value["module_sha256"] = dict(short="a"*63, uppercase="A"*64, badhex="g"*64,
                                      nonstring=123)[name.removeprefix("module_hash_")]
    elif name == "range_boolean": value["ranges"][0]["range_size"] = True
    elif name == "range_float": value["ranges"][0]["range_rva"] = 4096.0
    elif name == "range_zero": value["ranges"][0]["range_rva"] = 0
    elif name == "range_huge": value["ranges"][0]["range_rva"] = 2**64
    elif name == "duplicate_name": value["ranges"][1]["range_name"] = value["ranges"][0]["range_name"]
    elif name == "name_empty": value["ranges"][0]["range_name"] = ""
    elif name == "name_digit": value["ranges"][0]["range_name"] = "1bad"
    elif name == "name_long": value["ranges"][0]["range_name"] = "A"*65
    elif name == "range_extra_key": value["ranges"][0]["extra"] = 1
    elif name == "range_missing_key": value["ranges"][0].pop("reference_hex")
    elif name == "invalid_hex": value["ranges"][0]["reference_hex"] = "zz"
    elif name == "invalid_reference_hash": value["ranges"][0]["reference_sha256"] = "0"*64
    elif name == "range_65":
        row = value["ranges"][0]; raw = bytes.fromhex(row["reference_hex"])[:1] * 65
        row.update(range_size=65, reference_hex=raw.hex(), reference_sha256=hashlib.sha256(raw).hexdigest())
    elif name == "no_ranges": value["ranges"] = []
    elif name == "one_range": value["ranges"] = value["ranges"][:1]
    elif name == "seventeen_ranges": value["ranges"] = value["ranges"] * 9
    elif name == "hole": value["exclusions"][0]["range_size"] -= 1
    elif name == "overlap": value["exclusions"][0]["range_rva"] -= 1
    elif name == "outside": value["exclusions"][0]["range_rva"] += 30000
    elif name == "duplicate_exclusion": value["exclusions"].append(copy.deepcopy(value["exclusions"][0]))
    elif name == "unknown_exclusion": value["exclusions"][0]["reason"] = "trusted"
    elif name == "empty_executable": value["executable_ranges"] = []
    elif name == "overlap_executable": value["executable_ranges"].append(copy.deepcopy(value["executable_ranges"][0]))
    elif name == "wrong_checked_total": value["checked_bytes"] += 1
    elif name == "wrong_executable_total": value["executable_bytes"] += 1
    elif name == "wrong_excluded_total": value["excluded_bytes"] += 1
    else: raise AssertionError(name)


def check(recipe, folder):
    capture = capture_for(recipe)
    original = copy.deepcopy(capture)
    assert occupancy(capture["integrity_manifest"])
    assert integrity.validate(capture["integrity_manifest"]) == original["integrity_manifest"]
    empty = dict(schema=native.BASELINE_SCHEMA, entries=[])
    registry = native.approve(capture, empty, "Synthetic manifest-model fixture")
    kind, variant = recipe["kind"], recipe["variant"]
    if kind == "malformed":
        bad = copy.deepcopy(capture["integrity_manifest"]); mutate(bad, variant)
        direct = refuse(lambda: integrity.validate(bad))
        bad_capture = copy.deepcopy(capture); bad_capture["integrity_manifest"] = bad
        converted = refuse(lambda: native.convert(bad_capture, registry))
        rows, _ = rows_for(capture, registry)
        for row in rows:
            row.update(integrity_manifest=engine.canonical(bad), integrity_manifest_sha256=digest(bad))
        reasons = [refuse(lambda: analyze(rows, fmt)) for fmt in ("json", "jsonl")]
        return dict(outcome="refused_invalid_manifest", direct=direct, conversion=converted,
                    encoded=reasons, input_sha256=digest(bad))
    if kind == "encoded":
        rows, _ = rows_for(capture, registry)
        if variant in ("duplicate_integrity_key", "duplicate_range_key", "nonfinite_embedded"):
            for row in rows:
                if variant == "duplicate_integrity_key":
                    row["integrity_manifest"] = '{"schema":"contradiction",' + row["integrity_manifest"][1:]
                elif variant == "duplicate_range_key":
                    row["range_manifest"] = '[{"range_name":"Contradiction",' + row["range_manifest"][2:]
                else: row["integrity_manifest"] = '{"ignored":NaN,' + row["integrity_manifest"][1:]
        elif variant == "missing_manifest": rows[0].pop("integrity_manifest")
        elif variant == "missing_digest": rows[0].pop("integrity_manifest_sha256")
        elif variant == "wrong_digest": rows[0]["integrity_manifest_sha256"] = "0"*64
        elif variant == "poisoned_comparison": rows[0]["memory_matches"] = False
        elif variant == "poisoned_coverage": rows[0]["coverage_read_ranges"] += 1
        elif variant == "mixed_schema": rows[0]["schema"] = "ordinary"
        elif variant == "truncated_embedded": rows[0]["integrity_manifest"] = "{"
        elif variant == "wrong_embedded_type": rows[0]["integrity_manifest"] = "[]"
        else: raise AssertionError(variant)
        return dict(outcome="refused_encoded", reasons=[refuse(lambda: analyze(rows, fmt))
                    for fmt in ("json", "jsonl")], input_sha256=digest(rows))
    if kind == "approval_invalid":
        if variant == "duplicate":
            bad = copy.deepcopy(registry); bad["entries"].append(copy.deepcopy(bad["entries"][0]))
        elif variant == "missing_reason":
            bad = copy.deepcopy(registry); bad["entries"][0].pop("reason")
        elif variant == "wrong_manifest_digest":
            bad = copy.deepcopy(registry); bad["entries"][0]["integrity_manifest_sha256"] = "bad"
        elif variant == "extra_key":
            bad = copy.deepcopy(registry); bad["entries"][0]["unknown"] = True
        else: raise AssertionError(variant)
        return dict(outcome="refused_registry", reason=refuse(lambda: native.validate_baselines(
            engine.decode(encoded(bad).decode()))), input_sha256=digest(bad))
    approved, mode = True, "clean"
    if kind == "truth":
        state, mode = variant.split("_", 1)
        approved = state == "approved"
        if not approved: registry = empty
    elif variant == "module_changed":
        capture["integrity_manifest"]["module_sha256"] = "b"*64
        for row in capture["observations"]: row["module_sha256"] = "b"*64
        approved = False
    elif variant == "split_excluded":
        first = capture["integrity_manifest"]["exclusions"].pop(0)
        capture["integrity_manifest"]["exclusions"][:0] = [dict(first, range_size=1),
            dict(first, range_rva=first["range_rva"]+1, range_size=first["range_size"]-1)]
        approved = False
    elif variant == "array_reorder":
        capture["ranges"].reverse(); capture["integrity_manifest"]["ranges"].reverse(); approved = False
    elif variant == "legacy_registry":
        legacy = copy.deepcopy(capture); legacy.pop("integrity_manifest")
        registry = native.approve(legacy, empty, "Synthetic legacy approval"); approved = False
    elif variant == "legacy_capture": capture.pop("integrity_manifest"); approved = False
    elif variant == "name_64":
        before_name = capture["ranges"][0]["range_name"]
        for row in capture["ranges"] + capture["integrity_manifest"]["ranges"] + capture["observations"]:
            if row["range_name"] == before_name: row["range_name"] = "A"*64
        registry = native.approve(capture, empty, "Explicit Python representation control")
    elif variant != "clean": raise AssertionError(variant)
    if "integrity_manifest" in capture: assert occupancy(capture["integrity_manifest"])
    for row in capture["observations"]:
        if mode == "changed": row["observed_hex"] = "ff"*row["range_size"]
        elif mode == "unavailable": row.update(memory_status="failed", observed_hex=None)
        elif mode == "protection": row["page_protection"] = 64
    expected = TRUTH[approved, mode]
    if mode == "clean":
        new = native.approve(capture, empty, "Fresh explicit approval")
        assert all(r["baseline_approved"] for r in native.convert(capture, new))
    else: refuse(lambda: native.approve(capture, empty, "Must refuse nonclean capture"))
    saved_capture, saved_registry = copy.deepcopy(capture), copy.deepcopy(registry)
    rows, converted = rows_for(capture, registry)
    for row in converted + rows:
        assert (row["baseline_approved"], row["memory_matches"], row["protection_matches"]) == expected[:3]
    summaries, hashes, lengths = [], [], []
    for fmt in ("json", "jsonl"):
        data, config, result, size = analyze(rows, fmt)
        assert all(r["status"] == expected[3] and bool(r["gaps"]) is expected[4] for r in result["records"])
        alternative, _, alternative_result, _ = analyze(rows, fmt, True)
        assert alternative.rows == data.rows and alternative_result["records"] == result["records"]
        assert alternative_result["summary"] == result["summary"]
        summaries.append(result["summary"]); hashes.append(digest(result["records"])); lengths.append(size)
        if fmt == "jsonl" and recipe["save_case"]:
            path = folder / "model.surgecase"; engine.save_case(path, data, None, config, result)
            reopened = engine.open_case(path)
            assert reopened[0].manifest() == data.manifest() and reopened[2] == config and reopened[3] == result
            path.unlink()
    assert summaries[0] == summaries[1] and hashes[0] == hashes[1]
    assert capture == saved_capture and registry == saved_registry
    return dict(outcome="accepted", expected=list(expected), summary=summaries[0], records_sha256=hashes[0],
                input_sha256=digest(capture), encoded_bytes=lengths, case_replay=recipe["save_case"])


def main():
    request = json.loads(sys.stdin.readline()); recipe = request["recipe"]
    hits, arcs, functions, previous = {}, {}, {}, {}
    targets = {str(ROOT/name): name for name in ("engine.py", "native_integrity.py", "integrity_manifest.py", "native_stream.py")}
    def trace(frame, event, arg):
        name = targets.get(frame.f_code.co_filename)
        if name is None: return None
        functions.setdefault(name, set()).add(frame.f_code.co_name)
        if event == "line":
            hits.setdefault(name, set()).add(frame.f_lineno)
            if id(frame) in previous: arcs.setdefault(name, set()).add((previous[id(frame)], frame.f_lineno))
            previous[id(frame)] = frame.f_lineno
        elif event == "return": previous.pop(id(frame), None)
        return trace
    with (patch.object(native, "datetime", FixedFixtureClock), patch.object(stream, "datetime", FixedFixtureClock),
          patch.object(engine, "datetime", FixedFixtureClock)):
        sys.settrace(trace)
        try: result = check(recipe, Path(request["folder"]))
        finally: sys.settrace(None)
    print(json.dumps(dict(status="passed", recipe_sha256=digest(recipe), result=result, result_sha256=digest(result),
                         coverage={name: dict(lines=sorted(hits.get(name, [])), arcs=sorted(arcs.get(name, [])),
                                             functions=sorted(functions.get(name, []))) for name in hits}), sort_keys=True))


if __name__ == "__main__": main()

"""Verify portable model evidence without executing frozen or downloaded code."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
_caller_path = list(sys.path)
try:
    sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
    from run_stream_model import NEGATIVE, FRAMING, REPLAY, SOURCES as STREAM_SOURCES
    from run_manifest_model import MALFORMED, ENCODED, META, SOURCES as MANIFEST_SOURCES
    from retention_contract import CASE_IDS
finally:
    # Runner imports also modify sys.path; keep those changes local to this import.
    sys.path[:] = _caller_path
    del _caller_path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(value): return hashlib.sha256(canonical(value)).hexdigest()


def load(path): return json.loads(path.read_text(encoding="utf-8"))


def required(condition, message):
    if not condition: raise ValueError(message)


def inventories(schema):
    if schema == "surge-stream-model-v1":
        ordinary = {f"positive-{c}-{n}" for c,n in ((2,0),(2,1),(2,6),(3,2),(3,5),(16,1))}
        ordinary |= {kind+"-"+name for kind, names in (("negative",NEGATIVE),("framing",FRAMING),("replay",REPLAY)) for name in names}
        return {phase: set(CASE_IDS) if phase.startswith("boundary") else ordinary
                for phase in ("development","boundary-development","final","replay-1","replay-2","boundary-replay")}
    if schema != "surge-manifest-model-v1": raise ValueError("Unknown model evidence schema")
    ordinary = {f"truth-{a}_{mode}-{count}-{size}" for count in (2,3,16) for size in ("min","max")
                for a in ("approved","unapproved") for mode in ("clean","changed","unavailable","protection")}
    ordinary |= {f"metamorphic-{name}-{count}-{'max' if count==16 else 'min'}" for count in (2,3,16) for name in META}
    # Randomized malformed/encoded fixture cardinality is recorded in the recipe.
    # Its ID must uniquely choose one permitted cardinality for each fixed case.
    ordinary |= {f"malformed-{name.replace(':','_')}-{{count}}-min" for name in MALFORMED}
    ordinary |= {f"encoded-{name}-{{count}}-min" for name in ENCODED}
    ordinary |= {f"approval_invalid-{name}-2-min" for name in ("duplicate","missing_reason","wrong_manifest_digest","extra_key")}
    return {phase: ordinary for phase in ("development","final","replay-1","replay-2")}


def identity_key(row, schema):
    identity=row["id"]
    if schema == "surge-manifest-model-v1" and row["recipe"]["kind"] in ("malformed","encoded"):
        count=row["recipe"]["ranges"]
        required(count in (2,3), "Invalid malformed-fixture cardinality")
        suffix=f"-{count}-min"
        required(identity.endswith(suffix), "Fixture identity differs from its recipe")
        identity=identity[:-len(suffix)]+"-{count}-min"
    return identity


def verify(folder, allow_failed=False):
    folder=Path(folder).resolve()
    manifest=load(folder/"evidence-manifest.json")
    actual={p.relative_to(folder).as_posix() for p in folder.rglob("*")
            if p.is_file() and p.name!="evidence-manifest.json"}
    seen=set()
    for item in manifest:
        name=item["path"]; target=(folder/name).resolve()
        required(name not in seen and target.is_relative_to(folder), "Duplicate or escaping artifact path")
        seen.add(name); raw=target.read_bytes()
        required(type(item["bytes"]) is int and len(raw)==item["bytes"], "Artifact size differs: "+name)
        required(hashlib.sha256(raw).hexdigest()==item["sha256"], "Artifact hash differs: "+name)
    required(actual==seen, "Artifact inventory differs from its manifest")
    report=load(folder/"report.json"); schema=report["schema"]
    inventory=inventories(schema)
    required(report["original_campaign"]=="incomplete", "Original combined campaign was overstated")
    required(report["status"] in ("passed","failed"), "Model attempt was not finalized")
    passed=report["status"]=="passed"
    required(passed or allow_failed, "Model attempt failed; use --allow-failed only to inspect preserved failure evidence")
    required(passed or isinstance(report.get("error"),str) and bool(report["error"]),
             "Failed attempt has no diagnostic")
    limits=report["limits"]
    for key,value in dict(ordinary_input_bytes=262144, process_memory_bytes=1073741824,
                          ordinary_seconds=5, total_seconds=5400, log_bytes=10485760).items():
        required(type(limits.get(key)) is int and limits[key]==value, "Model limit differs: "+key)
    if schema=="surge-stream-model-v1":
        extra=dict(boundary_seconds=15, development_seconds=900, final_seconds=600, replay_seconds=900)
    else:
        extra=dict(development_cases=20000, development_seconds=600, final_cases=10000,
                   final_seconds=300, replay_seconds=900, corpus_bytes=33554432)
    for key,value in extra.items():
        required(type(limits.get(key)) is int and limits[key]==value, "Model limit differs: "+key)
    for name,fingerprint in report["source_sha256"].items():
        target=(folder/"source"/name).resolve()
        required(target.is_relative_to(folder/"source"), "Escaping frozen source path")
        required(hashlib.sha256(target.read_bytes()).hexdigest()==fingerprint, "Frozen source fingerprint differs: "+name)
    required({p.relative_to(folder/"source").as_posix() for p in (folder/"source").rglob("*") if p.is_file()}
             ==set(report["source_sha256"]), "Frozen source inventory differs")
    required(set(report["source_sha256"])==set(STREAM_SOURCES if schema=="surge-stream-model-v1" else MANIFEST_SOURCES),
             "Missing or unknown frozen source fingerprints")
    completed, peaks, durations, coverage, indexed, phases = 0, [], [], {}, {}, {}
    def check_child(parent, directory, control=False):
        child=load(directory/"result.json"); request=load(directory/"request.json")
        required(parent==child or all(k=="payload" or v==child.get(k) for k,v in parent.items()),
                 "Parent and child result differ")
        required(child["recipe_sha256"]==digest(request["recipe"]), "Child recipe fingerprint differs")
        if child["status"] not in ("passed","expected_timeout"):
            required(allow_failed and child.get("error"), "Missing failed-child diagnostic")
            return child,request,None
        required(child["job_limit_verified"] is True and child["process_memory_limit"]==1073741824,
                 "Worker memory limit was not verified")
        peak=child["peak_private_bytes"]
        required(type(peak) is int and 0<peak<=1073741824, "Invalid private-memory peak")
        if child["status"]=="expected_timeout":
            required(control and request["recipe"]["kind"]=="timeout_probe" and child["timed_out"] is True,
                     "Unexpected timeout was relabeled")
            required(child["timeout_seconds"]==5 and child["seconds"]>=5, "Invalid timeout control")
            return child,request,None
        required(child["timed_out"] is False and child["exit_code"]==0, "Successful worker actually failed")
        expected_timeout=15 if request["recipe"]["kind"]=="boundary" else 5
        required(child["timeout_seconds"]==expected_timeout, "Worker deadline differs")
        required(0<=child["seconds"]<=expected_timeout, "Successful worker exceeded deadline")
        payload=load(directory/"stdout.log")
        required(payload==child["payload"], "Child output and recorded payload differ")
        if "payload" in parent:
            required(all(v==payload.get(k) for k,v in parent["payload"].items()), "Parent semantic result differs")
        required(payload["status"]=="passed" and payload["recipe_sha256"]==child["recipe_sha256"], "Child payload identity differs")
        required(payload["result_sha256"]==digest(payload["result"]), "Child semantic fingerprint differs")
        required((directory/"stderr.log").stat().st_size==0, "Successful worker retained an unexplained stderr diagnostic")
        return child,request,payload
    controls={c["id"]:c for c in report["controls"]}
    if passed: required(set(controls)=={"safe_probe","memory_probe","timeout_probe"}, "Missing resource controls")
    for name,item in controls.items():
        child,request,payload=check_child(item["result"],folder/"preflight"/name,True)
        if name!="timeout_probe" and child["status"]=="passed":
            expected={"safe_probe":"safe_allocation_passed","memory_probe":"allocation_refused"}[name]
            required(payload["result"]["outcome"]==expected,"Resource control outcome differs")
    for row in report["runs"]:
        phase=row["phase"]; identity=identity_key(row,schema)
        required(phase in inventory and identity in inventory[phase], "Unknown scenario")
        key=(phase,identity); required(key not in indexed, "Duplicate scenario")
        indexed[key]=row; phases.setdefault(phase,set()).add(identity)
        if row["status"]=="not_run":
            required(not passed,"Passing report has unrun cases"); continue
        directory=folder/phase/row["id"]
        child,request,payload=check_child(row["result"],directory)
        required(request["recipe"]==row["recipe"] and row["status"]==child["status"],"Scenario differs from worker")
        if row["status"]!="passed": continue
        completed+=1; peaks.append(child["peak_private_bytes"]); durations.append(child["seconds"])
        for name,hit in payload.get("coverage",{}).items():
            required(name in report["source_sha256"],"Coverage has no frozen source")
            lines=len((folder/"source"/name).read_text(encoding="utf-8").splitlines())
            required(all(type(n) is int and 1<=n<=lines for n in hit["lines"]),"Coverage line outside frozen source")
            aggregate=coverage.setdefault(name,dict(lines=set(),arcs=set(),functions=set()))
            aggregate["lines"].update(hit["lines"]); aggregate["arcs"].update(map(tuple,hit["arcs"]))
            aggregate["functions"].update(hit["functions"])
    if passed:
        required(phases==inventory,"Incomplete scenario inventory")
        required(report["final_repeatability"]=="passed","Final replay incomplete")
        freeze=load(folder/"final-freeze.json"); final_recipes=load(folder/"final-recipes.json")
        required(freeze["source_sha256"]==report["source_sha256"] and freeze["limits"]==limits,"Final freeze differs")
        checkpoint=copy.deepcopy(report)
        checkpoint["status"]="incomplete"
        checkpoint.pop("final_repeatability",None); checkpoint.pop("campaign_seconds",None)
        checkpoint["runs"]=[r for r in checkpoint["runs"] if r["phase"] in ("development","boundary-development")]
        checkpoint["phases"]=[p for p in checkpoint["phases"] if p["name"] in ("development","boundary-development")]
        checkpoint_text=json.dumps(checkpoint,indent=2)+"\n"
        if b"\r\n" in (folder/"report.json").read_bytes():
            checkpoint_text=checkpoint_text.replace("\n","\r\n")
        checkpoint_bytes=checkpoint_text.encode()
        required(hashlib.sha256(checkpoint_bytes).hexdigest()==freeze["development_report_sha256"],
                 "Final freeze does not bind the completed development checkpoint")
        required(len(final_recipes)==len(inventory["final"]),"Missing concrete final recipes")
        for item in final_recipes:
            candidate=dict(id=item["id"],recipe=item["recipe"])
            identity=identity_key(candidate,schema)
            rows=[indexed[phase,identity] for phase in ("final","replay-1","replay-2")]
            required(all(r["recipe"]==item["recipe"] for r in rows),"Final recipe was changed on replay")
            required(len({r["result"]["payload"]["result_sha256"] for r in rows})==1,"Final semantic replay differs")
        if schema=="surge-stream-model-v1":
            for identity in CASE_IDS:
                a,b=(indexed[phase,identity] for phase in ("boundary-development","boundary-replay"))
                required(a["result"]["payload"]["result_sha256"]==b["result"]["payload"]["result_sha256"],"Boundary replay differs")
        phase_times={p["name"]:p["seconds"] for p in report["phases"]}
        required(set(phase_times)==set(inventory),"Missing phase timing")
        previous=report.get("prior_seconds",{})
        for label,names in (("development",("development","boundary-development")),("final",("final",)),("replay",("replay-1","replay-2","boundary-replay"))):
            required(sum(phase_times.get(n,0) for n in names)+previous.get(label,0)<=limits[label+"_seconds"],"Phase time budget exceeded")
        required(report["campaign_seconds"]+previous.get("total",0)<=5400,"Total component time budget exceeded")
    log_bytes=sum(p.stat().st_size for p in folder.rglob("*.log"))
    corpus_bytes=sum(p.stat().st_size for p in folder.rglob("request.json"))
    required(log_bytes<=10485760 and corpus_bytes<=33554432,"Evidence log/corpus budget exceeded")
    return dict(status="passed" if passed else "failed_attempt_preserved", schema=schema,
                evidence_files=len(manifest), retained_bytes=sum(item["bytes"] for item in manifest),
                completed_cases=completed, log_bytes=log_bytes, ordinary_recipe_bytes=corpus_bytes,
                maximum_private_bytes=max(peaks,default=0), maximum_case_seconds=max(durations,default=0),
                original_campaign="incomplete", final_variant_status=report.get("final_variant_status","post_freeze_synthetic_variants"),
                coverage={name:dict(executed_lines=len(v["lines"]),executed_arcs=len(v["arcs"]),functions=sorted(v["functions"]))
                          for name,v in coverage.items()})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("folder",type=Path)
    parser.add_argument("--allow-failed",action="store_true")
    arguments=parser.parse_args()
    print(json.dumps(verify(arguments.folder,arguments.allow_failed),sort_keys=True,indent=2))

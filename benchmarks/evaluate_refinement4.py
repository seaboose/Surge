"""Freeze and score one candidate once; never optimize using holdout results.

Run `freeze` only after security review and parent authorization. Run `evaluate`
only after that freeze. Snapshots are local integrity records, not OS isolation.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from prepare_refinement4 import OUT, PRIOR, ROOT, selection, write_new
from prepare_rt_iot2022 import NORMAL, ATTACK, encoded, sha

APP = ROOT.parents[1]
PLAN_SHA = "90340630356002ba45fd5f7284e12f0dee8c5a80d2ef2b5cd009bf54699d793d"
ADDENDUM_SHA = "d95722c6aac87be1086c879ee8a7cf8029aefeb802adb1d7b2f77d65055df3c1"
DEVELOPMENT_GATES = frozenset(
    (
        "total_false_positives_lower",
        "targeted_subgroup_present",
        "targeted_subgroup_false_positives_lower",
        "misses_not_higher",
        "no_targets_lost",
        "legitimate_unknown_not_higher",
        "no_legitimate_subgroup_regression",
        "no_legitimate_subgroup_unknown_regression",
        "long_duration_false_positives_not_higher",
        "long_duration_unresolved_not_higher",
    )
)
SCRIPTS = (
    "benchmarks/evaluate_refinement4.py",
    "benchmarks/prepare_refinement4.py",
    "benchmarks/prepare_rt_iot2022.py",
    "benchmarks/test_refinement4_protocol.py",
    "verification/audit_refinement4_evaluation.py",
)


def verify_plan():
    if sha((OUT / "protocol-addendum.json").read_bytes()) != ADDENDUM_SHA:
        raise ValueError("Reserved acceptance addendum changed.")
    if sha((OUT / "plan.json").read_bytes()) != PLAN_SHA:
        raise ValueError("Reserved holdout plan changed.")
    plan = json.loads((OUT / "plan.json").read_text())
    for name, digest in plan["prior_files"].items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise ValueError(f"Prior input changed: {name}")
    for name, digest in plan["baseline_files"].items():
        if sha((OUT / "baseline" / name).read_bytes()) != digest:
            raise ValueError(f"Baseline changed: {name}")
    if sha((ROOT / "source.zip").read_bytes()) != plan["archive_sha256"]:
        raise ValueError("Source archive changed.")
    if (
        sha((ROOT / "refinement-1/development.labels.json").read_bytes())
        != plan["development_labels_sha256"]
    ):
        raise ValueError("Development labels changed.")
    return plan


def code_files():
    files = (
        list(APP.glob("*.py"))
        + list((APP / "desktop").glob("*.cjs"))
        + list((APP / "desktop/src").glob("*"))
    )
    files += [APP / "desktop/package.json"]
    return sorted(p for p in files if p.is_file())


def freeze():
    verify_plan()
    if (OUT / "freeze.json").exists() or (OUT / "holdout-opened.json").exists():
        raise ValueError("Candidate already frozen or holdout already opened.")
    policy_path = OUT / "candidate.policy.json"
    policy = json.loads(policy_path.read_text())
    if policy.get("schema") != "surge-policy-v1":
        raise ValueError("Candidate policy required.")
    development = json.loads((OUT / "development-selection.json").read_text())
    security = json.loads((APP / "verification/refinement4-security-review.json").read_text())
    policy_digest = sha(policy_path.read_bytes())
    if (
        development["policy_sha256"] != policy_digest
        or development["selected"] != policy["settings"]
    ):
        raise ValueError("Submitted policy differs from development selection.")
    gates = development.get("gates", {})
    if (
        development.get("reservation_sha256") != PLAN_SHA
        or development.get("addendum_sha256") != ADDENDUM_SHA
        or not isinstance(gates, dict)
        or not DEVELOPMENT_GATES <= gates.keys()
        or not all(value is True for value in gates.values())
    ):
        raise ValueError("Development selection does not pass the reserved plan.")
    for name, digest in development["hashes"].items():
        if sha((APP / name).read_bytes()) != digest:
            raise ValueError(f"Development selection dependency changed: {name}")
    reviewed_policy = security["reviewed_sha256"][
        "benchmarks/rt-iot2022/refinement-4/candidate.policy.json"
    ]
    if security["blocking_findings"] or reviewed_policy != policy_digest:
        raise ValueError("Submitted policy lacks a matching unblocked security review.")
    for name, digest in security["reviewed_sha256"].items():
        if sha((APP / name).read_bytes()) != digest:
            raise ValueError(f"Security-reviewed dependency changed: {name}")
    snapshot = OUT / "candidate-source"
    snapshot.mkdir(exist_ok=False)
    hashes = {}
    for path in code_files():
        relative = path.relative_to(APP)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        with target.open("xb") as stream:
            stream.write(raw)
        hashes[relative.as_posix()] = sha(raw)
    frozen = dict(
        created_at=datetime.now(timezone.utc).isoformat(),
        plan_sha256=PLAN_SHA,
        protocol_addendum_sha256=ADDENDUM_SHA,
        candidate_policy_sha256=sha(policy_path.read_bytes()),
        candidate_source=hashes,
        development_selection_sha256=sha((OUT / "development-selection.json").read_bytes()),
        edge_protocol_sha256=sha((ROOT / "protocol.json").read_bytes()),
        security_review_sha256=sha(
            (APP / "verification/refinement4-security-review.json").read_bytes()
        ),
        baseline_manifest_sha256=sha((OUT / "baseline-source/manifest.json").read_bytes()),
        evaluator_source={name: sha((APP / name).read_bytes()) for name in SCRIPTS},
        authorization="Parent authorized after development selection, integration tests, and security review; candidate fixed before holdout materialization.",
    )
    write_new(OUT / "freeze.json", frozen)
    print(
        json.dumps(
            dict(
                frozen=True,
                freeze_sha256=sha((OUT / "freeze.json").read_bytes()),
                candidate_policy_sha256=frozen["candidate_policy_sha256"],
                source_files=len(hashes),
            ),
            indent=2,
        )
    )


def verify_freeze():
    plan = verify_plan()
    frozen = json.loads((OUT / "freeze.json").read_text())
    if frozen["protocol_addendum_sha256"] != ADDENDUM_SHA:
        raise ValueError("Freeze names wrong acceptance addendum.")
    if frozen["plan_sha256"] != PLAN_SHA:
        raise ValueError("Freeze names wrong plan.")
    if sha((OUT / "candidate.policy.json").read_bytes()) != frozen["candidate_policy_sha256"]:
        raise ValueError("Candidate policy changed after freeze.")
    if (
        sha((OUT / "development-selection.json").read_bytes())
        != frozen["development_selection_sha256"]
    ):
        raise ValueError("Development selection record changed after freeze.")
    if sha((ROOT / "protocol.json").read_bytes()) != frozen["edge_protocol_sha256"]:
        raise ValueError("Reference-only edge protocol changed after freeze.")
    if (
        sha((APP / "verification/refinement4-security-review.json").read_bytes())
        != frozen["security_review_sha256"]
    ):
        raise ValueError("Security review changed after freeze.")
    for name, digest in frozen["candidate_source"].items():
        if (
            sha((OUT / "candidate-source" / name).read_bytes()) != digest
            or sha((APP / name).read_bytes()) != digest
        ):
            raise ValueError(f"Candidate source changed after freeze: {name}")
    for name, digest in frozen["evaluator_source"].items():
        if sha((APP / name).read_bytes()) != digest:
            raise ValueError(f"Evaluator source changed after freeze: {name}")
    baseline_manifest = OUT / "baseline-source/manifest.json"
    if sha(baseline_manifest.read_bytes()) != frozen["baseline_manifest_sha256"]:
        raise ValueError("Baseline manifest changed.")
    for name, digest in json.loads(baseline_manifest.read_text()).items():
        if sha((OUT / "baseline-source" / name).read_bytes()) != digest:
            raise ValueError(f"Baseline source changed: {name}")
    # Critical baseline dependencies were committed before implementation began.
    for name in ("engine.py", "evaluation.py", "import_errors.py"):
        if sha((OUT / "baseline-source" / name).read_bytes()) != plan["baseline_files"][name]:
            raise ValueError(f"Baseline snapshot differs from committed file: {name}")
    return plan, frozen


def score(which):
    # Executed in a separate process, with only one engine version on sys.path.
    # This preserves version identity; it is not a hostile-code sandbox.
    verify_freeze()
    opened = json.loads((OUT / "holdout-opened.json").read_text())
    materialized = json.loads((OUT / "materialization.json").read_text())
    freeze_digest = sha((OUT / "freeze.json").read_bytes())
    if opened["freeze_sha256"] != freeze_digest or materialized["freeze_sha256"] != freeze_digest:
        raise ValueError("Materialized holdout belongs to another freeze.")
    for name, key in [("holdout.json", "source_sha256"), ("holdout.labels.json", "labels_sha256")]:
        if sha((OUT / name).read_bytes()) != materialized[key]:
            raise ValueError("Materialized holdout was changed.")
    snapshot = OUT / ("baseline-source" if which == "baseline" else "candidate-source")
    sys.path.insert(0, str(snapshot))
    import engine
    import evaluation

    source = engine.load_dataset(OUT / "holdout.json")
    reference = engine.load_dataset(ROOT / "reference.json")
    policy_path = OUT / ("baseline/policy.json" if which == "baseline" else "candidate.policy.json")
    config = json.loads(policy_path.read_text())["settings"]
    result = engine.analyze(source, reference, config)
    # Truth enters evaluation only after detection finishes.
    labels = evaluation.load(OUT / "holdout.labels.json", source)
    report = evaluation.evaluate(source, reference, config, result, labels)
    evaluation.write_new(OUT / (which + ".evaluation.json"), report)
    engine.save_case(OUT / (which + ".case.json"), source, reference, config, result)


def compare_reports(old, new, source, labels, edge_cutoff):
    if not len(old["records"]) == len(new["records"]) == len(source) == len(labels["labels"]):
        raise ValueError("Paired reports, source, and labels differ in length.")
    changes = dict(
        new_misses=[], recovered_targets=[], resolved_false_positives=[], new_false_positives=[]
    )
    for before, after in zip(old["records"], new["records"], strict=True):
        if (
            before["row"] != after["row"]
            or before["truth"] != after["truth"]
            or before["group"] != after["group"]
        ):
            raise ValueError("Paired evaluations do not identify the same records.")
        if before["outcome"] == "Detected" and after["outcome"] == "Missed":
            changes["new_misses"].append(after["row"])
        if before["outcome"] == "Missed" and after["outcome"] == "Detected":
            changes["recovered_targets"].append(after["row"])
        if before["outcome"] == "False positive" and after["outcome"] == "Clear":
            changes["resolved_false_positives"].append(after["row"])
        if (
            before["truth"] == "legitimate"
            and before["outcome"] != "False positive"
            and after["outcome"] == "False positive"
        ):
            changes["new_false_positives"].append(after["row"])
    b, c = old["summary"]["counts"], new["summary"]["counts"]
    old_groups = {g["group"]: g for g in old["groups"]}
    new_groups = {g["group"]: g for g in new["groups"]}
    if set(old_groups) != set(new_groups):
        raise ValueError("Paired evaluations do not identify the same groups.")
    legitimate_groups = {name for name, group in old_groups.items() if group["legitimate"]}
    for name, before in old_groups.items():
        after = new_groups[name]
        if (before["legitimate"], before["targets"]) != (after["legitimate"], after["targets"]):
            raise ValueError("Paired group denominators changed.")
    targeted = "Wipro_bulb"
    targeted_present = targeted in legitimate_groups
    gates = dict(
        false_positives_lower=c["False positive"] < b["False positive"],
        targeted_subgroup_present=targeted_present,
        targeted_subgroup_false_positives_lower=targeted_present
        and new_groups[targeted]["counts"]["False positive"]
        < old_groups[targeted]["counts"]["False positive"],
        no_legitimate_subgroup_false_positive_regression=all(
            new_groups[g]["counts"]["False positive"] <= old_groups[g]["counts"]["False positive"]
            for g in legitimate_groups
        ),
        no_legitimate_subgroup_unresolved_regression=all(
            new_groups[g]["counts"]["Unresolved"] <= old_groups[g]["counts"]["Unresolved"]
            for g in legitimate_groups
        ),
        misses_not_higher=c["Missed"] <= b["Missed"],
        no_previously_detected_targets_lost=not changes["new_misses"],
        legitimate_unresolved_not_higher=c["Unresolved"] <= b["Unresolved"],
    )
    edge_rows = {
        n
        for n, (row, label) in enumerate(zip(source, labels["labels"], strict=True), 1)
        if label["truth"] == "legitimate" and float(row["flow_duration"]) > edge_cutoff
    }

    def edge(report):
        return dict(
            records=len(edge_rows),
            false_positives=sum(
                r["row"] in edge_rows and r["outcome"] == "False positive"
                for r in report["records"]
            ),
            unresolved=sum(
                r["row"] in edge_rows and r["outcome"] == "Unresolved" for r in report["records"]
            ),
        )

    before_edge, after_edge = edge(old), edge(new)
    gates["long_duration_false_positives_not_higher"] = (
        after_edge["false_positives"] <= before_edge["false_positives"]
    )
    gates["long_duration_unresolved_not_higher"] = (
        after_edge["unresolved"] <= before_edge["unresolved"]
    )
    return dict(
        accepted=all(gates.values()),
        gates=gates,
        baseline=old["summary"],
        candidate=new["summary"],
        **changes,
        groups=dict(baseline=old["groups"], candidate=new["groups"]),
        targeted_subgroup=targeted,
        legitimate_groups_checked=sorted(legitimate_groups),
        subgroup_limit="Every represented legitimate publisher group is checked; absent groups are not validated and sparse groups have weak evidence.",
        unknown_counts={
            name: sum(r["status"] == "Unknown" for r in report["records"])
            for name, report in [("baseline", old), ("candidate", new)]
        },
        long_duration=dict(cutoff=edge_cutoff, baseline=before_edge, candidate=after_edge),
        limits="Fresh rows and projected vectors from the same public IoT capture; not independent sessions, anti-cheat, or AI-attack validation. No future miss-rate guarantee. No holdout-guided retuning.",
        protection="Role-separated, deferred holdout, committed membership and frozen code/policy; shared filesystem identity is not OS-enforced access isolation.",
    )


def evaluate():
    plan, frozen = verify_freeze()
    # Spend the holdout before data/labels are materialized; failures cannot
    # silently permit another candidate or reranked split.
    write_new(
        OUT / "holdout-opened.json",
        dict(
            opened_at=datetime.now(timezone.utc).isoformat(),
            freeze_sha256=sha((OUT / "freeze.json").read_bytes()),
            plan_sha256=PLAN_SHA,
            candidate_policy_sha256=frozen["candidate_policy_sha256"],
        ),
    )
    chosen, counts = selection(plan["sampling_salt"], include_truth=True)
    if counts["membership_sha256"] != plan["membership_sha256"]:
        raise ValueError("Reserved holdout membership changed.")
    inputs = [dict(source_record=item[1], **item[3]) for item in chosen]
    write_new(OUT / "holdout.json", inputs)
    labels = []
    for n, item in enumerate(chosen, 1):
        truth = item[4]
        if truth not in NORMAL | ATTACK:
            raise ValueError("Unexpected publisher class.")
        labels.append(
            dict(
                row=n,
                truth="legitimate" if truth in NORMAL else "target",
                group=truth,
                note=f"Publisher Attack_type={truth}; original source record {item[1]}.",
            )
        )
    label_doc = dict(
        schema="surge-labels-v1",
        source_sha256=sha((OUT / "holdout.json").read_bytes()),
        provenance=dict(
            author="RT-IoT2022 authors / UCI",
            method="Publisher class labels, unchanged; not independently re-audited.",
            partition=plan["selection"] + " Same capture; session independence not established.",
            purpose="holdout",
            independent_of_detector=True,
        ),
        labels=labels,
    )
    write_new(OUT / "holdout.labels.json", label_doc)
    write_new(
        OUT / "materialization.json",
        dict(
            **counts,
            source_sha256=label_doc["source_sha256"],
            labels_sha256=sha((OUT / "holdout.labels.json").read_bytes()),
            excluded_prior_vector_overlap=0,
            freeze_sha256=sha((OUT / "freeze.json").read_bytes()),
        ),
    )
    for which in ("baseline", "candidate"):
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "_score", which], cwd=APP, check=True
        )
    verify_freeze()
    reports = [
        json.loads((OUT / (which + ".evaluation.json")).read_text())
        for which in ("baseline", "candidate")
    ]
    cutoff = json.loads((ROOT / "protocol.json").read_text())["duration_edge_cutoff"]
    summary = compare_reports(*reports, inputs, label_doc, cutoff)
    write_new(OUT / "holdout-comparison.json", summary)
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k
                not in (
                    "groups",
                    "new_misses",
                    "recovered_targets",
                    "resolved_false_positives",
                    "new_false_positives",
                )
            }
            | {
                k: len(summary[k])
                for k in (
                    "new_misses",
                    "recovered_targets",
                    "resolved_false_positives",
                    "new_false_positives",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "evaluate", "_score"))
    parser.add_argument("which", nargs="?", choices=("baseline", "candidate"))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    elif args.action == "evaluate":
        evaluate()
    elif args.which:
        score(args.which)
    else:
        parser.error("_score requires an engine version")

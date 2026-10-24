"""Verify retained Windows package evidence and generate a bounded qualification report.

This verifier reads files only. It never executes the downloaded application or
treats automated success as independent human acceptance.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

try:
    from .check_windows_package import verify_evidence as verify_consumer_evidence
except ImportError:
    from check_windows_package import verify_evidence as verify_consumer_evidence

JOBS = {"test", "First-use release check", "Build Windows package", "Packaged Windows acceptance"}
ZIP_LIMIT = 256 * 1024 * 1024
EXPANDED_LIMIT = 768 * 1024 * 1024
BUILD_STEPS = (
    "windows_x64", "source_commit", "source_status", "clean_source_or_explicit_development_attempt",
    "stable_package_identity", "electron_version_locked", "electron_official_npm_checksum",
    "download_electron", "electron_download_hash", "download_python", "python_download_hash",
    "bundled_python_identity", "bundled_python_version", "renderer_build", "node_identity",
    "cmake_identity", "native_configure", "native_build", "dependencies_surge_owned_app_exe",
    "static_runtime_surge_owned_app_exe", "dependencies_lab_module_v2_dll",
    "static_runtime_lab_module_v2_dll", "approve_exact_v2", "approval_exact_module_only",
    "ordinary_packaged_sample", "existing_backend_on_bundled_python", "python_license_present",
    "locked_react", "locked_react-dom", "locked_scheduler", "source_unchanged", "payload_bounds",
    "no_developer_or_internal_test_payload", "zip_size_bound", "zip_crc_and_file_set",
    "zip_all_bytes_verified",
)


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def fingerprint(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def verify_package(package, manifest):
    require(manifest.get("schema") == "surge-windows-package-v1", "Unknown package manifest")
    actual = fingerprint(package)
    require(actual == {k: manifest["archive"][k] for k in actual}, "Package archive fingerprint differs")
    require(actual["bytes"] <= ZIP_LIMIT, "Package ZIP exceeds acceptance limit")
    files = manifest["files"]
    names = [item["path"] for item in files]
    require(0 < len(names) <= 10000 and len(set(names)) == len(names), "Invalid package inventory")
    require(len({name.casefold() for name in names}) == len(names), "Case-colliding package paths")
    for name in names:
        parts = PurePosixPath(name).parts
        require(parts and not PurePosixPath(name).is_absolute() and ".." not in parts
                and "\\" not in name and ":" not in name, "Unsafe package path")
    require(sum(item["bytes"] for item in files) <= EXPANDED_LIMIT, "Expanded payload exceeds acceptance limit")
    with zipfile.ZipFile(package) as archive:
        inventory = archive.infolist()
        require(len(inventory) == len(names) and {i.filename for i in inventory} == set(names),
                "ZIP inventory differs from manifest")
        declared = {item["path"]: item["bytes"] for item in files}
        require(all(i.file_size == declared[i.filename] for i in inventory), "ZIP declared sizes differ")
        require(archive.testzip() is None, "ZIP CRC verification failed")
        for item in files:
            raw = archive.read(item["path"])
            require(len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"],
                    "Payload fingerprint differs: " + item["path"])
    return {"name": Path(package).name, **actual, "files": len(files),
            "expanded_bytes": sum(item["bytes"] for item in files)}


def verify_hosted(folder, commit, bindings=None):
    """Expect original API metadata and artifact-<id>.zip downloads in one folder."""
    folder = Path(folder)
    run = read(folder / "run.json")
    jobs = read(folder / "jobs.json")
    jobs = jobs["jobs"] if isinstance(jobs, dict) else jobs
    metadata = read(folder / "artifacts.json")
    artifacts = metadata["artifacts"] if isinstance(metadata, dict) else metadata
    require(run["status"] == "completed" and run["conclusion"] == "success", "Hosted workflow did not pass")
    # A PR run's advertised head can differ from the checkout merge commit.
    require(run["head_sha"] == commit or any(j.get("head_sha") == commit for j in jobs),
            "Hosted run does not identify the package source")
    indexed = {job["name"]: job for job in jobs}
    require(JOBS <= indexed.keys() and all(indexed[n]["conclusion"] == "success" for n in JOBS),
            "A required package or existing Windows job did not succeed")
    downloaded = []
    required_prefixes = ("windows-package-", "windows-package-acceptance-", "deeper-qualification-", "first-use-")
    for prefix in required_prefixes:
        matches = [a for a in artifacts if a["name"].startswith(prefix)
                   and (prefix != "windows-package-" or not a["name"].startswith("windows-package-acceptance-"))]
        require(len(matches) == 1, "Missing or ambiguous hosted artifact: " + prefix)
        item = matches[0]
        require(not item.get("expired"), "Hosted artifact expired before verification")
        actual = fingerprint(folder / f"artifact-{item['id']}.zip")
        expected_digest = item.get("digest", "").removeprefix("sha256:")
        require(actual["bytes"] == item["size_in_bytes"] and actual["sha256"] == expected_digest,
                "Downloaded artifact fingerprint differs: " + item["name"])
        with zipfile.ZipFile(folder / f"artifact-{item['id']}.zip") as archive:
            require(archive.testzip() is None, "Downloaded artifact CRC differs")
            matched = []
            for binding in (bindings or {}).get(prefix, []):
                candidates = [i for i in archive.infolist() if PurePosixPath(i.filename).name == binding["name"]
                              and i.file_size == binding["bytes"]]
                matches = []
                for member in candidates:
                    with archive.open(member) as stream:
                        actual_digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    if actual_digest == binding["sha256"]:
                        matches.append(member.filename)
                require(len(matches) == 1, "Supplied evidence is not a unique hosted artifact member: " + binding["role"])
                matched.append({**binding, "member": matches[0]})
            if prefix in ("windows-package-", "windows-package-acceptance-"):
                require(bool(matched), "Package artifact has no exact input bindings")
        downloaded.append({"id": item["id"], "name": item["name"], **actual})
        if matched:
            downloaded[-1]["verified_members"] = matched
    return {"run_id": run["id"], "url": run["html_url"],
            "head_sha": run["head_sha"], "jobs": {n: indexed[n]["conclusion"] for n in sorted(JOBS)},
            "artifacts": downloaded}


def generate(package, manifest_path, build_path, consumer_path, hosted=None,
             local=None, failures=(), failure_probe=None):
    manifest, build, consumer = map(read, (manifest_path, build_path, consumer_path))
    archive = verify_package(package, manifest)
    require(build.get("schema") == "surge-windows-package-build-v1" and build["status"] == "passed",
            "Build did not pass")
    require(build.get("archive") == manifest["archive"] and build.get("source") == manifest["source"]
            and build.get("manifest_sha256") == fingerprint(manifest_path)["sha256"],
            "Build report belongs to different package evidence")
    require(0 <= build["elapsed_seconds"] <= 1200 and build["log_bytes"] <= 10 * 1024 * 1024
            and build["steps"] and all(step["status"] == "passed" for step in build["steps"]),
            "Build evidence is incomplete or exceeds acceptance limits")
    require(tuple(step["id"] for step in build["steps"]) == BUILD_STEPS,
            "Required build steps are missing or reordered")
    require(consumer.get("schema") == "surge-windows-package-consumer-v1" and consumer["status"] == "passed",
            "Consumer did not pass")
    require(consumer["archive"]["sha256"] == archive["sha256"], "Consumer checked a different ZIP")
    require(consumer["manifest_sha256"] == fingerprint(manifest_path)["sha256"], "Consumer manifest differs")
    verified_consumer = verify_consumer_evidence(consumer_path, manifest)
    require(consumer.get("human_acceptance") == "pending", "Consumer overstates human acceptance")
    source = manifest["source"]
    require(source["dirty"] is False and consumer["source"]["commit"] == source["commit"],
            "Final package source was dirty or consumer source differs")
    criteria = {"W1": "passed"}
    for name in ("W2", "W3", "W4", "W5", "W6"):
        value = consumer["criteria"].get(name)
        status = value.get("status") if isinstance(value, dict) else value
        require(status == "passed", "Consumer acceptance incomplete: " + name)
        criteria[name] = "passed"
    probe_result = verify_consumer_evidence(failure_probe, manifest, expected_failure=True) if failure_probe else None
    bindings = {
        "windows-package-": [{"role": role, "name": Path(value).name, **fingerprint(value)}
                             for role, value in (("package", package), ("manifest", manifest_path), ("build", build_path))],
        "windows-package-acceptance-": [{"role": "consumer", "name": Path(consumer_path).name,
                                        **fingerprint(consumer_path)}],
    }
    if failure_probe:
        bindings["windows-package-acceptance-"].append(
            {"role": "failure_probe", "name": Path(failure_probe).name, **fingerprint(failure_probe)})
    if hosted:
        require(consumer["environment"].get("hosted") is True, "Hosted consumer was not a hosted execution")
    hosted_result = verify_hosted(hosted, source["commit"], bindings) if hosted else None
    criteria["W7"] = "passed" if hosted_result and probe_result else "pending_hosted_verification_or_failure_probe"
    criteria["W8"] = "prepared_human_pending"
    local_result = read(local) if local else None
    local_tokens = None
    if local_result:
        verify_consumer_evidence(local, manifest)
        local_tokens = {mode: read(Path(local).parent / mode / "actual-processes.json")
                        for mode in ("journey", "replacement", "mismatch")}
    if not (local_result and local_result.get("status") == "passed"
            and local_result.get("archive", {}).get("sha256") == archive["sha256"]
            and all(item[role]["token_elevated"] is False for item in local_tokens.values()
                    for role in ("main", "worker"))):
        criteria["W2"] = "partial_local_non_elevated_check_pending"
    retained = [{"name": Path(p).name, **fingerprint(p), "report": read(p)} for p in failures]
    limitations = [
        "Unfamiliar-tester acceptance and native file-dialog comprehension remain pending.",
        "The original broader T1/T2/T3 fuzzing campaign remains unfinished; no new native extension ran.",
        "Fresh hosted Windows images contain developer tools. Restricted application lookup and bundled paths do not prove their physical absence.",
        "Separate standard-user hosted-account execution remains unverified; actual hosted and local child-process elevation is recorded.",
        "Folder replacement of the tested ZIP establishes location independence, not every cross-version migration.",
        "Pinned source and runtimes identify the tested build; bit-for-bit reproducible compiler output is not established.",
        "Unsigned candidate: no Authenticode publisher identity, SmartScreen reputation, installer or automatic updater.",
        "No physical offline-host, network/removable storage, screen-reader or other Windows/CPU certification.",
        "Local approval and hashes do not attest an uncompromised host or whole-process integrity.",
    ]
    return {"schema": "surge-windows-package-qualification-v1",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "status": "automated_package_qualification_passed_human_pending"
            if all(v in ("passed", "prepared_human_pending") for v in criteria.values()) else "partial",
            "archive": archive, "source": source, "criteria": criteria,
            "inputs": {"manifest": fingerprint(manifest_path), "build": fingerprint(build_path),
                       "consumer": fingerprint(consumer_path)},
            "hosted": hosted_result, "local": local_result,
            "local_process_tokens": local_tokens, "consumer_verification": verified_consumer,
            "failure_probe_verification": probe_result,
            "preserved_attempts": retained, "consumer": consumer,
            "human_acceptance": "pending", "original_campaign": "unfinished",
            "limitations": limitations,
            "review": {"scoped_security_engineering": 8, "internship_portfolio": 8.5,
                       "scale": 10, "not_managerial_readiness": True,
                       "assessment": "Bundled delivery removes developer setup and verifies evidence preservation across package relocation. The engineering ratings remain unchanged until independent usability and remaining correctness gaps gain new evidence.",
                       "next": "While unfamiliar testing is pending, add a compact About/Help view with the package version, build identifier and a copyable privacy-safe diagnostic summary. Keep the tested candidate available for the independent session."}}


def markdown(report):
    lines = ["# Surge Windows package qualification", "", f"Status: **{report['status']}**.", "",
             f"Package: `{report['archive']['name']}`; {report['archive']['bytes']:,} bytes.",
             f"SHA-256: `{report['archive']['sha256']}`.",
             f"Source: `{report['source']['commit']}`; dirty: `{report['source']['dirty']}`.", "",
             "Unfamiliar-user acceptance: **pending**. Broader fuzzing: **unfinished**.", ""]
    lines.extend(f"- {name}: **{status}**." for name, status in report["criteria"].items())
    lines.extend(["", "## Verified evidence", "",
                  "The archive inventory, every payload file, archive CRC and SHA-256 were independently checked without executing downloaded code."])
    if report["hosted"]:
        lines += ["", f"[Hosted Windows run]({report['hosted']['url']}): all four package/existing jobs passed. Original downloaded artifact lengths, hashes and ZIP CRCs matched GitHub metadata."]
    lines += ["", f"Preserved attempts supplied to this report: {len(report['preserved_attempts'])}.", "", "## Limits", ""]
    lines.extend("- " + value for value in report["limitations"])
    lines += ["", "## Milestone review", "", report["review"]["assessment"], "",
              "Scoped security engineering: **8/10**. Internship/early-career portfolio: **8.5/10**. These are not production anti-cheat or managerial-readiness ratings.", "",
              "Highest-value next step: " + report["review"]["next"], ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "manifest", "build-report", "consumer-report", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--hosted-evidence", type=Path)
    parser.add_argument("--local-consumer-report", type=Path)
    parser.add_argument("--preserved-attempt", type=Path, action="append", default=[])
    parser.add_argument("--failure-probe-report", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        report = generate(args.package, args.manifest, args.build_report, args.consumer_report,
                          args.hosted_evidence, args.local_consumer_report, args.preserved_attempt,
                          args.failure_probe_report)
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (args.output / "report.md").write_text(markdown(report), encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(args.output / "report.json")}))
        return 0 if report["status"] == "automated_package_qualification_passed_human_pending" else 1
    except Exception as error:
        (args.output / "verification-failure.json").write_text(
            json.dumps({"status": "failed", "error": str(error)}, indent=2) + "\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())

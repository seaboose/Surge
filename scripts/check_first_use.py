"""Package and verify the owned-sample first-use workflow; human acceptance stays pending."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

try:
    from . import qualify
    from .release_files import ROOT, source_files
except ImportError:
    import qualify
    from release_files import ROOT, source_files

TOTAL_SECONDS = 1800
UI_MINIMUM = {"replay": 8, "unapproved": 5, "approved": 6, "library": 9, "deletion": 3, "saved": 10}
LIMITS = [
    "Unfamiliar-tester acceptance is pending; no human comprehension or uncoached usability claim.",
    "Existing Windows host/user/toolchains; empty task-local dependency caches are not a fresh OS.",
    "Isolated Electron entry wrappers and substituted native file dialogs; normal launcher not tested.",
    "Original T1/T2/T3 fuzzing remains incomplete; no sanitizer, full qualification or endurance rerun.",
    "Hosted CI execution and repository branch-protection settings are separate from local validation.",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_for(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in source_files(root)}


def verify_source(root, manifest):
    # Comparing the complete publishable set also rejects unexpected source additions.
    if manifest_for(root) != manifest:
        raise ValueError("source_manifest_mismatch")


def environment(folder):
    env = qualify.test_environment(folder / "temp")
    for key in list(env):
        if key.lower().startswith(("npm_config_", "pnpm_config_", "electron_")):
            env.pop(key)
    env.pop("NODE_OPTIONS", None)
    env.update(PNPM_CONFIG_STORE_DIR=str(folder / "caches/pnpm"),
               electron_config_cache=str(folder / "caches/electron"),
               npm_config_cache=str(folder / "caches/npm"))
    return env


def plan(frozen, extracted):
    py = str(extracted / ".venv/Scripts/python.exe")
    steps = [
        ("package", [sys.executable, "-B", "scripts/package_source.py"], frozen, 60),
        ("cache_path", ["powershell.exe", "-NoProfile", "-Command", "pnpm store path"], extracted, 30),
        ("setup", ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "Setup-Surge.ps1", "-Python", sys.executable], extracted, 600),
        ("replay", ["node", "first-use.test.cjs", "replay"], extracted / "desktop", 180),
        ("native_configure", ["cmake", "-S", "native", "-B", "native/build", "-A", "x64"], extracted, 300),
        ("native_build", ["cmake", "--build", "native/build", "--config", "Release", "--", "/nodeReuse:false"], extracted, 300),
        ("native_ctest", ["ctest", "--test-dir", "native/build", "-C", "Release", "--output-on-failure", "--no-tests=error", "--timeout", "60"], extracted, 180),
        ("unapproved", ["node", "first-use.test.cjs", "unapproved"], extracted / "desktop", 180),
        ("approve", [py, "-B", "scripts/native_capture.py", "approve", "--build", "v2", "--reason", "Reviewed owned v2 fixture; isolated release check only"], extracted, 60),
        ("approved", ["node", "first-use.test.cjs", "approved"], extracted / "desktop", 180),
        ("library", ["node", "library-ui.test.cjs"], extracted / "desktop", 180),
        ("deletion", ["node", "library-deletion.test.cjs"], extracted / "desktop", 180),
        ("saved", ["node", "saved-flow.test.cjs"], extracted / "desktop", 180),
        ("replays", [py, "-B", "scripts/verify_native_demo.py"], extracted, 60),
        ("hygiene", [py, "-B", "scripts/check_release.py"], extracted, 60),
        ("format", ["powershell.exe", "-NoProfile", "-Command", "pnpm run format:check"], extracted / "desktop", 180),
    ]
    return [dict(id=i, argv=a, cwd=str(c), timeout_seconds=t) for i, a, c, t in steps]


def write_report(folder, report):
    artifacts = folder / "artifacts"
    artifacts.mkdir(exist_ok=True)
    lines = ["# Surge first-use release check", "", f"Automated status: **{report['status']}**.",
             "Unfamiliar-tester acceptance: **pending**.", "Original T1/T2/T3 fuzzing: **incomplete, not run**.", "",
             f"Git: `{report.get('git', {}).get('head', 'unavailable')}`; clean: {report.get('git', {}).get('clean')}.",
             f"Source archive SHA-256: `{report.get('archive_sha256', 'unavailable')}`.", ""]
    lines += [f"- {s['id']}: **{s['status']}**; {s.get('elapsed_seconds', 0)} s. {s.get('reason', '')}" for s in report['steps']]
    if report.get("error"):
        lines += ["", "Run error: " + report['error']]
    lines += ["", *["- " + x for x in LIMITS], "", "Raw logs can contain local paths; CI artifacts contain only owned test data."]
    for name, content in [("report.json", json.dumps(report, indent=2) + "\n"), ("report.md", "\n".join(lines) + "\n")]:
        temp = artifacts / (name + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(artifacts / name)


def validate_ui(step, files):
    if len(files) != 1:
        raise ValueError("missing_or_ambiguous_UI_evidence")
    data = json.loads(next(iter(files)).read_text(encoding="utf-8"))
    checks = data if isinstance(data, list) else data.get("checks", [])
    if len(checks) < UI_MINIMUM[step]:
        raise ValueError("short_UI_evidence")
    if isinstance(data, dict):
        if data.get("status") != "passed":
            raise ValueError("failed_UI_evidence")
        if step in ("replay", "unapproved", "approved") and (data.get("mode") != step or data.get("renderer_errors") != []):
            raise ValueError("invalid_first_use_evidence")
    for check in checks:
        if isinstance(check, dict):
            if check.get("passed") is not True:
                raise ValueError("failed_UI_assertion")
        elif not isinstance(check, str) or not check.strip():
            raise ValueError("invalid_UI_assertion")
    return len(checks)


def validate_cache(text, folder):
    if Path(text.strip()).resolve() != (folder / "caches/pnpm/v11").resolve():
        raise ValueError("cache_isolation_not_established")


def collect_ui(extracted, folder):
    # Copy explicit evidence extensions at one level; never copy app profiles.
    dest = folder / "artifacts/ui"
    for p in (extracted / "verification/electron").glob("*/*"):
        if p.is_file() and p.suffix in (".json", ".png", ".txt"):
            target = dest / p.parent.name / p.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)


def execute(steps, folder, report, env, deadline, validator, command_runner=qualify.run_command):
    for step, result in zip(steps, report['steps']):
        if time.monotonic() >= deadline:
            report['error'] = 'total_deadline_before_next_step'
            return False
        result['status'] = 'running'
        write_report(folder, report)
        log = folder / 'artifacts' / (step['id'] + '.log')
        print('Running ' + step['id'], flush=True)
        try:
            result.update(command_runner(step, log, env, deadline))
        except KeyboardInterrupt:
            result.update(status='cancelled', reason='interrupted')
        if result['status'] == 'passed':
            try:
                validator(step['id'], result, log)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                result.update(status='failed', reason=str(exc))
        write_report(folder, report)
        print(step['id'] + ': ' + result['status'], flush=True)
        if result['status'] != 'passed':
            return False
    return True


def main():
    folder = ROOT / 'verification/qualification' / ('first-use-' + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True)
    workspace = Path(tempfile.mkdtemp(prefix='surge-fu-'))
    frozen, extracted = folder / 'frozen', workspace / 'fresh extraction/Surge'
    steps = plan(frozen, extracted)
    report = dict(schema='surge-first-use-release-v1', status='incomplete', human_acceptance='pending',
                  fuzzing='incomplete_not_run', os=platform.platform(), python=platform.python_version(),
                  started_at_utc=qualify.utc(), workspace=str(workspace), limits=LIMITS, total_limit_seconds=TOTAL_SECONDS,
                  steps=[dict(id=s['id'], status='not_run', timeout_seconds=s['timeout_seconds'], command=s['argv']) for s in steps])
    write_report(folder, report)
    started = time.monotonic()
    manifest = None
    seen_ui = set()
    try:
        if os.name != 'nt':
            raise ValueError('Windows graphical session required')
        report['git'] = qualify.git_identity()
        manifest = manifest_for(ROOT)
        for name in manifest:
            target = frozen / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        verify_source(frozen, manifest)
        (workspace / 'temp').mkdir()
        report['initial_caches_absent'] = not (workspace / 'caches').exists()
        env = environment(workspace)

        def validator(name, result, log):
            nonlocal seen_ui
            text = log.read_text(encoding='utf-8-sig', errors='replace')
            if name == 'package':
                archived = json.loads((frozen / 'dist/source-manifest.json').read_text())
                if archived != manifest:
                    raise ValueError('package_manifest_mismatch')
                archive = frozen / 'dist/surge-source.zip'
                with zipfile.ZipFile(archive) as z:
                    if sorted(z.namelist()) != sorted('Surge/' + n for n in manifest):
                        raise ValueError('unexpected_archive_entries')
                    z.extractall(extracted.parent)
                verify_source(extracted, manifest)
                report['archive_sha256'] = sha(archive)
                report['manifest_sha256'] = sha(frozen / 'dist/source-manifest.json')
                for file in (archive, frozen / 'dist/source-manifest.json'):
                    shutil.copyfile(file, folder / 'artifacts' / file.name)
                absent = {p: not (extracted / p).exists() for p in ('.venv','desktop/node_modules','desktop/dist','native/build','native/captures','native/baselines.json')}
                report['initial_artifacts_absent'] = absent
                if not all(absent.values()):
                    raise ValueError('package_contains_generated_state')
            elif name == 'cache_path':
                validate_cache(text, workspace)
            elif name == 'setup':
                modules = (extracted / 'desktop/node_modules/.modules.yaml').read_text()
                expected = str(workspace / 'caches/pnpm/v11').replace('\\','/')
                if expected not in modules.replace('\\\\','/').replace('\\','/'):
                    raise ValueError('installed_store_not_isolated')
                if not list((workspace / 'caches/electron').rglob('electron-*.zip')):
                    raise ValueError('electron_cache_not_populated')
            elif name in UI_MINIMUM:
                files = set((extracted / 'verification/electron').glob('*/results.json'))
                result['verified_assertions'] = validate_ui(name, files - seen_ui)
                seen_ui = files
            elif name == 'native_ctest':
                qualify.verify_test_output(name, result, text)
            elif name == 'approve':
                registry = json.loads((extracted / 'native/baselines.json').read_text())
                if not registry.get('entries'):
                    raise ValueError('empty_approval_registry')
                report['baseline_sha256'] = sha(extracted / 'native/baselines.json')
            collect_ui(extracted, folder)

        passed = execute(steps, folder, report, env, started + TOTAL_SECONDS, validator)
        verify_source(ROOT, manifest)
        verify_source(extracted, manifest)
        report['source_unchanged'] = True
        if passed:
            report['status'] = 'passed'
    except KeyboardInterrupt:
        report['error'] = 'interrupted'
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        for item in report['steps']:
            if item['status'] == 'running':
                item.update(status='failed', reason='runner_interrupted')
        if report['status'] != 'passed':
            report['status'] = 'failed'
        try:
            collect_ui(extracted, folder)
        except OSError as exc:
            report.update(status='failed', error='artifact_collection_failed: ' + str(exc))
        report['finished_at_utc'] = qualify.utc()
        report['elapsed_seconds'] = round(time.monotonic()-started, 3)
        write_report(folder, report)
        print('First-use ' + report['status'] + ': ' + str(folder / 'artifacts/report.md'), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

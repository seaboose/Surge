"""Release acceptance must fail closed without erasing evidence or claiming human acceptance."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import check_first_use as runner


class FirstUseRunnerTests(unittest.TestCase):
    def test_scratch_work_is_not_release_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'work').mkdir()
            (root / 'work' / 'scratch.py').write_text('scratch')
            (root / 'app.py').write_text('release')
            self.assertEqual(set(runner.manifest_for(root)), {'app.py'})

    def run_stub(self, command, validator=lambda *a: None, deadline=None):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            steps = [dict(id=x, argv=['unused'], cwd=temp, timeout_seconds=3) for x in ('first','second')]
            report = dict(status='incomplete', human_acceptance='pending', steps=[dict(id=x,status='not_run') for x in ('first','second')])
            result = runner.execute(steps,folder,report,{},deadline or time.monotonic()+10,validator,command)
            data = json.loads((folder/'artifacts/report.json').read_text()) if (folder/'artifacts/report.json').exists() else report
            return result,data

    def test_failure_preserves_not_run_and_human_pending(self):
        def fail(step, log, env, deadline):
            log.write_text('first failure preserved')
            return dict(status='failed',exit_code=7)
        passed,r=self.run_stub(fail)
        self.assertFalse(passed)
        self.assertEqual([s['status'] for s in r['steps']],['failed','not_run'])
        self.assertEqual(r['human_acceptance'],'pending')

    def test_zero_exit_without_evidence_fails(self):
        def validate(*a):raise ValueError('missing evidence')
        passed,r=self.run_stub(lambda *a:dict(status='passed',exit_code=0),validate)
        self.assertFalse(passed)
        self.assertEqual(r['steps'][0]['reason'],'missing evidence')
        self.assertEqual(r['steps'][1]['status'],'not_run')

    def test_interrupt_is_recorded(self):
        def interrupt(*a):raise KeyboardInterrupt()
        passed,r=self.run_stub(interrupt)
        self.assertFalse(passed)
        self.assertEqual([s['status'] for s in r['steps']],['cancelled','not_run'])

    def test_deadline_prevents_launch(self):
        def forbidden(*a):self.fail('launched after deadline')
        passed,r=self.run_stub(forbidden,deadline=time.monotonic()-1)
        self.assertFalse(passed)
        self.assertTrue(all(s['status']=='not_run' for s in r['steps']))

    def test_source_drift_and_extra_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'a.py').write_text('original')
            manifest=runner.manifest_for(root)
            runner.verify_source(root,manifest)
            (root/'a.py').write_text('changed')
            with self.assertRaises(ValueError):runner.verify_source(root,manifest)
            (root/'a.py').write_text('original');(root/'extra.py').write_text('extra')
            with self.assertRaises(ValueError):runner.verify_source(root,manifest)

    def test_cache_mismatch_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            runner.validate_cache(str(folder/'caches/pnpm/v11'),folder)
            for text in ('',str(folder/'host-store')):
                with self.assertRaises(ValueError):runner.validate_cache(text,folder)

    def test_missing_short_failed_or_wrong_mode_ui_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'results.json'
            with self.assertRaises(ValueError):runner.validate_ui('approved',set())
            for data in ({}, {'status':'passed','checks':[]}, {'status':'passed','mode':'unapproved','renderer_errors':[],'checks':[{'passed':True}]*6}, {'status':'passed','mode':'approved','renderer_errors':[],'checks':[{'passed':False}]*6}):
                p.write_text(json.dumps(data))
                with self.assertRaises(ValueError):runner.validate_ui('approved',{p})
            p.write_text(json.dumps({'status':'passed','mode':'approved','renderer_errors':[],'checks':[{'passed':True}]*6}))
            self.assertEqual(runner.validate_ui('approved',{p}),6)

    def test_environment_removes_overrides(self):
        with patch.dict(runner.os.environ,{'ELECTRON_OVERRIDE_DIST_PATH':'bad','PNPM_CONFIG_STORE_DIR':'bad','NODE_OPTIONS':'bad','PYTHONOPTIMIZE':'1'}):
            env=runner.environment(Path('fresh'))
        self.assertNotIn('ELECTRON_OVERRIDE_DIST_PATH',env)
        self.assertNotIn('NODE_OPTIONS',env)
        self.assertNotIn('PYTHONOPTIMIZE',env)
        self.assertEqual(env['PNPM_CONFIG_STORE_DIR'],str(Path('fresh/caches/pnpm')))

    def test_artifact_collection_excludes_profiles_and_entry_scripts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);ex=root/'extracted';case=ex/'verification/electron/run';case.mkdir(parents=True)
            (case/'results.json').write_text('{}');(case/'failure.png').write_bytes(b'png')
            (case/'entry.cjs').write_text('script');(case/'profile').mkdir();(case/'profile/secret.json').write_text('{}')
            runner.collect_ui(ex,root)
            self.assertEqual({p.name for p in (root/'artifacts/ui/run').iterdir()},{'results.json','failure.png'})

    def test_plan_order_preserves_approval_boundary(self):
        steps=runner.plan(Path('frozen'),Path('extracted'))
        ids=[s['id'] for s in steps]
        for earlier,later in [('replay','native_build'),('native_build','unapproved'),('unapproved','approve'),('approve','approved')]:
            self.assertLess(ids.index(earlier),ids.index(later))
        self.assertTrue({'library','deletion','saved'} <= set(ids))

if __name__ == '__main__':
    unittest.main()

class HostedFailureProbe(unittest.TestCase):
    def test_intentional_hosted_failure(self):
        self.fail('SURGE_HOSTED_FAILURE_PROBE_20261023: intentional disposable-branch failure')

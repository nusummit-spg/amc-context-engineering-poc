"""Offline contract tests. Fixtures are synthetic and cannot establish UAT readiness."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from tools.amc_release import common, ledger, counts, slo, patch_ci, canary

SHA = 'a' * 40
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def event(n, *, id=None, status='PASS', source='ci'):
    return {'id': id or f'e{n}', 'sha': SHA, 'gate': 'CI07', 'status': status,
            'time': NOW.isoformat(), 'source': source, 'artifact_sha256': 'b' * 64}


class CommonTests(unittest.TestCase):
    def test_canonical_stability(self):
        self.assertEqual(common.digest({'b': 1, 'a': 2}), common.digest({'a': 2, 'b': 1}))
    def test_non_finite_rejected(self):
        with self.assertRaises(ValueError): common.digest({'latency': float('nan')})
    def test_commit_short_sha_fails(self):
        with self.assertRaises(ValueError): common.require_sha('abc123')
    def test_datetime_requires_timezone(self):
        with self.assertRaises(ValueError): common.utc('2026-11-11T10:00:00')
    def test_safe_relative_parent_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): common.safe_relative(Path(d), '../secret')
    def test_safe_relative_absolute_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): common.safe_relative(Path(d), '/etc/passwd')
    def test_safe_relative_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'bad').symlink_to(Path(d).parent, target_is_directory=True)
            with self.assertRaises(ValueError): common.safe_relative(root, 'bad/elsewhere')


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'evidence.jsonl'
    def test_create_verify(self):
        result = ledger.create(self.path, [event(1), event(2)])
        self.assertEqual(result['events'], 2)
        self.assertEqual(ledger.verify(self.path), result)
    def test_overwrite_prohibited(self):
        ledger.create(self.path, [event(1)])
        with self.assertRaises(FileExistsError): ledger.create(self.path, [event(2)])
    def test_missing_evidence_rejected(self):
        with self.assertRaises(ledger.LedgerError): ledger.create(self.path, [])
    def test_duplicate_id_rejected(self):
        with self.assertRaises(ledger.LedgerError): ledger.create(self.path, [event(1), event(1)])
    def test_bad_artifact_hash_rejected(self):
        bad = event(1); bad['artifact_sha256'] = 'bad'
        with self.assertRaises(ledger.LedgerError): ledger.create(self.path, [bad])
    def test_invalid_status_rejected(self):
        with self.assertRaises(ledger.LedgerError): ledger.create(self.path, [event(1, status='GOOD')])
    def test_no_timezone_rejected(self):
        bad = event(1); bad['time'] = '2026-11-11 12:00:00'
        with self.assertRaises(ValueError): ledger.create(self.path, [bad])
    def test_tamper_detected(self):
        ledger.create(self.path, [event(1), event(2)])
        data = self.path.read_text().replace('"PASS"', '"FAIL"', 1)
        self.path.write_text(data)
        with self.assertRaises(ledger.LedgerError): ledger.verify(self.path)
    def test_delete_event_detected(self):
        ledger.create(self.path, [event(1), event(2)])
        self.path.write_text(self.path.read_text().splitlines()[1]+'\n')
        with self.assertRaises(ledger.LedgerError): ledger.verify(self.path)
    def test_empty_ledger_refused(self):
        self.path.write_text('')
        with self.assertRaises(ledger.LedgerError): ledger.verify(self.path)


def window_samples(count=120, minutes=60, status=200, latency=100, tenant='t1'):
    return [{'tenant': tenant,
             'timestamp': (NOW - timedelta(seconds=minutes*60 - 1 - i*(minutes*60-2)/(count-1))).isoformat(),
             'status_code': status, 'latency_ms': latency} for i in range(count)]


class SLOTests(unittest.TestCase):
    def calc(self, es, **kwargs):
        return slo.evaluate(es, tenant='t1', now=NOW.isoformat(),
                            environment='staging', provenance='live', **kwargs)
    def test_clean_60minute_window(self):
        r = self.calc(window_samples())
        self.assertEqual(r['status'], 'PASS')
        self.assertEqual(r['samples'], 120)
        self.assertEqual(r['error_rate'], 0)
        self.assertGreaterEqual(r['bucket_coverage'], .95)
    def test_empty_unknown(self):
        self.assertEqual(self.calc([])['status'], 'UNKNOWN')
    def test_coverage_unknown(self):
        es = [{'tenant': 't1', 'timestamp': NOW.isoformat(), 'status_code': 200, 'latency_ms': 5}]*120
        self.assertEqual(self.calc(es)['status'], 'UNKNOWN')
    def test_insufficient_samples(self):
        self.assertEqual(self.calc(window_samples(24))['status'], 'UNKNOWN')
    def test_untrusted_telemetry(self):
        r = slo.evaluate(window_samples(), tenant='t1', now=NOW.isoformat(),
                         environment='simulation', provenance='synthetic')
        self.assertEqual(r['status'], 'UNKNOWN')
    def test_high_p95_fails(self):
        self.assertEqual(self.calc(window_samples(latency=5000))['status'], 'FAIL')
    def test_high_error_rate_fails(self):
        self.assertEqual(self.calc(window_samples(status=503))['status'], 'FAIL')
    def test_future_sample_fails_unknown(self):
        es = window_samples(); es.append({'tenant':'t1','timestamp':(NOW+timedelta(minutes=1)).isoformat(),'status_code':200,'latency_ms':1})
        self.assertEqual(self.calc(es)['status'], 'UNKNOWN')
    def test_invalid_numeric_fails_unknown(self):
        es = window_samples(); es.append({'tenant':'t1','timestamp':NOW.isoformat(),'status_code':200,'latency_ms':'nan'})
        self.assertEqual(self.calc(es)['status'], 'UNKNOWN')
    def test_wrong_tenant_ignored(self):
        self.assertEqual(self.calc(window_samples(tenant='t2'))['status'], 'UNKNOWN')
    def test_day_window(self):
        self.assertEqual(self.calc(window_samples(1500, 1440),minutes=1440,min_samples=1000)['status'], 'PASS')
    def test_unaligned_bucket_rejected(self):
        with self.assertRaises(slo.SLOError): self.calc(window_samples(), bucket_minutes=7)


XML = '''<testsuite tests="3"><testcase classname="T" name="ok"/><testcase classname="T" name="bad"><failure>error</failure></testcase><testcase classname="T" name="skip"><skipped/></testcase></testsuite>'''


class JUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'junit.xml'; self.path.write_text(XML)
    def test_count_fails_with_skip(self):
        r=counts.from_junit(self.path,SHA,'Linux','amc_release')
        self.assertEqual((r['passed'],r['failed'],r['skipped'],r['collected']),(1,1,1,3))
        self.assertEqual(r['status'],'FAIL')
    def test_clean_two_platform_reconciles(self):
        self.path.write_text('<testsuite><testcase classname="X" name="one"/></testsuite>')
        a=counts.from_junit(self.path,SHA,'Linux','amc_release')
        b=counts.from_junit(self.path,SHA,'Windows','amc_release')
        r=counts.reconcile([a,b], SHA,[('Linux','amc_release'),('Windows','amc_release')],historical_total=109)
        self.assertEqual(r['status'],'PASS')
        self.assertEqual(r['historical_total_comparison_only'],109)
    def test_missing_windows_fails(self):
        self.path.write_text('<testsuite><testcase classname="X" name="one"/></testsuite>')
        a=counts.from_junit(self.path,SHA,'Linux','amc_release')
        self.assertIn('MISSING_REQUIRED_OS_SUITE',counts.reconcile([a],SHA,[('Linux','amc_release'),('Windows','amc_release')])['reasons'])
    def test_drift_fails(self):
        a={'sha':SHA,'os':'Linux','suite':'s','collected':5,'status':'PASS','skipped':0}
        b={'sha':SHA,'os':'Windows','suite':'s','collected':4,'status':'PASS','skipped':0}
        self.assertIn('CROSS_OS_COUNT_DRIFT',counts.reconcile([a,b],SHA,[('Linux','s'),('Windows','s')])['reasons'])
    def test_mixed_sha_fails(self):
        a={'sha':SHA,'os':'Linux','suite':'s','collected':5,'status':'PASS','skipped':0}
        self.assertIn('STALE_OR_MIXED_SHA',counts.reconcile([a], 'b'*40, [('Linux','s')])['reasons'])
    def test_duplicate_case_refused(self):
        self.path.write_text('<testsuite><testcase classname="X" name="one"/><testcase classname="X" name="one"/></testsuite>')
        with self.assertRaises(counts.CountError): counts.from_junit(self.path,SHA,'Linux','s')
    def test_zero_tests_refused(self):
        self.path.write_text('<testsuite />')
        with self.assertRaises(counts.CountError): counts.from_junit(self.path,SHA,'Linux','s')


class CIPatchTests(unittest.TestCase):
    SRC='name: AMC\n      - name: Run fault injection tests\n         run: |\n          echo hi\n'
    def test_patch_rewrites_only_indent(self):
        self.assertIn('\n        run: |',patch_ci.fixed_workflow(self.SRC))
    def test_idempotent(self):
        v=patch_ci.fixed_workflow(self.SRC)
        self.assertEqual(patch_ci.fixed_workflow(v),v)
    def test_absent_anchor_rejected(self):
        with self.assertRaises(patch_ci.CIPatchError): patch_ci.fixed_workflow('anything else')
    def test_dry_run_no_file_change(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ci.yml';p.write_text(self.SRC)
            self.assertTrue(patch_ci.apply_workflow(p,check=True))
            self.assertEqual(p.read_text(),self.SRC)
    def test_apply_creates_backup(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ci.yml';p.write_text(self.SRC)
            self.assertTrue(patch_ci.apply_workflow(p,check=False))
            self.assertEqual(Path(str(p)+'.bak').read_text(),self.SRC)
            self.assertIn('        run: |',p.read_text())


class CanaryTests(unittest.TestCase):
    def test_http_blocked(self):
        with self.assertRaises(canary.CanaryError): canary.probe('http://stage.example.com',paths=['/health'],allowed_hostname='stage.example.com')
    def test_production_host_not_allowlisted(self):
        with self.assertRaises(canary.CanaryError): canary.probe('https://prod.example.com',paths=['/health'],allowed_hostname='stage.example.com')
    def test_mutating_path_refused(self):
        with self.assertRaises(canary.CanaryError): canary.probe('https://stage.example.com',paths=['/api/admin/delete'],allowed_hostname='stage.example.com')
    @patch('tools.amc_release.canary._open_readonly')
    def test_readonly_health(self, urlopen):
        cm=MagicMock();cm.__enter__.return_value.status=200;cm.__enter__.return_value.read.return_value=b'{"status":"ok"}'
        cm.__enter__.return_value.geturl.return_value='https://stage.example.com/health'
        urlopen.return_value=cm
        r=canary.probe('https://stage.example.com',paths=['/health'],allowed_hostname='stage.example.com')
        self.assertEqual(r['status'],'PASS')
        self.assertFalse(r['release_authorized'])
        self.assertEqual(urlopen.call_args.args[0].get_method(),'GET')


if __name__=='__main__': unittest.main()

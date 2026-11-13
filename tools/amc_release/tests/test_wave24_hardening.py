"""Negative-path regression: test identity, JUnit metadata, and staging GET safety."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tools.amc_release import canary, counts
from .test_release_core import SHA


class JUnitIdentityTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.p=Path(self.t.name)/'junit.xml'
    def report(self, case='one', plat='Linux', total=1):
        self.p.write_text(f'<testsuite tests="{total}"><testcase classname="Example" name="{case}"/></testsuite>')
        return counts.from_junit(self.p,SHA,plat,'backend_contracts')
    def test_identity_drift_blocks_equal_total(self):
        a=self.report('first');b=self.report('replaced','Windows')
        r=counts.reconcile([a,b],SHA,[('Linux','backend_contracts'),('Windows','backend_contracts')])
        self.assertIn('CROSS_OS_TEST_IDENTITY_DRIFT',r['reasons'])
        self.assertNotIn('CROSS_OS_COUNT_DRIFT',r['reasons'])
    def test_same_identities_across_os_pass(self):
        a=self.report('one');b=self.report('one','Windows')
        self.assertEqual(counts.reconcile([a,b],SHA,[('Linux','backend_contracts'),('Windows','backend_contracts')])['status'],'PASS')
    def test_declared_test_count_incorrect(self):
        self.p.write_text('<testsuite tests="2"><testcase classname="Example" name="one"/></testsuite>')
        with self.assertRaises(counts.CountError):counts.from_junit(self.p,SHA,'Linux','backend_contracts')
    def test_declared_failure_count_incorrect(self):
        self.p.write_text('<testsuite tests="1" failures="1"><testcase classname="T" name="ok"/></testsuite>')
        with self.assertRaises(counts.CountError):counts.from_junit(self.p,SHA,'Linux','backend_contracts')
    def test_nested_suite_count_incorrect(self):
        self.p.write_text('<testsuites tests="1"><testsuite tests="2"><testcase classname="T" name="ok"/></testsuite></testsuites>')
        with self.assertRaises(counts.CountError):counts.from_junit(self.p,SHA,'Linux','backend_contracts')
    def test_empty_class_name_with_valid_name(self):
        self.p.write_text('<testsuite><testcase name="case"/></testsuite>')
        self.assertEqual(counts.from_junit(self.p,SHA,'Linux','backend_contracts')['collected'],1)
    def test_duplicate_normalized_identity(self):
        self.p.write_text('<testsuite><testcase name="case"/><testcase classname="" name="case"/></testsuite>')
        with self.assertRaises(counts.CountError):counts.from_junit(self.p,SHA,'Linux','backend_contracts')


class CanaryProtectionTests(unittest.TestCase):
    def base(self,url='https://stage.example.com',paths=None):
        return canary.probe(url,paths=paths or ['/health'],allowed_hostname='stage.example.com')
    def test_query_and_path_rejected(self):
        for p in ['/api/admin/secret','/api/ingest','/health?write=true','/%2e%2e/admin','/health#x','//host','/api/governance']:
            with self.subTest(path=p),self.assertRaises(canary.CanaryError):self.base(paths=[p])
    def test_nonstandard_port_rejected(self):
        with self.assertRaises(canary.CanaryError):self.base(url='https://stage.example.com:444')
    def test_path_in_base_rejected(self):
        with self.assertRaises(canary.CanaryError):self.base(url='https://stage.example.com/not-origin')
    def test_redirect_handler_disallows_redirect(self):
        handler=canary._NoRedirect()
        self.assertIsNone(handler.redirect_request(MagicMock(),MagicMock(),302,'redirect',{},'https://evil.example/'))
    @patch('tools.amc_release.canary._open_readonly')
    def test_response_redirect_fails(self,opener):
        cm=MagicMock();cm.__enter__.return_value.status=200
        cm.__enter__.return_value.read.return_value=b'{"status":"ok"}'
        cm.__enter__.return_value.geturl.return_value='https://other.example.com/health'
        opener.return_value=cm
        self.assertEqual(self.base()['status'],'FAIL')
    @patch('tools.amc_release.canary._open_readonly')
    def test_unhealthy_json_fails(self,opener):
        cm=MagicMock();cm.__enter__.return_value.status=200
        cm.__enter__.return_value.read.return_value=b'{"status":"unhealthy"}'
        cm.__enter__.return_value.geturl.return_value='https://stage.example.com/health'
        opener.return_value=cm
        self.assertEqual(self.base()['status'],'FAIL')
    @patch('tools.amc_release.canary._open_readonly')
    def test_error_body_fails(self,opener):
        cm=MagicMock();cm.__enter__.return_value.status=200
        cm.__enter__.return_value.read.return_value=b'{"error":"database unavailable"}'
        cm.__enter__.return_value.geturl.return_value='https://stage.example.com/health'
        opener.return_value=cm
        self.assertEqual(self.base()['status'],'FAIL')
    @patch('tools.amc_release.canary._open_readonly')
    def test_oversized_response_fails(self,opener):
        cm=MagicMock();cm.__enter__.return_value.status=200
        cm.__enter__.return_value.read.return_value=b' '*262145
        cm.__enter__.return_value.geturl.return_value='https://stage.example.com/health'
        opener.return_value=cm
        self.assertEqual(self.base()['status'],'FAIL')

if __name__=='__main__':unittest.main()

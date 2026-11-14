"""SLO verification: 1h/24h windows, current UTC boundaries and source provenance."""
import copy
import unittest
from datetime import timedelta
from tools.amc_release import slo, gate
from .test_release_core import NOW, SHA, window_samples
from .test_uat_gate import good_evidence, KEY
import tempfile
from pathlib import Path


class SLOPairTests(unittest.TestCase):
    def test_both_windows_clean_pass(self):
        r=slo.evaluate_pair(window_samples(3000,1440), tenant='t1', now=NOW.isoformat(),environment='staging', provenance='live')
        self.assertEqual(r['status'],'PASS')
        self.assertEqual({x['window_minutes'] for x in r['windows']},{60,1440})
    def test_day_window_missing_blocks(self):
        r=slo.evaluate_pair(window_samples(150,60), tenant='t1', now=NOW.isoformat(),environment='staging', provenance='live')
        self.assertEqual(r['status'],'BLOCK')
        self.assertEqual(r['windows'][1]['status'],'UNKNOWN')
    def test_synthetic_provenance_is_not_live(self):
        r=slo.evaluate_pair(window_samples(3000,1440), tenant='t1', now=NOW.isoformat(),environment='simulation', provenance='synthetic')
        self.assertEqual(r['status'],'BLOCK')


class UATSLOFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.d=gate.attest(good_evidence(self.root),key=KEY,attestor='fixture')
    def evaluate(self,d):
        return gate.evaluate(d,root=self.root,now=NOW.isoformat(),verification_key=KEY)
    def mutate(self,field,value):
        o=copy.deepcopy(self.d)
        w=next(x for x in o['evidence'] if x['gate']=='FB05')['details']['windows']
        w[0][field]=value
        return o
    def test_older_slo_window_blocks(self):
        x=self.mutate('window_end',(NOW-timedelta(hours=2)).isoformat())
        self.assertIn('STALE_SLO_WINDOW',self.evaluate(x)['blocked_gates']['FB05'])
    def test_future_slo_window_blocks(self):
        x=self.mutate('window_end',(NOW+timedelta(hours=1)).isoformat())
        self.assertIn('STALE_SLO_WINDOW',self.evaluate(x)['blocked_gates']['FB05'])
    def test_window_duration_mismatch_blocks(self):
        x=self.mutate('window_start',(NOW-timedelta(minutes=55)).isoformat())
        self.assertIn('INVALID_SLO_WINDOW_BOUNDARIES',self.evaluate(x)['blocked_gates']['FB05'])
    def test_cross_tenant_slo_windows_block(self):
        x=self.mutate('tenant','other-tenant')
        self.assertIn('MIXED_OR_MISSING_SLO_TENANT',self.evaluate(x)['blocked_gates']['FB05'])
    def test_missing_time_bounds_blocks(self):
        x=self.mutate('window_start',None)
        self.assertIn('MISSING_SLO_TIME_BOUNDS',self.evaluate(x)['blocked_gates']['FB05'])

if __name__=='__main__': unittest.main()

"""UAT gate adversarial tests. All-good fixture is synthetic; not UAT evidence."""
import copy
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from tools.amc_release import common, ledger, gate
from .test_release_core import NOW, SHA, event
from .test_wave24_rollback import dataset as synthetic_rollback_proof
KEY = 'nonproduction-fixture-key-test-' * 3


def good_evidence(root: Path):
    f=root/'proof.json';f.write_text('{"sandbox":"fake fixtures for tests"}')
    led=root/'chain.jsonl'; anchor=ledger.create(led,[event(1)])
    detail={
        'GATE01':{'environment':'staging','mode':'live','graph_readbacks':1,'faiss_reload_probes':1,'rollback_drills':1,'feedback_roundtrips':1,'cross_tenant_violations':0,'synthetic_receipts':0},
        'GATE05':{'environment':'staging','mode':'live','read_only_probes':5,'duration_minutes':30,'failures':0,'rollback_probe':'PASS','rollback_observations':synthetic_rollback_proof()},
        'GATE06':{'ledger_file':'chain.jsonl','ledger_sha256':anchor['final_sha256'],'anchor_type':'github_artifact'},
        'GATE07':{'decision':'ACCEPT_UAT','scope':'uat','reviewers':['operator-a','operator-b'],'signatures_verified':True,'independent_review':True},
        'FB05':{'thresholds_approved':True,'limits':{'max_p95_ms':2000,'max_error_rate':.01},'windows':[{'window_minutes':n,'status':'PASS','environment':'staging','provenance':'live','tenant':'tenant-a','window_start':(NOW-timedelta(minutes=n)).isoformat(),'window_end':NOW.isoformat(),'samples':1000,'bucket_coverage':1.0,'p95_ms':200,'error_rate':0} for n in (60,1440)]},
        'FB06':{'runner':'playwright','environment':'staging','browsers':['chromium','firefox'],'scenarios':5,'failed':0,'skipped':0},
        'CI07':{'platforms':{'Windows':'PASS','Linux':'PASS'},'suites':{'amc_release':{'Windows':'PASS','Linux':'PASS'},'backend_contracts':{'Windows':'PASS','Linux':'PASS'}},'required_skips':0},
        'E05':{'workflows':{n:{'sha':SHA,'conclusion':'success','required_skips':0,'run_id':1,'job_count':2} for n in (
            'AMC Publication V2 Contract Tests','AMC Quality V2 Contract Tests','AMC Assurance Pipeline','AMC Release Verification Matrix')}},
        'CI08':{'reconciliation':{'sha':SHA,'status':'PASS','missing':[],'reports':4,'same_suite_per_platform_test_identity_sha256':{'amc_release':['f'*64,'f'*64],'backend_contracts':['e'*64,'e'*64]}}},
    }
    return {'schema':'amc-uat-evidence-v2.3','sha':SHA,
            'evidence':[{'gate':name,'sha':SHA,'status':'PASS','verified':True,
                         'source':'manual' if name=='GATE07' else 'live' if name in ('GATE01','GATE05','FB05','FB06') else 'ci',
                         'at':NOW.isoformat(),'artifact':'proof.json','artifact_sha256':common.hash_file(f),
                         'details':values} for name,values in detail.items()]}


class UATGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.obj=gate.attest(good_evidence(self.root), key=KEY, attestor='TEST_FIXTURE')
    def evaluate(self,obj=None):
        return gate.evaluate(obj or self.obj,root=self.root,now=NOW.isoformat(),verification_key=KEY)
    def test_unsigned_document_blocks(self):
        x=copy.deepcopy(self.obj);x.pop('attestation')
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_wrong_external_key_blocks(self):
        self.assertEqual(gate.evaluate(self.obj,root=self.root,now=NOW.isoformat(),verification_key='wrong'*10)['state'],'BLOCKED')
    def test_good_synthetic_contract(self):
        self.assertEqual(self.evaluate()['state'],'UAT_READY')
        self.assertEqual(self.evaluate()['production_release'],'REQUIRES_SEPARATE_APPROVAL')
    def test_missing_each_gate_blocks(self):
        for g in gate.GATES:
            with self.subTest(gate=g):
                x=copy.deepcopy(self.obj);x['evidence']=[e for e in x['evidence'] if e['gate']!=g]
                self.assertIn(g,self.evaluate(x)['blocked_gates'])
    def test_wrong_commit_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][0]['sha']='b'*40
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_future_time_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][0]['at']=(NOW+timedelta(days=1)).isoformat()
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_stale_time_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][0]['at']=(NOW-timedelta(days=8)).isoformat()
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_artifact_tampering_blocks(self):
        (self.root/'proof.json').write_text('new bytes')
        self.assertEqual(self.evaluate()['verified_gate_count'],0)
    def test_path_traversal_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][0]['artifact']='../outside'
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_fake_receipt_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][0]['details']['synthetic_receipts']=1
        self.assertIn('TENANT_OR_RECEIPT_INVARIANT_FAILED',self.evaluate(x)['blocked_gates']['GATE01'])
    def test_canary_too_short_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][1]['details']['duration_minutes']=10
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_canary_rollback_missing_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][1]['details']['rollback_probe']='NOT_RUN'
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_ledger_wrong_digest_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][2]['details']['ledger_sha256']='e'*64
        self.assertIn('LEDGER_HASH_OR_COUNT_MISMATCH',self.evaluate(x)['blocked_gates']['GATE06'])
    def test_ledger_external_anchor_required(self):
        x=copy.deepcopy(self.obj);x['evidence'][2]['details']['anchor_type']='none'
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_single_reviewer_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][3]['details']['reviewers']=['one']
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_unsigned_review_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][3]['details']['signatures_verified']=False
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_missing_daily_window_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][4]['details']['windows']=x['evidence'][4]['details']['windows'][:1]
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_high_measured_slo_blocks_even_if_marked_pass(self):
        x=copy.deepcopy(self.obj);x['evidence'][4]['details']['windows'][0]['error_rate']=.25
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_unapproved_slo_threshold_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][4]['details']['thresholds_approved']=False
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_unknown_slo_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][4]['details']['windows'][0]['status']='UNKNOWN'
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_missing_browser_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][5]['details']['browsers']=['chromium']
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_skipped_browser_case_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][5]['details']['skipped']=1
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_backend_matrix_missing_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][6]['details']['suites'].pop('backend_contracts')
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_windows_missing_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][6]['details']['platforms']={'Linux':'PASS'}
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_quality_workflow_sha_mismatch_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][7]['details']['workflows']['AMC Quality V2 Contract Tests']['sha']='d'*40
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_count_reconcile_missing_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][8]['details']['reconciliation']['status']='FAIL'
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_duplicate_gate_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'].append(copy.deepcopy(x['evidence'][0]))
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_untrusted_local_evidence_blocks(self):
        x=copy.deepcopy(self.obj);x['evidence'][0]['source']='simulation'
        self.assertEqual(self.evaluate(x)['state'],'BLOCKED')
    def test_malformed_schema_refused(self):
        x=copy.deepcopy(self.obj);x['schema']='old'
        with self.assertRaises(ValueError): self.evaluate(x)


if __name__=='__main__': unittest.main()

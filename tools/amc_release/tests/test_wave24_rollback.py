import copy
import unittest
from datetime import timedelta
from tools.amc_release import rollback
from .test_release_core import SHA, NOW


def dataset():
    b='1'*64;c='2'*64;d='3'*64;e='4'*64
    values=[('before',b,c),('published',d,e),('after_rollback',b,c)]
    return {'sha':SHA,'tenant':'t1','work_id':'pub_1','environment':'staging','source':'live',
            'rollback_receipt_verified':True,
            'observations':[{'phase':n,'tenant':'t1','work_id':'pub_1',
                             'graph_sha256':g,'generation_sha256':v,
                             'serving_reader_generation_sha256':v,'verified_readback':True,
                             'at':(NOW+timedelta(minutes=i)).isoformat()}
                            for i,(n,g,v) in enumerate(values)]}


class RollbackProofTests(unittest.TestCase):
    def result(self,obj): return rollback.evaluate(obj,expected_sha=SHA)
    def test_consistent_three_phase_proof(self):
        x=self.result(dataset());self.assertEqual(x['status'],'PASS')
        self.assertTrue(x['authenticity_requires_external_evidence'])
    def test_wrong_sha(self):
        x=dataset();x['sha']='f'*40
        self.assertIn('SHA_MISMATCH',self.result(x)['reasons'])
    def test_no_change_after_publish(self):
        x=dataset();x['observations'][1]['graph_sha256']='1'*64;x['observations'][1]['generation_sha256']='2'*64;x['observations'][1]['serving_reader_generation_sha256']='2'*64
        self.assertIn('CANARY_PUBLICATION_DID_NOT_CHANGE_EFFECTS',self.result(x)['reasons'])
    def test_wrong_tenant_in_after(self):
        x=dataset();x['observations'][2]['tenant']='t2'
        self.assertIn('OBSERVATION_TENANT_WORK_MISMATCH',self.result(x)['reasons'])
    def test_rollback_graph_not_restored(self):
        x=dataset();x['observations'][2]['graph_sha256']='a'*64
        self.assertIn('ROLLBACK_DID_NOT_RESTORE_graph_sha256',self.result(x)['reasons'])
    def test_rollback_vector_not_restored(self):
        x=dataset();x['observations'][2]['generation_sha256']='a'*64
        self.assertIn('ROLLBACK_DID_NOT_RESTORE_generation_sha256',self.result(x)['reasons'])
    def test_serving_reader_stale(self):
        x=dataset();x['observations'][2]['serving_reader_generation_sha256']='e'*64
        self.assertIn('SERVING_READER_NOT_CONVERGED',self.result(x)['reasons'])
    def test_not_live(self):
        x=dataset();x['source']='simulation'
        self.assertIn('LIVE_STAGING_OBSERVATIONS_REQUIRED',self.result(x)['reasons'])
    def test_unordered(self):
        x=dataset();x['observations'].reverse()
        self.assertIn('ORDERED_THREE_PHASE_OBSERVATIONS_REQUIRED',self.result(x)['reasons'])
    def test_timestamps_wrong(self):
        x=dataset();x['observations'][2]['at']=x['observations'][1]['at']
        self.assertIn('NONMONOTONIC_OBSERVATION_TIMES',self.result(x)['reasons'])
    def test_receipt_not_verified(self):
        x=dataset();x['rollback_receipt_verified']=False
        self.assertIn('ROLLBACK_RECEIPT_NOT_VERIFIED',self.result(x)['reasons'])
    def test_missing_hash(self):
        x=dataset();x['observations'][0].pop('graph_sha256')
        self.assertIn('MISSING_CONTENT_HASH_graph_sha256',self.result(x)['reasons'])

if __name__=='__main__':unittest.main()

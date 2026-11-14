"""Adapter contracts with a fake read_index; real FAISS binary remains NOT_RUN."""
from pathlib import Path
import json
import hashlib
import numpy as np
import pytest
from amc_publication.faiss_reader27 import VerifiedFaissRetriever
from amc_publication.serving27 import ServingDenied
from tools.amc_release.tests.test_wave27_serving import published, env

class FauxIndex:
    def __init__(self, n=1, d=3, ids=None, scores=None, cb=None):
        self.ntotal=n;self.d=d;self.ids=ids or [1];self.scores=scores or [.9];self.cb=cb
        self.id_map=np.arange(1,n+1)
    def search(self, matrix, k):
        if self.cb:self.cb()
        return np.asarray([self.scores]),np.asarray([self.ids])

class FauxFaiss:
    def __init__(self,idx):self.idx=idx;self.calls=0
    def read_index(self,path):self.calls+=1;return self.idx
    def vector_to_array(self,mapping): return np.asarray(mapping)
    @staticmethod
    def normalize_L2(matrix):
        matrix[:]=matrix/np.linalg.norm(matrix,axis=1,keepdims=True)

@pytest.fixture
def setup(env,monkeypatch):
    wid,rid,gen=published(env)
    subj=VerifiedFaissRetriever(env['sessions'],env['store'].root)
    fake=FauxFaiss(FauxIndex())
    # Offline contract fixture: bytes are artificial, not a real FAISS binary.
    directory=env['store']._path(gen.digest)
    (directory/'index.faiss').write_bytes(b'faux-index-bytes-only')
    manifest=json.loads((directory/'manifest.json').read_text())
    manifest.update({'index_hash':hashlib.sha256(b'faux-index-bytes-only').hexdigest(),
                     'dimension':3})
    (directory/'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(subj.store,'verify_by_digest',env['store'].verify_by_digest)
    monkeypatch.setattr(subj.store,'_imports',lambda:(fake,np))
    return subj,fake,wid,rid,gen,env


def test_verified_faiss_search_calls_loader_and_returns_traceable_hit(setup):
    x,fake,wid,rid,gen,env=setup
    hit=x.search('tenant_A',[1,0,0],work_id=wid,receipt_id=rid)
    assert fake.calls==1 and hit[0]['chunk_id']=='chunk-1' and hit[0]['score']==pytest.approx(.9)


def test_unauthenticated_or_wrong_tenant_refused(setup):
    x,*_=setup
    for tenant in ('', 'tenant_B'):
        with pytest.raises(ServingDenied):x.search(tenant,[1,0,0])

@pytest.mark.parametrize('lim',[0,101,1.5,True])
def test_unbounded_or_ambiguous_limit_refused(setup,lim):
    x,*_=setup
    with pytest.raises(ValueError):x.search('tenant_A',[1,0,0],limit=lim)

@pytest.mark.parametrize('vector',[[],[float('nan'),0,0],[float('inf'),0,0],['oops',0,0],None])
def test_nonnumeric_input_refused(setup,vector):
    x,*_=setup
    with pytest.raises(ValueError):x.search('tenant_A',vector)


def test_wrong_embedding_dimension_refused(setup):
    x,*_=setup
    with pytest.raises(ServingDenied,match='dimension'):x.search('tenant_A',[1,0])


def test_bad_faiss_out_of_range_id_refused(setup):
    x,fake,*_=setup
    fake.idx.ids=[500]
    with pytest.raises(ServingDenied,match='out-of-range'):x.search('tenant_A',[1,0,0])


def test_faiss_nonfinite_score_refused(setup):
    x,fake,*_=setup
    fake.idx.scores=[float('nan')]
    with pytest.raises(ServingDenied):x.search('tenant_A',[1,0,0])


def test_reader_change_mid_search_refused(setup):
    x,fake,wid,rid,gen,env=setup
    from amc_publication.models import GenerationPointer
    def stale():
        with env['sessions'].begin() as s:s.get(GenerationPointer,('tenant_A','vector_faiss')).epoch += 1
    fake.idx.cb=stale
    with pytest.raises(ServingDenied,match='pointer changed'):x.search('tenant_A',[1,0,0])


def test_probe_activation_not_same_as_serving_permission(setup):
    x,fake,wid,rid,gen,env=setup
    assert x.probe_activation('tenant_A',gen.digest,gen.digest) is True
    from amc_publication.models import PublicationWork
    with env['sessions'].begin() as s:s.get(PublicationWork,wid).status='rolled_back'
    with pytest.raises(ServingDenied):x.search('tenant_A',[1,0,0])


def test_index_count_mismatch_refused(setup):
    x,fake,*_=setup
    fake.idx.ntotal=3
    with pytest.raises(ServingDenied,match='count'):x.search('tenant_A',[1,0,0])


def test_binary_checksum_mismatch_refused_before_load(setup):
    x,fake,wid,rid,gen,env=setup
    (env['store']._path(gen.digest)/'index.faiss').write_bytes(b'mutated-index')
    with pytest.raises(ServingDenied,match='FAISS bytes changed'):x.search('tenant_A',[1,0,0])


def test_loaded_index_id_map_mismatch_refused(setup):
    x,fake,*_=setup
    fake.idx.id_map=np.asarray([99])
    with pytest.raises(ServingDenied,match='ID map mismatch'):x.search('tenant_A',[1,0,0])


def test_loaded_index_dimension_manifest_mismatch_refused(setup):
    x,fake,*_=setup
    fake.idx.d=99
    with pytest.raises(ServingDenied,match='count/dimension'):x.search('tenant_A',[1,0,0])


def test_binary_change_during_load_refused(setup):
    x,fake,wid,rid,gen,env=setup
    original=fake.read_index
    def race(path):
        result=original(path)
        Path(path).write_bytes(b'changed-after-read-index')
        return result
    fake.read_index=race
    with pytest.raises(ServingDenied,match='during serving load'):x.search('tenant_A',[1,0,0])

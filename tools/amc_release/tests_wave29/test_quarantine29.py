import hashlib
import json
from pathlib import Path
import pytest
from amc_publication.ingestion_boundary29 import (ImmutableIngestionQuarantine29,
    IngestionQuarantineError,DenyDirectVectorMutation29)
from amc_publication.serving27 import ServingDenied


@pytest.fixture
def stage(tmp_path):
    return ImmutableIngestionQuarantine29(tmp_path/'quarantine')


def docs(tenant='alpha'):
    return [{'chunk_id':'c2','tenant_id':tenant,'source_version':'s1',
             'source_sha256':'2'*64,'text':'B document', 'document_id':'doc-b'},
            {'chunk_id':'c1','tenant_id':tenant,'source_version':'s1',
             'source_sha256':'1'*64,'text':'A document', 'document_id':'doc-a'}]


def submit(store, data=None, **fields):
    obj={'tenant':'alpha','source_version':'s1','batch_id':'batch-A',
         'submitted_by':'ingestor-1','documents':docs() if data is None else data}
    obj.update(fields)
    return store.stage(**obj)


def test_staging_is_immutable_and_not_pub_authorized(stage):
    info=submit(stage)
    assert info['state']=='QUARANTINED_UNAPPROVED'
    assert info['publication_authorized'] is False
    payload=stage.verify(info['candidate_sha256'],tenant='alpha')
    assert payload['complete_corpus'] is False and payload['publication_authorized'] is False
    assert [d['chunk_id'] for d in payload['documents']]==['c1','c2']
    assert not hasattr(stage,'activate') and not hasattr(stage,'switch_pointer')


def test_retry_idempotent_and_permutation_independent(stage):
    first=submit(stage)['candidate_sha256']
    second=submit(stage,docs()[::-1])['candidate_sha256']
    assert first==second
    assert len(list(stage.root.rglob('*.json')))==1


@pytest.mark.parametrize('change',[
    lambda d:d.__setitem__(0,{**d[0], 'tenant_id':'beta'}),
    lambda d:d.__setitem__(0,{**d[0], 'chunk_id':''}),
    lambda d:d.__setitem__(0,{**d[0], 'chunk_id':d[1]['chunk_id']}),
    lambda d:d.__setitem__(0,{**d[0], 'text':None}),
    lambda d:d.__setitem__(0,{**d[0], 'text':'   '}),
    lambda d:d.__setitem__(0,{**d[0], 'source_version':'s2'}),
    lambda d:d.__setitem__(0,{**d[0], 'source_sha256':'garbage'}),
    lambda d:d.append('not dict'),
])
def test_invalid_candidate_refused(stage,change):
    d=docs();change(d)
    with pytest.raises(IngestionQuarantineError):submit(stage,d)


@pytest.mark.parametrize('change',[
    {'tenant':''},{'tenant':'alpha '},{'source_version':''},
    {'submitted_by':''},{'batch_id':''},
])
def test_identity_fields_mandatory(stage,change):
    with pytest.raises(IngestionQuarantineError):submit(stage,**change)


@pytest.mark.parametrize('candidate',[[],{},['x'],[1]])
def test_empty_unknown_document_collection(stage,candidate):
    with pytest.raises(IngestionQuarantineError):submit(stage,candidate)


def test_digest_tampering_refused(stage):
    digest=submit(stage)['candidate_sha256'];p=stage._path(digest)
    p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(IngestionQuarantineError,match='digest'):stage.verify(digest,tenant='alpha')


def test_symlink_quarantine_root_rejected(tmp_path):
    (tmp_path/'real').mkdir()
    (tmp_path/'pointer').symlink_to(tmp_path/'real',target_is_directory=True)
    with pytest.raises(IngestionQuarantineError):ImmutableIngestionQuarantine29(tmp_path/'pointer')


def test_symlink_shard_rejected(stage,tmp_path):
    outside=tmp_path/'outside';outside.mkdir()
    (stage.root/'ac').symlink_to(outside,target_is_directory=True)
    d=docs();r=submit(stage,d)
    with pytest.raises(IngestionQuarantineError):stage.verify('ac'+'0'*62,tenant='alpha')
    assert r['publication_authorized'] is False


def test_wrong_tenant_refused(stage):
    digest=submit(stage)['candidate_sha256']
    with pytest.raises(IngestionQuarantineError):stage.verify(digest,tenant='beta')


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['add','index_chunks','add_documents'])
async def test_ingestion_port_denies_direct_writes(operation):
    w=DenyDirectVectorMutation29()
    with pytest.raises(ServingDenied):await getattr(w,operation)([],{})


def test_unknown_mutation_api_rejected():
    with pytest.raises(ServingDenied):getattr(DenyDirectVectorMutation29(),'delete_by_chunk_id')


def test_nonhex_digest_rejected(stage):
    with pytest.raises(IngestionQuarantineError):stage.verify('../evil',tenant='alpha')


def test_immutability_existing_different_bytes_denied(stage):
    digest=submit(stage)['candidate_sha256'];p=stage._path(digest)
    p.write_bytes(b'bad')
    with pytest.raises(IngestionQuarantineError,match='tampered'):submit(stage)

"""Wave 2.6 exact signed-source catalog binding and fail-closed queue tests."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import hmac
import importlib.util
import json
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from amc_publication.models import Base, PublicationWork
from amc_publication.types import canonical_bytes

ROOT=Path(__file__).resolve().parents[3]
for name in ('catalog26','approval_adapter','approval_catalog26'):
    path=ROOT/f'backend/amc_publication/{name}.py'
    spec=importlib.util.spec_from_file_location(f'amc_publication.{name}',path)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
from amc_publication import catalog26 as cat, approval_catalog26 as approval

KEY='test-signing-only-0000000000000000000000000000000000'
DOCS=[{'chunk_id':'c01','tenant_id':'t','text':'term expense ratio'},
      {'chunk_id':'c02','tenant_id':'t','text':'scheme NAV 13.55'}]

def evidence(tmp_path, *, docs=None):
    docs=DOCS if docs is None else docs
    cat_raw=cat.inventory_bytes('t','v1',docs)
    manifest=tmp_path/'catalog.json'; manifest.write_bytes(cat_raw)
    body={'tenant':'t','proposal_id':'p1','approved_revision':1,'source_version':'v1',
          'source_manifest_sha256':hashlib.sha256(cat_raw).hexdigest(),
          'complete':True,'documents':docs}
    seal=hmac.new(KEY.encode(),canonical_bytes(body),hashlib.sha256).hexdigest()
    snap=tmp_path/'snapshot.json';snap.write_text(json.dumps({'payload':body,'hmac_sha256':seal}))
    return manifest,snap

@pytest.fixture
def env(tmp_path):
    eng=create_engine('sqlite:///'+str(tmp_path/'journal.sqlite'))
    Base.metadata.create_all(eng)
    sessions=sessionmaker(bind=eng,expire_on_commit=False)
    patch=SimpleNamespace(patch_id='p1',tenant_id='t',status='APPROVED',version=1,
                          entity_id='fund',attribute='nav',corrected_value='13.55',
                          provenance={'proposer_username':'author','approver_username':'reviewer'})
    yield sessions,patch,SimpleNamespace(username='deployer')
    eng.dispose()


def test_exact_catalog_documents_bound_by_signed_digest(tmp_path):
    manifest,snap=evidence(tmp_path)
    verified=sys.modules['amc_publication.approval_adapter'].load_verified_corpus(snap,KEY,tenant='t',proposal_id='p1',revision=1)
    proof=cat.verify_catalog(verified,manifest)
    assert proof['chunks']==2 and proof['tenant']=='t'


def test_disjoint_corpus_same_count_rejected(tmp_path):
    manifest,snap=evidence(tmp_path)
    verified=sys.modules['amc_publication.approval_adapter'].load_verified_corpus(snap,KEY,tenant='t',proposal_id='p1',revision=1)
    evil=[dict(DOCS[0]),dict(DOCS[1],text='incorrect NAV')]
    manifest.write_bytes(cat.inventory_bytes('t','v1',evil))
    with pytest.raises(cat.CatalogMismatch): cat.verify_catalog(verified,manifest)


def test_reordered_catalog_bytes_fail_closed(tmp_path):
    manifest,snap=evidence(tmp_path)
    verified=sys.modules['amc_publication.approval_adapter'].load_verified_corpus(snap,KEY,tenant='t',proposal_id='p1',revision=1)
    data=json.loads(manifest.read_bytes());manifest.write_text(json.dumps(data, indent=3))
    with pytest.raises(cat.CatalogMismatch):cat.verify_catalog(verified,manifest)


def test_cross_tenant_catalog_rejected():
    with pytest.raises(cat.CatalogMismatch):cat.inventory_bytes('t','v1',[dict(DOCS[0],tenant_id='other')])


def test_duplicate_canonical_ids_rejected():
    with pytest.raises(cat.CatalogMismatch):cat.inventory_bytes('t','v1',[DOCS[0],DOCS[0]])


def test_unsorted_source_still_canonical(tmp_path):
    manifest,_=evidence(tmp_path,docs=list(reversed(DOCS)))
    body=json.loads(manifest.read_bytes())
    assert [c['chunk_id'] for c in body['chunks']]==['c01','c02']


def test_valid_catalog_queue_with_existing_journal(tmp_path,env,monkeypatch):
    sessions,patch,actor=env
    catalog,snap=evidence(tmp_path)
    monkeypatch.setenv('AMC_PUBLICATION_CORPUS_SNAPSHOT',str(snap))
    monkeypatch.setenv('AMC_PUBLICATION_SOURCE_CATALOG',str(catalog))
    monkeypatch.setenv('AMC_PUBLICATION_CORPUS_SIGNING_KEY',KEY)
    work=approval.queue_from_environment_26(sessions=sessions,patch=patch,actor=actor)
    with sessions() as s:
        row=s.get(PublicationWork,work)
        assert row and row.tenant=='t' and row.payload['full_vector_snapshot']==DOCS
    # Idempotent when the same approved revision is retried.
    assert approval.queue_from_environment_26(sessions=sessions,patch=patch,actor=actor)==work


def test_missing_catalog_no_jobs(tmp_path,env,monkeypatch):
    sessions,patch,actor=env
    _,snap=evidence(tmp_path)
    monkeypatch.setenv('AMC_PUBLICATION_CORPUS_SNAPSHOT',str(snap))
    monkeypatch.setenv('AMC_PUBLICATION_CORPUS_SIGNING_KEY',KEY)
    monkeypatch.delenv('AMC_PUBLICATION_SOURCE_CATALOG',raising=False)
    with pytest.raises(Exception,match='catalog'):
        approval.queue_from_environment_26(sessions=sessions,patch=patch,actor=actor)
    with sessions() as s: assert s.query(PublicationWork).count()==0


def test_cross_version_catalog_no_jobs(tmp_path,env,monkeypatch):
    sessions,patch,actor=env
    manifest,snap=evidence(tmp_path)
    manifest.write_bytes(cat.inventory_bytes('t','v2',DOCS))
    monkeypatch.setenv('AMC_PUBLICATION_CORPUS_SNAPSHOT',str(snap))
    monkeypatch.setenv('AMC_PUBLICATION_CORPUS_SIGNING_KEY',KEY)
    monkeypatch.setenv('AMC_PUBLICATION_SOURCE_CATALOG',str(manifest))
    with pytest.raises(Exception,match='catalog'):
        approval.queue_from_environment_26(sessions=sessions,patch=patch,actor=actor)
    with sessions() as s: assert s.query(PublicationWork).count()==0


def test_cross_reviewer_rejected_even_with_catalog(tmp_path,env,monkeypatch):
    sessions,patch,actor=env
    catalog,snap=evidence(tmp_path)
    patch.provenance['approver_username']='author'
    monkeypatch.setenv('AMC_PUBLICATION_CORPUS_SNAPSHOT',str(snap))
    monkeypatch.setenv('AMC_PUBLICATION_CORPUS_SIGNING_KEY',KEY)
    monkeypatch.setenv('AMC_PUBLICATION_SOURCE_CATALOG',str(catalog))
    with pytest.raises(Exception,match='independent'):
        approval.queue_from_environment_26(sessions=sessions,patch=patch,actor=actor)
    with sessions() as s:assert s.query(PublicationWork).count()==0


def test_symlink_catalog_refused(tmp_path):
    manifest,snap=evidence(tmp_path)
    link=tmp_path/'catalog_link.json';link.symlink_to(manifest)
    verified=sys.modules['amc_publication.approval_adapter'].load_verified_corpus(snap,KEY,tenant='t',proposal_id='p1',revision=1)
    with pytest.raises(cat.CatalogMismatch):cat.verify_catalog(verified,link)

"""Wave 3.1 durable first-publication scope arbitration; disposable SQLite only."""
from __future__ import annotations
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from amc_publication.models import Base, PublicationWork
from amc_publication.journal import Journal
from amc_publication.active_authority28 import (
    PublicationScopeClaim31, _claim_scope, _require_scope, _release_scope,
)
from amc_publication.types import Conflict


@pytest.fixture
def db(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'scope31.sqlite'))
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine,expire_on_commit=False)
    def job(s, wid, tenant='T'):
        s.add(PublicationWork(id=wid,tenant=tenant,idempotency_key=wid,proposal_id=wid,
            approved_revision=1,payload_hash='a'*64,
            payload={'entity':wid,'attribute':'NAV','full_vector_snapshot':[]},status='queued'))
    with Session.begin() as s:
        for tenant in ('T','U'):
            for name in ('one','two','three'):
                job(s,tenant+name,tenant)
    yield Session
    engine.dispose()


def test_first_writer_without_authority_is_reserved(db):
    with db.begin() as s:
        lease=_claim_scope(s,'T','vector_faiss','Tone')
        assert lease.status=='HELD' and lease.claim_epoch==1
    with db() as s:
        assert s.get(PublicationScopeClaim31,('T','vector_faiss')).owner_work_id=='Tone'


def test_second_first_writer_is_refused_even_without_pointer_or_authority(db):
    with db.begin() as s:_claim_scope(s,'T','vector_faiss','Tone')
    with pytest.raises(Conflict,match='another publication'):
        with db.begin() as s:_claim_scope(s,'T','vector_faiss','Ttwo')


def test_same_work_crash_replay_preserves_scope_epoch(db):
    with db.begin() as s:_claim_scope(s,'T','vector_faiss','Tone')
    with db.begin() as s:
        claim=_claim_scope(s,'T','vector_faiss','Tone')
        assert claim.claim_epoch==1 and claim.status=='HELD'


def test_replacement_after_verified_release_increments_epoch(db):
    with db.begin() as s:
        _claim_scope(s,'T','vector_faiss','Tone')
        _release_scope(s,'T','vector_faiss','Tone')
    with db.begin() as s:
        claim=_claim_scope(s,'T','vector_faiss','Ttwo')
        assert claim.claim_epoch==2 and claim.owner_work_id=='Ttwo'


def test_same_old_work_cannot_restart_after_release(db):
    with db.begin() as s:
        _claim_scope(s,'T','vector_faiss','Tone')
        _release_scope(s,'T','vector_faiss','Tone')
    with pytest.raises(Conflict,match='previously released'):
        with db.begin() as s:_claim_scope(s,'T','vector_faiss','Tone')


def test_wrong_work_cannot_release(db):
    with db.begin() as s:_claim_scope(s,'T','vector_faiss','Tone')
    with pytest.raises(Conflict,match='no exclusive'):
        with db.begin() as s:_release_scope(s,'T','vector_faiss','Ttwo')
    with db() as s:assert s.get(PublicationScopeClaim31,('T','vector_faiss')).status=='HELD'


def test_duplicate_release_fails(db):
    with db.begin() as s:
        _claim_scope(s,'T','vector_faiss','Tone')
        _release_scope(s,'T','vector_faiss','Tone')
    with pytest.raises(Conflict,match='no exclusive'):
        with db.begin() as s:_release_scope(s,'T','vector_faiss','Tone')


def test_cross_tenant_independence(db):
    with db.begin() as s:
        _claim_scope(s,'T','vector_faiss','Tone')
        _claim_scope(s,'U','vector_faiss','Uone')
    with db() as s:
        assert s.query(PublicationScopeClaim31).count()==2


def test_independent_namespace_can_be_claimed(db):
    with db.begin() as s:
        _claim_scope(s,'T','vector_faiss','Tone')
        _claim_scope(s,'T','graph','Ttwo')
    with db() as s:assert s.query(PublicationScopeClaim31).count()==2


@pytest.mark.parametrize('tenant,namespace,owner',[
    ('','vector_faiss','Tone'),('T','','Tone'),('T','vector_faiss',''),
    (None,'vector_faiss','Tone'),('T',None,'Tone'),('T','vector_faiss',None),
])
def test_blank_scope_is_rejected(db,tenant,namespace,owner):
    with pytest.raises(Conflict,match='explicit'):
        with db.begin() as s:_claim_scope(s,tenant,namespace,owner)


def test_invalid_status_cannot_be_stored(db):
    with pytest.raises(IntegrityError):
        with db.begin() as s:
            s.add(PublicationScopeClaim31(tenant='T',namespace='vector_faiss',
                owner_work_id='Tone',status='BROKEN',claim_epoch=1))


def test_missing_claim_is_not_implicitly_accepted(db):
    with pytest.raises(Conflict,match='no exclusive'):
        with db.begin() as s:_require_scope(s,'T','vector_faiss','Tone')


def test_claim_requires_existing_work(db):
    # SQLite foreign key constraints are not enabled by default; resolve this
    # invariant in the journal work_lease requirement and PostgreSQL migration.
    with db.begin() as s:
        claim=_claim_scope(s,'T','vector_faiss','Tone')
        assert s.get(PublicationWork,claim.owner_work_id).tenant=='T'


def test_journal_prepare_claims_scope_before_first_publication(db):
    # Keep the fixture FK records but prevent them from being claimed first.
    with db.begin() as s:
        for row in s.scalars(select(PublicationWork)).all():
            row.status='failed'
    j=Journal(db)
    wid=j.submit(tenant='T',key='fresh',proposal_id='prop',revision=1,
        payload={'entity':'e','attribute':'NAV','corrected_value':'10',
                 'full_vector_snapshot':[{'tenant_id':'T','chunk_id':'a','text':'data'}]})
    claim=j.claim('worker')
    assert claim.work_id==wid
    j.prepare(claim,kind='graph',target='e',pre={'value':'old'},post={'value':'10'})
    with db() as s:
        c=s.get(PublicationScopeClaim31,('T','vector_faiss'))
        assert c.owner_work_id==wid and c.status=='HELD'
    with pytest.raises(Conflict,match='another publication'):
        with db.begin() as s:_claim_scope(s,'T','vector_faiss','Ttwo')


def test_second_journal_graph_preparation_cannot_mutate_same_tenant(db):
    with db.begin() as s:
        for row in s.scalars(select(PublicationWork)).all():row.status='failed'
    j=Journal(db)
    payload=lambda entity: {'entity':entity,'attribute':'NAV','corrected_value':'10',
        'full_vector_snapshot':[{'chunk_id':entity,'tenant_id':'T','text':'data'}]}
    a=j.submit(tenant='T',key='a',proposal_id='p-a',revision=1,payload=payload('e-a'))
    b=j.submit(tenant='T',key='b',proposal_id='p-b',revision=1,payload=payload('e-b'))
    c1=j.claim('one');c2=j.claim('two')
    assert {c1.work_id,c2.work_id}=={a,b}
    j.prepare(c1,kind='graph',target=c1.payload['entity'],pre={'value':'old'},post={'value':'10'})
    with pytest.raises(Conflict,match='another publication'):
        j.prepare(c2,kind='graph',target=c2.payload['entity'],pre={'value':'old'},post={'value':'10'})
    with db() as s:
        assert s.get(PublicationScopeClaim31,('T','vector_faiss')).owner_work_id==c1.work_id


def test_authorized_rollback_reacquires_released_work_scope(db):
    with db.begin() as s:
        _claim_scope(s,'T','vector_faiss','Tone')
        _release_scope(s,'T','vector_faiss','Tone')
    with db.begin() as s:
        claim=_claim_scope(s,'T','vector_faiss','Tone',rollback=True)
        assert claim.status=='HELD' and claim.claim_epoch==2
    with db.begin() as s:_release_scope(s,'T','vector_faiss','Tone')
    with db() as s:assert s.get(PublicationScopeClaim31,('T','vector_faiss')).status=='RELEASED'


def test_blocked_work_does_not_release_existing_claim(db):
    with db.begin() as s:_claim_scope(s,'T','vector_faiss','Tone')
    with pytest.raises(Conflict):
        with db.begin() as s:
            _claim_scope(s,'T','vector_faiss','Ttwo')
            _release_scope(s,'T','vector_faiss','Tone')
    with db() as s:
        row=s.get(PublicationScopeClaim31,('T','vector_faiss'))
        assert row.status=='HELD' and row.owner_work_id=='Tone'

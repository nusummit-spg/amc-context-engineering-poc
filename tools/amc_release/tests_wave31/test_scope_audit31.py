"""Read-only inspection of active/abandoned scope claims on disposable SQLite."""
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
import pytest
from amc_publication.models import Base, PublicationWork
from amc_publication.active_authority28 import PublicationScopeClaim31
from amc_publication.scope_audit31 import audit_scope_claims

@pytest.fixture
def db(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'audit31.sqlite'))
    Base.metadata.create_all(engine)
    S=sessionmaker(bind=engine,expire_on_commit=False)
    yield S
    engine.dispose()

def add(db, *, work_status='published',scope_status='RELEASED',tenant='T'):
    with db.begin() as s:
        s.add(PublicationWork(id='work',tenant=tenant,idempotency_key='w',proposal_id='w',
            approved_revision=1,payload_hash='0'*64,payload={},status=work_status))
        s.add(PublicationScopeClaim31(tenant=tenant,namespace='vector_faiss',owner_work_id='work',
            status=scope_status,claim_epoch=1))

def test_clean_released_claim_read_only(db):
    add(db)
    result=audit_scope_claims(db)
    assert result['status']=='READ_ONLY_NO_SCOPE_ANOMALIES'
    assert result['anomaly_count']==0
    with db() as s:assert s.scalar(select(PublicationScopeClaim31)).status=='RELEASED'

@pytest.mark.parametrize('state',['queued','failed','leased','rollback_pending'])
def test_release_without_terminal_completion_flagged(db,state):
    add(db,work_status=state)
    result=audit_scope_claims(db)
    assert result['status']=='NEEDS_OPERATOR'
    assert 'RELEASED_WITH_UNEXPECTED_WORK_STATE' in result['findings'][0]['anomalies']

@pytest.mark.parametrize('state',['queued','failed','published','rolled_back'])
def test_held_nonexecution_cannot_be_auto_released(db,state):
    add(db,work_status=state,scope_status='HELD')
    result=audit_scope_claims(db)
    assert result['status']=='NEEDS_OPERATOR' and result['read_only']
    assert 'HELD_WITH_NON_EXECUTING_WORK' in result['findings'][0]['anomalies']
    with db() as s:assert s.scalar(select(PublicationScopeClaim31)).status=='HELD'


def test_empty_db_distinguished_from_missing_migration(db,tmp_path):
    assert audit_scope_claims(db)['status']=='READ_ONLY_NO_SCOPE_ANOMALIES'
    engine=create_engine('sqlite:///'+str(tmp_path/'unmigrated.sqlite'))
    sessions=sessionmaker(bind=engine)
    assert audit_scope_claims(sessions)['status']=='BLOCKED'
    engine.dispose()


def test_tenant_filter_is_exact(db):
    add(db,tenant='T')
    assert audit_scope_claims(db,tenant='U')['scope_count']==0
    assert audit_scope_claims(db,tenant='T')['scope_count']==1
    with pytest.raises(ValueError):audit_scope_claims(db,tenant='')

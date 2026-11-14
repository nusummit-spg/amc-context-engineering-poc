"""Read-only SQL reconciliation fault matrix."""
import pytest
from sqlalchemy import select
from amc_publication.models import (PublicationWork, PublicationReceipt, PublicationEffect,
                                    GenerationPointer, FeedbackPublicationLink)
from amc_publication.reconcile27 import inspect
from tools.amc_release.tests.test_wave27_serving import published,env


def test_good_published_work_is_db_integrity_pass(env):
    published(env)
    item=inspect(env['sessions'],'tenant_A')
    assert item.database_integrity=='PASS' and item.external_services=='NOT_RUN' and item.release_status=='BLOCK'


def test_empty_dataset_is_not_release_pass(env):
    result=inspect(env['sessions'],'tenant_A')
    assert result.jobs==0 and result.release_status=='BLOCK'

@pytest.mark.parametrize('tenant',['',None,' '])
def test_tenant_required(env,tenant):
    with pytest.raises(ValueError):inspect(env['sessions'],tenant)

@pytest.mark.parametrize('limit',[0,-1,50001,'100'])
def test_bounded_limit_required(env,limit):
    with pytest.raises(ValueError):inspect(env['sessions'],'tenant_A',limit=limit)


def test_missing_verified_receipt_is_violation(env):
    wid,rid,_=published(env)
    with env['sessions'].begin() as s:s.get(PublicationReceipt,rid).verified=False
    assert 'PUBLISHED_WITHOUT_VERIFIED_RECEIPT' in inspect(env['sessions'],'tenant_A').violations


def test_wrong_pointer_is_violation(env):
    published(env)
    with env['sessions'].begin() as s:s.get(GenerationPointer,('tenant_A','vector_faiss')).generation_id='wrong'
    assert 'ACTIVE_POINTER_WITHOUT_UNIQUE_PUBLISHED_RECEIPT' in inspect(env['sessions'],'tenant_A').violations

@pytest.mark.parametrize('status',['queued','leased','rollback_pending'])
def test_incomplete_work_blocks(env,status):
    wid,rid,_=published(env)
    with env['sessions'].begin() as s:s.get(PublicationWork,wid).status=status
    assert 'INCOMPLETE_PUBLICATION_JOB' in inspect(env['sessions'],'tenant_A').violations


def test_failed_work_blocks(env):
    wid,rid,_=published(env)
    with env['sessions'].begin() as s:s.get(PublicationWork,wid).status='failed'
    assert 'FAILED_PUBLICATION_JOB' in inspect(env['sessions'],'tenant_A').violations


def test_effect_hash_altered_is_violation(env):
    wid,rid,_=published(env)
    with env['sessions'].begin() as s:
        row=s.scalar(select(PublicationEffect).where(PublicationEffect.work_id==wid))
        row.post_hash='f'*64
    assert 'INVALID_VERIFIED_EFFECT_HASH' in inspect(env['sessions'],'tenant_A').violations


def test_missing_effect_is_violation(env):
    wid,rid,_=published(env)
    with env['sessions'].begin() as s:
        e=s.scalar(select(PublicationEffect).where(PublicationEffect.work_id==wid,PublicationEffect.kind=='graph'))
        s.delete(e)
    assert 'PUBLISHED_WITHOUT_TWO_VERIFIED_EFFECTS' in inspect(env['sessions'],'tenant_A').violations


def test_resolved_feedback_requires_current_receipt(env):
    wid,rid,_=published(env)
    with env['sessions'].begin() as s:
        s.add(FeedbackPublicationLink(tenant='tenant_A',issue_id='issue1',work_id=wid,receipt_id=rid,status='resolved'))
    assert inspect(env['sessions'],'tenant_A').resolved_feedback==1
    with env['sessions'].begin() as s:s.get(PublicationWork,wid).status='rolled_back'
    assert 'RESOLVED_FEEDBACK_WITHOUT_ACTIVE_RECEIPT' in inspect(env['sessions'],'tenant_A').violations


def test_readonly_reconciliation_changes_no_work_states(env):
    wid,rid,_=published(env)
    before=inspect(env['sessions'],'tenant_A').to_dict()
    after=inspect(env['sessions'],'tenant_A').to_dict()
    assert before==after


def test_inventory_limit_is_fail_closed(env):
    published(env)
    assert inspect(env['sessions'],'tenant_A',limit=1).database_integrity=='PASS'
    with env['sessions'].begin() as s:
        s.add(PublicationWork(id='queuedextra',tenant='tenant_A',idempotency_key='extra',proposal_id='extra',
            approved_revision=1,payload_hash='x',payload={},status='queued'))
    assert 'UNBOUNDED_WORK_INVENTORY' in inspect(env['sessions'],'tenant_A',limit=1).violations


def test_scoped_to_one_tenant(env):
    published(env,tenant='tenant_A',suffix='a')
    published(env,tenant='tenant_B',suffix='b')
    assert inspect(env['sessions'],'tenant_A').jobs==1
    assert inspect(env['sessions'],'tenant_B').jobs==1

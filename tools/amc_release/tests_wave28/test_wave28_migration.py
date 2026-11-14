"""Apply actual 013 Alembic operations against a disposable SQLite DB."""
from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import create_engine,inspect,text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from amc_publication.models import Base
from amc_publication.active_authority28 import ActiveReceiptAuthority, AuthorityPreimage

MIGRATION=Path(__file__).resolve().parents[3]/'backend/alembic/versions/013_active_receipt_authority_v28.py'


def load():
    spec=importlib.util.spec_from_file_location('migration_wave28',MIGRATION)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_dag_is_exact_and_does_not_rewrite_history():
    m=load()
    assert m.revision=='013_active_receipt_authority_v28'
    assert m.down_revision=='012_wave19_durable_pub'
    assert m.branch_labels is None


def test_sqlite_additive_migration_upgrade_downgrade(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'migrate.sqlite'))
    try:
        existing=[t for t in Base.metadata.sorted_tables if t.name not in
                  {'publication_active_authority_v28','publication_authority_preimage_v28'}]
        Base.metadata.create_all(engine,tables=existing)
        old_names=set(inspect(engine).get_table_names())
        assert 'publication_pointer_v2' in old_names
        assert 'publication_active_authority_v28' not in old_names
        with engine.begin() as conn:
            m=load()
            m.op=Operations(MigrationContext.configure(conn))
            m.upgrade()
        new_names=set(inspect(engine).get_table_names())
        assert new_names-old_names=={'publication_active_authority_v28','publication_authority_preimage_v28'}
        columns={c['name']:c for c in inspect(engine).get_columns('publication_active_authority_v28')}
        for key in ('tenant','namespace','generation_id','digest','pointer_epoch','work_id','receipt_id','status','suspended_by','updated_at'):
            assert key in columns
        assert columns['status']['nullable'] is False
        with engine.begin() as conn:
            m=load();m.op=Operations(MigrationContext.configure(conn));m.downgrade()
        assert set(inspect(engine).get_table_names())==old_names
    finally: engine.dispose()


def test_db_rejects_invalid_active_authority_status(tmp_path):
    from sqlalchemy.orm import sessionmaker
    from amc_publication.models import PublicationWork, PublicationReceipt, GenerationPointer
    from sqlalchemy.exc import IntegrityError
    engine=create_engine('sqlite:///'+str(tmp_path/'status.sqlite'))
    Base.metadata.create_all(engine)
    try:
        Session=sessionmaker(bind=engine)
        with Session.begin() as s:
            s.add(PublicationWork(id='work',tenant='a',idempotency_key='key',proposal_id='p',approved_revision=1,
                payload_hash='x',payload={'entity':'e'},status='published'))
            s.add(PublicationReceipt(id='receipt',work_id='work',tenant='a',graph_hash='0'*64,
                generation_id='a'*64,generation_digest='a'*64,verified=True))
        with pytest.raises(IntegrityError):
            with Session.begin() as s:
                s.add(ActiveReceiptAuthority(tenant='a',namespace='vector_faiss',generation_id='a'*64,
                    digest='a'*64,pointer_epoch=1,work_id='work',receipt_id='receipt',status='GUESSED'))
    finally:engine.dispose()

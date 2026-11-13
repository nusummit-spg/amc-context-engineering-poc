"""Execute additive 014 DDL against an actual disposable SQLite database."""
from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from amc_publication.models import Base

MIGRATION=Path(__file__).resolve().parents[3]/'backend/alembic/versions/014_publication_scope_claim_v31.py'

def module():
    spec=importlib.util.spec_from_file_location('scope31_migration',MIGRATION)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def test_migration_is_contiguous_and_unambiguous():
    m=module();assert m.revision=='014_publication_scope_claim_v31'
    assert m.down_revision=='013_active_receipt_authority_v28'
    assert m.depends_on is None and m.branch_labels is None


def test_upgrade_downgrade_on_empty_sqlite(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'m.sqlite'))
    try:
        existing=[t for t in Base.metadata.sorted_tables if t.name!='publication_scope_claim_v31']
        Base.metadata.create_all(engine,tables=existing)
        before=set(inspect(engine).get_table_names()); assert 'publication_scope_claim_v31' not in before
        with engine.begin() as conn:
            m=module();m.op=Operations(MigrationContext.configure(conn));m.upgrade()
        after=set(inspect(engine).get_table_names())
        assert after-before=={'publication_scope_claim_v31'}
        cols={c['name']:c for c in inspect(engine).get_columns('publication_scope_claim_v31')}
        assert set(cols)=={'tenant','namespace','owner_work_id','status','claim_epoch','updated_at'}
        assert all(not cols[k]['nullable'] for k in ('tenant','namespace','owner_work_id','status','claim_epoch'))
        with engine.begin() as conn:
            m=module();m.op=Operations(MigrationContext.configure(conn));m.downgrade()
        assert set(inspect(engine).get_table_names())==before
    finally:engine.dispose()

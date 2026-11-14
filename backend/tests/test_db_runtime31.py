"""Pure configuration/DB gate tests; no live PostgreSQL required."""
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from app.core.db_runtime31 import resolve_database_url, verify_migrated_postgresql

def test_default_sqlite_off_mode(monkeypatch,tmp_path):
    monkeypatch.delenv("DATABASE_URL",raising=False)
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","off")
    assert resolve_database_url(tmp_path).startswith("sqlite:///")

def test_off_mode_explicit_pg_url(monkeypatch,tmp_path):
    monkeypatch.setenv("DATABASE_URL","postgresql+psycopg://u:p@localhost/amc")
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","off")
    assert resolve_database_url(tmp_path).startswith("postgresql+psycopg://")

def test_sqlite_rejected_in_verified_mode(monkeypatch,tmp_path):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","enforce")
    monkeypatch.setenv("DATABASE_URL","sqlite:///data.db")
    with pytest.raises(RuntimeError,match="postgresql"):
        resolve_database_url(tmp_path)

def test_wrong_pg_driver_rejected(monkeypatch,tmp_path):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","enforce")
    monkeypatch.setenv("DATABASE_URL","postgresql://u:p@localhost/amc")
    with pytest.raises(RuntimeError,match="psycopg"):
        resolve_database_url(tmp_path)

def test_invalid_mode_rejected(monkeypatch,tmp_path):
    monkeypatch.setenv("AMC_VERIFIED_SERVING_MODE","enforc")
    with pytest.raises(RuntimeError):
        resolve_database_url(tmp_path)

def test_sqlite_cannot_claim_migrated():
    with pytest.raises(RuntimeError,match="non-PostgreSQL"):
        verify_migrated_postgresql(create_engine("sqlite://"))

class FakeDB:
    dialect=SimpleNamespace(name="postgresql")
    def __init__(self,version):self.version=version
    def connect(self):return self
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,_):return self
    def scalars(self):return self
    def all(self):return [self.version]

def test_old_schema_blocks():
    with pytest.raises(RuntimeError,match="revision 014"):
        verify_migrated_postgresql(FakeDB("013_active_receipt_authority_v28"))

def test_exact_schema_passes():
    verify_migrated_postgresql(FakeDB("014_publication_scope_claim_v31"))

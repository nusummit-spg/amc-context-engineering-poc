# app/core/database.py
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
DATABASE_URL = f"sqlite:///{BASE_DIR / 'data.db'}"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    """SQLite ignores FOREIGN KEY constraints unless this is set per-connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.core.models import (
        UnifiedEvaluationRecord,
        AuditMetadata,
        Violation,
        ResponseFeedback,
        QueryEvidence,
        ComplianceRule,
        FundScheme,
        ChatSession,
    )

    Base.metadata.create_all(bind=engine)
# app/core/database.py
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
DATABASE_URL = f"sqlite:///{BASE_DIR / 'data.db'}"


Base = declarative_base()


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
    from app import schemas

    Base.metadata.create_all(bind=engine)
    try:
        from app.db.migrate_data import populate_data_db
        populate_data_db()
    except Exception as e:
        import logging
        logging.getLogger("app.core.database").warning("Failed to auto-populate data.db: %s", e)
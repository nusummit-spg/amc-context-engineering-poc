# app/core/database.py
"""Module providing database functionality."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
DATABASE_URL = f"sqlite:///{BASE_DIR / 'data.db'}"


Base = declarative_base()


engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30.0,  # 30-second lock timeout
    },
    pool_pre_ping=True,  # Verify connection health before use
)


@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    """SQLite ignores FOREIGN KEY constraints unless this is set per-connection.
    Also enables WAL mode for better concurrent access.

    Args:
        dbapi_connection: The dbapi connection.
        connection_record: The connection record.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30-second busy timeout
    cursor.close()


@event.listens_for(engine, "checkout")
def _verify_fk_on_checkout(dbapi_connection, connection_record, connection_proxy):
    """Verify FK enforcement is still active on pooled connections.

    Args:
        dbapi_connection: The dbapi connection.
        connection_record: The connection record.
        connection_proxy: The connection proxy.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys")
    result = cursor.fetchone()
    if result[0] != 1:
        cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Retrieve db.

    Returns:
        Yielded results or items.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize db.
    """
    from app import schemas

    Base.metadata.create_all(bind=engine)
    try:
        from scripts.migrate_user_ownership import run_migration
        run_migration(BASE_DIR / "data.db")
    except Exception as e:
        import logging
        logging.getLogger("app.core.database").warning("Failed to run user ownership migration: %s", e)

    try:
        from scripts.migrate_feedback_issues import run_migration as run_feedback_issues_migration
        run_feedback_issues_migration(BASE_DIR / "data.db")
    except Exception as e:
        import logging
        logging.getLogger("app.core.database").warning("Failed to run feedback issues migration: %s", e)

    try:
        from app.db.migrate_data import populate_data_db
        populate_data_db()
    except Exception as e:
        import logging
        logging.getLogger("app.core.database").warning("Failed to auto-populate data.db: %s", e)
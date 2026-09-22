#!/usr/bin/env python
"""
Reinitialize the data.db by truncating all tables and repopulating with seed data.
Run this with: python reinit_db.py
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.core.database import Base, engine
from app.db.migrate_data import populate_data_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reinit_db():
    """Drop all tables and recreate them with initial data."""
    try:
        logger.info("Disposing engine connections...")
        engine.dispose()

        db_path = backend_dir / "data.db"
        if db_path.exists():
            logger.info(f"Removing existing database file {db_path}...")
            try:
                db_path.unlink()
                for suffix in ["-wal", "-shm", "-journal"]:
                    extra = db_path.with_name(db_path.name + suffix)
                    if extra.exists():
                        extra.unlink()
                logger.info("Database file removed successfully.")
            except Exception as ex:
                logger.warning(f"Could not remove database file directly ({ex}), dropping tables with foreign keys disabled...")
                with engine.connect() as conn:
                    conn.exec_driver_sql("PRAGMA foreign_keys = OFF;")
                    for table in [
                        "unified_evaluation_records",
                        "response_feedback",
                        "query_evidence",
                        "violations",
                        "chat_sessions",
                        "compliance_rules",
                        "fund_schemes",
                        "audit_metadata",
                    ]:
                        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {table};")
                    conn.commit()
                    conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
                    conn.commit()
                logger.info("All tables dropped successfully.")
        else:
            logger.info("Database file does not exist, creating fresh database.")
        
        logger.info("Creating all tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("All tables created successfully")
        
        logger.info("Populating with initial data...")
        res = populate_data_db()
        logger.info(f"✓ Database reinitialized successfully! Summary: {res}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to reinitialize database: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = reinit_db()
    sys.exit(0 if success else 1)

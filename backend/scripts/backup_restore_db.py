#!/usr/bin/env python
"""
backup_restore_db.py
====================
Provides comprehensive backup, reinitialization, restoration, and verification
for backend/data.db.
"""

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data.db"
BACKUP_DB_PATH = BASE_DIR / "data.db.backup.sqlite"
BACKUP_JSON_PATH = BASE_DIR / "data.db.backup.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backup_restore_db")

# Add backend directory to sys.path
sys.path.insert(0, str(BASE_DIR))


def get_table_counts(conn: sqlite3.Connection) -> dict:
    """Return dictionary of {table_name: count}."""
    cursor = conn.cursor()
    tables = [
        row[0]
        for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if not row[0].startswith("sqlite")
    ]
    counts = {}
    for table in tables:
        count = cursor.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        counts[table] = count
    return counts


def create_backup():
    """Create complete atomic backup of data.db to SQLite file and JSON dump."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database file not found: {DB_PATH}")

    logger.info("Connecting to source database: %s", DB_PATH)
    source_conn = sqlite3.connect(str(DB_PATH))
    source_conn.row_factory = sqlite3.Row

    # Record counts before backup
    counts = get_table_counts(source_conn)
    logger.info("Source database table counts: %s", counts)

    # 1. Atomic SQLite backup
    logger.info("Writing atomic SQLite backup to: %s", BACKUP_DB_PATH)
    if BACKUP_DB_PATH.exists():
        BACKUP_DB_PATH.unlink()
    dest_conn = sqlite3.connect(str(BACKUP_DB_PATH))
    source_conn.backup(dest_conn)
    dest_conn.close()

    # 2. JSON data dump (preserves records independently of schema)
    logger.info("Writing JSON backup to: %s", BACKUP_JSON_PATH)
    json_dump = {}
    cursor = source_conn.cursor()
    for table in counts.keys():
        rows = cursor.execute(f'SELECT * FROM "{table}"').fetchall()
        json_dump[table] = [dict(r) for r in rows]

    with open(BACKUP_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_dump, f, indent=2, default=str)

    source_conn.close()
    logger.info("✓ Complete backup successfully created! Total tables: %d", len(counts))
    return counts


def reinitialize_database():
    """Run reinit_db to recreate schema and seed baseline data."""
    logger.info("Reinitializing database using reinit_db...")
    from reinit_db import reinit_db

    success = reinit_db()
    if not success:
        raise RuntimeError("reinit_db() returned False")

    conn = sqlite3.connect(str(DB_PATH))
    counts = get_table_counts(conn)
    conn.close()
    logger.info("Fresh database table counts after reinit: %s", counts)
    return counts


def restore_backup(expected_counts: dict):
    """Restore all backed-up data into the freshly initialized data.db."""
    if not BACKUP_DB_PATH.exists() and not BACKUP_JSON_PATH.exists():
        raise FileNotFoundError("Backup files not found for restoration!")

    logger.info("Restoring data from backup into: %s", DB_PATH)
    target_conn = sqlite3.connect(str(DB_PATH))
    target_conn.row_factory = sqlite3.Row
    cursor = target_conn.cursor()

    # Disable foreign keys during batch restoration to avoid ordering constraints
    cursor.execute("PRAGMA foreign_keys = OFF;")

    with open(BACKUP_JSON_PATH, "r", encoding="utf-8") as f:
        json_dump = json.load(f)

    for table, rows in json_dump.items():
        if not rows:
            logger.info("Table '%s' has 0 rows in backup, skipping.", table)
            continue

        # Get existing columns in target table
        table_info = cursor.execute(f'PRAGMA table_info("{table}")').fetchall()
        col_names = [col[1] for col in table_info]

        # Clear target table before restoring exact snapshot
        cursor.execute(f'DELETE FROM "{table}";')

        # Insert rows
        cols_to_insert = [c for c in col_names if c in rows[0]]
        col_placeholders = ", ".join(["?"] * len(cols_to_insert))
        col_list_str = ", ".join([f'"{c}"' for c in cols_to_insert])
        sql = f'INSERT INTO "{table}" ({col_list_str}) VALUES ({col_placeholders})'

        row_tuples = [
            tuple(r.get(c) for c in cols_to_insert)
            for r in rows
        ]
        cursor.executemany(sql, row_tuples)
        logger.info("Restored %d rows into table '%s'", len(row_tuples), table)

    target_conn.commit()

    # Re-enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    target_conn.commit()

    # Verify restoration
    restored_counts = get_table_counts(target_conn)
    logger.info("Restored database table counts: %s", restored_counts)

    # Check counts against expected
    mismatches = []
    for table, count in expected_counts.items():
        res_count = restored_counts.get(table, 0)
        if res_count != count:
            mismatches.append(f"Table '{table}': expected {count}, got {res_count}")

    if mismatches:
        target_conn.close()
        raise ValueError(f"Restoration verification failed due to count mismatches: {mismatches}")

    # Check SQLite integrity
    integrity_result = cursor.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity_result != "ok":
        target_conn.close()
        raise ValueError(f"SQLite PRAGMA integrity_check failed: {integrity_result}")

    # Check foreign key integrity
    fk_violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
    if fk_violations:
        target_conn.close()
        raise ValueError(f"SQLite PRAGMA foreign_key_check found violations: {fk_violations}")

    target_conn.close()
    logger.info("✓ Restoration verified successfully! Integrity check: ok, FK check: passed.")
    return restored_counts


def delete_backup():
    """Delete the backup files once restoration is confirmed."""
    logger.info("Deleting backup files...")
    deleted = []
    if BACKUP_DB_PATH.exists():
        BACKUP_DB_PATH.unlink()
        deleted.append(str(BACKUP_DB_PATH))
    if BACKUP_JSON_PATH.exists():
        BACKUP_JSON_PATH.unlink()
        deleted.append(str(BACKUP_JSON_PATH))
    logger.info("✓ Backup deleted successfully: %s", deleted)


def run_full_cycle():
    """Execute complete backup -> reinit -> restore -> verify -> delete backup."""
    logger.info("=== STEP 1: Creating backup of existing data.db ===")
    initial_counts = create_backup()

    logger.info("=== STEP 2: Reinitializing data.db ===")
    reinitialize_database()

    logger.info("=== STEP 3: Restoring backed-up data into newly initialized data.db ===")
    restored_counts = restore_backup(initial_counts)

    logger.info("=== STEP 4: Deleting backup files upon confirmed restoration ===")
    delete_backup()

    logger.info("=== COMPLETED SUCCESSFULLY! Database restored and verified. ===")
    return restored_counts


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        conn = sqlite3.connect(str(DB_PATH))
        counts = get_table_counts(conn)
        print("Table counts:", counts)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        print("Integrity check:", integrity)
        print("FK check violations:", len(fk))
        conn.close()
    else:
        run_full_cycle()

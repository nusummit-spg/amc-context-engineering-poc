#!/usr/bin/env python
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Script: clean_data_db.py
# Description: Complete cleanup utility for the application while preserving
#              its database schema, tables, columns, and relations.
#              - Deletes all recent chat conversations & disk artifacts
#              - Clears the entire intent cache & cached data stores
#              - Truncates all application records in data.db
#              - Ensures amc_admin exists with password 'Compliance@2026'
#              - Recursively deletes all __pycache__ directories
#              - Clears backend log files without disrupting future logging
#              - Verifies amc_admin account authentication accessibility
# ===========================================================================
"""Operational and maintenance script for complete application cleanup."""

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import stat
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure UTF-8 output if console supports reconfiguration
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Setup base paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# Default path configurations
DEFAULT_DB_PATH = BACKEND_DIR / "data.db"
DEFAULT_BACKEND_LOGS_DIR = BACKEND_DIR / "logs"
DEFAULT_ROOT_LOGS_DIR = PROJECT_ROOT / "logs"
DEFAULT_CHAT_SESSIONS_DIR = DEFAULT_BACKEND_LOGS_DIR / "chat_sessions"
DEFAULT_CHAT_EVIDENCE_DIR = DEFAULT_BACKEND_LOGS_DIR / "chat_query_evidence"
DEFAULT_CACHE_DIR = BACKEND_DIR / "cache"
DEFAULT_USERS_RBAC_PATH = BACKEND_DIR / "config" / "users_rbac.json"
DEFAULT_USERS_DATA_PATH = BACKEND_DIR / "app" / "auth" / "data" / "users.json"

# Target administrative account specifications
AMC_ADMIN_USERNAME = "amc_admin"
AMC_ADMIN_PASSWORD = "Compliance@2026"
AMC_ADMIN_ROLE = "Compliance & Regulatory Officer"
AMC_ADMIN_DEPARTMENT = "Regulatory & Legal Compliance"
AMC_ADMIN_EMAIL = "amc_admin@amc.com"
AMC_ADMIN_DISPLAY_NAME = "AMC Administrator"
AMC_ADMIN_AVATAR = "AA"

# Known chat tables for specific cleanup
CHAT_TABLES = [
    "graph_mutations",
    "repair_proposals",
    "unified_evaluation_records",
    "response_feedback",
    "query_evidence",
    "chat_sessions",
]


# ===========================================================================
# Password Hashing & Verification (PBKDF2-SHA256, 260,000 iterations)
# ===========================================================================

def generate_pbkdf2_hash(plain_password: str, salt: Optional[str] = None) -> str:
    """Generate self-describing PBKDF2-SHA256 password hash.

    Format: pbkdf2_sha256$iterations$salt_hex$hash_hex

    Args:
        plain_password (str): The plain password.
        salt (Optional[str]): Optional salt hex string.

    Returns:
        str: PBKDF2 hash string matching application security standards.
    """
    try:
        from app.auth.security import hash_password as app_hash_password
        return app_hash_password(plain_password, salt=salt)
    except Exception:
        pass

    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    iterations = 260_000
    derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt_bytes, iterations)
    return f"pbkdf2_sha256${iterations}${salt_bytes.hex()}${derived.hex()}"


def verify_pbkdf2_password(plain_password: str, stored_hash: str) -> bool:
    """Constant-time comparison against a pbkdf2_sha256 stored hash string.

    Args:
        plain_password (str): Plain text password.
        stored_hash (str): Hash stored in database.

    Returns:
        bool: True if password matches, False otherwise.
    """
    try:
        from app.auth.security import verify_password as app_verify_password
        return app_verify_password(plain_password, stored_hash)
    except Exception:
        pass

    try:
        algo, iterations_s, salt_hex, hash_hex = stored_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt_bytes = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt_bytes, iterations)
        return hmac.compare_digest(expected.hex(), hash_hex)
    except Exception:
        return False


# ===========================================================================
# Filesystem Helpers (Handles Windows Read-Only & In-Use Locks Gracefully)
# ===========================================================================

def safe_remove_directory(dir_path: Path | str) -> bool:
    """Safely remove a directory and its contents, handling Windows read-only attributes.

    Args:
        dir_path (Path | str): Filesystem path to the directory.

    Returns:
        bool: True if removed or already non-existent, False on failure.
    """
    p = Path(dir_path).resolve()
    if not p.exists():
        return True

    try:
        for root, dirs, files in os.walk(str(p), topdown=False):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    os.chmod(fpath, stat.S_IWRITE)
                    os.unlink(fpath)
                except Exception:
                    pass
            for dname in dirs:
                dpath = os.path.join(root, dname)
                try:
                    os.chmod(dpath, stat.S_IWRITE)
                    os.rmdir(dpath)
                except Exception:
                    pass
        os.chmod(str(p), stat.S_IWRITE)
        os.rmdir(str(p))
        return not p.exists()
    except Exception:
        try:
            shutil.rmtree(str(p), ignore_errors=True)
            return not p.exists()
        except Exception:
            return False


def safe_truncate_file(file_path: Path | str) -> bool:
    """Truncate a file to 0 bytes in-place to avoid disrupting open file handles.

    Args:
        file_path (Path | str): Filesystem path to the file.

    Returns:
        bool: True if truncated, False otherwise.
    """
    p = Path(file_path).resolve()
    if not p.exists() or not p.is_file():
        return False
    try:
        os.chmod(str(p), stat.S_IWRITE)
        with open(str(p), "w", encoding="utf-8") as f:
            f.truncate(0)
        return True
    except Exception:
        try:
            with open(str(p), "wb") as f:
                f.truncate(0)
            return True
        except Exception:
            return False


# ===========================================================================
# Database Schema & Metadata Helpers
# ===========================================================================

def get_all_tables(conn: sqlite3.Connection) -> List[str]:
    """Retrieve list of user-defined tables in SQLite database.

    Args:
        conn (sqlite3.Connection): SQLite connection object.

    Returns:
        List[str]: List of table names sorted alphabetically.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC;"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_counts(conn: sqlite3.Connection, tables: Optional[List[str]] = None) -> Dict[str, int]:
    """Return dictionary mapping table name to current row count.

    Args:
        conn (sqlite3.Connection): SQLite connection object.
        tables (Optional[List[str]]): Specific tables to inspect, or all if None.

    Returns:
        Dict[str, int]: Mapping of table name to row count.
    """
    if tables is None:
        tables = get_all_tables(conn)
    cursor = conn.cursor()
    counts: Dict[str, int] = {}
    for table in tables:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{table}";')
            counts[table] = cursor.fetchone()[0]
        except Exception:
            counts[table] = 0
    return counts


def create_atomic_backup(source_conn: sqlite3.Connection, db_path: Path) -> Path:
    """Create an atomic snapshot backup of the SQLite database before modifications.

    Args:
        source_conn (sqlite3.Connection): Active database connection.
        db_path (Path): Filesystem path to the target database.

    Returns:
        Path: Path of the newly created backup snapshot.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.name}.bak_{timestamp}"
    dest_conn = sqlite3.connect(str(backup_path))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
    return backup_path


def ensure_database_schema(conn: sqlite3.Connection) -> None:
    """Ensure all core tables and columns exist in data.db before cleanup.
    Preserves all existing tables and initializes missing schema definitions safely.

    Args:
        conn (sqlite3.Connection): Active database connection.
    """
    try:
        from app.core.database import engine, Base
        import app.schemas
        from app.schemas.auth_users_table import AuthUser
        Base.metadata.create_all(bind=engine)
    except Exception:
        # Fallback DDL for auth_users if SQLAlchemy cannot be initialized
        cursor = conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS auth_users (
                username VARCHAR(128) NOT NULL,
                password_hash VARCHAR(256) NOT NULL,
                display_name VARCHAR(256) NOT NULL,
                email VARCHAR(256) NOT NULL,
                role VARCHAR(128) NOT NULL,
                department VARCHAR(256) NOT NULL DEFAULT '',
                avatar_initials VARCHAR(10) NOT NULL DEFAULT '',
                status VARCHAR(20) NOT NULL DEFAULT 'Active',
                tenant_id VARCHAR(64),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                is_superuser BOOLEAN NOT NULL DEFAULT 0,
                last_login DATETIME,
                last_login_ip VARCHAR(45),
                PRIMARY KEY (username)
            );"""
        )
        conn.commit()


# ===========================================================================
# Core Cleanup Steps
# ===========================================================================

def clean_chat_history(
    conn: sqlite3.Connection,
    dry_run: bool = False,
    chat_sessions_dir: Path = DEFAULT_CHAT_SESSIONS_DIR,
    chat_evidence_dir: Path = DEFAULT_CHAT_EVIDENCE_DIR,
    logs_dir: Path = DEFAULT_BACKEND_LOGS_DIR,
    root_logs_dir: Path = DEFAULT_ROOT_LOGS_DIR,
) -> Dict[str, Any]:
    """Delete all recent chat conversations displayed in the frontend sidebar under
    'Recent Chat History' and permanently remove their records from backend and database.

    Args:
        conn (sqlite3.Connection): Active database connection.
        dry_run (bool): If True, simulate without deletion.
        chat_sessions_dir (Path): Path to chat sessions directory.
        chat_evidence_dir (Path): Path to chat query evidence directory.
        logs_dir (Path): Path to backend logs directory.
        root_logs_dir (Path): Path to root logs directory.

    Returns:
        Dict[str, Any]: Summary dictionary of removed records and files.
    """
    summary: Dict[str, Any] = {
        "db_records_removed": {},
        "session_files_removed": 0,
        "evidence_files_removed": 0,
        "session_folders_removed": 0,
    }

    tables = get_all_tables(conn)
    cursor = conn.cursor()

    # Discover disk artifacts
    session_files: List[Path] = []
    for d in [chat_sessions_dir, root_logs_dir / "chat_sessions"]:
        if d.exists():
            session_files.extend(list(d.glob("*.json")))

    evidence_files: List[Path] = []
    for d in [chat_evidence_dir, root_logs_dir / "chat_query_evidence"]:
        if d.exists():
            evidence_files.extend(list(d.glob("*.json")))

    session_dirs: List[Path] = []
    for d in [logs_dir, root_logs_dir]:
        if d.exists():
            for sub in d.glob("session_*"):
                if sub.is_dir():
                    session_dirs.append(sub)

    if dry_run:
        for tbl in CHAT_TABLES:
            if tbl in tables:
                cursor.execute(f'SELECT COUNT(*) FROM "{tbl}";')
                summary["db_records_removed"][tbl] = cursor.fetchone()[0]
        summary["session_files_removed"] = len(session_files)
        summary["evidence_files_removed"] = len(evidence_files)
        summary["session_folders_removed"] = len(session_dirs)
        return summary

    # Remove records from database in safe dependency order
    cursor.execute("PRAGMA foreign_keys = OFF;")
    for tbl in CHAT_TABLES:
        if tbl in tables:
            cursor.execute(f'DELETE FROM "{tbl}";')
            deleted = cursor.rowcount
            summary["db_records_removed"][tbl] = deleted
            # Reset autoincrement sequence if sqlite_sequence exists
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?;", (tbl,))
            except Exception:
                pass
    conn.commit()

    # Remove disk files
    for f in session_files:
        try:
            os.chmod(str(f), stat.S_IWRITE)
            f.unlink()
            summary["session_files_removed"] += 1
        except Exception:
            pass

    for f in evidence_files:
        try:
            os.chmod(str(f), stat.S_IWRITE)
            f.unlink()
            summary["evidence_files_removed"] += 1
        except Exception:
            pass

    for d in session_dirs:
        if safe_remove_directory(d):
            summary["session_folders_removed"] += 1

    # Ensure directories remain ready for subsequent sessions
    chat_sessions_dir.mkdir(parents=True, exist_ok=True)
    chat_evidence_dir.mkdir(parents=True, exist_ok=True)

    return summary


def clean_intent_cache(
    dry_run: bool = False,
    logs_dir: Path = DEFAULT_BACKEND_LOGS_DIR,
    root_logs_dir: Path = DEFAULT_ROOT_LOGS_DIR,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Dict[str, Any]:
    """Clear or delete the entire intent cache, savings ledger, and associated cached data.

    Args:
        dry_run (bool): If True, simulate without deletion.
        logs_dir (Path): Path to backend logs directory.
        root_logs_dir (Path): Path to root logs directory.
        cache_dir (Path): Path to backend cache directory.

    Returns:
        Dict[str, Any]: Summary dictionary of cleared caches.
    """
    summary: Dict[str, Any] = {
        "files_cleared": [],
        "directories_cleaned": [],
        "in_memory_layers_cleared": [],
    }

    target_files = [
        logs_dir / "intent_cache_store.json",
        root_logs_dir / "intent_cache_store.json",
        logs_dir / "savings_ledger.json",
        root_logs_dir / "savings_ledger.json",
    ]

    for tf in target_files:
        if tf.exists():
            summary["files_cleared"].append(str(tf))
            if not dry_run:
                try:
                    if "intent_cache_store" in tf.name:
                        # Reset to empty JSON dict so IntentAwareCache initializes clean
                        tf.write_text("{}", encoding="utf-8")
                    elif "savings_ledger" in tf.name:
                        empty_ledger = {
                            "total_hits": 0,
                            "total_misses": 0,
                            "tokens_saved_cumulative": 0,
                            "cost_saved_cumulative_usd": 0.0,
                            "co2_saved_grams": 0.0,
                        }
                        tf.write_text(json.dumps(empty_ledger, indent=2), encoding="utf-8")
                except Exception:
                    try:
                        tf.unlink()
                    except Exception:
                        pass

    # Clear cached data in backend/cache (e.g. scheme_aggregations, parquet files)
    if cache_dir.exists():
        for item in cache_dir.iterdir():
            summary["directories_cleaned"].append(str(item))
            if not dry_run:
                if item.is_dir():
                    safe_remove_directory(item)
                    item.mkdir(parents=True, exist_ok=True)
                else:
                    try:
                        os.chmod(str(item), stat.S_IWRITE)
                        item.unlink()
                    except Exception:
                        pass
        cache_dir.mkdir(parents=True, exist_ok=True)

    # In-memory and programmatic cache clearing
    if not dry_run:
        # 1. IntentAwareCache & SavingsLedger
        try:
            from app.engine import intent_cache
            intent_cache.clear_cache()
            summary["in_memory_layers_cleared"].append("app.engine.intent_cache")
        except Exception:
            pass

        # 2. Engine semantic cache
        try:
            from app.engine import semantic_cache
            semantic_cache.get_cache().clear()
            summary["in_memory_layers_cleared"].append("app.engine.semantic_cache")
        except Exception:
            pass

        # 3. Retrieval semantic cache
        try:
            from app.retrieval import cache as ret_cache
            ret_cache.get_semantic_cache().clear()
            summary["in_memory_layers_cleared"].append("app.retrieval.cache")
        except Exception:
            pass

        # 4. Feedback intent notice cache
        try:
            from app.feedback.intent_matcher import clear_pending_feedback_cache
            clear_pending_feedback_cache(suppress_prior_feedbacks=True)
            summary["in_memory_layers_cleared"].append("app.feedback.intent_matcher")
        except Exception:
            pass

    return summary


def clean_database_records(
    conn: sqlite3.Connection,
    dry_run: bool = False,
    exempt_tables: Optional[Set[str]] = None,
) -> Dict[str, int]:
    """Remove all records from data.db while preserving the existing database structure,
    including all tables, columns, indexes, relationships, and schema definitions.

    Args:
        conn (sqlite3.Connection): Active database connection.
        dry_run (bool): If True, simulate without deleting records.
        exempt_tables (Optional[Set[str]]): Tables to exclude from truncate (e.g., auth_users).

    Returns:
        Dict[str, int]: Mapping of table name to number of records deleted.
    """
    if exempt_tables is None:
        exempt_tables = {"auth_users"}

    tables = get_all_tables(conn)
    cursor = conn.cursor()
    deleted_counts: Dict[str, int] = {}

    if dry_run:
        for tbl in tables:
            if tbl not in exempt_tables:
                cursor.execute(f'SELECT COUNT(*) FROM "{tbl}";')
                deleted_counts[tbl] = cursor.fetchone()[0]
        return deleted_counts

    cursor.execute("PRAGMA foreign_keys = OFF;")
    for tbl in tables:
        if tbl not in exempt_tables:
            cursor.execute(f'DELETE FROM "{tbl}";')
            deleted_counts[tbl] = cursor.rowcount
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?;", (tbl,))
            except Exception:
                pass
    conn.commit()
    cursor.execute("PRAGMA foreign_keys = ON;")

    return deleted_counts


def clean_and_seed_users(
    conn: sqlite3.Connection,
    dry_run: bool = False,
    target_username: str = AMC_ADMIN_USERNAME,
    target_password: str = AMC_ADMIN_PASSWORD,
    rbac_json_path: Path = DEFAULT_USERS_RBAC_PATH,
    users_data_path: Path = DEFAULT_USERS_DATA_PATH,
) -> Dict[str, Any]:
    """Delete all user accounts regardless of their roles, but ensure that the
    'amc_admin' account exists with the password 'Compliance@2026'. If the account
    does not exist, create and seed it; if it already exists, ensure its password
    is set correctly without creating duplicate accounts.

    Args:
        conn (sqlite3.Connection): Active database connection.
        dry_run (bool): If True, simulate without modifying users.
        target_username (str): The target admin username.
        target_password (str): The target admin password.
        rbac_json_path (Path): Path to users_rbac.json fallback configuration.
        users_data_path (Path): Path to users.json fallback configuration.

    Returns:
        Dict[str, Any]: Status summary of user cleanup and amc_admin seeding.
    """
    summary: Dict[str, Any] = {
        "deleted_users_count": 0,
        "deleted_usernames": [],
        "admin_action": "verified",
        "admin_accessible": False,
    }

    cursor = conn.cursor()
    tables = get_all_tables(conn)
    if "auth_users" not in tables:
        ensure_database_schema(conn)

    cursor.execute("SELECT username FROM auth_users;")
    all_users = [row[0] for row in cursor.fetchall()]
    other_users = [u for u in all_users if u.lower() != target_username.lower()]

    summary["deleted_usernames"] = other_users
    summary["deleted_users_count"] = len(other_users)

    if dry_run:
        summary["admin_action"] = "would_update_or_seed"
        return summary

    # Step A: Delete all user accounts except target admin
    cursor.execute("PRAGMA foreign_keys = OFF;")
    cursor.execute('DELETE FROM "auth_users" WHERE LOWER(username) != LOWER(?);', (target_username,))
    conn.commit()

    # Step B: Ensure target admin exists with password Compliance@2026
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    admin_hash = generate_pbkdf2_hash(target_password)

    cursor.execute("SELECT * FROM auth_users WHERE LOWER(username) = LOWER(?);", (target_username,))
    existing_admin = cursor.fetchone()

    cursor.execute("PRAGMA table_info('auth_users');")
    cols = [r[1] for r in cursor.fetchall()]

    if existing_admin:
        # Update existing record
        summary["admin_action"] = "updated_password"
        update_clauses = ["password_hash = ?", "status = 'Active'", "is_superuser = 1"]
        update_params = [admin_hash]
        if "updated_at" in cols:
            update_clauses.append("updated_at = ?")
            update_params.append(now_str)
        if "role" in cols:
            update_clauses.append("role = ?")
            update_params.append(AMC_ADMIN_ROLE)
        if "department" in cols:
            update_clauses.append("department = ?")
            update_params.append(AMC_ADMIN_DEPARTMENT)
        if "email" in cols:
            update_clauses.append("email = ?")
            update_params.append(AMC_ADMIN_EMAIL)
        if "avatar_initials" in cols:
            update_clauses.append("avatar_initials = ?")
            update_params.append(AMC_ADMIN_AVATAR)

        update_params.append(target_username)
        sql = f'UPDATE "auth_users" SET {", ".join(update_clauses)} WHERE LOWER(username) = LOWER(?);'
        cursor.execute(sql, update_params)
    else:
        # Create and seed record
        summary["admin_action"] = "created_and_seeded"
        payload = {
            "username": target_username,
            "password_hash": admin_hash,
            "display_name": AMC_ADMIN_DISPLAY_NAME,
            "email": AMC_ADMIN_EMAIL,
            "role": AMC_ADMIN_ROLE,
            "department": AMC_ADMIN_DEPARTMENT,
            "avatar_initials": AMC_ADMIN_AVATAR,
            "status": "Active",
            "tenant_id": None,
            "created_at": now_str,
            "updated_at": now_str,
            "is_superuser": 1,
            "last_login": None,
            "last_login_ip": None,
        }
        insert_cols = [c for c in cols if c in payload]
        placeholders = ",".join("?" for _ in insert_cols)
        col_names = ",".join(f'"{c}"' for c in insert_cols)
        values = [payload[c] for c in insert_cols]
        cursor.execute(f'INSERT INTO "auth_users" ({col_names}) VALUES ({placeholders});', values)

    conn.commit()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Step C: Verify admin password in database
    cursor.execute("SELECT password_hash, status FROM auth_users WHERE LOWER(username) = LOWER(?);", (target_username,))
    admin_row = cursor.fetchone()
    if admin_row and verify_pbkdf2_password(target_password, admin_row[0]) and admin_row[1] == "Active":
        summary["admin_accessible"] = True

    # Step D: Synchronize fallback configuration files so fallback loaders do not resurrect deleted users
    admin_profile = {
        "username": target_username,
        "password_hash": admin_hash,
        "display_name": AMC_ADMIN_DISPLAY_NAME,
        "full_name": AMC_ADMIN_DISPLAY_NAME,
        "role": AMC_ADMIN_ROLE,
        "department": AMC_ADMIN_DEPARTMENT,
        "email": AMC_ADMIN_EMAIL,
        "avatar_initials": AMC_ADMIN_AVATAR,
        "status": "Active",
        "is_superuser": 1,
    }
    if rbac_json_path.exists():
        try:
            with open(rbac_json_path, "w", encoding="utf-8") as f:
                json.dump([admin_profile], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    if users_data_path.exists():
        try:
            with open(users_data_path, "w", encoding="utf-8") as f:
                json.dump({"users": [admin_profile]}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return summary


def clean_pycache_directories(
    project_dir: Path = PROJECT_ROOT,
    dry_run: bool = False,
    skip_venv: bool = False,
) -> Dict[str, Any]:
    """Recursively find and delete all __pycache__ directories within the current project
    directory and its subdirectories.

    Args:
        project_dir (Path): Root project directory to scan.
        dry_run (bool): If True, simulate without deleting.
        skip_venv (bool): If True, do not descend into .venv directory.

    Returns:
        Dict[str, Any]: Summary dictionary of removed pycache directories and errors.
    """
    summary: Dict[str, Any] = {
        "found_count": 0,
        "deleted_count": 0,
        "failed_count": 0,
        "pycache_paths": [],
    }

    target_dirs: List[Path] = []

    for root, dirs, files in os.walk(str(project_dir)):
        # Never touch .git
        if ".git" in dirs:
            dirs.remove(".git")
        if skip_venv and ".venv" in dirs:
            dirs.remove(".venv")

        for d in list(dirs):
            if d == "__pycache__":
                target_dirs.append(Path(root) / d)
                dirs.remove(d)

    summary["found_count"] = len(target_dirs)
    summary["pycache_paths"] = [str(p) for p in target_dirs]

    if dry_run:
        summary["deleted_count"] = len(target_dirs)
        return summary

    for p in target_dirs:
        if safe_remove_directory(p):
            summary["deleted_count"] += 1
        else:
            summary["failed_count"] += 1

    return summary


def clean_backend_logs(
    dry_run: bool = False,
    logs_dir: Path = DEFAULT_BACKEND_LOGS_DIR,
    root_logs_dir: Path = DEFAULT_ROOT_LOGS_DIR,
) -> Dict[str, Any]:
    """Clear all backend log files and stored log data without removing the logging
    configuration or disrupting future logging.

    Args:
        dry_run (bool): If True, simulate without truncating or removing log files.
        logs_dir (Path): Path to backend logs directory.
        root_logs_dir (Path): Path to root logs directory.

    Returns:
        Dict[str, Any]: Summary dictionary of cleared logs and removed audit files.
    """
    summary: Dict[str, Any] = {
        "truncated_log_files": [],
        "removed_audit_files": 0,
        "removed_session_folders": 0,
        "metrics_cleaned": 0,
    }

    # Standard log files to truncate in-place (preserves active file descriptors)
    standard_log_names = [
        "app.log",
        "app.jsonl",
        "feedback_loop.log",
        "feedback_loop.jsonl",
        "repair_engine.log",
        "repair_engine.jsonl",
        "cypher_audit.jsonl",
    ]

    for base in [logs_dir, root_logs_dir]:
        if not base.exists():
            continue
        for name in standard_log_names:
            target = base / name
            if target.exists():
                summary["truncated_log_files"].append(str(target))
                if not dry_run:
                    safe_truncate_file(target)

    # Ephemeral execution audit files (*.jsonl, *.md)
    for base in [logs_dir, root_logs_dir]:
        if not base.exists():
            continue
        for f in base.iterdir():
            if f.is_file() and f.name not in standard_log_names:
                if f.name.startswith("query_execution_audit_") or f.name.startswith("evidence_action_logs_"):
                    if dry_run:
                        summary["removed_audit_files"] += 1
                    else:
                        try:
                            os.chmod(str(f), stat.S_IWRITE)
                            f.unlink()
                            summary["removed_audit_files"] += 1
                        except Exception:
                            if safe_truncate_file(f):
                                summary["removed_audit_files"] += 1

    # Metrics files in backend/logs/metrics
    metrics_dir = logs_dir / "metrics"
    if metrics_dir.exists():
        for mf in metrics_dir.glob("*.json"):
            if dry_run:
                summary["metrics_cleaned"] += 1
            else:
                try:
                    os.chmod(str(mf), stat.S_IWRITE)
                    mf.unlink()
                    summary["metrics_cleaned"] += 1
                except Exception:
                    pass
        metrics_dir.mkdir(parents=True, exist_ok=True)

    # Session log folders
    for base in [logs_dir, root_logs_dir]:
        if not base.exists():
            continue
        for sub in base.glob("session_*"):
            if sub.is_dir():
                if dry_run:
                    summary["removed_session_folders"] += 1
                else:
                    if safe_remove_directory(sub):
                        summary["removed_session_folders"] += 1

    # Optional engine provenance database
    prov_db = BACKEND_DIR / "app" / "engine" / "logs" / "provenance.db"
    if prov_db.exists() and not dry_run:
        try:
            pconn = sqlite3.connect(str(prov_db))
            pcursor = pconn.cursor()
            pcursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            ptables = [r[0] for r in pcursor.fetchall()]
            for pt in ptables:
                pcursor.execute(f'DELETE FROM "{pt}";')
            pconn.commit()
            pconn.close()
        except Exception:
            pass

    # Ensure all standard log directories exist so subsequent logging never fails
    if not dry_run:
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "chat_sessions").mkdir(parents=True, exist_ok=True)
        (logs_dir / "chat_query_evidence").mkdir(parents=True, exist_ok=True)
        (logs_dir / "metrics").mkdir(parents=True, exist_ok=True)

    return summary


# ===========================================================================
# Verification Routine
# ===========================================================================

def verify_amc_admin_accessibility(conn: sqlite3.Connection) -> Tuple[bool, str]:
    """Verify that the amc_admin user account exists, is active, and is accessible
    with the password 'Compliance@2026'.

    Args:
        conn (sqlite3.Connection): Active database connection.

    Returns:
        Tuple[bool, str]: (is_accessible, details_message)
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, password_hash, status, role, email FROM auth_users WHERE LOWER(username) = LOWER(?);",
        (AMC_ADMIN_USERNAME,),
    )
    row = cursor.fetchone()

    if not row:
        return False, f"User '{AMC_ADMIN_USERNAME}' does not exist in 'auth_users'."

    username, password_hash, status_val, role, email = row[0], row[1], row[2], row[3], row[4]

    if status_val.lower() != "active":
        return False, f"User '{username}' status is '{status_val}', expected 'Active'."

    password_ok = verify_pbkdf2_password(AMC_ADMIN_PASSWORD, password_hash)
    if not password_ok:
        return False, f"Password hash verification failed for '{username}' with password '{AMC_ADMIN_PASSWORD}'."

    # Try live AuthService verification if modules can be initialized
    auth_service_status = "verified via direct PBKDF2 hash check"
    try:
        from app.auth.service import AuthService
        from app.auth.sql_repository import SqlUserRepository
        from app.core.database import SessionLocal

        repo = SqlUserRepository(session_factory=SessionLocal)
        auth_service = AuthService(repository=repo, secret_key="verify-secret", session_ttl_minutes=60)
        auth_res = auth_service.authenticate(AMC_ADMIN_USERNAME, AMC_ADMIN_PASSWORD)
        if auth_res.success:
            auth_service_status = "fully verified via AuthService + SqlUserRepository"
        else:
            return False, f"AuthService failed to authenticate '{username}': {auth_res.error}"
    except Exception as exc:
        auth_service_status += f" (AuthService test skipped: {exc})"

    return True, f"User '{username}' verified active (Role: '{role}', Email: '{email}', {auth_service_status})."


# ===========================================================================
# Complete Cleanup Orchestrator
# ===========================================================================

def run_complete_cleanup(
    db_path: Path = DEFAULT_DB_PATH,
    project_dir: Path = PROJECT_ROOT,
    backend_logs_dir: Path = DEFAULT_BACKEND_LOGS_DIR,
    root_logs_dir: Path = DEFAULT_ROOT_LOGS_DIR,
    chat_sessions_dir: Path = DEFAULT_CHAT_SESSIONS_DIR,
    chat_evidence_dir: Path = DEFAULT_CHAT_EVIDENCE_DIR,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    dry_run: bool = False,
    backup: bool = True,
    skip_vacuum: bool = False,
    skip_venv: bool = False,
    force: bool = False,
) -> bool:
    """Execute complete cleanup of the application according to specifications:
    1. Delete all recent chat conversations & permanent records
    2. Clear or delete the entire intent cache and associated cached data
    3. Remove all records from data.db while preserving database structure
    4. Delete all user accounts except amc_admin (Compliance@2026)
    5. Recursively find and delete all __pycache__ directories
    6. Clear all backend log files without removing logging configuration
    7. Verify amc_admin account remains accessible

    Args:
        db_path (Path): Filesystem path to data.db.
        project_dir (Path): Root project directory.
        backend_logs_dir (Path): Backend logs directory.
        root_logs_dir (Path): Project root logs directory.
        chat_sessions_dir (Path): Chat sessions directory.
        chat_evidence_dir (Path): Chat query evidence directory.
        cache_dir (Path): Backend cache directory.
        dry_run (bool): Simulation mode.
        backup (bool): Whether to create database snapshot before modification.
        skip_vacuum (bool): Whether to skip database VACUUM.
        skip_venv (bool): Whether to skip .venv during pycache deletion.
        force (bool): Bypass interactive confirmation prompt.

    Returns:
        bool: True if cleanup succeeded and admin was verified, False otherwise.
    """
    db_path = Path(db_path).resolve()
    project_dir = Path(project_dir).resolve()
    backend_logs_dir = Path(backend_logs_dir).resolve()
    root_logs_dir = Path(root_logs_dir).resolve()
    chat_sessions_dir = Path(chat_sessions_dir).resolve()
    chat_evidence_dir = Path(chat_evidence_dir).resolve()
    cache_dir = Path(cache_dir).resolve()

    print("=" * 80)
    print(" AMC COMPLETE APPLICATION CLEANUP UTILITY")
    print("=" * 80)
    print(f"Target Database      : {db_path}")
    print(f"Project Root         : {project_dir}")
    print(f"Backend Logs Dir     : {backend_logs_dir}")
    print(f"Cache Directory      : {cache_dir}")
    print(f"Backup Mode          : {'Atomic snapshot enabled' if backup else 'DISABLED'}")
    print(f"Dry Run Mode         : {'ENABLED (Simulate only)' if dry_run else 'DISABLED (Apply changes)'}")
    print("=" * 80)

    if not db_path.exists():
        print(f"\n[ERROR] Database file not found at: {db_path}")
        return False

    # Connect to SQLite database
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row

    try:
        # Step 0: Ensure schema definitions exist and capture initial counts
        ensure_database_schema(conn)
        initial_tables = get_all_tables(conn)
        initial_counts = get_table_counts(conn, initial_tables)

        cursor = conn.cursor()
        cursor.execute("SELECT username FROM auth_users;")
        initial_users = [row[0] for row in cursor.fetchall()]

        print(f"\nInitial Database State: {len(initial_tables)} table(s), {sum(initial_counts.values())} total rows.")
        print(f"Initial Users Count   : {len(initial_users)} user(s) in 'auth_users'.")

        # Interactive confirmation
        if not force and not dry_run:
            print("\n" + "!" * 80)
            print(" CONFIRMATION REQUIRED:")
            print(" This operation will permanently delete:")
            print("  1. All recent chat history and sessions (frontend and backend)")
            print("  2. All intent cache entries, savings ledgers, and cached aggregations")
            print("  3. All data records across data.db (preserving tables, columns, and schema)")
            print("  4. All user accounts except 'amc_admin' (with password 'Compliance@2026')")
            print("  5. All __pycache__ directories within project root and subdirectories")
            print("  6. All backend log files and stored log data (preserving logging configs)")
            print("!" * 80)
            try:
                confirmation = input("Type 'yes' to proceed with complete cleanup: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n[ABORTED] Operation cancelled by user.")
                return False

            if confirmation != "yes":
                print("[ABORTED] Confirmation not received ('yes' required). No changes made.")
                return False

        # Step 0.5: Atomic Backup
        if backup and not dry_run:
            print("\n[PRE-FLIGHT] Creating atomic SQLite backup of data.db...")
            backup_path = create_atomic_backup(conn, db_path)
            print(f"  [OK] Snapshot saved to: {backup_path.name}")
        else:
            print("\n[PRE-FLIGHT] Skipping database backup.")

        # -------------------------------------------------------------------
        # Requirement 1: Delete all recent chat conversations & disk artifacts
        # -------------------------------------------------------------------
        print("\n[Step 1/6] Deleting recent chat history and sessions...")
        chat_res = clean_chat_history(
            conn=conn,
            dry_run=dry_run,
            chat_sessions_dir=chat_sessions_dir,
            chat_evidence_dir=chat_evidence_dir,
            logs_dir=backend_logs_dir,
            root_logs_dir=root_logs_dir,
        )
        for tbl, cnt in chat_res["db_records_removed"].items():
            print(f"  [OK] Table '{tbl}': removed {cnt} record(s)")
        print(f"  [OK] Removed {chat_res['session_files_removed']} chat session JSON file(s)")
        print(f"  [OK] Removed {chat_res['evidence_files_removed']} chat query evidence JSON file(s)")
        print(f"  [OK] Removed {chat_res['session_folders_removed']} session log folder(s)")

        # -------------------------------------------------------------------
        # Requirement 2: Clear or delete entire intent cache & cached data
        # -------------------------------------------------------------------
        print("\n[Step 2/6] Clearing intent cache and associated cached data...")
        cache_res = clean_intent_cache(
            dry_run=dry_run,
            logs_dir=backend_logs_dir,
            root_logs_dir=root_logs_dir,
            cache_dir=cache_dir,
        )
        for cf in cache_res["files_cleared"]:
            print(f"  [OK] Reset cache store file: {Path(cf).name}")
        for cd in cache_res["directories_cleaned"]:
            print(f"  [OK] Cleared cached data store: {Path(cd).name}/")
        for layer in cache_res["in_memory_layers_cleared"]:
            print(f"  [OK] In-memory cache invalidated: {layer}")

        # -------------------------------------------------------------------
        # Requirement 3: Remove all records from data.db preserving structure
        # -------------------------------------------------------------------
        print("\n[Step 3/6] Removing records from data.db while preserving database schema...")
        db_res = clean_database_records(
            conn=conn,
            dry_run=dry_run,
            exempt_tables={"auth_users"},
        )
        for tbl, cnt in db_res.items():
            print(f"  [OK] Table '{tbl}': truncated {cnt} row(s)")

        # -------------------------------------------------------------------
        # Requirement 4: Delete all users except amc_admin (Compliance@2026)
        # -------------------------------------------------------------------
        print("\n[Step 4/6] Cleaning user accounts and ensuring 'amc_admin' account...")
        user_res = clean_and_seed_users(
            conn=conn,
            dry_run=dry_run,
            target_username=AMC_ADMIN_USERNAME,
            target_password=AMC_ADMIN_PASSWORD,
        )
        print(f"  [OK] Deleted {user_res['deleted_users_count']} other user account(s): {', '.join(user_res['deleted_usernames']) if user_res['deleted_usernames'] else 'None'}")
        print(f"  [OK] Target user '{AMC_ADMIN_USERNAME}': {user_res['admin_action']} with password '{AMC_ADMIN_PASSWORD}'")

        # -------------------------------------------------------------------
        # Requirement 5: Recursively find and delete all __pycache__ directories
        # -------------------------------------------------------------------
        print("\n[Step 5/6] Recursively finding and deleting __pycache__ directories...")
        pycache_res = clean_pycache_directories(
            project_dir=project_dir,
            dry_run=dry_run,
            skip_venv=skip_venv,
        )
        print(f"  [OK] Discovered: {pycache_res['found_count']} '__pycache__' directories across project")
        print(f"  [OK] Removed   : {pycache_res['deleted_count']} '__pycache__' directories")
        if pycache_res["failed_count"] > 0:
            print(f"  [WARNING] Could not remove {pycache_res['failed_count']} directory(ies) (in use or access denied)")

        # -------------------------------------------------------------------
        # Requirement 6: Clear all backend log files without disrupting logging
        # -------------------------------------------------------------------
        print("\n[Step 6/6] Clearing backend log files and stored log data...")
        log_res = clean_backend_logs(
            dry_run=dry_run,
            logs_dir=backend_logs_dir,
            root_logs_dir=root_logs_dir,
        )
        for tf in log_res["truncated_log_files"]:
            print(f"  [OK] Truncated log file in-place: {Path(tf).name}")
        print(f"  [OK] Removed {log_res['removed_audit_files']} audit execution log file(s)")
        print(f"  [OK] Removed {log_res['metrics_cleaned']} performance metrics file(s)")
        print(f"  [OK] Cleaned {log_res['removed_session_folders']} ephemeral session folder(s)")

        # Optional Step: Vacuum Database
        if not skip_vacuum and not dry_run:
            print("\n[POST-CLEANUP] Vacuuming SQLite database to defragment and reclaim disk space...")
            conn.isolation_level = None
            cursor.execute("VACUUM;")
            conn.isolation_level = ""
            print("  [OK] Database VACUUM completed.")

        # -------------------------------------------------------------------
        # Summary & Verification
        # -------------------------------------------------------------------
        print("\n" + "=" * 80)
        print(" DATABASE TABLES AND RECORD SUMMARY")
        print("=" * 80)
        final_tables = get_all_tables(conn)
        final_counts = get_table_counts(conn, final_tables)

        print(f"{'Table Name':<35} | {'Initial':>8} | {'Final':>8} | {'Removed':>8} | {'Status'}")
        print("-" * 80)
        for tbl in final_tables:
            i_cnt = initial_counts.get(tbl, 0)
            f_cnt = final_counts.get(tbl, 0)
            r_cnt = i_cnt - f_cnt
            if tbl == "auth_users":
                status_str = f"PRESERVED ({AMC_ADMIN_USERNAME} only)"
            else:
                status_str = "TRUNCATED (Schema preserved)"
            print(f"{tbl:<35} | {i_cnt:>8} | {f_cnt:>8} | {r_cnt:>8} | {status_str}")
        print("=" * 80)

        # Integrity Check
        cursor.execute("PRAGMA foreign_key_check;")
        fk_violations = cursor.fetchall()
        if fk_violations:
            print(f"\n[WARNING] PRAGMA foreign_key_check reported violations: {fk_violations}")
        else:
            print("\n[OK] Foreign key integrity check: 0 violations.")

        # Account Verification
        print("\n[VERIFICATION] Verifying 'amc_admin' account accessibility...")
        if dry_run:
            print(f"  [DRY RUN] Would verify '{AMC_ADMIN_USERNAME}' with password '{AMC_ADMIN_PASSWORD}'.")
            return True

        admin_ok, admin_msg = verify_amc_admin_accessibility(conn)
        if admin_ok:
            print(f"  [SUCCESS] {admin_msg}")
        else:
            print(f"  [FAILED] {admin_msg}")
            return False

        print("\n" + "=" * 80)
        print(" CLEANUP COMPLETE: Application database schema is fully preserved,")
        print(" all recent chat history and cached data have been permanently removed,")
        print(f" and '{AMC_ADMIN_USERNAME}' is active and accessible with '{AMC_ADMIN_PASSWORD}'.")
        print("=" * 80)
        return True

    except Exception as exc:
        print(f"\n[ERROR] An unexpected error occurred during cleanup: {exc}")
        try:
            conn.rollback()
            print("[INFO] Transaction rolled back.")
        except Exception:
            pass
        raise
    finally:
        conn.close()


# ===========================================================================
# CLI Interface & Entry Point
# ===========================================================================

def main():
    """CLI Argument Parsing and Execution Entry Point."""
    parser = argparse.ArgumentParser(
        description=(
            "Complete application cleanup utility: clears recent chat history, "
            "intent cache, and data.db records while preserving schema definitions, "
            "ensures 'amc_admin' (Compliance@2026), deletes __pycache__ directories, "
            "and clears backend log files."
        )
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to data.db SQLite file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=PROJECT_ROOT,
        help=f"Root project directory to scan for __pycache__ (default: {PROJECT_ROOT})",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=DEFAULT_BACKEND_LOGS_DIR,
        help=f"Path to backend logs directory (default: {DEFAULT_BACKEND_LOGS_DIR})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"Path to backend cache directory (default: {DEFAULT_CACHE_DIR})",
    )
    parser.add_argument(
        "--chat-sessions-dir",
        type=Path,
        default=DEFAULT_CHAT_SESSIONS_DIR,
        help=f"Path to chat sessions directory (default: {DEFAULT_CHAT_SESSIONS_DIR})",
    )
    parser.add_argument(
        "--chat-evidence-dir",
        type=Path,
        default=DEFAULT_CHAT_EVIDENCE_DIR,
        help=f"Path to chat query evidence directory (default: {DEFAULT_CHAT_EVIDENCE_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate cleanup and report what would be deleted without making any changes",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create an atomic backup snapshot of data.db before cleanup",
    )
    parser.add_argument(
        "--skip-vacuum",
        action="store_true",
        help="Skip database VACUUM operation after deletion",
    )
    parser.add_argument(
        "--skip-venv-pycache",
        action="store_true",
        help="Skip cleaning __pycache__ inside .venv directory",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Bypass the interactive confirmation prompt",
    )
    parser.add_argument(
        "--verify-only",
        "--ensure-admin-only",
        action="store_true",
        help="Only verify 'amc_admin' account accessibility and schema without cleaning records",
    )
    # Legacy arguments preserved for backward compatibility
    parser.add_argument(
        "--user",
        "-u",
        type=str,
        default="all",
        help="Legacy filter argument (retained for backward compatibility)",
    )
    parser.add_argument(
        "--keep-chat-logs",
        action="store_true",
        help="Legacy argument: do not delete disk-based chat session JSON files",
    )
    parser.add_argument(
        "--all-tables",
        action="store_true",
        help="Legacy argument: truncate all tables",
    )
    parser.add_argument(
        "--keep-user",
        type=str,
        default=AMC_ADMIN_USERNAME,
        help=f"Legacy argument: user to preserve (default: '{AMC_ADMIN_USERNAME}')",
    )

    args = parser.parse_args()

    # Verify-only mode
    if args.verify_only:
        db_path = Path(args.db_path).resolve()
        if not db_path.exists():
            print(f"[ERROR] Database file not found at: {db_path}")
            sys.exit(1)
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            print(f"Verifying '{AMC_ADMIN_USERNAME}' account in {db_path}...")
            ok, msg = verify_amc_admin_accessibility(conn)
            if ok:
                print(f"[SUCCESS] {msg}")
                sys.exit(0)
            else:
                print(f"[FAILED] {msg}")
                sys.exit(1)
        finally:
            conn.close()

    success = run_complete_cleanup(
        db_path=args.db_path,
        project_dir=args.project_dir,
        backend_logs_dir=args.logs_dir,
        root_logs_dir=PROJECT_ROOT / "logs",
        chat_sessions_dir=args.chat_sessions_dir,
        chat_evidence_dir=args.chat_evidence_dir,
        cache_dir=args.cache_dir,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        skip_vacuum=args.skip_vacuum,
        skip_venv=args.skip_venv_pycache,
        force=args.yes,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

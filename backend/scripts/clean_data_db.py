#!/usr/bin/env python
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Script: clean_data_db.py
# Description: Remove and delete recent chat history and sessions from all users
#              (or a specified user) in data.db and disk logs, while keeping
#              all user accounts in auth_users and system knowledge schemas intact.
#              Automatically verifies that the 'amc_admin' user record exists,
#              and seeds it if it is missing.
# ===========================================================================
"""Operational and maintenance script for clean data db."""


import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure UTF-8 output if console supports reconfiguration
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Default paths and configurations
BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_DIR / "data.db"
DEFAULT_CHAT_SESSIONS_DIR = BACKEND_DIR / "logs" / "chat_sessions"
DEFAULT_CHAT_EVIDENCE_DIR = BACKEND_DIR / "logs" / "chat_query_evidence"
DEFAULT_LOGS_DIR = BACKEND_DIR / "logs"
DEFAULT_USERS_RBAC_PATH = BACKEND_DIR / "config" / "users_rbac.json"
DEFAULT_KEEP_USER = "amc_admin"

# Default password hash for amc_admin (PBKDF2-SHA256)
AMC_ADMIN_DEFAULT_HASH = (
    "pbkdf2_sha256$260000$290925852b00bde18f0bef23d06b73cb$"
    "01848670be1dfa8597fd99c2fa77d3713ab688140989e33f10a9e229c5333006"
)

# Standard template values for amc_admin user record
DEFAULT_AMC_ADMIN_DATA = {
    "username": DEFAULT_KEEP_USER,
    "password_hash": AMC_ADMIN_DEFAULT_HASH,
    "display_name": "AMC Administrator",
    "email": "amc_admin@amc.com",
    "role": "Compliance & Regulatory Officer",
    "department": "Regulatory & Legal Compliance",
    "avatar_initials": "AA",
    "status": "Active",
    "tenant_id": None,
    "is_superuser": 1,
}

# Tables associated with chat sessions, query turns, and response evaluations
CHAT_TABLES = [
    "graph_mutations",
    "repair_proposals",
    "unified_evaluation_records",
    "response_feedback",
    "query_evidence",
    "chat_sessions",
]


def get_all_tables(conn: sqlite3.Connection) -> List[str]:
    """Retrieve list of all user-defined tables (ignoring SQLite internal tables).

    Args:
        conn (sqlite3.Connection): The conn.

    Returns:
        List[str]: List of resulting items or records.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC;"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_counts(conn: sqlite3.Connection, tables: List[str]) -> Dict[str, int]:
    """Return dictionary mapping table name to row count.

    Args:
        conn (sqlite3.Connection): The conn.
        tables (List[str]): Collection or list of tables.

    Returns:
        Dict[str, int]: Dictionary containing result data or status.
    """
    cursor = conn.cursor()
    counts = {}
    for table in tables:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        counts[table] = cursor.fetchone()[0]
    return counts


def create_atomic_backup(source_conn: sqlite3.Connection, db_path: Path) -> Path:
    """Create an atomic backup of the SQLite database file before modification.

    Args:
        source_conn (sqlite3.Connection): The source conn.
        db_path (Path): Filesystem path to the db.

    Returns:
        Path: Resulting Path instance.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.name}.bak_{timestamp}"
    dest_conn = sqlite3.connect(str(backup_path))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
    return backup_path


def load_amc_admin_seed_data() -> Dict[str, Any]:
    """Load amc_admin seed template from users_rbac.json or use hardcoded standard defaults.

    Returns:
        Dict[str, Any]: Dictionary containing result data or status.
    """
    seed_data = dict(DEFAULT_AMC_ADMIN_DATA)
    if DEFAULT_USERS_RBAC_PATH.exists():
        try:
            with open(DEFAULT_USERS_RBAC_PATH, "r", encoding="utf-8") as f:
                rbac_users = json.load(f)
            if isinstance(rbac_users, list):
                for u in rbac_users:
                    if isinstance(u, dict) and u.get("username") == DEFAULT_KEEP_USER:
                        seed_data["display_name"] = u.get("display_name") or u.get("full_name") or seed_data["display_name"]
                        seed_data["email"] = u.get("email") or seed_data["email"]
                        seed_data["role"] = u.get("role") or seed_data["role"]
                        seed_data["department"] = u.get("department") or seed_data["department"]
                        seed_data["avatar_initials"] = u.get("avatar_initials") or seed_data["avatar_initials"]
                        seed_data["status"] = u.get("status") or seed_data["status"]
                        seed_data["tenant_id"] = u.get("tenant_id")
                        if "is_superuser" in u:
                            seed_data["is_superuser"] = 1 if u["is_superuser"] else 0
                        break
        except Exception:
            pass
    return seed_data


def ensure_amc_admin_seeded(conn: sqlite3.Connection, dry_run: bool = False) -> bool:
    """Check if the 'amc_admin' user record is present in 'auth_users'.
    If not present, seeds it into 'auth_users'.
    Returns True if user exists or was seeded, False on failure.

    Args:
        conn (sqlite3.Connection): The conn.
        dry_run (bool): The dry run.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    cursor = conn.cursor()
    tables = get_all_tables(conn)

    # Ensure auth_users table exists
    if "auth_users" not in tables:
        if dry_run:
            print("  [DRY RUN] 'auth_users' table does not exist. Would create schema and seed 'amc_admin'.")
            return True
        print("  [INFO] 'auth_users' table not found. Creating table schema...")
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

    # Query for amc_admin record
    cursor.execute("SELECT * FROM auth_users WHERE username = ?;", (DEFAULT_KEEP_USER,))
    user_row = cursor.fetchone()

    if user_row:
        user_role = user_row["role"] if "role" in user_row.keys() else "N/A"
        user_email = user_row["email"] if "email" in user_row.keys() else "N/A"
        print(f"  [OK] User '{DEFAULT_KEEP_USER}' is present in 'auth_users' (Role: {user_role}, Email: {user_email})")
        return True

    # User is missing
    print(f"\n[NOTICE] User '{DEFAULT_KEEP_USER}' is MISSING from 'auth_users'!")
    if dry_run:
        print(f"  [DRY RUN] Would seed user '{DEFAULT_KEEP_USER}' into 'auth_users'.")
        return True

    print(f"  [SEED] Seeding '{DEFAULT_KEEP_USER}' user record into 'auth_users'...")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    seed_payload = load_amc_admin_seed_data()
    seed_payload["created_at"] = now_str
    seed_payload["updated_at"] = now_str

    cursor.execute("PRAGMA table_info('auth_users');")
    existing_cols = [r[1] for r in cursor.fetchall()]

    insert_cols = [c for c in existing_cols if c in seed_payload]
    placeholders = ",".join("?" for _ in insert_cols)
    col_names = ",".join(f'"{c}"' for c in insert_cols)
    values = [seed_payload[c] for c in insert_cols]

    cursor.execute(f'INSERT INTO "auth_users" ({col_names}) VALUES ({placeholders});', values)
    conn.commit()
    print(f"  [OK] Successfully seeded user '{DEFAULT_KEEP_USER}' into 'auth_users'.")
    return True


def get_user_session_stats(conn: sqlite3.Connection) -> Dict[str, int]:
    """Return count of chat sessions grouped by user_id.

    Args:
        conn (sqlite3.Connection): The conn.

    Returns:
        Dict[str, int]: Dictionary containing result data or status.
    """
    tables = get_all_tables(conn)
    if "chat_sessions" not in tables:
        return {}
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(user_id, 'UNKNOWN'), COUNT(*) FROM chat_sessions GROUP BY user_id ORDER BY COUNT(*) DESC;"
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def chunked_delete(cursor: sqlite3.Cursor, table: str, column: str, values: List[str]) -> int:
    """Delete rows from table where column IN values, chunking to avoid SQLite parameter limits.

    Args:
        cursor (sqlite3.Cursor): The cursor.
        table (str): The table.
        column (str): The column.
        values (List[str]): Collection or list of values.

    Returns:
        int: Resulting int instance.
    """
    if not values:
        return 0
    total_deleted = 0
    chunk_size = 500
    for i in range(0, len(values), chunk_size):
        chunk = values[i : i + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        cursor.execute(f'DELETE FROM "{table}" WHERE "{column}" IN ({placeholders})', chunk)
        total_deleted += cursor.rowcount
    return total_deleted


def discover_disk_artifacts(
    chat_sessions_dir: Path,
    chat_evidence_dir: Path,
    logs_dir: Path,
    target_sessions: Optional[Set[str]] = None,
    target_user: Optional[str] = None,
) -> Tuple[List[Path], List[Path], List[Path]]:
    """Discover on-disk session files and folders.
    If target_sessions is None, returns all chat session files/directories.
    Otherwise filters to those matching target_sessions or target_user.

    Args:
        chat_sessions_dir (Path): The chat sessions dir.
        chat_evidence_dir (Path): The chat evidence dir.
        logs_dir (Path): The logs dir.
        target_sessions (Optional[Set[str]]): Collection or list of target sessions.
        target_user (Optional[str]): The target user.

    Returns:
        Tuple[List[Path], List[Path], List[Path]]: List of resulting items or records.
    """
    session_files: List[Path] = []
    if chat_sessions_dir.exists():
        for f in chat_sessions_dir.glob("*.json"):
            if target_sessions is None:
                session_files.append(f)
            elif f.stem in target_sessions:
                session_files.append(f)
            elif target_user and target_user.lower() != "all":
                # Check user_id in json
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("user_id") == target_user:
                        session_files.append(f)
                except Exception:
                    pass

    evidence_files: List[Path] = []
    if chat_evidence_dir.exists():
        for f in chat_evidence_dir.glob("*.json"):
            if target_sessions is None:
                evidence_files.append(f)
            else:
                # chat_evidence_{session_id}.json
                matched = False
                for sid in target_sessions:
                    if sid in f.stem:
                        evidence_files.append(f)
                        matched = True
                        break
                if not matched and target_user and target_user.lower() != "all":
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        sess_user = data.get("session", {}).get("user_id") if isinstance(data, dict) else None
                        if sess_user == target_user:
                            evidence_files.append(f)
                    except Exception:
                        pass

    session_dirs: List[Path] = []
    if logs_dir.exists():
        for d in logs_dir.glob("session_*"):
            if d.is_dir():
                if target_sessions is None:
                    session_dirs.append(d)
                else:
                    for sid in target_sessions:
                        if sid in d.name:
                            session_dirs.append(d)
                            break

    return session_files, evidence_files, session_dirs


def clean_recent_chats(
    db_path: Path = DEFAULT_DB_PATH,
    chat_sessions_dir: Path = DEFAULT_CHAT_SESSIONS_DIR,
    chat_evidence_dir: Path = DEFAULT_CHAT_EVIDENCE_DIR,
    logs_dir: Path = DEFAULT_LOGS_DIR,
    target_user: str = "all",
    dry_run: bool = False,
    backup: bool = True,
    clear_chat_logs: bool = True,
    skip_vacuum: bool = False,
    force: bool = False,
) -> bool:
    """Remove recent chats / chat sessions from all users (or a specific user).
    Preserves all user accounts in auth_users and all non-chat tables (fund_schemes,
    compliance_rules, violations, feedback_issues, audit_metadata).
    Checks and seeds 'amc_admin' if it is not present in auth_users.

    Args:
        db_path (Path): Filesystem path to the db.
        chat_sessions_dir (Path): The chat sessions dir.
        chat_evidence_dir (Path): The chat evidence dir.
        logs_dir (Path): The logs dir.
        target_user (str): The target user.
        dry_run (bool): The dry run.
        backup (bool): The backup.
        clear_chat_logs (bool): Collection or list of clear chat logs.
        skip_vacuum (bool): The skip vacuum.
        force (bool): The force.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    db_path = Path(db_path).resolve()
    chat_sessions_dir = Path(chat_sessions_dir).resolve()
    chat_evidence_dir = Path(chat_evidence_dir).resolve()
    logs_dir = Path(logs_dir).resolve()

    clean_all_users = not target_user or target_user.strip().lower() == "all"
    target_user_display = "ALL USERS" if clean_all_users else f"'{target_user}'"

    print("=" * 76)
    print(" AMC RECENT CHATS CLEANUP UTILITY")
    print("=" * 76)
    print(f"Target Database     : {db_path}")
    print(f"Target User(s)      : {target_user_display}")
    print(f"Chat Sessions Dir   : {chat_sessions_dir}")
    print(f"Chat Evidence Dir   : {chat_evidence_dir}")
    print(f"Clear Disk Logs     : {'YES (Will remove session JSON files and folders)' if clear_chat_logs else 'NO (Keep disk logs)'}")
    print(f"Backup Database     : {'YES (Will create atomic snapshot)' if backup else 'NO (Skipped)'}")
    print(f"Dry Run Mode        : {'ENABLED (No modifications will be made)' if dry_run else 'DISABLED (Changes will be applied)'}")
    print("=" * 76)

    if not db_path.exists():
        print(f"\n[ERROR] Database file not found at: {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        tables = get_all_tables(conn)
        initial_counts = get_table_counts(conn, tables)

        # Step 1: Check and ensure amc_admin user record is present in auth_users
        print("\n[Step 1] Verifying 'auth_users' and 'amc_admin' account presence...")
        ensure_amc_admin_seeded(conn, dry_run=dry_run)

        # Inspect all users in auth_users
        tables = get_all_tables(conn)
        if "auth_users" in tables:
            cursor = conn.cursor()
            cursor.execute("SELECT username, role FROM auth_users ORDER BY username ASC;")
            rows = cursor.fetchall()
            print(f"\n[OK] Found {len(rows)} user account(s) in 'auth_users' (ALL WILL BE PRESERVED):")
            for r in rows:
                print(f"     - {r['username']} ({r['role']})")

        # Step 2: Inspect existing chat sessions grouped by user
        user_session_counts = get_user_session_stats(conn)
        total_sessions = sum(user_session_counts.values())
        print(f"\nFound {total_sessions} chat session(s) in database across {len(user_session_counts)} user(s):")
        for u, cnt in user_session_counts.items():
            is_target = clean_all_users or u == target_user
            mark = " [TARGET]" if is_target else " [PRESERVED]"
            print(f"  - {u.ljust(25)}: {cnt:>5} session(s){mark}")

        # Step 3: Determine target sessions and responses to remove
        cursor = conn.cursor()
        target_session_ids: Set[str] = set()
        target_response_ids: Set[str] = set()

        if clean_all_users:
            if "chat_sessions" in tables:
                cursor.execute("SELECT session_id FROM chat_sessions;")
                target_session_ids.update(row[0] for row in cursor.fetchall())
            if "query_evidence" in tables:
                cursor.execute("SELECT DISTINCT session_id, response_id FROM query_evidence WHERE session_id IS NOT NULL;")
                for r in cursor.fetchall():
                    target_session_ids.add(r[0])
                    if r[1]:
                        target_response_ids.add(r[1])
            if "unified_evaluation_records" in tables:
                cursor.execute("SELECT DISTINCT session_id, response_id FROM unified_evaluation_records;")
                for r in cursor.fetchall():
                    if r[0]:
                        target_session_ids.add(r[0])
                    if r[1]:
                        target_response_ids.add(r[1])
        else:
            if "chat_sessions" in tables:
                cursor.execute("SELECT session_id FROM chat_sessions WHERE user_id = ?;", (target_user,))
                target_session_ids.update(row[0] for row in cursor.fetchall())
            if "query_evidence" in tables:
                cursor.execute("SELECT DISTINCT session_id, response_id FROM query_evidence WHERE user_id = ?;", (target_user,))
                for r in cursor.fetchall():
                    if r[0]:
                        target_session_ids.add(r[0])
                    if r[1]:
                        target_response_ids.add(r[1])
            if target_session_ids and "unified_evaluation_records" in tables:
                ph = ",".join("?" for _ in target_session_ids)
                cursor.execute(f"SELECT DISTINCT response_id FROM unified_evaluation_records WHERE session_id IN ({ph});", list(target_session_ids))
                for r in cursor.fetchall():
                    if r[0]:
                        target_response_ids.add(r[0])

        # Step 4: Discover on-disk artifacts
        disk_sessions = None if clean_all_users else target_session_ids
        session_files, evidence_files, session_dirs = discover_disk_artifacts(
            chat_sessions_dir=chat_sessions_dir,
            chat_evidence_dir=chat_evidence_dir,
            logs_dir=logs_dir,
            target_sessions=disk_sessions,
            target_user=target_user if not clean_all_users else None,
        )

        print("\nDisk-based chat artifacts to clean:")
        print(f"  - chat_sessions/       : {len(session_files):>5} .json file(s)")
        print(f"  - chat_query_evidence/ : {len(evidence_files):>5} .json file(s)")
        print(f"  - session log folders  : {len(session_dirs):>5} folder(s)")

        # Dry run summary
        if dry_run:
            print("\n" + "-" * 76)
            print("[DRY RUN SUMMARY] The following records and files WOULD be removed:")
            for tbl in tables:
                if tbl in CHAT_TABLES:
                    if clean_all_users:
                        rem_count = initial_counts.get(tbl, 0)
                    else:
                        rem_count = len(target_session_ids) if tbl == "chat_sessions" else "filtered by user"
                    print(f"  - {tbl.ljust(35)}: remove {rem_count} record(s)")
                else:
                    print(f"  - {tbl.ljust(35)}: KEEP {initial_counts.get(tbl, 0)} record(s) intact (PRESERVED)")
            if clear_chat_logs:
                print(f"  - Disk chat session files : remove {len(session_files)} file(s)")
                print(f"  - Disk query evidence files: remove {len(evidence_files)} file(s)")
                print(f"  - Disk session log folders : remove {len(session_dirs)} folder(s)")
            print("-" * 76)
            print("[DRY RUN COMPLETE] No records or files were deleted.")
            return True

        # Interactive confirmation
        if not force:
            print("\n" + "!" * 76)
            print(" CONFIRMATION REQUIRED:")
            print(f" This will permanently delete recent chats for {target_user_display}.")
            print(" All user accounts in 'auth_users' and non-chat tables WILL BE PRESERVED.")
            if clear_chat_logs:
                print(f" Disk artifacts: {len(session_files) + len(evidence_files)} JSON file(s) and {len(session_dirs)} session folder(s) will be deleted.")
            print("!" * 76)
            try:
                confirmation = input("Type 'yes' to proceed with deletion: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n[ABORTED] Operation cancelled.")
                return False

            if confirmation != "yes":
                print("[ABORTED] Confirmation not received ('yes' required). No changes made.")
                return False

        # Step 5: Pre-cleanup atomic backup
        step_idx = 1
        total_steps = 4 if not clear_chat_logs else 5

        if backup:
            print(f"\n[Step {step_idx}/{total_steps}] Creating atomic SQLite backup...")
            backup_file = create_atomic_backup(conn, db_path)
            print(f"  [OK] Snapshot saved to: {backup_file.name}")
        else:
            print(f"\n[Step {step_idx}/{total_steps}] Skipping backup (--no-backup specified).")
        step_idx += 1

        # Step 6: Delete chat records inside SQLite transaction
        print(f"\n[Step {step_idx}/{total_steps}] Deleting recent chat records from database...")
        step_idx += 1
        cursor.execute("PRAGMA foreign_keys = OFF;")

        deleted_counts: Dict[str, int] = {}
        sids_list = list(target_session_ids)
        rids_list = list(target_response_ids)

        if clean_all_users:
            # Delete from all chat tables in safe child-to-parent order
            for tbl in [
                "graph_mutations",
                "repair_proposals",
                "unified_evaluation_records",
                "response_feedback",
                "query_evidence",
                "chat_sessions",
            ]:
                if tbl in tables:
                    cursor.execute(f'DELETE FROM "{tbl}";')
                    deleted_counts[tbl] = cursor.rowcount
                    print(f"  [OK] '{tbl}': deleted {deleted_counts[tbl]} record(s)")

            # Reset autoincrement sequence for cleared chat tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';")
            if cursor.fetchone():
                for tbl in CHAT_TABLES:
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?;", (tbl,))
        else:
            # Delete specific user's chat records
            # 1. repair_proposals / graph_mutations linked to user response_ids
            if "repair_proposals" in tables and rids_list:
                ph = ",".join("?" for _ in rids_list)
                cursor.execute(f"SELECT proposal_id FROM repair_proposals WHERE unified_record_ref IN ({ph});", rids_list)
                p_ids = [r[0] for r in cursor.fetchall()]
                if p_ids and "graph_mutations" in tables:
                    del_gm = chunked_delete(cursor, "graph_mutations", "proposal_id", p_ids)
                    deleted_counts["graph_mutations"] = del_gm
                del_rp = chunked_delete(cursor, "repair_proposals", "unified_record_ref", rids_list)
                deleted_counts["repair_proposals"] = del_rp

            # 2. unified_evaluation_records for target sessions
            if "unified_evaluation_records" in tables and sids_list:
                del_uer = chunked_delete(cursor, "unified_evaluation_records", "session_id", sids_list)
                deleted_counts["unified_evaluation_records"] = del_uer

            # 3. response_feedback for target sessions
            if "response_feedback" in tables and sids_list:
                del_rf = chunked_delete(cursor, "response_feedback", "session_id", sids_list)
                deleted_counts["response_feedback"] = del_rf

            # 4. query_evidence for target sessions
            if "query_evidence" in tables and sids_list:
                del_qe = chunked_delete(cursor, "query_evidence", "session_id", sids_list)
                deleted_counts["query_evidence"] = del_qe

            # 5. chat_sessions for target sessions
            if "chat_sessions" in tables and sids_list:
                del_cs = chunked_delete(cursor, "chat_sessions", "session_id", sids_list)
                deleted_counts["chat_sessions"] = del_cs

            for tbl, cnt in deleted_counts.items():
                print(f"  [OK] '{tbl}': deleted {cnt} record(s) for user '{target_user}'")

        # Commit transaction
        conn.commit()

        # Re-enable foreign keys and verify integrity
        cursor.execute("PRAGMA foreign_keys = ON;")
        fk_violations = cursor.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_violations:
            print(f"  [WARNING] PRAGMA foreign_key_check reported violations: {fk_violations}")
        else:
            print("  [OK] Foreign key integrity check passed: 0 violations.")

        # Ensure amc_admin remains seeded and present
        ensure_amc_admin_seeded(conn, dry_run=False)

        # Step 7: Clear disk-based chat logs
        if clear_chat_logs:
            print(f"\n[Step {step_idx}/{total_steps}] Cleaning disk-based chat logs and artifacts...")
            step_idx += 1
            del_sf = 0
            for f in session_files:
                try:
                    f.unlink()
                    del_sf += 1
                except Exception as ex:
                    print(f"  [WARNING] Could not delete {f.name}: {ex}")

            del_ef = 0
            for f in evidence_files:
                try:
                    f.unlink()
                    del_ef += 1
                except Exception as ex:
                    print(f"  [WARNING] Could not delete {f.name}: {ex}")

            del_sd = 0
            for d in session_dirs:
                try:
                    shutil.rmtree(d, ignore_errors=True)
                    del_sd += 1
                except Exception as ex:
                    print(f"  [WARNING] Could not delete folder {d.name}: {ex}")

            print(f"  [OK] Removed {del_sf} chat session file(s) from {chat_sessions_dir.name}/")
            print(f"  [OK] Removed {del_ef} query evidence file(s) from {chat_evidence_dir.name}/")
            print(f"  [OK] Removed {del_sd} session log folder(s) from {logs_dir.name}/")

        # Step 8: Vacuum database to reclaim disk space
        if not skip_vacuum:
            print(f"\n[Step {step_idx}/{total_steps}] Vacuuming database to reclaim space...")
            step_idx += 1
            conn.isolation_level = None
            cursor.execute("VACUUM;")
            conn.isolation_level = ""
            print("  [OK] Database VACUUM completed.")
        else:
            print(f"\n[Step {step_idx}/{total_steps}] Skipping VACUUM (--skip-vacuum specified).")
            step_idx += 1

        # Step 9: Verify final row counts
        print(f"\n[Step {step_idx}/{total_steps}] Verifying final database state...")
        final_tables = get_all_tables(conn)
        final_counts = get_table_counts(conn, final_tables)

        print("\n" + "=" * 76)
        print(f"{'Table Name':<35} | {'Initial':>8} | {'Final':>8} | {'Removed':>8}")
        print("-" * 76)
        total_removed = 0
        for tbl in final_tables:
            init_c = initial_counts.get(tbl, 0)
            fin_c = final_counts.get(tbl, 0)
            rem_c = init_c - fin_c
            total_removed += rem_c
            status_note = ""
            if tbl not in CHAT_TABLES:
                status_note = " (PRESERVED)"
            print(f"{tbl:<35} | {init_c:>8} | {fin_c:>8} | {rem_c:>8}{status_note}")
        print("=" * 76)
        print(f"{'TOTAL':<35} | {sum(initial_counts.values()):>8} | {sum(final_counts.values()):>8} | {total_removed:>8}")
        print("=" * 76)

        # Print remaining users in auth_users
        if "auth_users" in final_tables:
            cursor = conn.cursor()
            cursor.execute("SELECT username, role, email FROM auth_users ORDER BY username ASC;")
            rem_users = cursor.fetchall()
            print(f"\nUser accounts preserved in auth_users ({len(rem_users)} total):")
            for u in rem_users:
                print(f"  - username: {u['username'].ljust(25)} | role: {u['role']}")

        print(f"\n[SUCCESS] Recent chats have been successfully deleted for {target_user_display}.")
        print("          All user accounts and system knowledge tables remain fully intact.")
        print(f"          User '{DEFAULT_KEEP_USER}' is verified and present in 'auth_users'.")
        print("          Tip: Refresh client browser / clear browser cache to reset frontend session display.")
        return True

    except Exception as e:
        print(f"\n[ERROR] An exception occurred during cleanup: {e}")
        try:
            conn.rollback()
            print("[INFO] Transaction rolled back.")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def clean_all_tables_legacy(
    db_path: Path = DEFAULT_DB_PATH,
    chat_sessions_dir: Path = DEFAULT_CHAT_SESSIONS_DIR,
    keep_user: str = DEFAULT_KEEP_USER,
    dry_run: bool = False,
    backup: bool = True,
    clear_chat_logs: bool = True,
    skip_vacuum: bool = False,
    force: bool = False,
) -> bool:
    """Legacy mode: truncate all user tables preserving only keep_user in auth_users.

    Args:
        db_path (Path): Filesystem path to the db.
        chat_sessions_dir (Path): The chat sessions dir.
        keep_user (str): The keep user.
        dry_run (bool): The dry run.
        backup (bool): The backup.
        clear_chat_logs (bool): Collection or list of clear chat logs.
        skip_vacuum (bool): The skip vacuum.
        force (bool): The force.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    db_path = Path(db_path).resolve()
    chat_sessions_dir = Path(chat_sessions_dir).resolve()

    print("=" * 76)
    print(" AMC FULL DATABASE TRUNCATION (LEGACY MODE)")
    print("=" * 76)
    print(f"Target Database   : {db_path}")
    print(f"Preserved User    : '{keep_user}' in 'auth_users' table")
    print("=" * 76)

    if not db_path.exists():
        print(f"\n[ERROR] Database file not found at: {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        tables = get_all_tables(conn)

        if not force and not dry_run:
            print("\nWARNING: This will truncate ALL tables in data.db, keeping only keep_user in auth_users.")
            resp = input("Are you sure? Type 'yes' to confirm: ").strip().lower()
            if resp != "yes":
                print("[ABORTED] Operation cancelled.")
                return False

        if backup and not dry_run:
            backup_file = create_atomic_backup(conn, db_path)
            print(f"[OK] Backup created: {backup_file.name}")

        if dry_run:
            print("[DRY RUN] Would truncate all tables except keep_user in auth_users.")
            ensure_amc_admin_seeded(conn, dry_run=True)
            return True

        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")
        for tbl in tables:
            if tbl == "auth_users":
                cursor.execute('DELETE FROM "auth_users" WHERE username != ?', (keep_user,))
            else:
                cursor.execute(f'DELETE FROM "{tbl}"')
        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Ensure amc_admin is present or seeded
        ensure_amc_admin_seeded(conn, dry_run=False)

        if clear_chat_logs and chat_sessions_dir.exists():
            for cf in chat_sessions_dir.glob("*.json"):
                try:
                    cf.unlink()
                except Exception:
                    pass

        if not skip_vacuum:
            conn.isolation_level = None
            cursor.execute("VACUUM;")
            conn.isolation_level = ""

        print("[SUCCESS] All tables truncated (legacy mode).")
        return True
    finally:
        conn.close()


def main():
    """Main.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Remove and delete recent chat history and sessions from all users "
            "(or a specified user) in data.db and disk logs, while keeping all user "
            "accounts in auth_users and system knowledge schemas intact. "
            "Automatically verifies that 'amc_admin' exists, and seeds it if missing."
        )
    )
    parser.add_argument(
        "--user",
        "-u",
        type=str,
        default="all",
        help="Username whose recent chats to delete, or 'all' to delete recent chats for all users (default: 'all')",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to data.db file (default: {DEFAULT_DB_PATH})",
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
        "--logs-dir",
        type=Path,
        default=DEFAULT_LOGS_DIR,
        help=f"Path to logs root directory (default: {DEFAULT_LOGS_DIR})",
    )
    parser.add_argument(
        "--keep-chat-logs",
        action="store_true",
        help="Do not delete disk-based chat session JSON files and folders",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the cleanup and report what records/files would be deleted without modifying anything",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a timestamped backup of data.db before deleting records",
    )
    parser.add_argument(
        "--skip-vacuum",
        action="store_true",
        help="Skip the VACUUM operation after deletion",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Bypass the interactive confirmation prompt",
    )
    parser.add_argument(
        "--ensure-admin-only",
        action="store_true",
        help="Check and seed 'amc_admin' if missing, without performing chat history deletion",
    )
    parser.add_argument(
        "--all-tables",
        action="store_true",
        help="Legacy full-database truncate mode: truncate ALL tables, keeping only keep_user in auth_users",
    )
    parser.add_argument(
        "--keep-user",
        type=str,
        default=DEFAULT_KEEP_USER,
        help=f"Username to preserve in auth_users when --all-tables is used (default: '{DEFAULT_KEEP_USER}')",
    )

    args = parser.parse_args()

    if args.ensure_admin_only:
        db_path = Path(args.db_path).resolve()
        if not db_path.exists():
            print(f"[ERROR] Database file not found at: {db_path}")
            sys.exit(1)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            print(f"Checking 'amc_admin' in {db_path}...")
            ok = ensure_amc_admin_seeded(conn, dry_run=args.dry_run)
            sys.exit(0 if ok else 1)
        finally:
            conn.close()

    if args.all_tables:
        success = clean_all_tables_legacy(
            db_path=args.db_path,
            chat_sessions_dir=args.chat_sessions_dir,
            keep_user=args.keep_user,
            dry_run=args.dry_run,
            backup=not args.no_backup,
            clear_chat_logs=not args.keep_chat_logs,
            skip_vacuum=args.skip_vacuum,
            force=args.yes,
        )
    else:
        success = clean_recent_chats(
            db_path=args.db_path,
            chat_sessions_dir=args.chat_sessions_dir,
            chat_evidence_dir=args.chat_evidence_dir,
            logs_dir=args.logs_dir,
            target_user=args.user,
            dry_run=args.dry_run,
            backup=not args.no_backup,
            clear_chat_logs=not args.keep_chat_logs,
            skip_vacuum=args.skip_vacuum,
            force=args.yes,
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

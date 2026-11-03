#!/usr/bin/env python
"""Restore vector store from timestamped backup."""

import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

VECTOR_STORE_DIR = Path("data/vector_store/v2_baseline_20260814")
if not VECTOR_STORE_DIR.exists() and Path("backend/data/vector_store/v2_baseline_20260814").exists():
    VECTOR_STORE_DIR = Path("backend/data/vector_store/v2_baseline_20260814")

BACKUP_ROOT = Path("data/backups/vector_store")
if not BACKUP_ROOT.exists() and Path("backend/data/backups/vector_store").exists():
    BACKUP_ROOT = Path("backend/data/backups/vector_store")

def restore_vector_store(timestamp):
    """Restore vector store from backup."""
    backup_dir = BACKUP_ROOT / f"backup_{timestamp}"
    
    if not backup_dir.exists():
        print(f"[FAIL] Backup not found: {backup_dir}")
        return False
    
    print(f"Restoring from: {backup_dir}")
    
    # Restore index
    if (backup_dir / "index.faiss").exists():
        shutil.copy2(backup_dir / "index.faiss", VECTOR_STORE_DIR / "index.faiss")
        print(f"[OK] Restored index.faiss")
    
    # Restore payloads
    if (backup_dir / "payloads.json").exists():
        shutil.copy2(backup_dir / "payloads.json", VECTOR_STORE_DIR / "payloads.json")
        print(f"[OK] Restored payloads.json")
    
    print(f"\n[OK] Vector store restored from {timestamp}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python restore_vector_store.py <timestamp>")
        print("Example: python restore_vector_store.py 20240101_120000")
        sys.exit(1)
    
    restore_vector_store(sys.argv[1])

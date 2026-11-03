#!/usr/bin/env python
"""Backup vector store (FAISS index + payloads) with timestamp."""

import shutil
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()
load_dotenv("backend/.env")

VECTOR_STORE_DIR = Path("data/vector_store/v2_baseline_20260814")
if not VECTOR_STORE_DIR.exists() and Path("backend/data/vector_store/v2_baseline_20260814").exists():
    VECTOR_STORE_DIR = Path("backend/data/vector_store/v2_baseline_20260814")

BACKUP_ROOT = Path("data/backups/vector_store")
if not BACKUP_ROOT.parent.exists() and Path("backend/data").exists():
    BACKUP_ROOT = Path("backend/data/backups/vector_store")

def backup_vector_store():
    """Create timestamped backup of vector store."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Backup index
    if (VECTOR_STORE_DIR / "index.faiss").exists():
        shutil.copy2(VECTOR_STORE_DIR / "index.faiss", backup_dir / "index.faiss")
        print(f"[OK] Backed up index.faiss")
    
    # Backup payloads
    if (VECTOR_STORE_DIR / "payloads.json").exists():
        shutil.copy2(VECTOR_STORE_DIR / "payloads.json", backup_dir / "payloads.json")
        print(f"[OK] Backed up payloads.json")
    
    # Create metadata
    metadata = {
        "timestamp": timestamp,
        "source": str(VECTOR_STORE_DIR),
        "backup_path": str(backup_dir),
        "files": ["index.faiss", "payloads.json"]
    }
    
    with open(backup_dir / "backup_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n[OK] Backup created: {backup_dir}")
    print(f"  To restore: python scripts/restore_vector_store.py {timestamp}")
    
    return backup_dir

if __name__ == "__main__":
    backup_vector_store()

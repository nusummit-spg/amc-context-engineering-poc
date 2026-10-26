#!/usr/bin/env python
# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""
Migration script: Move users from JSON file to database.

This script:
1. Reads from backend/app/auth/data/users.json
2. Inserts all users into the auth_users table
3. Verifies the migration was successful
"""
import json
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.core.database import SessionLocal
from app.schemas.auth_users_table import AuthUser
from app.auth.security import hash_password


def migrate_users():
    """Load users from JSON and insert into database.

    Returns:
        Result of the operation.
    """
    
    # Path to JSON users file
    json_path = backend_path / "app" / "auth" / "data" / "users.json"
    
    if not json_path.exists():
        print(f"ERROR: Users JSON file not found at {json_path}")
        return False
    
    print(f"Reading users from {json_path}...")
    
    with open(json_path, "r") as f:
        data = json.load(f)
    
    users = data.get("users", [])
    print(f"Found {len(users)} users in JSON file")
    
    # Get database session
    db = SessionLocal()
    
    try:
        migrated = 0
        errors = 0
        
        for user_data in users:
            try:
                username = user_data.get("username")
                
                # Check if user already exists
                existing = db.query(AuthUser).filter_by(username=username).first()
                if existing:
                    print(f"  [-] User '{username}' already exists in database (skipped)")
                    continue
                
                # Create user record
                user = AuthUser(
                    username=username,
                    password_hash=user_data.get("password_hash", ""),
                    display_name=user_data.get("display_name", username),
                    email=user_data.get("email", ""),
                    role=user_data.get("role", ""),
                    department=user_data.get("department", ""),
                    avatar_initials=user_data.get("avatar_initials", ""),
                    status=user_data.get("status", "Active"),
                    tenant_id=user_data.get("tenant_id"),
                )
                
                db.add(user)
                db.commit()
                
                print(f"  [OK] Migrated user: {username} ({user.role})")
                migrated += 1
                
            except Exception as e:
                db.rollback()
                print(f"  [X] Error migrating user '{username}': {e}")
                errors += 1
        
        print(f"\n[OK] Migration complete: {migrated} users migrated, {errors} errors")
        return errors == 0
        
    finally:
        db.close()


def seed_compliance_officer():
    """Seed a Compliance & Regulatory Officer user.

    Returns:
        Result of the operation.
    """
    
    db = SessionLocal()
    
    try:
        # Check if user exists
        username = "compliance_officer"
        existing = db.query(AuthUser).filter_by(username=username).first()
        
        if existing:
            print(f"User '{username}' already exists in database")
            return True
        
        # Create the user
        user = AuthUser(
            username=username,
            password_hash=hash_password("Compliance@2026"),
            display_name="Compliance Officer",
            email="compliance@amc.com",
            role="Compliance & Regulatory Officer",
            department="Regulatory & Legal Compliance",
            avatar_initials="CO",
            status="Active",
        )
        
        db.add(user)
        db.commit()
        
        print(f"[OK] Seeded user: {username} ({user.role})")
        print(f"  Email: {user.email}")
        print(f"  Password: Compliance@2026")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"[X] Error seeding compliance officer: {e}")
        return False
        
    finally:
        db.close()


def verify_migration():
    """Verify that users were migrated successfully.

    Returns:
        Result of the operation.
    """
    
    db = SessionLocal()
    
    try:
        count = db.query(AuthUser).count()
        print(f"\n[OK] Database now contains {count} users")
        
        # Show all users
        print("\nUsers in database:")
        users = db.query(AuthUser).all()
        for user in users:
            status_marker = "[OK]" if user.status == "Active" else "[X]"
            print(f"  {status_marker} {user.username:25} | {user.display_name:20} | {user.role}")
        
        return count > 0
        
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("User Migration Script: JSON -> Database")
    print("=" * 70)
    
    # Step 1: Migrate users
    print("\n[Step 1] Migrating users from JSON file...")
    success = migrate_users()
    
    if not success:
        print("\nMigration encountered errors")
        sys.exit(1)
    
    # Step 2: Seed compliance officer
    print("\n[Step 2] Seeding Compliance & Regulatory Officer...")
    success = seed_compliance_officer()
    
    if not success:
        print("Failed to seed compliance officer")
        sys.exit(1)
    
    # Step 3: Verify
    print("\n[Step 3] Verifying migration...")
    verify_migration()
    
    print("\n" + "=" * 70)
    print("[OK] Migration completed successfully!")
    print("=" * 70)

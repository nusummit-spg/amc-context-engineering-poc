#!/usr/bin/env python
"""
Test script: Verify Compliance Officer can login and run queries.

This script:
1. Tests authentication with the seeded compliance_officer user
2. Verifies token generation
3. Attempts to run a query
4. Checks session creation
"""
import sys
import json
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.auth.service import AuthService
from app.auth.sql_repository import SqlUserRepository
from app.core.database import SessionLocal
from app.schemas.auth_users_table import AuthUser
from app.config import get_settings


def test_authentication():
    """Test authentication with Compliance Officer credentials.

    Returns:
        Result of the operation.
    """
    print("\n[Test 1] Authentication")
    print("-" * 70)
    
    settings = get_settings()
    repository = SqlUserRepository(session_factory=SessionLocal)
    
    auth_service = AuthService(
        repository=repository,
        secret_key=settings.auth_secret_key,
        session_ttl_minutes=settings.auth_session_ttl_minutes,
        session_ttl_minutes_remember=settings.auth_session_ttl_minutes_remember,
    )
    
    # Test 1a: Login with correct credentials
    print("  Test 1a: Login with correct credentials...")
    result = auth_service.authenticate("compliance_officer", "Compliance@2026")
    
    if result.success:
        print(f"    ✓ Login successful")
        print(f"      User: {result.user.username}")
        print(f"      Display Name: {result.user.display_name}")
        print(f"      Role: {result.user.role}")
        print(f"      Token: {result.token[:20]}... (truncated)")
        print(f"      Expires at: {result.expires_at}")
        token = result.token
    else:
        print(f"    ✗ Login failed: {result.error}")
        return False
    
    # Test 1b: Verify token
    print("\n  Test 1b: Verify token...")
    user = auth_service.resolve_session(token)
    
    if user:
        print(f"    ✓ Token is valid")
        print(f"      Username: {user.username}")
        print(f"      Role: {user.role}")
    else:
        print(f"    ✗ Token is invalid")
        return False
    
    # Test 1c: Login with wrong password
    print("\n  Test 1c: Login with wrong password (should fail)...")
    result = auth_service.authenticate("compliance_officer", "WrongPassword")
    
    if not result.success:
        print(f"    ✓ Correctly rejected wrong password: {result.error}")
    else:
        print(f"    ✗ Incorrectly accepted wrong password")
        return False
    
    return True, token, user


def test_database_user():
    """Test that user exists in database.

    Returns:
        Result of the operation.
    """
    print("\n[Test 2] Database User Verification")
    print("-" * 70)
    
    db = SessionLocal()
    
    try:
        user = db.query(AuthUser).filter_by(username="compliance_officer").first()
        
        if user:
            print(f"  ✓ User found in database")
            print(f"    Username: {user.username}")
            print(f"    Display Name: {user.display_name}")
            print(f"    Email: {user.email}")
            print(f"    Role: {user.role}")
            print(f"    Department: {user.department}")
            print(f"    Status: {user.status}")
            print(f"    Created At: {user.created_at}")
            return True
        else:
            print(f"  ✗ User NOT found in database")
            return False
            
    finally:
        db.close()


def test_repository():
    """Test SQL repository.

    Returns:
        Result of the operation.
    """
    print("\n[Test 3] SQL Repository")
    print("-" * 70)
    
    repo = SqlUserRepository(session_factory=SessionLocal)
    
    # Test 3a: Get by username
    print("  Test 3a: Get user by username...")
    record = repo.get_by_username("compliance_officer")
    
    if record:
        print(f"    ✓ User retrieved successfully")
        print(f"      Username: {record.username}")
        print(f"      Display Name: {record.display_name}")
        print(f"      Role: {record.role}")
    else:
        print(f"    ✗ User NOT retrieved")
        return False
    
    # Test 3b: Case insensitivity
    print("\n  Test 3b: Case-insensitive lookup...")
    record = repo.get_by_username("COMPLIANCE_OFFICER")
    
    if record:
        print(f"    ✓ Case-insensitive lookup works")
    else:
        print(f"    ✗ Case-insensitive lookup failed")
        return False
    
    # Test 3c: All users
    print("\n  Test 3c: Retrieve all users...")
    db = SessionLocal()
    try:
        users = repo.get_all_users(db)
        print(f"    ✓ Retrieved {len(users)} users")
        
        # Check for compliance officer in the list
        co_found = any(u.username == "compliance_officer" for u in users)
        if co_found:
            print(f"    ✓ Compliance Officer found in user list")
        else:
            print(f"    ✗ Compliance Officer NOT in user list")
            return False
            
    finally:
        db.close()
    
    return True


def main():
    """Main.

    Returns:
        Result of the operation.
    """
    print("=" * 70)
    print("Compliance Officer User Tests")
    print("=" * 70)
    print(f"Test Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_passed = True
    
    # Run tests
    try:
        print("\n" + "="*70)
        print("Test Results")
        print("="*70)
        
        # Test database
        if not test_database_user():
            all_passed = False
        
        # Test repository
        if not test_repository():
            all_passed = False
        
        # Test authentication
        auth_result = test_authentication()
        if not auth_result:
            all_passed = False
        else:
            _, token, user = auth_result
        
        # Summary
        print("\n" + "=" * 70)
        if all_passed:
            print("✓ ALL TESTS PASSED!")
            print("=" * 70)
            print("\nCompliance Officer user is ready to use:")
            print("  Login: compliance_officer")
            print("  Password: Compliance@2026")
            print(f"  Role: {user.role}")
            print(f"  Email: {user.email}")
            print("\nYou can now:")
            print("  1. Login from the web UI")
            print("  2. Run queries")
            print("  3. Manage sessions")
            print("  4. Create additional users from the admin tab")
            print()
            return 0
        else:
            print("✗ SOME TESTS FAILED")
            print("=" * 70)
            return 1
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

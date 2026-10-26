#!/usr/bin/env python
"""
Comprehensive database seeding script.

Creates the auth_users table and seeds all users (including Compliance Officer).
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import text
from app.core.database import engine, SessionLocal, Base
from app.schemas.auth_users_table import AuthUser
from app.auth.security import hash_password


def create_tables():
    """Create all necessary tables."""
    print("[Step 1] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("  ✓ Tables created")


def seed_users():
    """Seed all users to the database.

    Returns:
        Result of the operation.
    """
    print("\n[Step 2] Seeding users...")
    
    db = SessionLocal()
    
    try:
        # Define all users
        users_data = [
            {
                "username": "compliance_officer",
                "password": "Compliance@2026",
                "display_name": "Compliance Officer",
                "email": "compliance@amc.com",
                "role": "Compliance & Regulatory Officer",
                "department": "Regulatory & Legal Compliance",
                "avatar_initials": "CO",
                "status": "Active",
            },
            {
                "username": "sarah.compliance",
                "password_hash": "pbkdf2_sha256$260000$52a5b1dfcd28274230cf2f4d5e23eb16$171fd0d36b213661b2588d135faf3c5b977642e8720e1067d63ba55aed5a6f9d",
                "display_name": "Sarah Kapoor",
                "email": "s.kapoor@amc.com",
                "role": "Compliance & Regulatory Officer",
                "department": "Regulatory & Legal Compliance",
                "avatar_initials": "SK",
                "status": "Active",
            },
            {
                "username": "vikram.pm",
                "password_hash": "pbkdf2_sha256$260000$de8faf693c45fb169ea1610b2004f57f$1540f4383b1452faa092e313b545176582f2270d248bb944a138ca39b2a272a9",
                "display_name": "Vikram Mehta",
                "email": "v.mehta@amc.com",
                "role": "Fund Manager / Portfolio Manager",
                "department": "Equity Investment Management",
                "avatar_initials": "VM",
                "status": "Active",
            },
            {
                "username": "ananya.esg",
                "password_hash": "pbkdf2_sha256$260000$d2393463fbf466b8781504a469966ec0$57d83ce591184e9786acae4be1087e3d9e6a1867f2f77c81b92939fa0e6e4ffc",
                "display_name": "Ananya Sharma",
                "email": "a.sharma@amc.com",
                "role": "ESG & Sustainability Analyst",
                "department": "Sustainable Investing & ESG",
                "avatar_initials": "AS",
                "status": "Active",
            },
            {
                "username": "rahul.sales",
                "password_hash": "pbkdf2_sha256$260000$43b0361482f093d8aa70414dfdf04652$3308438578fc4b7b730ff70c296ccc017ab300118de9e667629d97104488c26c",
                "display_name": "Rahul Verma",
                "email": "r.verma@amc.com",
                "role": "Sales & Distribution Manager",
                "department": "Institutional & Retail Distribution",
                "avatar_initials": "RV",
                "status": "Active",
            },
            {
                "username": "priya.investor",
                "password_hash": "pbkdf2_sha256$260000$63d2bfbabbe58b82d294f19c452f30a6$27671786c38258ef8b822bcdad861337a7b0e133687ad02c4abc1404efba3e21",
                "display_name": "Priya Nair",
                "email": "p.nair@public.com",
                "role": "Retail Investor / Public Client",
                "department": "External Client Portal",
                "avatar_initials": "PN",
                "status": "Active",
            },
            {
                "username": "admin",
                "password_hash": "pbkdf2_sha256$260000$8dde1e3b272503fd786b93f2a2f2d073$8dbed544eb6fc98e0599364ffb5b03008f90d28bf778f4e1f9bf6427184a030e",
                "display_name": "Sarah Kapoor (Admin)",
                "email": "admin@amc.com",
                "role": "Compliance & Regulatory Officer",
                "department": "Regulatory & Legal Compliance",
                "avatar_initials": "AD",
                "status": "Active",
            },
        ]
        
        seeded = 0
        skipped = 0
        
        for user_data in users_data:
            username = user_data["username"]
            
            # Check if user exists
            existing = db.query(AuthUser).filter_by(username=username).first()
            if existing:
                print(f"  ⊘ User '{username}' already exists (skipped)")
                skipped += 1
                continue
            
            # Handle password hashing
            if "password" in user_data:
                password_hash = hash_password(user_data["password"])
            else:
                password_hash = user_data.get("password_hash", "")
            
            # Create user
            user = AuthUser(
                username=username,
                password_hash=password_hash,
                display_name=user_data["display_name"],
                email=user_data["email"],
                role=user_data["role"],
                department=user_data["department"],
                avatar_initials=user_data.get("avatar_initials", ""),
                status=user_data.get("status", "Active"),
            )
            
            db.add(user)
            db.commit()
            
            print(f"  ✓ Seeded user: {username} ({user.role})")
            seeded += 1
        
        print(f"\n  Summary: {seeded} users seeded, {skipped} skipped")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"  ✗ Error seeding users: {e}")
        return False
        
    finally:
        db.close()


def verify_users():
    """Verify users were seeded.

    Returns:
        Result of the operation.
    """
    print("\n[Step 3] Verifying seeded users...")
    
    db = SessionLocal()
    
    try:
        count = db.query(AuthUser).count()
        print(f"  ✓ Database contains {count} users")
        
        # Show all users
        users = db.query(AuthUser).order_by(AuthUser.created_at.desc()).all()
        
        print("\n  Users in database:")
        print(f"  {'Username':<25} | {'Display Name':<20} | {'Role':<35} | {'Status':<10}")
        print(f"  {'-'*25}-+-{'-'*20}-+-{'-'*35}-+-{'-'*10}")
        
        for user in users:
            status_marker = "✓" if user.status == "Active" else "✗"
            print(f"  {status_marker} {user.username:<23} | {user.display_name:<20} | {user.role:<35} | {user.status:<10}")
        
        # Check compliance officer
        co = db.query(AuthUser).filter_by(username="compliance_officer").first()
        
        if co:
            print("\n  ✓ Compliance & Regulatory Officer details:")
            print(f"    Username: {co.username}")
            print(f"    Display Name: {co.display_name}")
            print(f"    Email: {co.email}")
            print(f"    Role: {co.role}")
            print(f"    Department: {co.department}")
            print(f"    Status: {co.status}")
            print(f"    Password: Compliance@2026 (plaintext)")
        
        return True
        
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 80)
    print("Database Seeding Script")
    print("=" * 80)
    
    try:
        create_tables()
        seed_users()
        verify_users()
        
        print("\n" + "=" * 80)
        print("✓ Database seeding completed successfully!")
        print("=" * 80)
        print("\nYou can now login with:")
        print("  Username: compliance_officer")
        print("  Password: Compliance@2026")
        print()
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)

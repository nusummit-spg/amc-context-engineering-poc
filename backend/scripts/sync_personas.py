"""Operational and maintenance script for sync personas."""

import json
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
from app.auth.security import hash_password, verify_password
from app.core.database import SessionLocal
from app.schemas.auth_users_table import AuthUser

personas = [
    {
        "username": "compliance_officer",
        "password": "Compliance@2026",
        "display_name": "Compliance Officer",
        "role": "Compliance & Regulatory Officer",
        "department": "Regulatory & Legal Compliance",
        "email": "compliance@amc.com",
        "avatar_initials": "CO",
        "status": "Active"
    },
    {
        "username": "sarah.compliance",
        "password": "Compliance@2026",
        "display_name": "Sarah Kapoor",
        "role": "Compliance & Regulatory Officer",
        "department": "Regulatory & Legal Compliance",
        "email": "s.kapoor@amc.com",
        "avatar_initials": "SK",
        "status": "Active"
    },
    {
        "username": "vikram.pm",
        "password": "Portfolio@2026",
        "display_name": "Vikram Mehta",
        "role": "Fund Manager / Portfolio Manager",
        "department": "Equity Investment Management",
        "email": "v.mehta@amc.com",
        "avatar_initials": "VM",
        "status": "Active"
    },
    {
        "username": "ananya.esg",
        "password": "Sustainability@2026",
        "display_name": "Ananya Sharma",
        "role": "ESG & Sustainability Analyst",
        "department": "Sustainable Investing & ESG",
        "email": "a.sharma@amc.com",
        "avatar_initials": "AS",
        "status": "Active"
    },
    {
        "username": "rahul.sales",
        "password": "Distribution@2026",
        "display_name": "Rahul Verma",
        "role": "Sales & Distribution Manager",
        "department": "Institutional & Retail Distribution",
        "email": "r.verma@amc.com",
        "avatar_initials": "RV",
        "status": "Active"
    },
    {
        "username": "priya.investor",
        "password": "Investor@2026",
        "display_name": "Priya Nair",
        "role": "Retail Investor / Public Client",
        "department": "External Client Portal",
        "email": "p.nair@public.com",
        "avatar_initials": "PN",
        "status": "Active"
    },
    {
        "username": "admin",
        "password": "Compliance@2026",
        "display_name": "Sarah Kapoor (Admin)",
        "role": "Compliance & Regulatory Officer",
        "department": "Regulatory & Legal Compliance",
        "email": "admin@amc.com",
        "avatar_initials": "AD",
        "status": "Active"
    }
]

def main():
    """Main.
    """
    # Update SQLite Database
    with SessionLocal() as db:
        for p in personas:
            u = db.query(AuthUser).filter(AuthUser.username.ilike(p["username"])).first()
            if not u and "." in p["username"]:
                u = db.query(AuthUser).filter(AuthUser.username.ilike(p["username"].replace(".", "_"))).first()
            if u:
                u.username = p["username"]
                u.password_hash = hash_password(p["password"])
                u.display_name = p["display_name"]
                u.role = p["role"]
                u.department = p["department"]
                u.email = p["email"]
                u.avatar_initials = p["avatar_initials"]
                u.status = p["status"]
                print(f"Updated in DB: {p['username']}")
            else:
                new_u = AuthUser(
                    username=p["username"],
                    password_hash=hash_password(p["password"]),
                    display_name=p["display_name"],
                    role=p["role"],
                    department=p["department"],
                    email=p["email"],
                    avatar_initials=p["avatar_initials"],
                    status=p["status"]
                )
                db.add(new_u)
                print(f"Inserted into DB: {p['username']}")
        db.commit()

    # Update users.json
    json_path = Path("app/auth/data/users.json")
    with open(json_path, "r", encoding="utf-8") as f:
        jdata = json.load(f)

    users_list = jdata.get("users", [])
    by_name = {u["username"].lower(): u for u in users_list}

    for p in personas:
        uname = p["username"].lower()
        if uname in by_name:
            rec = by_name[uname]
            rec["password_hash"] = hash_password(p["password"])
            rec["display_name"] = p["display_name"]
            rec["role"] = p["role"]
            rec["department"] = p["department"]
            rec["email"] = p["email"]
            rec["avatar_initials"] = p["avatar_initials"]
            rec["status"] = p["status"]
            print(f"Updated in users.json: {p['username']}")
        else:
            new_rec = {
                "username": p["username"],
                "password_hash": hash_password(p["password"]),
                "display_name": p["display_name"],
                "role": p["role"],
                "department": p["department"],
                "email": p["email"],
                "avatar_initials": p["avatar_initials"],
                "status": p["status"]
            }
            users_list.append(new_rec)
            by_name[uname] = new_rec
            print(f"Inserted into users.json: {p['username']}")

    jdata["users"] = users_list
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(jdata, f, indent=2, ensure_ascii=False)

    print("Sync completed successfully!")

if __name__ == "__main__":
    main()

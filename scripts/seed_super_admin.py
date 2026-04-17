"""One-time super-admin seed script.

Usage:
    cd backend
    python scripts/seed_super_admin.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from getpass import getpass

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.user import User


def main() -> None:
    admin_email = settings.admin_seed_email.strip().lower()
    admin_password = settings.admin_seed_password.strip()
    admin_name = settings.admin_seed_full_name.strip() or "Super Admin"

    if not admin_email:
        admin_email = input("Super-admin email: ").strip().lower()
    if not admin_password:
        admin_password = getpass("Super-admin password: ").strip()
    if not settings.admin_seed_full_name.strip():
        entered_name = input("Super-admin full name [Super Admin]: ").strip()
        if entered_name:
            admin_name = entered_name

    if not admin_email or not admin_password:
        raise RuntimeError("Super-admin email and password are required.")

    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.email == admin_email).one_or_none()
        if admin_user is None:
            admin_user = User(
                email=admin_email,
                full_name=admin_name,
                hashed_password=get_password_hash(admin_password),
                role="admin",
                is_active=True,
            )
            db.add(admin_user)
            action = "created"
        else:
            admin_user.full_name = admin_name
            admin_user.hashed_password = get_password_hash(admin_password)
            admin_user.role = "admin"
            admin_user.is_active = True
            db.add(admin_user)
            action = "updated"

        db.commit()
        print(f"Super-admin {action}: {admin_email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

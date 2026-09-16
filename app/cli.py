from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal, init_db
from app.models import User

# The studio keeps exactly two keys: the owner and Raph. There is no
# public signup anywhere, so this cap is the whole lock — once the
# second founder exists, no further account can be created.
MAX_FOUNDERS = 2


def create_founder(
    email: str, password: str, display_name: str = "", session_factory=None
) -> User:
    if session_factory is None:
        init_db()
        session_factory = SessionLocal
    with session_factory() as db:
        if db.query(User).filter(User.role == "founder").count() >= MAX_FOUNDERS:
            raise SystemExit("The studio keeps two keys — both are already cut.")
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit(f"A studio account already exists for {email}.")
        user = User(
            email=email,
            password_hash=hash_password(password),
            role="founder",
            display_name=display_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def main() -> None:
    parser = argparse.ArgumentParser(description="£UVR€ studio administration")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-founder", help="Create a studio (founder) account")
    p.add_argument("email")
    p.add_argument("--name", default="")
    args = parser.parse_args()
    if args.cmd == "create-founder":
        password = getpass.getpass("Studio password: ")
        if len(password) < 12:
            raise SystemExit("Use at least 12 characters.")
        user = create_founder(args.email, password, args.name)
        print(f"Studio account ready for {user.email}.")


if __name__ == "__main__":
    main()

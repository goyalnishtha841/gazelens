"""
init_db.py

Schema setup.

    cd backend
    python -m api.init_db                 # create tables if missing
    python -m api.init_db --reset         # DROP everything, then create
    python -m api.init_db --demo-user     # also create a demo account

Idempotent, so running it against an existing database is safe. `--reset` is
not: it drops every table, and it asks before doing so unless --yes is passed.

There is no Alembic. At this stage the schema changes by editing models.py and
recreating a throwaway pilot database. The moment the study has collected data
worth migrating rather than regenerating, add it -- see CONTRACT.md.
"""

import argparse
import sys

from .db import DATABASE_URL, engine, init_db
from .models import Session as SessionModel, User


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the GazeLens schema")
    parser.add_argument("--reset", action="store_true",
                       help="DROP all tables first -- destroys existing sessions")
    parser.add_argument("--yes", action="store_true", help="skip the --reset prompt")
    parser.add_argument("--demo-user", action="store_true",
                       help="create demo@example.com / demo-password-123")
    args = parser.parse_args()

    print(f"database: {DATABASE_URL}")

    if args.reset and not args.yes:
        # Guarded because a --reset on the pilot database would destroy
        # participant sessions that cannot be re-collected.
        if not sys.stdin.isatty():
            print("--reset needs --yes when stdin isn't a terminal. Aborting.")
            return 1
        if input("Drop ALL tables and recreate? [y/N] ").strip().lower() != "y":
            print("aborted")
            return 1

    try:
        init_db(drop=args.reset)
    except RuntimeError as exc:
        # init_db already turned SQLAlchemy's traceback into something
        # actionable; printing it raw is the whole point.
        print(f"\n{exc}")
        return 1
    print("schema created" + (" (after drop)" if args.reset else ""))

    if args.demo_user:
        from .db import SessionLocal
        from .security import hash_password

        db = SessionLocal()
        try:
            # NOT a .local address. Pydantic's EmailStr rejects special-use
            # and reserved domains (.local, localhost), so a demo account
            # created there could never log in -- /api/auth/login would 422 on
            # the address before it ever checked the password.
            email = "demo@example.com"
            if db.query(User).filter(User.email == email).first():
                print(f"demo user already exists: {email}")
            else:
                db.add(User(email=email,
                            password_hash=hash_password("demo-password-123")))
                db.commit()
                print(f"demo user created: {email} / demo-password-123")
        finally:
            db.close()

    with engine.connect() as conn:
        tables = sorted(engine.dialect.get_table_names(conn))
    print(f"tables: {tables}")

    from .db import SessionLocal

    db = SessionLocal()
    try:
        print(f"users: {db.query(User).count()}  "
              f"sessions: {db.query(SessionModel).count()}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

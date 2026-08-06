"""
db.py

SQLite via SQLAlchemy 2.0. Chosen because the repo declared no database
dependency at all, and the brief names this as the sensible default at this
scale -- a pilot study with tens of participants, not a production service.

WHAT LIVES IN THE DATABASE, AND WHAT DOESN'T
--------------------------------------------
The DB holds session records, users, and report metadata. It deliberately
does NOT hold:

  * calibration samples -- backend/calibration already owns those in its own
    JSON store. A session row keeps a REFERENCE (cal_<id>). Copying them here
    would create two truths about the same participant sitting.
  * trained gaze models -- backend/gaze_estimation owns those, keyed by the
    same calibration session id.
  * raw gaze streams -- bulk timeseries, appended to a JSONL file per session
    and referenced by path. A 10-minute session at 30Hz is ~18k points; that
    is fine in SQLite but pointless in it, since nothing ever queries an
    individual gaze point.

So the DB is the index that ties the modules together, not a second copy of
what they already store.
"""

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

API_DIR = Path(__file__).resolve().parent

# Overridable so the tests can point at a temp file instead of the real DB.
DATABASE_URL = os.environ.get(
    "GAZELENS_DATABASE_URL",
    f"sqlite:///{(API_DIR / 'gazelens.db').as_posix()}",
)

# Where per-session bulk data (gaze streams, generated reports) is written.
DATA_DIR = Path(os.environ.get("GAZELENS_DATA_DIR", API_DIR / "session_data"))


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    # check_same_thread=False: FastAPI serves requests from a threadpool, and
    # SQLite's default refuses a connection used across threads. Each request
    # still gets its own Session via get_db, so no connection is shared.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            # SQLite has foreign keys OFF by default. Without this, the
            # ON DELETE CASCADE from sessions to reports silently does
            # nothing and deleting a session orphans its report row.
            cur.execute("PRAGMA foreign_keys=ON")
            # WAL lets a read (dashboard polling for status) proceed while a
            # write (the pipeline finishing) is in flight.
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


engine = _make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(drop: bool = False) -> None:
    """Create the schema. Idempotent.

    No Alembic: at this stage the schema changes by editing models.py and
    recreating a throwaway pilot database, and a migration tool would be
    ceremony around a file that gets deleted. If the study ever collects data
    worth migrating rather than regenerating, that is the moment to add it --
    flagged in CONTRACT.md rather than pre-built.
    """
    from sqlalchemy.exc import OperationalError

    from . import models  # noqa: F401 -- registers the mappers on Base

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Create the database file's own directory. SQLite will not, and its error
    # for a missing parent is "unable to open database file" wrapped in a
    # 60-line SQLAlchemy traceback that says nothing about which path or why.
    if DATABASE_URL.startswith("sqlite:///"):
        db_file = Path(DATABASE_URL.replace("sqlite:///", "", 1))
        if str(db_file) not in (":memory:", ""):
            try:
                db_file.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise RuntimeError(
                    f"cannot create the database directory {db_file.parent}: {exc}\n"
                    f"GAZELENS_DATABASE_URL={DATABASE_URL}"
                ) from exc

    try:
        if drop:
            Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        raise RuntimeError(
            f"could not open the database at {DATABASE_URL}.\n"
            f"Check the path is writable, or set GAZELENS_DATABASE_URL to one "
            f"that is.\nUnderlying error: {exc.orig}"
        ) from exc


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one Session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def configure(url: str, data_dir: Path) -> None:
    """Repoint the engine and data directory. Used by the tests.

    Rebinds the module-level engine and sessionmaker so everything that
    imports them picks up the change -- the alternative is threading a
    connection through every call site for the sake of tests.
    """
    global engine, SessionLocal, DATABASE_URL, DATA_DIR

    DATABASE_URL = url
    DATA_DIR = Path(data_dir)
    engine = _make_engine(url)
    SessionLocal.configure(bind=engine)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "DATABASE_URL",
    "DATA_DIR",
    "init_db",
    "get_db",
    "configure",
]

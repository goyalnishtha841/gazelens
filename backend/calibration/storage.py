"""
storage.py

Persistence for calibration sessions.

JSON files on disk, one per session, plus a CSV export of the flat training
rows. Deliberately not SQLite: backend/db isn't built yet and owning a schema
here would collide with it later. A directory of self-describing JSON files
is trivial to hand-inspect, trivial to hand to gaze_estimation, and trivial
to migrate into whatever backend/db settles on.

    calibration_data/
      cal_a1b2c3d4e5f6.json      full session -- points, samples, quality
      cal_a1b2c3d4e5f6.csv       flat training rows (written on completion)

Sessions are held in memory while in progress and flushed to disk on every
mutation. At a few hundred samples per session that's cheap, and it means a
server restart mid-calibration doesn't cost the participant their time.
"""

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from .session import (
    STATUS_COMPLETE,
    TRAINING_ROW_COLUMNS,
    CalibrationSession,
)

DATA_DIR = Path(__file__).resolve().parent / "calibration_data"


class SessionNotFound(KeyError):
    """No session with that id, in memory or on disk."""


class CalibrationStore:
    """In-memory registry with a JSON file behind it."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self._sessions: Dict[str, CalibrationSession] = {}

    # ------------------------------------------------------------------

    def _path(self, session_id: str) -> Path:
        # session_ids are server-generated (cal_<hex>), but this is the one
        # place a client-supplied string becomes a filesystem path, so refuse
        # anything that could climb out of the data directory.
        if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
            raise SessionNotFound(f"invalid session id {session_id!r}")
        return self.data_dir / f"{session_id}.json"

    def _ensure_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------

    def save(self, session: CalibrationSession) -> Path:
        """Write the session to disk atomically.

        Atomic because the client posts samples in a rapid burst: a plain
        truncate-and-write that gets interrupted leaves a half-written JSON
        file, which loses the whole session rather than one sample.
        """
        self._ensure_dir()
        path = self._path(session.session_id)
        fd, tmp = tempfile.mkstemp(dir=str(self.data_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(session.to_dict(), fh, indent=2)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self._sessions[session.session_id] = session
        return path

    def get(self, session_id: str) -> CalibrationSession:
        """From memory, falling back to disk. Raises SessionNotFound."""
        if session_id in self._sessions:
            return self._sessions[session_id]

        path = self._path(session_id)
        if not path.exists():
            raise SessionNotFound(f"no calibration session {session_id!r}")

        with path.open(encoding="utf-8") as fh:
            session = CalibrationSession.from_dict(json.load(fh))
        self._sessions[session_id] = session
        return session

    def exists(self, session_id: str) -> bool:
        try:
            self.get(session_id)
        except SessionNotFound:
            return False
        return True

    def list_sessions(self) -> List[dict]:
        """Lightweight index of everything on disk -- no samples loaded."""
        if not self.data_dir.exists():
            return []

        out: List[dict] = []
        for path in sorted(self.data_dir.glob("*.json")):
            try:
                with path.open(encoding="utf-8") as fh:
                    d = json.load(fh)
            except (json.JSONDecodeError, OSError):
                continue    # a half-written or hand-edited file shouldn't
                            # take down the whole listing
            out.append({
                "session_id": d.get("session_id"),
                "participant_id": d.get("participant_id"),
                "pattern": d.get("pattern"),
                "status": d.get("status"),
                "created_at": d.get("created_at"),
                "total_samples": len(d.get("samples", [])),
                "usable": (d.get("quality") or {}).get("usable"),
            })
        return out

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        self._sessions.pop(session_id, None)
        existed = path.exists()
        path.unlink(missing_ok=True)
        path.with_suffix(".csv").unlink(missing_ok=True)
        return existed

    # ------------------------------------------------------------------

    def export_training_csv(self, session: CalibrationSession) -> Path:
        """Flat rows -> CSV, the file backend/gaze_estimation reads.

        Written alongside the JSON on completion. Same data as
        session.training_rows(); the CSV just means the next module can start
        with pandas.read_csv and no bespoke parsing.
        """
        self._ensure_dir()
        path = self._path(session.session_id).with_suffix(".csv")
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=TRAINING_ROW_COLUMNS)
            writer.writeheader()
            for row in session.training_rows():
                writer.writerow(row)
        return path

    def complete(self, session: CalibrationSession) -> Dict[str, Path]:
        """Mark finished, persist, and write the training export."""
        session.status = STATUS_COMPLETE
        return {
            "json": self.save(session),
            "csv": self.export_training_csv(session),
        }


# Process-wide store, mirroring cv.get_pipeline(). Tests point this at a
# temp directory via set_store() so they never touch calibration_data/.
_store: Optional[CalibrationStore] = None


def get_store() -> CalibrationStore:
    global _store
    if _store is None:
        _store = CalibrationStore()
    return _store


def set_store(store: Optional[CalibrationStore]) -> None:
    global _store
    _store = store


__all__ = [
    "CalibrationStore",
    "SessionNotFound",
    "DATA_DIR",
    "get_store",
    "set_store",
]

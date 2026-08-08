"""
models.py

The three tables the session layer needs: users, sessions, reports.

A note on the columns that are references rather than data:
`Session.calibration_session_id` points into backend/calibration's JSON store
and `Session.gaze_path` points at a JSONL file. Those modules own that data;
see db.py for why it isn't duplicated here.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    # Timezone-aware throughout. Naive datetimes compare and serialise
    # ambiguously, and a pilot study that runs across a DST boundary would
    # otherwise produce sessions that appear to finish before they started.
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ----------------------------------------------------------------------
# session status vocabulary


STATUS_CREATED = "created"
STATUS_CALIBRATING = "calibrating"
STATUS_CALIBRATED = "calibrated"
STATUS_RECORDING = "recording"
STATUS_PROCESSING = "processing"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

SESSION_STATUSES = (
    STATUS_CREATED,
    STATUS_CALIBRATING,
    STATUS_CALIBRATED,
    STATUS_RECORDING,
    STATUS_PROCESSING,
    STATUS_COMPLETE,
    STATUS_FAILED,
)

# Statuses from which no further work happens.
TERMINAL_STATUSES = (STATUS_COMPLETE, STATUS_FAILED)

MODE_TEST_UI = "test_ui"
MODE_URL = "url"
SESSION_MODES = (MODE_TEST_UI, MODE_URL)


# ----------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True,
                                    default=lambda: _new_id("usr"))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=_utcnow)

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    """One participant sitting: calibrate, record, analyse, report."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True,
                                    default=lambda: _new_id("ses"))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    mode: Mapped[str] = mapped_column(String(16), default=MODE_TEST_UI)
    ui_page: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    target_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(24), default=STATUS_CREATED, index=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # References into the modules that own this data -- not copies.
    calibration_session_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    gaze_model_trained: Mapped[bool] = mapped_column(default=False)
    gaze_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gaze_point_count: Mapped[int] = mapped_column(default=0)

    # The element layout this session was recorded against, kept so a report
    # can be re-derived later even if the test UI or the page changes.
    element_layout: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    layout_is_placeholder: Mapped[bool] = mapped_column(default=False)
    # For mode="url": what backend/render detected, how much of it was guessed,
    # and where the screenshot went. Kept so a reader can audit which elements
    # the agents' findings were actually about.
    capture_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=_utcnow, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    report: Mapped[Optional["Report"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )

    # The dashboard's default query is "my sessions, newest first"; without
    # this it degrades to a scan once a participant has a few hundred.
    __table_args__ = (
        Index("ix_sessions_user_created", "user_id", "created_at"),
    )

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class Report(Base):
    """The agent chain's output for one session, plus rendered artefacts."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True,
                                    default=lambda: _new_id("rep"))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, index=True
    )

    # Stored verbatim, exactly as orchestrator.run_pipeline() returned it.
    # Reshaping it here would mean the API and the agents could drift, and
    # backend/reports already consumes this exact shape.
    pipeline_result: Mapped[dict] = mapped_column(JSON)
    # SessionMetrics as produced by backend/attribution, kept so a report can
    # be explained ("dwell was 2%") without re-running the gaze pipeline.
    metrics: Mapped[dict] = mapped_column(JSON)

    html_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    heatmap_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scanpath_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_backend: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=_utcnow)

    session: Mapped["Session"] = relationship(back_populates="report")


__all__ = [
    "User",
    "Session",
    "Report",
    "SESSION_STATUSES",
    "SESSION_MODES",
    "TERMINAL_STATUSES",
    "STATUS_CREATED",
    "STATUS_CALIBRATING",
    "STATUS_CALIBRATED",
    "STATUS_RECORDING",
    "STATUS_PROCESSING",
    "STATUS_COMPLETE",
    "STATUS_FAILED",
    "MODE_TEST_UI",
    "MODE_URL",
]

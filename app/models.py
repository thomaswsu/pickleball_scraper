"""Database models."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .db import Base


class TimestampMixin:
    """Reusable created/updated columns."""

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )


class Location(Base, TimestampMixin):
    """Playable location managed by SF Rec & Park."""

    __tablename__ = "locations"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    timezone = Column(String, nullable=True)
    image_url = Column(String, nullable=True)

    slots = relationship("AvailabilitySlot", back_populates="location", cascade="all, delete")
    watches = relationship("WatchRule", back_populates="location", cascade="all, delete")


class AvailabilitySlot(Base):
    """Represents a single available time slot."""

    __tablename__ = "availability_slots"
    __table_args__ = (
        UniqueConstraint("location_id", "court_id", "slot_time_local", name="uq_slot"),
    )

    id = Column(Integer, primary_key=True)
    location_id = Column(String, ForeignKey("locations.id"), nullable=False, index=True)
    court_id = Column(String, nullable=False)
    court_name = Column(String, nullable=True)
    sport_id = Column(String, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    slot_time_local = Column(DateTime(timezone=True), nullable=False, index=True)
    slot_time_utc = Column(DateTime(timezone=True), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    location = relationship("Location", back_populates="slots")


class WatchRule(Base, TimestampMixin):
    """User-defined alert rule."""

    __tablename__ = "watch_rules"

    id = Column(Integer, primary_key=True)
    label = Column(String, nullable=True)
    location_id = Column(String, ForeignKey("locations.id"), nullable=False, index=True)
    court_query = Column(String, nullable=True)
    target_date = Column(Date, nullable=True)
    time_from = Column(Time, nullable=True)
    time_to = Column(Time, nullable=True)
    contact = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    trigger_count = Column(Integer, nullable=False, default=0)

    location = relationship("Location", back_populates="watches")
    alerts = relationship("Alert", back_populates="watch", cascade="all, delete")


class Alert(Base):
    """Persisted alert fire for a watch rule."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("watch_id", "court_id", "slot_time_local", name="uq_watch_slot"),
    )

    id = Column(Integer, primary_key=True)
    watch_id = Column(Integer, ForeignKey("watch_rules.id"), nullable=False, index=True)
    location_id = Column(String, ForeignKey("locations.id"), nullable=False)
    court_id = Column(String, nullable=False)
    court_name = Column(String, nullable=True)
    slot_time_local = Column(DateTime(timezone=True), nullable=False)
    slot_time_utc = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    watch = relationship("WatchRule", back_populates="alerts")
    location = relationship("Location")


class SystemStatus(Base):
    """Tracks last sync/health information."""

    __tablename__ = "system_status"

    id = Column(Integer, primary_key=True, default=1)
    last_successful_sync = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)

"""Pydantic schemas for API responses/requests."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SlotResponse(BaseModel):
    """Single available slot."""

    court_id: str
    court_name: Optional[str] = None
    sport_id: Optional[str] = None
    duration_minutes: Optional[int] = None
    slot_time_local: datetime
    slot_time_utc: datetime
    court_count: int = 1
    court_names: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class LocationAvailabilityResponse(BaseModel):
    """Availability grouped by location."""

    location_id: str = Field(alias="id")
    name: str
    address: Optional[str] = None
    image_url: Optional[str] = None
    slots: List[SlotResponse]


class LocationsEnvelope(BaseModel):
    """Wrapper for availability response."""

    last_updated: Optional[datetime] = None
    locations: List[LocationAvailabilityResponse]


class WatchRuleCreate(BaseModel):
    """Request payload for creating a watch rule."""

    location_id: str
    label: Optional[str] = None
    court_query: Optional[str] = None
    target_date: Optional[date] = None
    time_from: Optional[time] = None
    time_to: Optional[time] = None
    contact: Optional[str] = None
    notes: Optional[str] = None


class WatchRuleResponse(WatchRuleCreate):
    """Read model for watch rules."""

    id: int
    location_name: str
    active: bool
    trigger_count: int
    created_at: datetime
    last_triggered_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AlertResponse(BaseModel):
    """Alert row response."""

    id: int
    watch_id: int
    location_id: str
    court_id: str
    court_name: Optional[str] = None
    slot_time_local: datetime
    slot_time_utc: datetime
    created_at: datetime
    watch_label: Optional[str] = None


class StatusResponse(BaseModel):
    """System status metadata."""

    last_successful_sync: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None

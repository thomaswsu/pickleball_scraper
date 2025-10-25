"""Business logic for syncing availability data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from typing import Iterable

from sqlalchemy.orm import Session

from .config import get_settings
from .models import Alert, AvailabilitySlot, Location, SystemStatus, WatchRule
from .notifier import send_email_alert

settings = get_settings()
logger = logging.getLogger("pickleball_scraper")


@dataclass(frozen=True)
class SlotRecord:
    """Canonical representation of a slot produced by the scraper."""

    location_id: str
    location_name: str
    location_address: str | None
    image_url: str | None
    timezone: str
    court_id: str
    court_name: str | None
    sport_id: str | None
    slot_time_local: datetime
    slot_time_utc: datetime
    duration_minutes: int | None


def parse_slot(slot_str: str, timezone_name: str) -> tuple[datetime, datetime]:
    """Parse Rec formatted slot string into timezone aware datetimes."""
    tz = ZoneInfo(timezone_name or settings.timezone)
    local_dt = datetime.strptime(slot_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
    return local_dt, local_dt.astimezone(UTC)


def upsert_location(db: Session, payload: dict) -> Location:
    """Insert or update a location row."""
    location = db.get(Location, payload["id"])
    image_url = (payload.get("images") or {}).get("thumbnail")
    if location is None:
        location = Location(
            id=payload["id"],
            name=payload["name"],
            address=payload.get("formattedAddress"),
            timezone=payload.get("timezone"),
            image_url=image_url,
        )
        db.add(location)
    else:
        location.name = payload.get("name", location.name)
        location.address = payload.get("formattedAddress", location.address)
        location.timezone = payload.get("timezone", location.timezone)
        location.image_url = image_url or location.image_url
    return location


DEFAULT_DURATION_MINUTES = 60


def sync_availability(db: Session, payload: list[dict]) -> list[SlotRecord]:
    """Persist API payload and return new availability slots."""
    existing_slots = db.query(AvailabilitySlot).all()

    def normalize(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None)

    existing_index = {
        (slot.location_id, slot.court_id, normalize(slot.slot_time_local)): slot
        for slot in existing_slots
    }
    incoming_keys: set[tuple[str, str, datetime]] = set()
    new_records: list[SlotRecord] = []

    for entry in payload:
        location_payload = entry.get("location") or {}
        if not location_payload:
            continue

        location = upsert_location(db, location_payload)
        timezone_name = location_payload.get("timezone") or settings.timezone
        image_url = location_payload.get("images", {}).get("thumbnail")

        target_sport_id = settings.pickleball_sport_id
        for court in location_payload.get("courts", []):
            court_id = court.get("id")
            if not court_id:
                continue
            court_name = court.get("name") or court.get("displayName")
            sport_id = None
            sports = court.get("sports") or []
            if sports:
                sport_id = sports[0].get("sportId") or sports[0].get("id")
            if target_sport_id and sports:
                sport_ids = {
                    (sport.get("sportId") or sport.get("id"))
                    for sport in sports
                    if sport.get("sportId") or sport.get("id")
                }
                if target_sport_id not in sport_ids:
                    continue
            elif target_sport_id and not sports:
                continue

            allowed_minutes = (court.get("allowedReservationDurations") or {}).get("minutes") or []
            if allowed_minutes:
                duration_minutes = max(allowed_minutes)
            else:
                max_time = court.get("maxReservationTime")
                duration_minutes = None
                if max_time and isinstance(max_time, str) and ":" in max_time:
                    h, m, s = [int(part) for part in max_time.split(":")]
                    duration_minutes = h * 60 + m + (1 if s >= 30 else 0)
            if not duration_minutes:
                duration_minutes = (location_payload.get("maxReservationTime") or DEFAULT_DURATION_MINUTES)
                if isinstance(duration_minutes, str) and ":" in duration_minutes:
                    h, m, s = [int(part) for part in duration_minutes.split(":")]
                    duration_minutes = h * 60 + m + (1 if s >= 30 else 0)
                elif isinstance(duration_minutes, (int, float)):
                    duration_minutes = int(duration_minutes)
                else:
                    duration_minutes = DEFAULT_DURATION_MINUTES

            for raw_slot in court.get("availableSlots", []):
                try:
                    local_dt, utc_dt = parse_slot(raw_slot, timezone_name)
                except Exception:
                    continue

                storage_local_dt = normalize(local_dt)
                key = (location.id, court_id, storage_local_dt)
                incoming_keys.add(key)
                existing = existing_index.get(key)
                if existing:
                    # Backfill duration/sport/court metadata if it changed.
                    changed = False
                    if duration_minutes and existing.duration_minutes != duration_minutes:
                        existing.duration_minutes = duration_minutes
                        changed = True
                    if sport_id and existing.sport_id != sport_id:
                        existing.sport_id = sport_id
                        changed = True
                    if court_name and not existing.court_name:
                        existing.court_name = court_name
                        changed = True
                    if changed:
                        db.add(existing)
                    continue

                slot_model = AvailabilitySlot(
                    location_id=location.id,
                    court_id=court_id,
                    court_name=court_name,
                    sport_id=sport_id,
                    duration_minutes=duration_minutes,
                    slot_time_local=local_dt,
                    slot_time_utc=utc_dt,
                )
                db.add(slot_model)

                new_records.append(
                    SlotRecord(
                        location_id=location.id,
                        location_name=location.name,
                        location_address=location.address,
                        image_url=image_url,
                        timezone=timezone_name,
                        court_id=court_id,
                        court_name=court_name,
                        sport_id=sport_id,
                        slot_time_local=local_dt,
                        slot_time_utc=utc_dt,
                        duration_minutes=duration_minutes,
                    )
                )

    for key, slot in existing_index.items():
        if key not in incoming_keys:
            db.delete(slot)

    return new_records


def update_status(db: Session, *, error: str | None = None) -> None:
    """Record scraper status in the database."""
    status = db.get(SystemStatus, 1)
    if not status:
        status = SystemStatus(id=1)
        db.add(status)

    if error:
        status.last_error = error
        status.last_error_at = datetime.now(tz=UTC)
    else:
        status.last_successful_sync = datetime.now(tz=UTC)
        status.last_error = None
        status.last_error_at = None


def match_watch(slot: SlotRecord, watch: WatchRule) -> bool:
    """Return True if a slot satisfies a watch rule."""
    if not watch.active:
        return False
    if watch.location_id != slot.location_id:
        return False
    if watch.court_query:
        court = (slot.court_name or "").lower()
        if watch.court_query.lower() not in court:
            return False
    if watch.target_date and slot.slot_time_local.date() != watch.target_date:
        return False
    slot_time = slot.slot_time_local.time()
    if watch.time_from and slot_time < watch.time_from:
        return False
    if watch.time_to and slot_time > watch.time_to:
        return False
    return True


def create_alerts(db: Session, slots: Iterable[SlotRecord]) -> list[Alert]:
    """Evaluate watches against new slots and persist alerts."""
    watches = db.query(WatchRule).filter(WatchRule.active.is_(True)).all()
    alerts: list[Alert] = []
    for slot in slots:
        for watch in watches:
            if not match_watch(slot, watch):
                continue

            existing = (
                db.query(Alert)
                .filter(
                    Alert.watch_id == watch.id,
                    Alert.court_id == slot.court_id,
                    Alert.slot_time_local == slot.slot_time_local,
                )
                .first()
            )
            if existing:
                continue

            alert = Alert(
                watch_id=watch.id,
                location_id=slot.location_id,
                court_id=slot.court_id,
                court_name=slot.court_name,
                slot_time_local=slot.slot_time_local,
                slot_time_utc=slot.slot_time_utc,
            )
            db.add(alert)
            watch.last_triggered_at = datetime.now(tz=UTC)
            watch.trigger_count = (watch.trigger_count or 0) + 1
            try:
                send_email_alert(
                    watch=watch,
                    subject=f"Court available at {slot.location_name}",
                    body=(
                        f"{slot.location_name}\n"
                        f"Court: {slot.court_name or slot.court_id}\n"
                        f"Time: {slot.slot_time_local.strftime('%Y-%m-%d %H:%M')} {slot.timezone}\n"
                        f"Reservation link: https://www.rec.us/locations/{slot.location_id}"
                    ),
                )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to send notification for watch %s", watch.id)
            alerts.append(alert)
    return alerts
